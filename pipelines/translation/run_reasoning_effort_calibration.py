#!/usr/bin/env python3
"""Blindly judge high and xhigh witness-resolution outputs on identical inputs."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from run_codex_volume_revision import (
    atomic_json,
    index_by_scan,
    read_jsonl,
    retain_input_snapshot,
    run_codex,
    sha256_file,
    sha256_text,
)
from run_codex_volume_critic import record_sha256


PROMPT_VERSION = "isabah-v8-reasoning-effort-blind-judge-v1"
PASS_NAME = "reasoning_effort_calibration"
PAIR_FIELDS = (
    "source_sha256",
    "translation_sha256",
    "critique_sha256",
    "candidate_evidence_sha256",
    "witness_image_sha256",
    "secondary_evidence_sha256",
    "supplemental_evidence_sha256",
    "concern_ids",
    "model",
    "prompt_version",
    "prompt_sha256",
    "output_schema_sha256",
    "urdu_witness_candidates",
    "secondary_witness_evidence",
    "supplemental_witness_evidence",
)
PUBLIC_CANDIDATE_FIELDS = (
    "overall_status",
    "summary",
    "findings",
    "remaining_unresolved",
)
SCORE_FIELDS = (
    "canonical_fidelity",
    "concern_coverage",
    "evidence_use",
    "uncertainty_calibration",
    "editorial_usefulness",
)


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def validate_pair(high: dict, xhigh: dict) -> tuple[bool, str]:
    if high.get("scan_page") != xhigh.get("scan_page"):
        return False, "scan_page mismatch"
    if high.get("reasoning_effort") != "high":
        return False, "first candidate is not a high-effort result"
    if xhigh.get("reasoning_effort") != "xhigh":
        return False, "second candidate is not an xhigh-effort result"
    for field in PAIR_FIELDS:
        if canonical_json(high.get(field)) != canonical_json(xhigh.get(field)):
            return False, f"{field} mismatch"
    return True, "matched"


def balanced_high_labels(scans: list[int]) -> dict[int, str]:
    """Assign high to A/B in a deterministic, balanced, non-page-order pattern."""
    ranked = sorted(
        scans,
        key=lambda scan: hashlib.sha256(
            f"{PROMPT_VERSION}:{scan}".encode("utf-8")
        ).hexdigest(),
    )
    a_count = (len(ranked) + 1) // 2
    return {scan: ("A" if index < a_count else "B") for index, scan in enumerate(ranked)}


def public_candidate(record: dict) -> dict:
    return {field: record.get(field) for field in PUBLIC_CANDIDATE_FIELDS}


def build_prompt(
    *,
    source: dict,
    translation: dict,
    critique: dict,
    evidence_record: dict,
    candidate_a: dict,
    candidate_b: dict,
) -> str:
    return f"""You are the blinded quality judge for two independently produced witness analyses used in a scholarly Arabic-to-English translation of Ibn Hajar's al-Isabah, Volume 8.

Candidate A and Candidate B received identical inputs. Their model settings are intentionally hidden. Do not guess their identities or reward verbosity. Judge only substantive quality against the canonical Arabic and supplied evidence.

Priorities, in order:
1. Fidelity to canonical Arabic, including names, genealogies, isnads, negation, numbers, variants, notes, poetry, and lacunae.
2. Correct coverage of every listed concern without inventing support.
3. Accurate use of Urdu and collateral witnesses, including their limits.
4. Honest uncertainty calibration. A supported unresolved result is better than a false resolution.
5. Editorial usefulness of the recommended English.

A material quality difference means one answer would create or fail to catch a meaningful error in the eventual English edition. Mere wording, length, or stylistic preference is not material. Score each dimension from 1 (poor) to 5 (excellent). Return one concern_assessment for each concern ID, in the supplied order. If neither candidate is substantively better, choose tie.

SCAN PAGE: {source['scan_page']}

CANONICAL ARABIC:
{source['arabic_text']}

CURRENT ENGLISH UNDER REVIEW:
{translation['english_text']}

INDEPENDENT CRITIC:
{canonical_json({'verdict': critique.get('verdict'), 'summary': critique.get('summary'), 'issues': critique.get('issues') or []})}

CONCERN IDS:
{canonical_json(evidence_record.get('concern_ids') or [])}

URDU WITNESS CANDIDATE METADATA (facsimile images are attached separately):
{canonical_json(evidence_record.get('urdu_witness_candidates') or [])}

COLLATERAL MACHINE-READABLE WITNESS EVIDENCE:
{canonical_json(evidence_record.get('secondary_witness_evidence') or [])}

SUPPLEMENTAL WITNESS EVIDENCE:
{canonical_json(evidence_record.get('supplemental_witness_evidence') or [])}

CANDIDATE A:
{canonical_json(candidate_a)}

CANDIDATE B:
{canonical_json(candidate_b)}
"""


def expected_provenance(
    *,
    prompt: str,
    scan: int,
    high: dict,
    xhigh: dict,
    candidate_a_sha256: str,
    candidate_b_sha256: str,
    model: str,
    reasoning_effort: str,
    schema_sha256: str,
) -> dict[str, object]:
    return {
        "schema": "firstlight.codex-reasoning-effort-judgment.v1",
        "scan_page": scan,
        "source_sha256": high["source_sha256"],
        "translation_sha256": high["translation_sha256"],
        "critique_sha256": high["critique_sha256"],
        "high_result_sha256": record_sha256(high),
        "xhigh_result_sha256": record_sha256(xhigh),
        "candidate_a_sha256": candidate_a_sha256,
        "candidate_b_sha256": candidate_b_sha256,
        "model": model,
        "reasoning_effort": reasoning_effort,
        "pass": PASS_NAME,
        "prompt_version": PROMPT_VERSION,
        "prompt_sha256": sha256_text(prompt),
        "output_schema_sha256": schema_sha256,
    }


def validate_existing_page(
    path: Path,
    expected: dict[str, object],
    concern_ids: list[str],
    expected_result_sha256: str | None = None,
) -> tuple[bool, str]:
    if not path.is_file():
        return False, "missing"
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"unreadable: {exc}"
    for field, value in expected.items():
        if record.get(field) != value:
            return False, f"{field} mismatch"
    observed = [item.get("concern_id") for item in record.get("concern_assessments") or []]
    if observed != concern_ids:
        return False, "concern assessment coverage mismatch"
    if expected_result_sha256 and sha256_file(path) != expected_result_sha256:
        return False, "result_sha256 mismatch with checkpoint state"
    return True, "current"


def candidate_total(record: dict, label: str) -> int:
    score = record[f"candidate_{label.lower()}"]
    return sum(int(score[field]) for field in SCORE_FIELDS)


def build_summary(records: list[dict]) -> dict:
    counts = {"high": 0, "xhigh": 0, "tie": 0}
    material = {"high": 0, "xhigh": 0, "tie": 0}
    totals = {"high": 0, "xhigh": 0}
    high_only_material_errors = 0
    pages = []
    for record in records:
        high_label = record["high_candidate_label"]
        preferred = record["preferred_candidate"]
        if preferred == "tie":
            winner = "tie"
        else:
            winner = "high" if preferred == high_label else "xhigh"
        counts[winner] += 1
        if record["material_quality_difference"]:
            material[winner] += 1
        high_score_key = "candidate_a" if high_label == "A" else "candidate_b"
        xhigh_score_key = "candidate_b" if high_label == "A" else "candidate_a"
        totals["high"] += candidate_total(record, high_label)
        totals["xhigh"] += candidate_total(record, "B" if high_label == "A" else "A")
        high_errors = record[high_score_key]["material_errors"]
        xhigh_errors = record[xhigh_score_key]["material_errors"]
        if high_errors and not xhigh_errors:
            high_only_material_errors += 1
        pages.append({
            "scan_page": record["scan_page"],
            "high_candidate_label": high_label,
            "winner": winner,
            "material_quality_difference": record["material_quality_difference"],
            "high_score": candidate_total(record, high_label),
            "xhigh_score": candidate_total(record, "B" if high_label == "A" else "A"),
            "confidence": record["confidence"],
        })
    count = len(records)
    high_mean = totals["high"] / count if count else 0.0
    xhigh_mean = totals["xhigh"] / count if count else 0.0
    high_noninferior = (
        count > 0
        and material["xhigh"] == 0
        and high_only_material_errors == 0
        and high_mean >= xhigh_mean - 0.5
        and counts["high"] + counts["tie"] >= max(1, count - 2)
    )
    return {
        "schema": "firstlight.reasoning-effort-calibration-summary.v1",
        "sample_pages": count,
        "wins": counts,
        "material_wins": material,
        "mean_total_score": {"high": round(high_mean, 3), "xhigh": round(xhigh_mean, 3)},
        "high_only_material_error_pages": high_only_material_errors,
        "decision_policy": {
            "no_material_xhigh_wins": material["xhigh"] == 0,
            "no_high_only_material_errors": high_only_material_errors == 0,
            "high_mean_within_half_point": high_mean >= xhigh_mean - 0.5,
            "high_wins_or_ties_on_all_but_two": counts["high"] + counts["tie"] >= max(1, count - 2),
        },
        "recommendation": "high" if high_noninferior else "xhigh",
        "pages": sorted(pages, key=lambda item: item["scan_page"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aligned-source", required=True)
    parser.add_argument("--translations", required=True)
    parser.add_argument("--criticisms", required=True)
    parser.add_argument("--high-dir", required=True)
    parser.add_argument("--xhigh-dir", action="append", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--schema", default=str(Path(__file__).with_name("schemas") / "codex-reasoning-effort-judge.schema.json"))
    parser.add_argument("--codex", required=True)
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--reasoning-effort", default="xhigh")
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--retry-backoff-seconds", type=float, default=5.0)
    parser.add_argument("--request-delay-seconds", type=float, default=1.0)
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    args = parser.parse_args()

    source_path = Path(args.aligned_source).resolve()
    translations_path = Path(args.translations).resolve()
    criticisms_path = Path(args.criticisms).resolve()
    high_dir = Path(args.high_dir).resolve()
    xhigh_dirs = [Path(path).resolve() for path in args.xhigh_dir]
    out_dir = Path(args.out_dir).resolve()
    page_dir = out_dir / "pages"
    log_dir = out_dir / "logs"
    sandbox_dir = out_dir / "sandbox"
    snapshot_dir = out_dir / "input-snapshots"
    for directory in (page_dir, log_dir, sandbox_dir, snapshot_dir):
        directory.mkdir(parents=True, exist_ok=True)

    source_by_scan = index_by_scan(read_jsonl(source_path), "Aligned source")
    translation_by_scan = index_by_scan(read_jsonl(translations_path), "Translations")
    critique_by_scan = index_by_scan(read_jsonl(criticisms_path), "Criticisms")
    high_paths = sorted((high_dir / "pages").glob("*.json"))
    scans = [int(path.stem) for path in high_paths]
    high_labels = balanced_high_labels(scans)
    schema_path = Path(args.schema).resolve()
    schema_sha256 = sha256_file(schema_path)

    jobs: dict[int, dict] = {}
    parity = []
    for high_path in high_paths:
        scan = int(high_path.stem)
        matches = [directory / "pages" / high_path.name for directory in xhigh_dirs if (directory / "pages" / high_path.name).is_file()]
        if len(matches) != 1:
            raise RuntimeError(f"Expected exactly one xhigh result for scan {scan}; found {len(matches)}")
        high_snapshot = retain_input_snapshot(high_path, snapshot_dir, f"high-{scan:04d}")
        xhigh_snapshot = retain_input_snapshot(matches[0], snapshot_dir, f"xhigh-{scan:04d}")
        high = json.loads(Path(str(high_snapshot["path"])).read_text(encoding="utf-8"))
        xhigh = json.loads(Path(str(xhigh_snapshot["path"])).read_text(encoding="utf-8"))
        matched, reason = validate_pair(high, xhigh)
        parity.append({"scan_page": scan, "matched": matched, "reason": reason})
        if not matched:
            raise RuntimeError(f"Calibration parity failed for scan {scan}: {reason}")
        high_label = high_labels[scan]
        candidate_a = public_candidate(high if high_label == "A" else xhigh)
        candidate_b = public_candidate(xhigh if high_label == "A" else high)
        prompt = build_prompt(
            source=source_by_scan[scan],
            translation=translation_by_scan[scan],
            critique=critique_by_scan[scan],
            evidence_record=high,
            candidate_a=candidate_a,
            candidate_b=candidate_b,
        )
        jobs[scan] = {
            "high": high,
            "xhigh": xhigh,
            "high_label": high_label,
            "prompt": prompt,
            "concern_ids": list(high.get("concern_ids") or []),
            "images": [high_dir / "witness-images" / f"arabic-{scan:04d}-urdu-{int(item['scan_page']):04d}.png" for item in high.get("urdu_witness_candidates") or []],
            "expected": expected_provenance(
                prompt=prompt,
                scan=scan,
                high=high,
                xhigh=xhigh,
                candidate_a_sha256=sha256_text(canonical_json(candidate_a)),
                candidate_b_sha256=sha256_text(canonical_json(candidate_b)),
                model=args.model,
                reasoning_effort=args.reasoning_effort,
                schema_sha256=schema_sha256,
            ),
        }
        missing_images = [str(path) for path in jobs[scan]["images"] if not path.is_file()]
        if missing_images:
            raise RuntimeError(f"Missing witness images for scan {scan}: {missing_images}")

    state_path = out_dir / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {}
    if state.get("schema") != "firstlight.reasoning-effort-calibration-state.v1":
        state = {"schema": "firstlight.reasoning-effort-calibration-state.v1", "completed": {}, "failed": {}, "stale": {}}
    pending = []
    for scan, job in jobs.items():
        result_path = page_dir / f"{scan:04d}.json"
        checkpoint = (state["completed"].get(str(scan)) or {}).get("result_sha256")
        current, reason = validate_existing_page(result_path, job["expected"], job["concern_ids"], checkpoint)
        if current:
            state["completed"][str(scan)] = {"result_sha256": sha256_file(result_path)}
            state["failed"].pop(str(scan), None)
            state["stale"].pop(str(scan), None)
        else:
            pending.append(scan)
            state["completed"].pop(str(scan), None)
            if reason != "missing":
                state["stale"][str(scan)] = {"reason": reason}
    atomic_json(state_path, state)
    atomic_json(out_dir / "run-manifest.json", {
        "schema": "firstlight.reasoning-effort-calibration-run.v1",
        "prompt_version": PROMPT_VERSION,
        "aligned_source_sha256": sha256_file(source_path),
        "translations_sha256": sha256_file(translations_path),
        "criticisms_sha256": sha256_file(criticisms_path),
        "output_schema_sha256": schema_sha256,
        "model": args.model,
        "reasoning_effort": args.reasoning_effort,
        "selected_pages": scans,
        "parity": parity,
        "candidate_label_balance": {"high_as_a": list(high_labels.values()).count("A"), "high_as_b": list(high_labels.values()).count("B")},
        "pending_pages_at_start": len(pending),
        "started_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    })

    for scan in pending:
        result_path = page_dir / f"{scan:04d}.json"
        candidate_path = page_dir / f".{scan:04d}.candidate.json"
        last_error = ""
        for attempt in range(1, args.max_retries + 1):
            try:
                candidate_path.unlink(missing_ok=True)
                completed = run_codex(
                    codex_path=Path(args.codex).resolve(),
                    work_dir=sandbox_dir,
                    schema_path=schema_path,
                    prompt=jobs[scan]["prompt"],
                    result_path=candidate_path,
                    model=args.model,
                    reasoning_effort=args.reasoning_effort,
                    timeout_seconds=args.timeout_seconds,
                    image_paths=jobs[scan]["images"],
                )
                (log_dir / f"{scan:04d}.stdout.log").write_text(completed.stdout, encoding="utf-8")
                (log_dir / f"{scan:04d}.stderr.log").write_text(completed.stderr, encoding="utf-8")
                if completed.returncode != 0:
                    raise RuntimeError(f"Codex exited {completed.returncode}: {completed.stderr[-1200:]}")
                record = json.loads(candidate_path.read_text(encoding="utf-8"))
                record.update(jobs[scan]["expected"])
                record["high_candidate_label"] = jobs[scan]["high_label"]
                record["generated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
                atomic_json(result_path, record)
                candidate_path.unlink(missing_ok=True)
                valid, reason = validate_existing_page(result_path, jobs[scan]["expected"], jobs[scan]["concern_ids"])
                if not valid:
                    raise RuntimeError(reason)
                state["completed"][str(scan)] = {"attempts": attempt, "result_sha256": sha256_file(result_path)}
                state["failed"].pop(str(scan), None)
                state["stale"].pop(str(scan), None)
                atomic_json(state_path, state)
                print(f"ok scan_page={scan} preferred={record['preferred_candidate']} attempt={attempt}", flush=True)
                break
            except Exception as exc:
                last_error = str(exc)
                candidate_path.unlink(missing_ok=True)
                if attempt < args.max_retries:
                    time.sleep(args.retry_backoff_seconds * attempt)
        else:
            state["failed"][str(scan)] = {"error": last_error}
            atomic_json(state_path, state)
            print(f"fail scan_page={scan}: {last_error}", flush=True)
        time.sleep(max(0.0, args.request_delay_seconds))

    records = []
    for scan, job in jobs.items():
        path = page_dir / f"{scan:04d}.json"
        checkpoint = (state["completed"].get(str(scan)) or {}).get("result_sha256")
        current, _ = validate_existing_page(path, job["expected"], job["concern_ids"], checkpoint)
        if current:
            records.append(json.loads(path.read_text(encoding="utf-8")))
    summary = build_summary(records)
    summary["generated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    atomic_json(out_dir / "summary.json", summary)
    print(json.dumps(summary, indent=2))
    return 0 if len(records) == len(jobs) and not state["failed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

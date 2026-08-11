#!/usr/bin/env python3
"""Run a resumable, provenance-bound Codex fidelity critique over translated pages."""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from run_codex_volume_revision import (
    atomic_json,
    index_by_scan,
    read_jsonl,
    read_retained_jsonl,
    require_volume8_scan_coverage,
    run_codex,
    sha256_file,
    sha256_text,
)
from isabah_translation_policy import NAME_POLICY


PROMPT_VERSION = "isabah-v8-fidelity-critic-v2"
PASS_NAME = "fidelity_critic"


def record_sha256(record: dict) -> str:
    canonical = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256_text(canonical)


def validate_translation_provenance(source: dict, translation: dict) -> tuple[bool, str]:
    expected = {
        "work_id": source.get("work_id"),
        "volume": source.get("volume"),
        "scan_page": source.get("scan_page"),
        "source_sha256": source.get("arabic_text_sha256"),
    }
    for field, value in expected.items():
        if translation.get(field) != value:
            return (
                False,
                f"{field} mismatch: expected {value!r}, found {translation.get(field)!r}",
            )
    return True, "current"


def validate_critique_provenance(
    source: dict,
    translation: dict,
    critique: dict,
) -> tuple[bool, str]:
    current, reason = validate_translation_provenance(source, translation)
    if not current:
        return False, f"translation {reason}"
    expected = {
        "work_id": source.get("work_id"),
        "volume": source.get("volume"),
        "scan_page": source.get("scan_page"),
        "source_sha256": source.get("arabic_text_sha256"),
        "translation_sha256": record_sha256(translation),
    }
    for field, value in expected.items():
        if critique.get(field) != value:
            return (
                False,
                f"{field} mismatch: expected {value!r}, found {critique.get(field)!r}",
            )
    return True, "current"


def build_prompt(
    source: dict,
    translation: dict,
    previous_source: dict | None,
    following_source: dict | None,
) -> str:
    before = str((previous_source or {}).get("arabic_text") or "")[-1400:]
    after = str((following_source or {}).get("arabic_text") or "")[:1400]
    return f"""You are an independent fidelity critic for a scholarly Arabic-to-English translation of Ibn Hajar al-Asqalani's al-Isabah fi Tamyiz al-Sahabah, Volume 8.

Audit CURRENT ENGLISH against CURRENT ARABIC line by line. You did not write the translation. Arabic is authoritative. Do not reward fluent English when it is incomplete or unsupported.

Check especially:
- every heading, entry number, name, genealogy, isnad link, quotation, negation, number, cross-reference, variant, poem, footnote, and editorial note;
- omissions, additions, collapsed distinctions, shifted page-continuation text, and confident resolution of genuinely ambiguous Arabic;
- whether name transliterations are stable and distinguish separate people.

{NAME_POLICY}

Do not demand general prose rewriting when meaning and structure are faithful. Treat a violation of the explicit name/search policy as a precise minor style or name issue, because inconsistent names damage the review corpus. Use verdict "pass" only when there is no fidelity or policy issue. Use "witness_required" only where canonical Arabic is genuinely damaged or ambiguous and another edition/language could resolve it. Otherwise use "revise" and give precise minimal fixes. Audit only scan page {source['scan_page']}.

PREVIOUS ARABIC CONTEXT (context only):
{before or '[none]'}

CURRENT ARABIC:
{source['arabic_text']}

CURRENT ENGLISH TO AUDIT:
{translation['english_text']}

NEXT ARABIC CONTEXT (context only):
{after or '[none]'}
"""


def expected_provenance(
    *,
    prompt: str,
    source: dict,
    translation: dict,
    model: str,
    reasoning_effort: str,
    schema_sha256: str,
) -> dict[str, object]:
    return {
        "schema": "firstlight.codex-page-critique.v1",
        "scan_page": int(source["scan_page"]),
        "work_id": source["work_id"],
        "volume": source["volume"],
        "source_sha256": source["arabic_text_sha256"],
        "translation_sha256": record_sha256(translation),
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
    expected_result_sha256: str | None = None,
) -> tuple[bool, str]:
    if not path.exists():
        return False, "missing"
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"unreadable: {exc}"
    for key, value in expected.items():
        if record.get(key) != value:
            return False, f"{key} mismatch: expected {value!r}, found {record.get(key)!r}"
    if expected_result_sha256 and sha256_file(path) != expected_result_sha256:
        return False, "result_sha256 mismatch with checkpoint state"
    verdict = record.get("verdict")
    issues = record.get("issues")
    if verdict == "pass" and issues:
        return False, "pass verdict contains issues"
    if verdict == "pass" and not all((record.get("checks") or {}).values()):
        return False, "pass verdict contains a failed check"
    if verdict in {"revise", "witness_required"} and not issues:
        return False, f"{verdict} verdict contains no issues"
    if verdict == "witness_required" and not any(
        issue.get("witness_check_recommended") for issue in issues
    ):
        return False, "witness_required verdict contains no actionable witness concern"
    return True, "current"


def aggregate(page_dir: Path, output_path: Path, included_scans: set[int]) -> int:
    records = []
    for scan in sorted(included_scans):
        path = page_dir / f"{scan:04d}.json"
        records.append(json.loads(path.read_text(encoding="utf-8")))
    pending = output_path.with_suffix(output_path.suffix + ".tmp")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pending.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    pending.replace(output_path)
    return len(records)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aligned-source", required=True)
    parser.add_argument("--translations", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--schema", default=str(Path(__file__).with_name("schemas") / "codex-page-critique.schema.json"))
    parser.add_argument("--codex", required=True)
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--reasoning-effort", default="high")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--page", type=int, action="append", default=[])
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--retry-backoff-seconds", type=float, default=5.0)
    parser.add_argument("--request-delay-seconds", type=float, default=1.0)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    args = parser.parse_args()

    source_path = Path(args.aligned_source).resolve()
    translations_path = Path(args.translations).resolve()
    out_dir = Path(args.out_dir).resolve()
    page_dir = out_dir / "pages"
    log_dir = out_dir / "logs"
    work_dir = out_dir / "sandbox"
    for directory in (page_dir, log_dir, work_dir):
        directory.mkdir(parents=True, exist_ok=True)
    translations, translations_snapshot = read_retained_jsonl(
        translations_path, out_dir / "input-snapshots", "translations"
    )
    source = read_jsonl(source_path)
    by_scan = index_by_scan(source, "Aligned source")
    translation_by_scan = index_by_scan(translations, "Blind translations")
    if not args.page and args.limit <= 0:
        require_volume8_scan_coverage(by_scan, "Aligned source")
        require_volume8_scan_coverage(translation_by_scan, "Blind translations")
    for scan, translation in translation_by_scan.items():
        if scan not in by_scan:
            raise RuntimeError(f"Blind translation scan {scan} is absent from aligned source")
        current, reason = validate_translation_provenance(by_scan[scan], translation)
        if not current:
            raise RuntimeError(
                f"Blind translation provenance mismatch at scan {scan}: {reason}"
            )
    scans = sorted(by_scan)
    selected = [
        scan for scan in scans
        if scan in translation_by_scan and (not args.page or scan in set(args.page))
    ]

    schema_path = Path(args.schema).resolve()
    schema_sha256 = sha256_file(schema_path)

    state_path = out_dir / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    if state.get("schema") != "firstlight.codex-critic-state.v1":
        state = {"schema": "firstlight.codex-critic-state.v1", "completed": {}, "failed": {}, "stale": {}}

    prompt_by_scan: dict[int, str] = {}
    expected_by_scan: dict[int, dict[str, object]] = {}
    pending_scans: list[int] = []
    for scan in selected:
        index = scans.index(scan)
        prompt = build_prompt(
            by_scan[scan],
            translation_by_scan[scan],
            by_scan[scans[index - 1]] if index > 0 else None,
            by_scan[scans[index + 1]] if index + 1 < len(scans) else None,
        )
        expected = expected_provenance(
            prompt=prompt,
            source=by_scan[scan],
            translation=translation_by_scan[scan],
            model=args.model,
            reasoning_effort=args.reasoning_effort,
            schema_sha256=schema_sha256,
        )
        prompt_by_scan[scan] = prompt
        expected_by_scan[scan] = expected
        result_path = page_dir / f"{scan:04d}.json"
        checkpoint_sha = (state.get("completed", {}).get(str(scan)) or {}).get("result_sha256")
        current, reason = validate_existing_page(result_path, expected, checkpoint_sha)
        if current:
            state["completed"][str(scan)] = {
                "translation_sha256": expected["translation_sha256"],
                "prompt_sha256": expected["prompt_sha256"],
                "result_sha256": sha256_file(result_path),
            }
            state["failed"].pop(str(scan), None)
            state["stale"].pop(str(scan), None)
        else:
            pending_scans.append(scan)
            state["completed"].pop(str(scan), None)
            if reason != "missing":
                state["stale"][str(scan)] = {"reason": reason}
    if args.limit > 0:
        pending_scans = pending_scans[:args.limit]

    atomic_json(state_path, state)
    atomic_json(out_dir / "run-manifest.json", {
        "schema": "firstlight.codex-critic-run.v1",
        "prompt_version": PROMPT_VERSION,
        "aligned_source_sha256": sha256_file(source_path),
        "translations_sha256": translations_snapshot["sha256"],
        "translations_snapshot": translations_snapshot,
        "output_schema_sha256": schema_sha256,
        "model": args.model,
        "reasoning_effort": args.reasoning_effort,
        "selected_pages": len(selected),
        "missing_translation_pages": len(by_scan) - len(translation_by_scan),
        "pending_pages_at_start": len(pending_scans),
        "started_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    })

    for scan in pending_scans:
        result_path = page_dir / f"{scan:04d}.json"
        candidate_path = page_dir / f".{scan:04d}.candidate.json"
        last_error = ""
        for attempt in range(1, args.max_retries + 1):
            try:
                candidate_path.unlink(missing_ok=True)
                completed = run_codex(
                    codex_path=Path(args.codex).resolve(),
                    work_dir=work_dir,
                    schema_path=schema_path,
                    prompt=prompt_by_scan[scan],
                    result_path=candidate_path,
                    model=args.model,
                    reasoning_effort=args.reasoning_effort,
                    timeout_seconds=args.timeout_seconds,
                )
                (log_dir / f"{scan:04d}.stdout.log").write_text(completed.stdout, encoding="utf-8")
                (log_dir / f"{scan:04d}.stderr.log").write_text(completed.stderr, encoding="utf-8")
                if completed.returncode != 0:
                    raise RuntimeError(f"Codex exited {completed.returncode}: {completed.stderr[-1200:]}")
                record = json.loads(candidate_path.read_text(encoding="utf-8"))
                if int(record.get("scan_page", -1)) != scan:
                    raise RuntimeError(f"Codex returned scan_page {record.get('scan_page')} for {scan}")
                record.update(expected_by_scan[scan])
                record["generated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
                atomic_json(result_path, record)
                candidate_path.unlink(missing_ok=True)
                valid, reason = validate_existing_page(result_path, expected_by_scan[scan])
                if not valid:
                    raise RuntimeError(reason)
                state["completed"][str(scan)] = {
                    "attempts": attempt,
                    "translation_sha256": expected_by_scan[scan]["translation_sha256"],
                    "prompt_sha256": expected_by_scan[scan]["prompt_sha256"],
                    "result_sha256": sha256_file(result_path),
                }
                state["failed"].pop(str(scan), None)
                state["stale"].pop(str(scan), None)
                atomic_json(state_path, state)
                print(f"ok scan_page={scan} verdict={record['verdict']} attempt={attempt}", flush=True)
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

    current_scans = {
        scan for scan in selected
        if str(scan) in state["completed"] and validate_existing_page(
            page_dir / f"{scan:04d}.json",
            expected_by_scan[scan],
            (state.get("completed", {}).get(str(scan)) or {}).get("result_sha256"),
        )[0]
    }
    count = aggregate(page_dir, out_dir / "criticisms.jsonl", current_scans)
    print(json.dumps({
        "source_pages": len(by_scan),
        "translation_pages": len(translation_by_scan),
        "selected": len(selected),
        "aggregated": count,
        "failed": len(state["failed"]),
    }, indent=2))
    return 0 if not state["failed"] and count == len(selected) else 2


if __name__ == "__main__":
    raise SystemExit(main())

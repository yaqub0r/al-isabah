#!/usr/bin/env python3
"""Adjudicate disputed al-Isabah translations at high reasoning against all evidence."""
from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from isabah_entry_sequence import normalize_digits, probable_entry_numbers
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
from run_codex_volume_critic import (
    record_sha256,
    validate_critique_provenance,
)
from run_codex_witness_resolution import (
    validate_witness_provenance,
    witness_concerns,
)
from isabah_translation_policy import NAME_POLICY


PROMPT_VERSION = "isabah-v8-adjudication-v5"
SUPPLEMENTAL_PROMPT_VERSION = "isabah-v8-adjudication-v6-supplemental"
PASS_NAME = "translation_adjudication"
PROHIBITED_TRANSLITERATION_CHARACTERS = frozenset(
    "\u02bf\u02be"
    "\u0101\u012b\u016b\u1e0d\u1e25\u1e63\u1e6d\u1e93"
    "\u1e0f\u1e35\u0121\u0161\u1e6f\u1e95"
    "\u0100\u012a\u016a\u1e0c\u1e24\u1e62\u1e6c\u1e92"
    "\u1e0e\u1e34\u0120\u0160\u1e6e\u1e94"
)
SUPERSCRIPT_DIGIT_MAP = str.maketrans(
    "\u2070\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079",
    "0123456789",
)
FOOTNOTE_RE = re.compile(r"(?m)^\s*\((\d{1,3})\)")
ENGLISH_FOOTNOTE_RE = re.compile(
    r"(?m)^\s*(?:\((\d{1,3})\)|\[(\d{1,3})\]|(\d{1,3})[.)])\s+"
)
SUPERSCRIPT_FOOTNOTE_RE = re.compile(
    r"[\u2070\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079]+"
)
NAME_APOSTROPHE_TRANSLATION = str.maketrans({
    "\u02bf": "'",
    "\u02be": "'",
    "\u2018": "'",
    "\u2019": "'",
    "`": "'",
})


def transliteration_policy_violations(text: str) -> list[str]:
    return sorted(set(str(text or "")) & PROHIBITED_TRANSLITERATION_CHARACTERS)


def normalize_name_label(value: str) -> str:
    return str(value or "").translate(NAME_APOSTROPHE_TRANSLATION).strip()


def normalize_name_mappings(names: list[dict]) -> tuple[list[dict], list[dict]]:
    normalized = []
    changes = []
    for mapping in names:
        current = dict(mapping)
        before = str(current.get("english") or "")
        after = normalize_name_label(before)
        current["english"] = after
        normalized.append(current)
        if after != before:
            changes.append({
                "arabic": current.get("arabic"),
                "before": before,
                "after": after,
            })
    return normalized, changes


def footnote_labels(text: str) -> set[int]:
    return {int(value) for value in FOOTNOTE_RE.findall(normalize_digits(text))}


def english_footnote_labels(text: str) -> set[int]:
    conventional = {
        int(value)
        for groups in ENGLISH_FOOTNOTE_RE.findall(normalize_digits(text))
        for value in groups
        if value
    }
    superscript = {
        int(value.translate(SUPERSCRIPT_DIGIT_MAP))
        for value in SUPERSCRIPT_FOOTNOTE_RE.findall(text)
    }
    return conventional | superscript


def numeric_tokens(text: str) -> set[int]:
    normalized = normalize_digits(text).translate(SUPERSCRIPT_DIGIT_MAP)
    return {int(value) for value in re.findall(r"\d+", normalized)}


def deterministic_translation_issues(
    source: dict | None,
    translation: dict,
) -> list[dict]:
    issues = []
    name_violations = name_mapping_policy_violations(translation.get("names") or [])
    if name_violations:
        issues.append({"code": "name_mapping_policy", "details": name_violations})
    prohibited = transliteration_policy_violations(translation.get("english_text") or "")
    if prohibited:
        issues.append({"code": "transliteration_policy", "characters": prohibited})
    if source is None:
        return issues
    source_text = str(source.get("arabic_text") or "")
    english_text = str(translation.get("english_text") or "")
    source_entries = probable_entry_numbers(source_text)
    english_entries = probable_entry_numbers(english_text)
    if source_entries != english_entries:
        issues.append({
            "code": "entry_number_mismatch",
            "source": source_entries,
            "english": english_entries,
        })
    missing_notes = sorted(footnote_labels(source_text) - english_footnote_labels(english_text))
    if missing_notes:
        issues.append({"code": "missing_footnote_labels", "labels": missing_notes})
    missing_numbers = sorted(numeric_tokens(source_text) - numeric_tokens(english_text))
    missing_material_numbers = [value for value in missing_numbers if value >= 10]
    if missing_material_numbers:
        issues.append({
            "code": "missing_material_numeric_tokens",
            "numbers": missing_material_numbers,
        })
    return issues


def requires_adjudication(
    translation: dict,
    critique: dict,
    source: dict | None = None,
) -> bool:
    fidelity = translation.get("fidelity") or {}
    return bool(
        critique.get("verdict") != "pass"
        or critique.get("issues")
        or translation.get("uncertainties")
        or deterministic_translation_issues(source, translation)
        or any(value is False for value in fidelity.values() if isinstance(value, bool))
    )


def should_adjudicate_page(
    translation: dict,
    critique: dict,
    source: dict | None = None,
    *,
    all_pages: bool = False,
) -> bool:
    return all_pages or requires_adjudication(translation, critique, source)


def name_mapping_policy_violations(names: list[dict]) -> list[dict]:
    violations = []
    for mapping in names:
        original = str(mapping.get("english") or "").strip()
        value = normalize_name_label(original)
        reasons = []
        if not value:
            reasons.append("empty")
        if any(ord(character) > 127 for character in value):
            reasons.append("non_ascii")
        # A colon can be part of a stable bibliographic title (for example,
        # "al-Tajrid: Asma al-Sahaba"). It remains disallowed for identity
        # labels, and annotation-style punctuation remains disallowed for all
        # entity kinds.
        prohibited_punctuation = ",;()\r\n" if mapping.get("kind") == "work" else ",;():\r\n"
        if any(character in value for character in prohibited_punctuation):
            reasons.append("descriptive_punctuation")
        if mapping.get("kind") == "person" and (
            " and " in value.casefold() or " or " in value.casefold()
        ):
            reasons.append("multiple_people_or_variants")
        if len(value) > 160:
            reasons.append("excessive_length")
        if reasons:
            violations.append({
                "english": original,
                "normalized_english": value,
                "reasons": reasons,
            })
    return violations


def build_prompt(
    source: dict,
    translation: dict,
    critique: dict,
    witness: dict | None,
    previous_source: dict | None,
    following_source: dict | None,
) -> str:
    before = str((previous_source or {}).get("arabic_text") or "")[-1400:]
    after = str((following_source or {}).get("arabic_text") or "")[:1400]
    prompt = f"""You are the final autonomous adjudicator for a scholarly translation of Ibn Hajar al-Asqalani's al-Isabah, Volume 8.

Produce the strongest complete English for CURRENT ARABIC PAGE. The canonical al-Isabah Arabic is authoritative. The blind translation is a candidate, the fidelity critique is diagnostic evidence, and the witness resolution may contain an Urdu translation witness plus collateral Arabic entries from Usd al-Ghaba and al-Isti'ab. Those collateral works can clarify shared material but are not alternative manuscripts of al-Isabah. Decide each disagreement yourself; do not mechanically accept any model or witness. Preserve every heading, entry number, genealogy, isnad, quotation, negation, number, variant, poem, footnote, editorial note, and page continuation. Do not summarize or silently omit. Do not introduce facts absent from the canonical Arabic.

{NAME_POLICY}

Every names[].english value is a stable searchable identity label. Use only the name or title, with ASCII transliteration and punctuation; do not include commas, parentheses, identity notes, or explanatory prose. It may normalize an Arabic or English ellipsis into the complete name supplied by the current source context.

Return a complete final_english_text and a names array that follows the policy for page {source['scan_page']}, even if only a small correction is needed. Use decision "accept" if the blind translation survives adjudication unchanged, "revised" if you correct it, and "unresolved" only where all supplied evidence cannot safely decide. Record every material change, including name-policy corrections, and every remaining uncertainty. Previous and next Arabic are context only.

PREVIOUS ARABIC CONTEXT:
{before or '[none]'}

CURRENT ARABIC:
{source['arabic_text']}

BLIND ENGLISH CANDIDATE:
{translation['english_text']}

INDEPENDENT FIDELITY CRITIQUE:
{json.dumps(critique, ensure_ascii=False, indent=2)}

SECONDARY WITNESS RESOLUTION:
{json.dumps(witness or {}, ensure_ascii=False, indent=2)}

DETERMINISTIC PRE-ADJUDICATION ISSUES:
{json.dumps(deterministic_translation_issues(source, translation), ensure_ascii=False, indent=2)}

NEXT ARABIC CONTEXT:
{after or '[none]'}
"""
    if (witness or {}).get("supplemental_witness_evidence"):
        prompt += """
SUPPLEMENTAL EVIDENCE RULE:
The witness resolution contains hash-bound outside evidence classified by kind. Use an alternative edition to establish whether a reading recurs and a parallel transmission to clarify shared material, but never silently substitute either for the canonical al-Isabah wording. Preserve a transparent editorial note when the canonical wording remains corrupt, and cite the relevant evidence ID in changes or unresolved items.
"""
    return prompt


def expected_provenance(
    *,
    prompt: str,
    source: dict,
    translation: dict,
    critique: dict,
    witness: dict | None,
    model: str,
    reasoning_effort: str,
    schema_sha256: str,
) -> dict[str, object]:
    return {
        "schema": "firstlight.codex-page-adjudication.v1",
        "scan_page": int(source["scan_page"]),
        "work_id": source["work_id"],
        "volume": source["volume"],
        "source_sha256": source["arabic_text_sha256"],
        "translation_sha256": record_sha256(translation),
        "critique_sha256": record_sha256(critique),
        "witness_resolution_sha256": record_sha256(witness) if witness else None,
        "model": model,
        "reasoning_effort": reasoning_effort,
        "pass": PASS_NAME,
        "prompt_version": (
            SUPPLEMENTAL_PROMPT_VERSION
            if (witness or {}).get("supplemental_witness_evidence")
            else PROMPT_VERSION
        ),
        "prompt_sha256": sha256_text(prompt),
        "output_schema_sha256": schema_sha256,
    }


def normalize_decision_state(record: dict) -> str | None:
    """Normalize a page label when the model already supplied explicit uncertainty.

    This changes no translated content or scholarly judgment. It only makes the
    page-level decision agree with the non-empty unresolved array and records
    the model's original label for audit.
    """
    original = record.get("decision")
    if record.get("unresolved") and original in {"accept", "revised"}:
        record["decision_normalized_from"] = original
        record["decision"] = "unresolved"
        return str(original)
    return None


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
    if not str(record.get("final_english_text") or "").strip():
        return False, "empty final_english_text"
    if record.get("decision") == "accept" and record.get("changes"):
        return False, "accept decision contains changes"
    if record.get("decision") == "revised" and not record.get("changes"):
        return False, "revised decision contains no changes"
    if record.get("decision") == "unresolved" and not record.get("unresolved"):
        return False, "unresolved decision contains no unresolved items"
    if record.get("decision") != "unresolved" and record.get("unresolved"):
        return False, f"{record.get('decision')} decision contains unresolved items"
    if record.get("decision") != "unresolved" and not all((record.get("fidelity") or {}).values()):
        return False, f"{record.get('decision')} decision contains a failed fidelity check"
    return True, "current"


def aggregate(page_dir: Path, output_path: Path, scans: set[int]) -> int:
    pending = output_path.with_suffix(output_path.suffix + ".tmp")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pending.open("w", encoding="utf-8", newline="\n") as handle:
        for scan in sorted(scans):
            record = json.loads((page_dir / f"{scan:04d}.json").read_text(encoding="utf-8"))
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    pending.replace(output_path)
    return len(scans)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aligned-source", required=True)
    parser.add_argument("--translations", required=True)
    parser.add_argument("--criticisms", required=True)
    parser.add_argument("--witness-resolutions")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--schema", default=str(Path(__file__).with_name("schemas") / "codex-page-adjudication.schema.json"))
    parser.add_argument("--codex", required=True)
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--reasoning-effort", default="xhigh")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--page", type=int, action="append", default=[])
    parser.add_argument(
        "--all-pages",
        action="store_true",
        help="Adjudicate every selected source page, including pages whose critic verdict passed.",
    )
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--retry-backoff-seconds", type=float, default=8.0)
    parser.add_argument("--request-delay-seconds", type=float, default=1.0)
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    args = parser.parse_args()

    source_path = Path(args.aligned_source).resolve()
    translations_path = Path(args.translations).resolve()
    criticisms_path = Path(args.criticisms).resolve()
    witness_path = (
        Path(args.witness_resolutions).resolve()
        if args.witness_resolutions else None
    )
    out_dir = Path(args.out_dir).resolve()
    page_dir = out_dir / "pages"
    log_dir = out_dir / "logs"
    work_dir = out_dir / "sandbox"
    for directory in (page_dir, log_dir, work_dir):
        directory.mkdir(parents=True, exist_ok=True)
    translation_records, translations_snapshot = read_retained_jsonl(
        translations_path, out_dir / "input-snapshots", "translations"
    )
    critique_records, criticisms_snapshot = read_retained_jsonl(
        criticisms_path, out_dir / "input-snapshots", "criticisms"
    )
    input_snapshots = {
        "translations": translations_snapshot,
        "criticisms": criticisms_snapshot,
    }
    witness_records = []
    if witness_path:
        witness_records, witness_snapshot = read_retained_jsonl(
            witness_path,
            out_dir / "input-snapshots",
            "witness-resolutions",
        )
        input_snapshots["witness_resolutions"] = witness_snapshot
    source = read_jsonl(source_path)
    source_by_scan = index_by_scan(source, "Aligned source")
    scans = sorted(source_by_scan)
    translation_by_scan = index_by_scan(translation_records, "Blind translations")
    critique_by_scan = index_by_scan(critique_records, "Fidelity criticisms")
    if not args.page and args.limit <= 0:
        require_volume8_scan_coverage(source_by_scan, "Aligned source")
        require_volume8_scan_coverage(translation_by_scan, "Blind translations")
        require_volume8_scan_coverage(critique_by_scan, "Fidelity criticisms")
    witness_by_scan = {}
    if witness_path:
        witness_by_scan = index_by_scan(witness_records, "Witness resolutions")

    missing_critique = sorted(set(translation_by_scan) - set(critique_by_scan))
    if missing_critique:
        raise RuntimeError(f"Critique is incomplete; {len(missing_critique)} translated pages lack criticism")
    for scan, translation in translation_by_scan.items():
        source_record = source_by_scan.get(scan)
        if source_record is None:
            raise RuntimeError(f"Blind translation scan {scan} is absent from aligned source")
        current, reason = validate_critique_provenance(
            source_record, translation, critique_by_scan[scan]
        )
        if not current:
            raise RuntimeError(
                f"Critique provenance mismatch at scan {scan}: {reason}"
            )
    for scan, witness in witness_by_scan.items():
        if (
            scan not in source_by_scan
            or scan not in translation_by_scan
            or scan not in critique_by_scan
        ):
            raise RuntimeError(
                f"Witness resolution scan {scan} lacks its source, translation, or critique"
            )
        current, reason = validate_witness_provenance(
            source_by_scan[scan],
            translation_by_scan[scan],
            critique_by_scan[scan],
            witness,
        )
        if not current:
            raise RuntimeError(
                f"Witness provenance mismatch at scan {scan}: {reason}"
            )

    selected = []
    missing_witness = []
    for scan in sorted(translation_by_scan):
        if args.page and scan not in set(args.page):
            continue
        translation = translation_by_scan[scan]
        critique = critique_by_scan[scan]
        if not should_adjudicate_page(
            translation,
            critique,
            source_by_scan[scan],
            all_pages=args.all_pages,
        ):
            continue
        if witness_concerns(translation, critique) and scan not in witness_by_scan:
            missing_witness.append(scan)
            continue
        selected.append(scan)
    if missing_witness:
        raise RuntimeError(f"Witness resolution is incomplete; {len(missing_witness)} adjudication pages require it")

    schema_path = Path(args.schema).resolve()
    schema_sha256 = sha256_file(schema_path)

    state_path = out_dir / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    if state.get("schema") != "firstlight.codex-adjudication-state.v1":
        state = {"schema": "firstlight.codex-adjudication-state.v1", "completed": {}, "failed": {}, "stale": {}}

    jobs = {}
    pending_scans = []
    for scan in selected:
        index = scans.index(scan)
        prompt = build_prompt(
            source_by_scan[scan], translation_by_scan[scan], critique_by_scan[scan], witness_by_scan.get(scan),
            source_by_scan[scans[index - 1]] if index > 0 else None,
            source_by_scan[scans[index + 1]] if index + 1 < len(scans) else None,
        )
        expected = expected_provenance(
            prompt=prompt,
            source=source_by_scan[scan],
            translation=translation_by_scan[scan],
            critique=critique_by_scan[scan],
            witness=witness_by_scan.get(scan),
            model=args.model,
            reasoning_effort=args.reasoning_effort,
            schema_sha256=schema_sha256,
        )
        jobs[scan] = {"prompt": prompt, "expected": expected}
        result_path = page_dir / f"{scan:04d}.json"
        normalized_existing = False
        if result_path.is_file():
            try:
                existing_record = json.loads(result_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                existing_record = None
            if existing_record is not None and normalize_decision_state(existing_record):
                atomic_json(result_path, existing_record)
                normalized_existing = True
        checkpoint_sha = None if normalized_existing else (
            state.get("completed", {}).get(str(scan)) or {}
        ).get("result_sha256")
        current, reason = validate_existing_page(result_path, expected, checkpoint_sha)
        if current:
            state["completed"][str(scan)] = {"result_sha256": sha256_file(result_path)}
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
        "schema": "firstlight.codex-adjudication-run.v1",
        "prompt_version": PROMPT_VERSION,
        "prompt_versions": sorted({
            str(job["expected"]["prompt_version"]) for job in jobs.values()
        }),
        "aligned_source_sha256": sha256_file(source_path),
        "translations_sha256": translations_snapshot["sha256"],
        "criticisms_sha256": criticisms_snapshot["sha256"],
        "witness_resolutions_sha256": (
            input_snapshots["witness_resolutions"]["sha256"]
            if witness_path else None
        ),
        "input_snapshots": input_snapshots,
        "output_schema_sha256": schema_sha256,
        "model": args.model,
        "reasoning_effort": args.reasoning_effort,
        "selected_pages": len(selected),
        "selected_scan_pages": selected,
        "selection_policy": "all_pages" if args.all_pages else "triggered_pages",
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
                    codex_path=Path(args.codex).resolve(), work_dir=work_dir, schema_path=schema_path,
                    prompt=jobs[scan]["prompt"], result_path=candidate_path,
                    model=args.model, reasoning_effort=args.reasoning_effort,
                    timeout_seconds=args.timeout_seconds,
                )
                (log_dir / f"{scan:04d}.stdout.log").write_text(completed.stdout, encoding="utf-8")
                (log_dir / f"{scan:04d}.stderr.log").write_text(completed.stderr, encoding="utf-8")
                if completed.returncode != 0:
                    raise RuntimeError(f"Codex exited {completed.returncode}: {completed.stderr[-1200:]}")
                record = json.loads(candidate_path.read_text(encoding="utf-8"))
                if int(record.get("scan_page", -1)) != scan:
                    raise RuntimeError(f"Codex returned scan_page {record.get('scan_page')} for {scan}")
                normalize_decision_state(record)
                record.update(jobs[scan]["expected"])
                record["generated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
                atomic_json(result_path, record)
                candidate_path.unlink(missing_ok=True)
                valid, reason = validate_existing_page(result_path, jobs[scan]["expected"])
                if not valid:
                    raise RuntimeError(reason)
                state["completed"][str(scan)] = {"attempts": attempt, "result_sha256": sha256_file(result_path)}
                state["failed"].pop(str(scan), None)
                state["stale"].pop(str(scan), None)
                atomic_json(state_path, state)
                print(f"ok scan_page={scan} decision={record['decision']} attempt={attempt}", flush=True)
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
            jobs[scan]["expected"],
            (state.get("completed", {}).get(str(scan)) or {}).get("result_sha256"),
        )[0]
    }
    count = aggregate(page_dir, out_dir / "adjudications.jsonl", current_scans)
    print(json.dumps({"selected": len(selected), "aggregated": count, "failed": len(state["failed"])}, indent=2))
    return 0 if not state["failed"] and count == len(selected) else 2


if __name__ == "__main__":
    raise SystemExit(main())

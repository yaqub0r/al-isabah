#!/usr/bin/env python3
"""Build and deterministically validate canonical English translation units."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from isabah_entry_sequence import (
    VOLUME8_FIRST_ENTRY,
    VOLUME8_LAST_ENTRY,
    audit_entry_sequence,
)
from run_codex_volume_revision import read_jsonl, sha256_file
from run_codex_volume_critic import record_sha256
from run_codex_volume_adjudication import (
    name_mapping_policy_violations,
    normalize_name_mappings,
    requires_adjudication,
    transliteration_policy_violations,
)
from run_codex_witness_resolution import candidate_evidence_sha256, witness_concerns
from usul_secondary_witness import evidence_sha256


DIGIT_MAP = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
SUPERSCRIPT_DIGIT_MAP = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
# Usul's Arabic uses a dash after biography numbers, while a natural English
# rendering may use a dash, period, or colon.  The number still has to begin a
# line and be a five-digit Volume 8 entry, which keeps four-digit report/page
# citations and prose numerals out of the match.
ENTRY_RE = re.compile(r"(?m)^\s*[\[(]?\s*(\d{5})\s*[\])]?\s*(?:[-–—.:]|\))")
FOOTNOTE_RE = re.compile(r"(?m)^\s*\((\d{1,3})\)")
ENGLISH_FOOTNOTE_RE = re.compile(r"(?m)^\s*(?:\((\d{1,3})\)|\[(\d{1,3})\]|(\d{1,3})[.)])\s+")
SUPERSCRIPT_FOOTNOTE_RE = re.compile(r"[⁰¹²³⁴⁵⁶⁷⁸⁹]+")
ARABIC_MARK_RE = re.compile(r"[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed]")
WORD_RE = re.compile(r"\w+", re.UNICODE)
NUMERIC_CORRECTION_CATEGORIES = {
    "bibliographic_citation",
    "bibliographic_reference",
    "citation",
    "citation_correction",
    "footnote_reference",
    "number",
}


def normalize_digits(value: str) -> str:
    return value.translate(DIGIT_MAP)


def probable_entry_numbers(arabic_text: str) -> list[int]:
    return [int(value) for value in ENTRY_RE.findall(normalize_digits(arabic_text))]


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


def documented_numeric_corrections(adjudication: dict | None, final_text: str) -> set[int]:
    """Return source tokens replaced by explicit, evidenced numeric corrections.

    Some RTL citations lose their separator in the canonical OCR (for example,
    a flattened ``5218`` for ``8/52``). A fidelity check must not call a verified
    correction an omission, but it also must not let free-form model prose
    waive missing numbers. The exemption therefore requires a structured
    numeric-change category, the replacement verbatim in the final text, and
    non-empty rationale and evidence. Concatenating the original digit groups
    recognizes a model's readable ``5/218`` description of the flattened
    source token ``5218``.
    """
    if not adjudication:
        return set()
    corrected: set[int] = set()
    for change in adjudication.get("changes", []):
        if not isinstance(change, dict):
            continue
        category = re.sub(
            r"[^a-z0-9]+", "_", str(change.get("category", "")).casefold()
        ).strip("_")
        if category not in NUMERIC_CORRECTION_CATEGORIES:
            continue
        original = str(change.get("original", "")).strip()
        replacement = str(change.get("replacement", "")).strip()
        rationale = str(change.get("rationale", "")).strip()
        evidence = str(change.get("evidence", "")).strip()
        if (
            not all((original, replacement, rationale, evidence))
            or replacement not in final_text
        ):
            continue
        normalized = normalize_digits(original).translate(SUPERSCRIPT_DIGIT_MAP)
        groups = re.findall(r"\d+", normalized)
        corrected.update(int(value) for value in groups)
        if len(groups) > 1:
            corrected.add(int("".join(groups)))
    return corrected


def boundary_word_overlap(left: str, right: str, *, limit: int = 120) -> tuple[int, str]:
    """Return exact suffix/prefix overlap without comparing whole-page boilerplate."""
    left_words = WORD_RE.findall(normalize_digits(left).casefold())[-limit:]
    right_words = WORD_RE.findall(normalize_digits(right).casefold())[:limit]
    for size in range(min(len(left_words), len(right_words)), 0, -1):
        if left_words[-size:] == right_words[:size]:
            return size, " ".join(left_words[-size:])
    return 0, ""


def stable_unit_id(work_id: str, volume: int, scan_page: int, source_sha256: str) -> str:
    return f"{work_id}:arabic:v{volume:02d}:p{scan_page:04d}:{source_sha256[:16]}"


def provenance_chain_errors(
    source: dict,
    translation: dict,
    critique: dict,
    witness: dict | None,
    adjudication: dict | None,
) -> list[dict]:
    scan = int(source["scan_page"])
    expected_identity = {
        "scan_page": scan,
        "work_id": source["work_id"],
        "volume": source["volume"],
        "source_sha256": source["arabic_text_sha256"],
    }
    errors = []

    def require(record: dict, stage: str, expected: dict[str, object]) -> None:
        for field, value in expected.items():
            if record.get(field) != value:
                errors.append({
                    "scan_page": scan,
                    "code": "provenance_chain_mismatch",
                    "stage": stage,
                    "field": field,
                    "expected": value,
                    "actual": record.get(field),
                })

    require(translation, "translation", {
        **expected_identity,
        "schema": "firstlight.codex-page-translation.v1",
        "pass": "blind_translation",
    })
    require(critique, "critique", {
        **expected_identity,
        "schema": "firstlight.codex-page-critique.v1",
        "pass": "fidelity_critic",
        "translation_sha256": record_sha256(translation),
    })
    if witness:
        require(witness, "witness", {
            **expected_identity,
            "schema": "firstlight.codex-witness-resolution.v1",
            "pass": "multilingual_witness_resolution",
            "translation_sha256": record_sha256(translation),
            "critique_sha256": record_sha256(critique),
        })
        observed_evidence_sha = evidence_sha256(witness.get("secondary_witness_evidence") or [])
        if witness.get("secondary_evidence_sha256") != observed_evidence_sha:
            errors.append({
                "scan_page": scan,
                "code": "provenance_chain_mismatch",
                "stage": "witness",
                "field": "secondary_witness_evidence",
                "expected": witness.get("secondary_evidence_sha256"),
                "actual": observed_evidence_sha,
            })
        observed_supplemental = witness.get("supplemental_witness_evidence") or []
        declared_supplemental_sha = witness.get("supplemental_evidence_sha256")
        if observed_supplemental or declared_supplemental_sha is not None:
            observed_supplemental_sha = evidence_sha256(observed_supplemental)
            if declared_supplemental_sha != observed_supplemental_sha:
                errors.append({
                    "scan_page": scan,
                    "code": "provenance_chain_mismatch",
                    "stage": "witness",
                    "field": "supplemental_witness_evidence",
                    "expected": declared_supplemental_sha,
                    "actual": observed_supplemental_sha,
                })
        observed_candidates_sha = candidate_evidence_sha256(witness.get("urdu_witness_candidates") or [])
        if witness.get("candidate_evidence_sha256") != observed_candidates_sha:
            errors.append({
                "scan_page": scan,
                "code": "provenance_chain_mismatch",
                "stage": "witness",
                "field": "urdu_witness_candidates",
                "expected": witness.get("candidate_evidence_sha256"),
                "actual": observed_candidates_sha,
            })
    if adjudication:
        require(adjudication, "adjudication", {
            **expected_identity,
            "schema": "firstlight.codex-page-adjudication.v1",
            "pass": "translation_adjudication",
            "translation_sha256": record_sha256(translation),
            "critique_sha256": record_sha256(critique),
            "witness_resolution_sha256": record_sha256(witness) if witness else None,
        })
    return errors


def final_page_record(
    source: dict,
    translation: dict,
    critique: dict,
    witness: dict | None,
    adjudication: dict | None,
) -> tuple[dict, list[dict], list[dict]]:
    scan = int(source["scan_page"])
    final_text = adjudication["final_english_text"] if adjudication else translation["english_text"]
    raw_names = adjudication["names"] if adjudication else translation.get("names", [])
    names, name_normalization_changes = normalize_name_mappings(raw_names)
    model_entries = adjudication["entry_numbers"] if adjudication else translation.get("entry_numbers", [])
    unresolved = adjudication.get("unresolved", []) if adjudication else []
    if not adjudication and witness and witness.get("remaining_unresolved"):
        unresolved.extend({
            "category": "witness",
            "arabic_span": "",
            "explanation": item,
            "human_review_priority": "high",
        } for item in witness["remaining_unresolved"])

    errors = []
    warnings = []
    name_policy_violations = name_mapping_policy_violations(names)
    if name_policy_violations:
        errors.append({
            "scan_page": scan,
            "code": "name_mapping_policy_violation",
            "mappings": name_policy_violations,
        })
    prohibited_transliteration = transliteration_policy_violations(final_text)
    if prohibited_transliteration:
        errors.append({
            "scan_page": scan,
            "code": "transliteration_policy_violation",
            "characters": prohibited_transliteration,
        })
    source_entries = probable_entry_numbers(source["arabic_text"])
    english_entries = probable_entry_numbers(final_text)
    final_entries = source_entries
    if source_entries != english_entries:
        errors.append({
            "scan_page": scan,
            "code": "entry_number_mismatch",
            "source": source_entries,
            "english": english_entries,
        })
    if source_entries != [int(value) for value in model_entries]:
        warnings.append({
            "scan_page": scan,
            "code": "entry_number_metadata_corrected_from_canonical_source",
            "model": model_entries,
            "canonical": source_entries,
        })
    source_notes = footnote_labels(source["arabic_text"])
    english_notes = english_footnote_labels(final_text)
    missing_notes = sorted(source_notes - english_notes)
    if missing_notes:
        errors.append({"scan_page": scan, "code": "missing_footnote_labels", "labels": missing_notes})
    extra_notes = sorted(english_notes - source_notes)
    if extra_notes:
        warnings.append({"scan_page": scan, "code": "extra_footnote_labels", "labels": extra_notes})
    missing_numbers = sorted(numeric_tokens(source["arabic_text"]) - numeric_tokens(final_text))
    numeric_corrections = documented_numeric_corrections(adjudication, final_text)
    accepted_corrections = sorted(set(missing_numbers) & numeric_corrections)
    if accepted_corrections:
        warnings.append({
            "scan_page": scan,
            "code": "documented_numeric_corrections",
            "numbers": accepted_corrections,
        })
    missing_numbers = [value for value in missing_numbers if value not in numeric_corrections]
    missing_material_numbers = [value for value in missing_numbers if value >= 10]
    if missing_material_numbers:
        errors.append({
            "scan_page": scan,
            "code": "missing_numeric_tokens",
            "numbers": missing_material_numbers,
        })
    missing_small_numbers = [value for value in missing_numbers if 5 <= value < 10]
    if missing_small_numbers:
        warnings.append({
            "scan_page": scan,
            "code": "possibly_missing_small_numeric_tokens",
            "numbers": missing_small_numbers,
        })
    if not final_text.strip():
        errors.append({"scan_page": scan, "code": "empty_english_text"})
    ratio = len(final_text.strip()) / max(1, len(source["arabic_text"].strip()))
    if ratio < 0.7 or ratio > 4.5:
        warnings.append({"scan_page": scan, "code": "length_ratio_outlier", "ratio": round(ratio, 4)})

    flags = []
    if adjudication:
        flags.append(f"adjudication:{adjudication['decision']}")
    if witness:
        flags.append(f"multilingual_witness:{witness['overall_status']}")
    flags.extend(f"unresolved:{item['category']}" for item in unresolved)
    target_state = "machine_validated_unresolved" if unresolved else "machine_validated_unreviewed"
    record = {
        "schema": "firstlight.reviewable-translation-unit.v1",
        "unit_id": stable_unit_id(source["work_id"], int(source["volume"]), scan, source["arabic_text_sha256"]),
        "work_id": source["work_id"],
        "witness_id": "ibn_hajar_isabah_v1_arabic_v1",
        "source": {
            "language": "ar",
            "volume": source["volume"],
            "scan_page": scan,
            "printed_page": source.get("printed_page"),
            "reader_page": source.get("reader_page"),
            "reader_url": source.get("reader_url"),
            "pdf": source.get("facsimile_pdf"),
            "text_sha256": source["arabic_text_sha256"],
            "text": source["arabic_text"],
            "state": source["source_state"],
            "alignment": source.get("alignment"),
        },
        "target": {
            "language": "en",
            "text": final_text,
            "printed_page": source.get("printed_page"),
            "state": target_state,
            "names": names,
            "entry_numbers": final_entries,
            "unresolved": unresolved,
            "flags": flags,
        },
        "translation": {
            "method": "codex_blind_translation_with_independent_critique_multilingual_witness_and_full_adjudication",
            "blind_model": translation.get("model"),
            "blind_reasoning_effort": translation.get("reasoning_effort"),
            "blind_prompt_version": translation.get("prompt_version"),
            "critic_model": critique.get("model"),
            "critic_reasoning_effort": critique.get("reasoning_effort"),
            "critic_prompt_version": critique.get("prompt_version"),
            "adjudication_model": (adjudication or {}).get("model"),
            "adjudication_reasoning_effort": (adjudication or {}).get("reasoning_effort"),
            "adjudication_prompt_version": (adjudication or {}).get("prompt_version"),
            "generated_at_utc": (adjudication or translation).get("generated_at"),
        },
        "quality": {
            "critic_verdict": critique["verdict"],
            "critic_issue_count": len(critique.get("issues") or []),
            "witness_status": (witness or {}).get("overall_status", "not_required"),
            "adjudication_decision": (adjudication or {}).get("decision", "not_required_critic_pass"),
            "deterministic_normalizations": {
                "name_ascii_apostrophes": name_normalization_changes,
            },
            "deterministic_errors": errors,
            "deterministic_warnings": warnings,
        },
        "review": {"state": "unreviewed", "reviewer": None, "notes": None},
        "urdu_cross_check": {
            "state": (witness or {}).get("overall_status", "not_required"),
            "witness_id": "ibn_hajar_isabah_urdu_v1",
            "citation": sorted({page for finding in (witness or {}).get("findings", []) for page in finding.get("witness_pages", [])}),
            "notes": (witness or {}).get("summary"),
            "candidates": (witness or {}).get("urdu_witness_candidates") or [],
            "candidate_evidence_sha256": (witness or {}).get("candidate_evidence_sha256"),
        },
        "collateral_cross_check": {
            "state": (witness or {}).get("overall_status", "not_required"),
            "notes": (witness or {}).get("summary"),
            "evidence": (witness or {}).get("secondary_witness_evidence") or [],
            "evidence_sha256": (witness or {}).get("secondary_evidence_sha256"),
        },
        "supplemental_cross_check": {
            "state": (witness or {}).get("overall_status", "not_required"),
            "evidence": (witness or {}).get("supplemental_witness_evidence") or [],
            "evidence_sha256": (witness or {}).get("supplemental_evidence_sha256"),
        },
    }
    return record, errors, warnings


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + ".tmp")
    with pending.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    pending.replace(path)


def build_name_report(records: list[dict]) -> dict:
    arabic_to_english: dict[str, set[str]] = defaultdict(set)
    english_to_arabic: dict[str, set[str]] = defaultdict(set)
    mentions = 0
    for record in records:
        for name in record["target"].get("names") or []:
            arabic = ARABIC_MARK_RE.sub("", unicodedata.normalize("NFKC", str(name["arabic"])).replace("ـ", ""))
            arabic = " ".join(arabic.split())
            english = unicodedata.normalize("NFKC", str(name["english"]))
            english = " ".join(english.replace("’", "'").replace("‘", "'").replace("`", "'").split())
            arabic_to_english[arabic].add(english)
            english_to_arabic[english.casefold()].add(arabic)
            mentions += 1
    variants = [
        {"arabic": arabic, "english_forms": sorted(forms)}
        for arabic, forms in sorted(arabic_to_english.items()) if len(forms) > 1
    ]
    collisions = [
        {"english": english, "arabic_forms": sorted(forms)}
        for english, forms in sorted(english_to_arabic.items()) if len(forms) > 1
    ]
    return {
        "schema": "firstlight.translation-name-consistency.v1",
        "name_mentions": mentions,
        "unique_arabic_forms": len(arabic_to_english),
        "arabic_forms_with_multiple_english_renderings": variants,
        "english_renderings_with_multiple_arabic_forms": collisions,
    }


def records_in_scan_range(records: list[dict], expected_scans: set[int]) -> dict[int, dict]:
    """Index only the requested scan range.

    The range flags are used for isolated pipeline proofs as well as the full
    production build. Inputs may therefore be complete-volume supersets during
    a proof; pages outside the explicitly requested range are intentionally not
    part of that build's coverage contract.
    """
    indexed = {}
    duplicates = []
    for record in records:
        scan = int(record["scan_page"])
        if scan not in expected_scans:
            continue
        if scan in indexed:
            duplicates.append(scan)
        indexed[scan] = record
    if duplicates:
        raise RuntimeError(f"Input contains duplicate scan pages: {sorted(set(duplicates))[:20]}")
    return indexed


def requires_final_adjudication(
    translation: dict,
    critique: dict,
    source: dict,
    *,
    complete_volume: bool,
) -> bool:
    """Require the deliberately exhaustive pass for a production Volume 8 build."""
    return complete_volume or requires_adjudication(translation, critique, source)


def witness_evidence_report(witness_records: list[dict]) -> dict:
    evidence = [
        item
        for record in witness_records
        for item in (record.get("secondary_witness_evidence") or [])
    ]
    supplemental = [
        item
        for record in witness_records
        for item in (record.get("supplemental_witness_evidence") or [])
    ]
    return {
        "resolution_pages": len(witness_records),
        "collateral_records": len(evidence),
        "query_attempts": len({(item.get("work_id"), item.get("query")) for item in evidence}),
        "unique_queries": len({item.get("query") for item in evidence if item.get("query")}),
        "retrieval_hits": sum(item.get("retrieval_state") == "hit" for item in evidence),
        "retrieval_no_matches": sum(item.get("retrieval_state") == "no_match" for item in evidence),
        "retrieval_errors": sum(item.get("retrieval_state") == "error" for item in evidence),
        "retrieval_unavailable": sum(item.get("retrieval_state") == "unavailable" for item in evidence),
        "retrieval_incomplete": sum(
            item.get("retrieval_state") not in {"hit", "no_match"}
            for item in evidence
        ),
        "works": sorted({str(item.get("work_id")) for item in evidence if item.get("work_id")}),
        "supplemental_records": len(supplemental),
        "supplemental_kinds": sorted({
            str(item.get("kind")) for item in supplemental if item.get("kind")
        }),
        "supplemental_scans": sorted({
            int(item["scan_page"]) for item in supplemental if item.get("scan_page") is not None
        }),
    }


def unresolved_passage_report(records: list[dict]) -> list[dict]:
    return [
        {
            "scan_page": int(record["source"]["scan_page"]),
            "printed_page": record["source"].get("printed_page"),
            "reader_url": record["source"].get("reader_url"),
            "unit_id": record["unit_id"],
            "items": record["target"].get("unresolved") or [],
        }
        for record in records
        if record["target"].get("unresolved")
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aligned-source", required=True)
    parser.add_argument("--translations", required=True)
    parser.add_argument("--criticisms", required=True)
    parser.add_argument("--witness-resolutions")
    parser.add_argument("--adjudications")
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--expected-first-scan", type=int, default=4)
    parser.add_argument("--expected-last-scan", type=int, default=494)
    args = parser.parse_args()

    source_path = Path(args.aligned_source).resolve()
    translations_path = Path(args.translations).resolve()
    criticisms_path = Path(args.criticisms).resolve()
    expected_scans = set(range(args.expected_first_scan, args.expected_last_scan + 1))
    if not expected_scans:
        raise RuntimeError("Expected scan range must not be empty")
    complete_volume = expected_scans == set(range(4, 495))
    source = read_jsonl(source_path)
    source_by_scan = records_in_scan_range(source, expected_scans)
    translation_by_scan = records_in_scan_range(read_jsonl(translations_path), expected_scans)
    critique_by_scan = records_in_scan_range(read_jsonl(criticisms_path), expected_scans)
    witness_by_scan = records_in_scan_range(
        read_jsonl(Path(args.witness_resolutions).resolve()), expected_scans
    ) if args.witness_resolutions else {}
    adjudication_by_scan = records_in_scan_range(
        read_jsonl(Path(args.adjudications).resolve()), expected_scans
    ) if args.adjudications else {}
    errors = []
    warnings = []
    for label, observed in (
        ("source", set(source_by_scan)),
        ("translation", set(translation_by_scan)),
        ("critique", set(critique_by_scan)),
    ):
        if observed != expected_scans:
            errors.append({
                "code": f"{label}_coverage",
                "missing": sorted(expected_scans - observed),
                "extra": sorted(observed - expected_scans),
            })

    records = []
    unresolved_count = 0
    adjudication_required = []
    witness_required = []
    if not errors:
        for scan in sorted(expected_scans):
            source_page = source_by_scan[scan]
            translation = translation_by_scan[scan]
            critique = critique_by_scan[scan]
            chain_errors = provenance_chain_errors(
                source_page,
                translation,
                critique,
                witness_by_scan.get(scan),
                adjudication_by_scan.get(scan),
            )
            if chain_errors:
                errors.extend(chain_errors)
                continue
            if translation.get("source_sha256") != source_page["arabic_text_sha256"]:
                errors.append({"scan_page": scan, "code": "translation_source_hash_mismatch"})
                continue
            if critique.get("source_sha256") != source_page["arabic_text_sha256"]:
                errors.append({"scan_page": scan, "code": "critique_source_hash_mismatch"})
                continue
            if witness_concerns(translation, critique):
                witness_required.append(scan)
                if scan not in witness_by_scan:
                    errors.append({"scan_page": scan, "code": "missing_witness_resolution"})
                    continue
            if requires_final_adjudication(
                translation,
                critique,
                source_page,
                complete_volume=complete_volume,
            ):
                adjudication_required.append(scan)
                if scan not in adjudication_by_scan:
                    errors.append({"scan_page": scan, "code": "missing_adjudication"})
                    continue
            record, page_errors, page_warnings = final_page_record(
                source_page, translation, critique, witness_by_scan.get(scan), adjudication_by_scan.get(scan)
            )
            records.append(record)
            errors.extend(page_errors)
            warnings.extend(page_warnings)
            unresolved_count += len(record["target"]["unresolved"])

    entry_sequence = [number for record in records for number in record["target"]["entry_numbers"]]
    reversals = [
        {"previous": left, "next": right}
        for left, right in zip(entry_sequence, entry_sequence[1:]) if right < left
    ]
    if reversals:
        errors.append({"code": "entry_number_reversal", "examples": reversals[:20], "count": len(reversals)})
    entry_sequence_audit = {
        "enforced": complete_volume,
        "observed_count": len(entry_sequence),
        "observed_first": entry_sequence[0] if entry_sequence else None,
        "observed_last": entry_sequence[-1] if entry_sequence else None,
    }
    if complete_volume:
        entry_sequence_audit = {
            "enforced": True,
            **audit_entry_sequence(
                entry_sequence,
                expected_first=VOLUME8_FIRST_ENTRY,
                expected_last=VOLUME8_LAST_ENTRY,
            ),
        }
        if not entry_sequence_audit["pass"]:
            errors.append({
                "code": "canonical_entry_sequence_mismatch",
                "expected_first": VOLUME8_FIRST_ENTRY,
                "expected_last": VOLUME8_LAST_ENTRY,
                "expected_count": entry_sequence_audit["expected_count"],
                "observed_count": entry_sequence_audit["observed_count"],
                "gaps": entry_sequence_audit["gaps"][:50],
                "duplicates": entry_sequence_audit["duplicates"][:50],
                "reversals": entry_sequence_audit["reversals"][:50],
                "out_of_range": entry_sequence_audit["out_of_range"][:50],
            })

    for left, right in zip(records, records[1:]):
        left_scan = int(left["source"]["scan_page"])
        right_scan = int(right["source"]["scan_page"])
        if right_scan != left_scan + 1:
            continue
        english_overlap, preview = boundary_word_overlap(left["target"]["text"], right["target"]["text"])
        source_overlap, _ = boundary_word_overlap(left["source"]["text"], right["source"]["text"])
        if source_overlap == 0 and english_overlap >= 30:
            errors.append({
                "code": "probable_cross_page_context_duplication",
                "left_scan_page": left_scan,
                "right_scan_page": right_scan,
                "overlap_words": english_overlap,
                "preview": preview[:500],
            })
        elif source_overlap == 0 and english_overlap >= 12:
            warnings.append({
                "code": "possible_cross_page_context_duplication",
                "left_scan_page": left_scan,
                "right_scan_page": right_scan,
                "overlap_words": english_overlap,
                "preview": preview[:500],
            })
    name_report = build_name_report(records)
    if name_report["arabic_forms_with_multiple_english_renderings"]:
        warnings.append({
            "code": "name_rendering_variants",
            "count": len(name_report["arabic_forms_with_multiple_english_renderings"]),
        })

    witness_evidence = witness_evidence_report(list(witness_by_scan.values()))
    unresolved_passages = unresolved_passage_report(records)
    if witness_evidence["retrieval_incomplete"]:
        errors.append({
            "code": "incomplete_collateral_witness_evidence",
            "count": witness_evidence["retrieval_incomplete"],
        })
    ready = not errors and len(records) == len(expected_scans)
    output_path = Path(args.output).resolve()
    report_path = Path(args.report).resolve()
    if ready:
        write_jsonl(output_path, records)
    report = {
        "schema": "firstlight.translation-machine-readiness.v1",
        "work_id": source[0]["work_id"] if source else "ibn_hajar_isabah_v1",
        "volume": 8,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "ready_for_human_review": ready,
        "expected_pages": len(expected_scans),
        "final_pages": len(records),
        "witness_required_pages": witness_required,
        "adjudication_required_pages": adjudication_required,
        "unresolved_item_count": unresolved_count,
        "unresolved_passages": unresolved_passages,
        "entry_sequence_audit": entry_sequence_audit,
        "witness_evidence": witness_evidence,
        "errors": errors,
        "warnings": warnings,
        "name_consistency": name_report,
        "inputs": {
            "aligned_source_sha256": sha256_file(source_path),
            "translations_sha256": sha256_file(translations_path),
            "criticisms_sha256": sha256_file(criticisms_path),
            "witness_resolutions_sha256": sha256_file(Path(args.witness_resolutions).resolve()) if args.witness_resolutions else None,
            "adjudications_sha256": sha256_file(Path(args.adjudications).resolve()) if args.adjudications else None,
        },
        "output": str(output_path) if ready else None,
        "output_sha256": sha256_file(output_path) if ready else None,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "ready_for_human_review": ready,
        "final_pages": len(records),
        "errors": len(errors),
        "warnings": len(warnings),
        "unresolved_items": unresolved_count,
    }, indent=2))
    return 0 if ready else 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Publish verified Volume 8 machine-readiness evidence into the al-Isabah source bundle."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def presentation_source_marker(source_sha256: str) -> str:
    return f'<meta name="firstlight-source-sha256" content="{source_sha256}">'


def atomic_json(path: Path, value: dict) -> None:
    pending = path.with_suffix(path.suffix + ".tmp")
    pending.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pending.replace(path)


def artifact(bundle: dict, artifact_id: str) -> dict:
    return next(item for item in bundle["artifacts"] if item["artifact_id"] == artifact_id)


def upsert_artifact(bundle: dict, payload: dict) -> dict:
    current = next(
        (item for item in bundle["artifacts"] if item["artifact_id"] == payload["artifact_id"]),
        None,
    )
    if current is None:
        bundle["artifacts"].append(payload)
        return payload
    current.clear()
    current.update(payload)
    return current


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--alignment-report", required=True, type=Path)
    parser.add_argument("--aligned-source", required=True, type=Path)
    parser.add_argument("--readiness", required=True, type=Path)
    parser.add_argument("--readiness-label", type=Path)
    parser.add_argument("--structured-english", required=True, type=Path)
    parser.add_argument("--presentation", required=True, type=Path)
    parser.add_argument("--name-review", required=True, type=Path)
    parser.add_argument(
        "--supplemental-witness-evidence",
        type=Path,
        help=(
            "Hash-bound witness JSONL. Defaults to "
            "volume_08.supplemental-witness-evidence.jsonl beside --aligned-source."
        ),
    )
    args = parser.parse_args()

    bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
    alignment = json.loads(args.alignment_report.read_text(encoding="utf-8"))
    readiness = json.loads(args.readiness.read_text(encoding="utf-8"))
    names = json.loads(args.name_review.read_text(encoding="utf-8"))
    units = read_jsonl(args.structured_english)
    aligned_units = read_jsonl(args.aligned_source)
    supplemental_path = args.supplemental_witness_evidence or args.aligned_source.with_name(
        "volume_08.supplemental-witness-evidence.jsonl"
    )
    if not supplemental_path.is_file():
        raise RuntimeError(f"Supplemental witness evidence is missing: {supplemental_path}")
    supplemental_evidence = read_jsonl(supplemental_path)
    aligned_source_sha256 = sha256(args.aligned_source)
    if not alignment.get("pass") or int(alignment.get("page_count", 0)) != 491:
        raise RuntimeError("Volume 8 source alignment has not passed for all 491 pages")
    entry_audit = alignment.get("entry_sequence_audit") or {}
    if (
        not entry_audit.get("pass")
        or entry_audit.get("expected_first") != 10759
        or entry_audit.get("expected_last") != 12308
        or entry_audit.get("observed_count") != 1550
    ):
        raise RuntimeError("Volume 8 canonical entry sequence has not passed")
    if alignment.get("output_sha256") != aligned_source_sha256:
        raise RuntimeError("Alignment report is stale relative to aligned Arabic")
    aligned_scans = [int(item.get("scan_page", -1)) for item in aligned_units]
    if aligned_scans != list(range(4, 495)):
        raise RuntimeError("Aligned Arabic does not contain exact scan-page coverage 4-494")
    if not readiness.get("ready_for_human_review") or len(units) != 491:
        raise RuntimeError("Volume 8 machine-readiness has not passed for all 491 pages")
    readiness_entry_audit = readiness.get("entry_sequence_audit") or {}
    if not readiness_entry_audit.get("pass"):
        raise RuntimeError("Machine readiness did not pass the canonical entry sequence")
    if (readiness.get("inputs") or {}).get("aligned_source_sha256") != aligned_source_sha256:
        raise RuntimeError("Machine readiness is stale relative to aligned Arabic")
    if readiness.get("output_sha256") != sha256(args.structured_english):
        raise RuntimeError("Structured English hash does not match the readiness report")
    if names.get("schema") != "firstlight.name-review.v1" or names.get("work_id") != bundle.get("work_id"):
        raise RuntimeError("Name-review authority is incompatible with this source bundle")
    if names.get("source", {}).get("sha256") != sha256(args.structured_english):
        raise RuntimeError("Name-review authority is stale relative to structured English")
    structured_english_sha256 = sha256(args.structured_english)
    if presentation_source_marker(structured_english_sha256) not in args.presentation.read_text(encoding="utf-8"):
        raise RuntimeError("English review presentation is stale relative to structured English")
    if not supplemental_evidence:
        raise RuntimeError("Supplemental witness evidence is empty")
    for item in supplemental_evidence:
        if item.get("schema") != "firstlight.supplemental-witness-evidence.v1":
            raise RuntimeError("Supplemental witness evidence has an unsupported schema")
        excerpt_sha = hashlib.sha256(str(item.get("excerpt") or "").encode("utf-8")).hexdigest()
        if item.get("excerpt_sha256") != excerpt_sha:
            raise RuntimeError(
                f"Supplemental witness evidence {item.get('evidence_id')} has a stale excerpt hash"
            )
        if int(item.get("scan_page", -1)) not in aligned_scans:
            raise RuntimeError(
                f"Supplemental witness evidence {item.get('evidence_id')} targets an unknown scan"
            )

    source_artifact_id = "isabah-volume-08-aligned-arabic"
    aligned_artifact = next((item for item in bundle["artifacts"] if item["artifact_id"] == source_artifact_id), None)
    aligned_payload = {
        "artifact_id": source_artifact_id,
        "role": "alignment_evidence",
        "language": "ar",
        "format": "application/x-ndjson",
        "edition_relationship": "exact_canonical",
        "state": "verified_local",
        "source_platform": "Usul + FirstLight facsimile repair",
        "source_url": "https://usul.ai/t/isaba-fi-tamyiz/3916",
        "local_path": str(args.aligned_source).replace("\\", "/"),
        "sha256": aligned_source_sha256,
        "byte_size": args.aligned_source.stat().st_size,
        "page_count": 491,
        "provider_ids": {"first_reader_page": 3916, "last_reader_page": 4406},
        "derived_from": ["isabah-usul-4CPCkl83K7-facsimile", "isabah-usul-4CPCkl83K7-text"],
        "coverage": "volume 8 substantive scan pages 4-494",
        "verification": {
            "alignment_report": str(args.alignment_report).replace("\\", "/"),
            "canonical_usul_reader_pages": alignment.get("canonical_usul_pages"),
            "canonical_facsimile_transcription_pages": alignment.get("canonical_facsimile_transcription_pages"),
            "canonical_facsimile_correction_pages": alignment.get("canonical_facsimile_correction_pages"),
            "heading_mismatches": alignment.get("heading_mismatches"),
            "entry_sequence_audit": entry_audit,
            "pass": True,
        },
        "notes": "Every substantive Volume 8 page is aligned to the locked facsimile; one unavailable Usul reader chunk was transcribed and eight exact OCR defects were repaired from the canonical scans. Entry headings are continuous from 10759 through 12308.",
    }
    if aligned_artifact is None:
        bundle["artifacts"].insert(2, aligned_payload)
    else:
        aligned_artifact.clear()
        aligned_artifact.update(aligned_payload)

    textual_witnesses = [
        {
            "artifact_id": "isabah-usul-usd-al-ghaba-collateral",
            "role": "textual_witness",
            "language": "ar",
            "format": "Usul public machine-readable text + PDF facsimile",
            "edition_relationship": "different_work",
            "state": "verified_remote",
            "source_platform": "Usul",
            "source_url": "https://usul.ai/t/asad-al-ghaba-fi-marifat-al-sahaba",
            "local_path": None,
            "sha256": None,
            "byte_size": None,
            "page_count": None,
            "provider_ids": {
                "book_id": "e5j6lo7201j98j5cnn750wc6",
                "version_id": "pRzuFotC79",
                "source_and_version": "turath:1110",
                "facsimile_url": "https://assets.usul.ai/pdfs/pRzuFotC79.pdf",
            },
            "derived_from": [],
            "coverage": "Complete independent companion dictionary; exact subject-heading queries used only for flagged Volume 8 uncertainties",
            "verification": {
                "retrieval": "Usul public keyword-search API",
                "query_policy": "concern-local exact biography heading",
                "canonical_override_allowed": False,
            },
            "notes": "Collateral Arabic witness for shared names and reports; this is not an edition or manuscript of al-Isabah.",
        },
        {
            "artifact_id": "isabah-usul-istiab-collateral",
            "role": "textual_witness",
            "language": "ar",
            "format": "Usul public machine-readable text + PDF facsimile",
            "edition_relationship": "different_work",
            "state": "verified_remote",
            "source_platform": "Usul",
            "source_url": "https://usul.ai/t/isticab-fi-macrifat-ashab",
            "local_path": None,
            "sha256": None,
            "byte_size": None,
            "page_count": None,
            "provider_ids": {
                "book_id": "0463IbnCabdBarr.IsticabFiMacrifatAshab",
                "version_id": "zDYIs6bLxz",
                "source_and_version": "turath:12288",
                "facsimile_url": "https://assets.usul.ai/pdfs/zDYIs6bLxz.pdf",
            },
            "derived_from": [],
            "coverage": "Complete independent companion dictionary; exact subject-heading queries used only for flagged Volume 8 uncertainties",
            "verification": {
                "retrieval": "Usul public keyword-search API",
                "query_policy": "concern-local exact biography heading",
                "canonical_override_allowed": False,
            },
            "notes": "Collateral Arabic witness for shared names and reports; provider errors and absent entries remain explicit inconclusive evidence.",
        },
        {
            "artifact_id": "isabah-usul-dar-hajr-alternative-edition",
            "role": "textual_witness",
            "language": "ar",
            "format": "Usul OpenITI machine-readable text",
            "edition_relationship": "different_edition",
            "state": "verified_remote",
            "source_platform": "Usul",
            "source_url": "https://usul.ai/t/isaba-fi-tamyiz",
            "local_path": None,
            "sha256": None,
            "byte_size": None,
            "page_count": None,
            "provider_ids": {
                "book_id": "0852IbnHajarCasqalani.IsabaFiTamyiz",
                "version_id": "-aZ_8_5c6S",
                "source_and_version": "openiti:0852IbnHajarCasqalani.IsabaFiTamyiz.ShamAY0034568-ara3",
            },
            "derived_from": [],
            "coverage": "Independent Dar Hajr / Markaz Hajr edition of al-Isabah; queried only for damaged, contradictory, or explicitly uncertain canonical passages",
            "verification": {
                "retrieval": "Usul exact-version keyword search",
                "query_policy": "concern-local active biography heading",
                "canonical_override_allowed": False,
                "transparent_citation_required": True,
            },
            "notes": "Alternative edition of the same work. Agreement may support a cited emendation but never a silent replacement of the locked Dar al-Kutub al-Ilmiyyah text.",
        },
        {
            "artifact_id": "isabah-usul-dar-jil-alternative-edition",
            "role": "textual_witness",
            "language": "ar",
            "format": "Usul OpenITI machine-readable text",
            "edition_relationship": "different_edition",
            "state": "verified_remote",
            "source_platform": "Usul",
            "source_url": "https://usul.ai/t/isaba-fi-tamyiz",
            "local_path": None,
            "sha256": None,
            "byte_size": None,
            "page_count": None,
            "provider_ids": {
                "book_id": "0852IbnHajarCasqalani.IsabaFiTamyiz",
                "version_id": "xAOjIqxYuv",
                "source_and_version": "openiti:0852IbnHajarCasqalani.IsabaFiTamyiz.JK000533-ara1",
            },
            "derived_from": [],
            "coverage": "Independent Ali Muhammad al-Bajawi / Dar al-Jil edition of al-Isabah; queried only for damaged, contradictory, or explicitly uncertain canonical passages",
            "verification": {
                "retrieval": "Usul exact-version keyword search",
                "query_policy": "concern-local active biography heading",
                "canonical_override_allowed": False,
                "transparent_citation_required": True,
            },
            "notes": "Second alternative edition of the same work, retained independently so agreement between editions is visible and auditable.",
        },
    ]
    for witness in textual_witnesses:
        upsert_artifact(bundle, witness)

    supplemental_artifact_id = "isabah-volume-08-supplemental-witness-evidence"
    upsert_artifact(bundle, {
        "artifact_id": supplemental_artifact_id,
        "role": "quality_evidence",
        "language": "mul",
        "format": "application/x-ndjson",
        "edition_relationship": "derived_from_canonical",
        "state": "verified_local",
        "source_platform": "FirstLight + cited public source witnesses",
        "source_url": None,
        "local_path": str(supplemental_path).replace("\\", "/"),
        "sha256": sha256(supplemental_path),
        "byte_size": supplemental_path.stat().st_size,
        "page_count": None,
        "provider_ids": {},
        "derived_from": [source_artifact_id],
        "coverage": (
            "Hash-bound external evidence for flagged Volume 8 scans "
            + ", ".join(str(scan) for scan in sorted({int(item["scan_page"]) for item in supplemental_evidence}))
        ),
        "verification": {
            "schema": "firstlight.supplemental-witness-evidence.v1",
            "evidence_count": len(supplemental_evidence),
            "scan_pages": sorted({int(item["scan_page"]) for item in supplemental_evidence}),
            "excerpt_hashes_verified": True,
            "concern_links_present": all(bool(item.get("concern_ids")) for item in supplemental_evidence),
            "canonical_override_allowed": False,
        },
        "notes": "Alternative editions and parallel transmissions are concern-scoped, inspectable inputs. Their kind determines evidentiary weight; none silently replaces canonical al-Isabah Arabic.",
    })

    unresolved = sum(len(unit["target"].get("unresolved") or []) for unit in units)
    name_mentions = sum(len(unit["target"].get("names") or []) for unit in units)
    english_words = sum(len(re.findall(r"\b[\w'-]+\b", unit["target"]["text"])) for unit in units)
    critic_issues = sum(int(unit.get("quality", {}).get("critic_issue_count", 0)) for unit in units)
    structured = artifact(bundle, "isabah-volume-08-structured-english")
    structured.update({
        "state": "verified_local",
        "local_path": str(args.structured_english).replace("\\", "/"),
        "sha256": sha256(args.structured_english),
        "byte_size": args.structured_english.stat().st_size,
        "page_count": 491,
        "derived_from": [
            source_artifact_id,
            "isabah-urdu-eight-volume-witness",
            "isabah-usul-usd-al-ghaba-collateral",
            "isabah-usul-istiab-collateral",
            "isabah-usul-dar-hajr-alternative-edition",
            "isabah-usul-dar-jil-alternative-edition",
            supplemental_artifact_id,
        ],
        "verification": {
            "substantive_units": 491,
            "translated_units": 491,
            "critic_units": 491,
            "approved_units": 0,
            "unresolved_items": unresolved,
            "structured_name_mentions": name_mentions,
            "english_words": english_words,
            "machine_readiness_report": str(args.readiness_label or args.readiness).replace("\\", "/"),
            "machine_readiness_pass": True,
        },
        "notes": "Codex blind translation, independent fidelity criticism, selective image-aware Urdu checks, concern-local collateral Arabic checks in Usd al-Ghaba and al-Isti'ab, exact-version checks in the Dar Hajr and Dar al-Jil al-Isabah editions, hash-bound outside evidence, full xhigh adjudication, and deterministic validation are complete. Human review has not begun.",
    })
    presentation = artifact(bundle, "isabah-volume-08-english-review-presentation")
    presentation.update({
        "state": "verified_local",
        "local_path": str(args.presentation).replace("\\", "/"),
        "sha256": sha256(args.presentation),
        "byte_size": args.presentation.stat().st_size,
        "page_count": 491,
        "verification": {
            "generator": "firstlight-research/scripts/translation/render_english_review.py",
            "source_structured_english_sha256": structured["sha256"],
            "operator_approval": "not_approved",
        },
        "notes": "Generated bilingual reading/review surface with names and explicit unresolved items; edit JSONL and regenerate.",
    })
    name_artifact_id = "isabah-volume-08-name-review"
    name_artifact = next((item for item in bundle["artifacts"] if item["artifact_id"] == name_artifact_id), None)
    name_payload = {
        "artifact_id": name_artifact_id,
        "role": "quality_evidence",
        "language": "en",
        "format": "application/json",
        "edition_relationship": "derived_from_canonical",
        "state": "verified_local",
        "source_platform": "FirstLight",
        "source_url": None,
        "local_path": str(args.name_review).replace("\\", "/"),
        "sha256": sha256(args.name_review),
        "byte_size": args.name_review.stat().st_size,
        "page_count": 491,
        "provider_ids": {},
        "derived_from": ["isabah-volume-08-structured-english"],
        "coverage": "Volume 8 machine-extracted name candidates and exact English mentions",
        "verification": {
            "candidate_count": len(names.get("candidates") or []),
            "mention_count": len(names.get("mentions") or []),
            "operator_reviewed_candidates": sum(1 for item in names.get("candidates") or [] if item.get("review") is not None),
            "source_structured_english_sha256": names["source"]["sha256"],
        },
        "notes": "Durable JSON review authority generated from validated English name mappings; machine candidates remain unapproved and ELIXR is a rebuildable projection.",
    }
    if name_artifact is None:
        bundle["artifacts"].append(name_payload)
    else:
        name_artifact.clear()
        name_artifact.update(name_payload)

    bundle["workflow"]["source_text_alignment"] = {
        "state": "complete",
        "evidence": "All 491 substantive Volume 8 scan pages are aligned: 490 canonical Usul reader pages and one canonical facsimile transcription; eight exact facsimile corrections are provenance-recorded; heading comparison passed with zero mismatches; all 1,550 entries are continuous from 10759 through 12308.",
    }
    bundle["workflow"]["english_draft"] = {
        "state": "complete",
        "evidence": "All 491 substantive pages completed blind Codex translation, independent criticism, required Urdu and collateral Arabic witness checks, adjudication, and deterministic QA.",
    }
    bundle["workflow"]["english_presentation"] = {
        "state": "complete",
        "evidence": "The bilingual Volume 8 presentation was regenerated from the machine-validated structured English and exposes all unresolved items.",
    }
    bundle["workflow"]["english_approval"] = {
        "state": "review_required",
        "evidence": f"Autonomous checks are exhausted for Volume 8; zero units are operator-approved and {unresolved} explicitly unresolved items are queued for human judgment.",
    }
    bundle["quality"]["source_text"].update({
        "state": "pass_volume_08",
        "full_capture": "4398_of_4406_reader_chunks; eight provider URLs returned 404",
        "facsimile_alignment": "pass_volume_08_491_of_491",
        "volume_08_heading_mismatches": 0,
    })
    bundle["quality"]["translation"] = {
        "state": "ready_for_human_review_volume_08",
        "volume_8_substantive_coverage": 1.0,
        "approved_units": 0,
        "blind_translation_pages": 491,
        "independent_critic_pages": 491,
        "critic_issues": critic_issues,
        "adjudication_pages": len(readiness.get("adjudication_required_pages") or []),
        "witness_pages": len(readiness.get("witness_required_pages") or []),
        "witness_method": "image-aware Urdu, exact-heading Usul searches in Usd al-Ghaba and al-Isti'ab, and concern-scoped hash-bound edition/parallel evidence",
        "collateral_arabic_witnesses": 2,
        "supplemental_witness_evidence": len(supplemental_evidence),
        "collateral_retrieval": readiness.get("witness_evidence") or {},
        "unresolved_items": unresolved,
        "deterministic_validation": "pass",
    }
    bundle["quality"]["structure"] = {
        "state": "pass_volume_08",
        "page_boundaries_preserved": True,
        "entry_number_validation": "pass",
        "footnote_label_validation": "pass",
        "printed_page_fields_present": True,
        "name_consistency_reported": True,
        "name_review_json": "ready_for_operator_review",
    }
    bundle["quality"]["human_review"] = {
        "state": "ready_not_started",
        "approved_units": 0,
        "explicit_unresolved_items": unresolved,
        "required_focus": [
            "explicit unresolved passages",
            "names and stable identities",
            "isnads",
            "entry numbering",
            "negation and dates",
            "quoted evidence",
            "editorial apparatus",
        ],
    }
    bundle["next_actions"] = [
        "Open the generated bilingual Volume 8 presentation for final human review.",
        "Resolve the explicitly queued uncertainties and write decisions back to structured JSONL.",
        "Review and merge machine-extracted name candidates in the durable JSON authority.",
        "Repeat the proven alignment and translation workflow for Volumes 1-7.",
    ]

    atomic_json(args.bundle, bundle)
    print(json.dumps({
        "bundle": str(args.bundle),
        "structured_english_sha256": structured["sha256"],
        "presentation_sha256": presentation["sha256"],
        "unresolved_items": unresolved,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Atomically open the human-review gate after every Volume 8 artifact validates."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def jsonl_count(path: Path) -> int:
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def normalized_name(value: str) -> str:
    value = value.replace("’", "'").replace("‘", "'").replace("`", "'")
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip().casefold()


def validate_name_review(names: dict, units: list[dict]) -> None:
    candidates = names.get("candidates") or []
    mentions = names.get("mentions") or []
    candidate_ids = [str(item.get("candidate_id") or "") for item in candidates]
    mention_ids = [str(item.get("mention_id") or "") for item in mentions]
    if not all(candidate_ids) or len(candidate_ids) != len(set(candidate_ids)):
        raise RuntimeError("Name-review candidate IDs are missing or duplicated")
    if not all(mention_ids) or len(mention_ids) != len(set(mention_ids)):
        raise RuntimeError("Name-review mention IDs are missing or duplicated")

    candidate_by_id = {item["candidate_id"]: item for item in candidates}
    mention_by_id = {item["mention_id"]: item for item in mentions}
    referenced_mentions: list[str] = []
    for candidate in candidates:
        for mention_id in candidate.get("mention_ids") or []:
            referenced_mentions.append(mention_id)
            mention = mention_by_id.get(mention_id)
            if mention is None:
                raise RuntimeError(f"Name-review candidate has a dangling mention: {mention_id}")
            if mention.get("candidate_id") != candidate["candidate_id"]:
                raise RuntimeError(f"Name-review mention is linked to the wrong candidate: {mention_id}")
    if len(referenced_mentions) != len(set(referenced_mentions)):
        raise RuntimeError("Name-review mention is referenced by multiple candidates")
    if set(referenced_mentions) != set(mention_by_id):
        raise RuntimeError("Name-review contains unreferenced mentions")
    if any(item.get("candidate_id") not in candidate_by_id for item in mentions):
        raise RuntimeError("Name-review mention refers to an unknown candidate")

    expected_forms = {
        normalized_name(mapping.get("english") or "")
        for unit in units
        for mapping in (unit.get("target", {}).get("names") or [])
        if str(mapping.get("english") or "").strip()
    }
    candidate_forms = {str(item.get("normalized_form") or "") for item in candidates}
    missing_forms = sorted(expected_forms - candidate_forms)
    if missing_forms:
        raise RuntimeError(f"Name-review is missing adjudicated name mappings: {missing_forms[:10]}")


def unresolved_passage_report(units: list[dict]) -> list[dict]:
    return [
        {
            "scan_page": int(unit["source"]["scan_page"]),
            "printed_page": unit["source"].get("printed_page"),
            "reader_url": unit["source"].get("reader_url"),
            "unit_id": unit["unit_id"],
            "items": unit["target"].get("unresolved") or [],
        }
        for unit in units
        if unit.get("target", {}).get("unresolved")
    ]


def presentation_source_marker(source_sha256: str) -> str:
    return f'<meta name="firstlight-source-sha256" content="{source_sha256}">'


def validate(
    *, candidate_path: Path, units_path: Path, presentation_path: Path,
    name_review_path: Path, name_index_path: Path, bundle_path: Path,
    aligned_source_path: Path,
) -> dict:
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    if candidate.get("schema") != "firstlight.translation-machine-readiness.v1":
        raise RuntimeError("Candidate readiness schema is incompatible")
    if not candidate.get("ready_for_human_review") or candidate.get("errors"):
        raise RuntimeError("Machine QA candidate has not passed")
    entry_audit = candidate.get("entry_sequence_audit") or {}
    if (
        not entry_audit.get("pass")
        or entry_audit.get("expected_first") != 10759
        or entry_audit.get("expected_last") != 12308
        or entry_audit.get("observed_count") != 1550
    ):
        raise RuntimeError("Machine QA did not pass the canonical entry sequence")
    units = read_jsonl(units_path)
    if int(candidate.get("expected_pages", 0)) != 491 or len(units) != 491:
        raise RuntimeError("Validated English does not cover all 491 pages")
    observed_scans = [int((unit.get("source") or {}).get("scan_page", -1)) for unit in units]
    if observed_scans != list(range(4, 495)):
        raise RuntimeError("Validated English scan order is not exactly 4-494")
    invalid_units = [
        scan
        for scan, unit in zip(observed_scans, units)
        if (
            unit.get("schema") != "firstlight.reviewable-translation-unit.v1"
            or (unit.get("target") or {}).get("state")
            not in {"machine_validated_unreviewed", "machine_validated_unresolved"}
            or (unit.get("review") or {}).get("state") != "unreviewed"
        )
    ]
    if invalid_units:
        raise RuntimeError(
            f"Validated English contains invalid review states on {len(invalid_units)} pages"
        )
    if candidate.get("adjudication_required_pages") != list(range(4, 495)):
        raise RuntimeError("Machine QA did not require full-volume xhigh adjudication")
    witness_evidence = candidate.get("witness_evidence") or {}
    if witness_evidence.get("retrieval_incomplete") != 0:
        raise RuntimeError("Machine QA retains incomplete collateral witness evidence")
    expected_lineage = {
        "method": "codex_blind_translation_with_independent_critique_multilingual_witness_and_full_adjudication",
        "blind_model": "gpt-5.6-sol",
        "blind_reasoning_effort": "high",
        "critic_model": "gpt-5.6-sol",
        "critic_reasoning_effort": "high",
        "adjudication_model": "gpt-5.6-sol",
        "adjudication_reasoning_effort": "xhigh",
    }
    lineage_failures = []
    for offset, unit in enumerate(units, start=4):
        lineage = unit.get("translation") or {}
        mismatches = {
            key: lineage.get(key)
            for key, expected in expected_lineage.items()
            if lineage.get(key) != expected
        }
        if mismatches:
            lineage_failures.append({
                "scan_page": (unit.get("source") or {}).get("scan_page", offset),
                "mismatches": mismatches,
            })
    if lineage_failures:
        raise RuntimeError(
            f"Validated English has invalid Codex model lineage on {len(lineage_failures)} pages"
        )
    unresolved_passages = unresolved_passage_report(units)
    unresolved_count = sum(len(item["items"]) for item in unresolved_passages)
    if candidate.get("unresolved_item_count") != unresolved_count:
        raise RuntimeError("Machine QA unresolved-item count is stale")
    if candidate.get("unresolved_passages") != unresolved_passages:
        raise RuntimeError("Machine QA unresolved-passage report is stale")
    units_sha = sha256(units_path)
    if candidate.get("output_sha256") != units_sha:
        raise RuntimeError("Validated English hash does not match machine QA")

    presentation = presentation_path.read_text(encoding="utf-8")
    if presentation.count('<article class="page"') != 491:
        raise RuntimeError("Review presentation does not contain 491 page articles")
    if presentation_source_marker(units_sha) not in presentation:
        raise RuntimeError("Review presentation is stale relative to validated English")

    names = json.loads(name_review_path.read_text(encoding="utf-8"))
    if names.get("schema") != "firstlight.name-review.v1" or names.get("work_id") != candidate.get("work_id"):
        raise RuntimeError("Name-review document is incompatible")
    if names.get("source", {}).get("sha256") != units_sha:
        raise RuntimeError("Name-review document was not built from the validated English")
    extraction = names.get("extraction") or {}
    if extraction.get("candidate_count") != len(names.get("candidates") or []):
        raise RuntimeError("Name-review candidate count is inconsistent")
    if extraction.get("mention_count") != len(names.get("mentions") or []):
        raise RuntimeError("Name-review mention count is inconsistent")
    validate_name_review(names, units)
    index = json.loads(name_index_path.read_text(encoding="utf-8"))
    indexed_path = (index.get("works") or {}).get(candidate["work_id"])
    if not indexed_path or Path(str(indexed_path)).name != name_review_path.name:
        raise RuntimeError("Name-review index does not expose the validated work")

    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    by_id = {item["artifact_id"]: item for item in bundle.get("artifacts") or []}
    required_textual_witnesses = {
        "isabah-usul-usd-al-ghaba-collateral": "different_work",
        "isabah-usul-istiab-collateral": "different_work",
        "isabah-usul-dar-hajr-alternative-edition": "different_edition",
        "isabah-usul-dar-jil-alternative-edition": "different_edition",
    }
    for artifact_id, relationship in sorted(required_textual_witnesses.items()):
        item = by_id.get(artifact_id) or {}
        if (
            item.get("role") != "textual_witness"
            or item.get("edition_relationship") != relationship
            or item.get("state") != "verified_remote"
        ):
            raise RuntimeError(f"Source bundle textual witness is missing or invalid: {artifact_id}")
    aligned_artifact = by_id.get("isabah-volume-08-aligned-arabic") or {}
    candidate_source_sha = (candidate.get("inputs") or {}).get("aligned_source_sha256")
    if not candidate_source_sha or aligned_artifact.get("sha256") != candidate_source_sha:
        raise RuntimeError("Source bundle aligned Arabic is stale relative to machine QA")
    if sha256(aligned_source_path) != candidate_source_sha:
        raise RuntimeError("Aligned Arabic on disk is stale relative to machine QA")
    bundle_entry_audit = (
        (aligned_artifact.get("verification") or {}).get("entry_sequence_audit") or {}
    )
    if not bundle_entry_audit.get("pass"):
        raise RuntimeError("Source bundle lacks a passing canonical entry audit")
    if candidate.get("witness_required_pages"):
        observed_works = set((candidate.get("witness_evidence") or {}).get("works") or [])
        required_works = {
            "ibn_al_athir_usd_al_ghaba_v1",
            "ibn_abd_al_barr_istiab_v1",
            "ibn_hajar_isabah_dar_hajr_v1",
            "ibn_hajar_isabah_dar_jil_v1",
        }
        if not required_works.issubset(observed_works):
            raise RuntimeError("Machine QA did not record all required textual witness searches")
    supplemental_artifact = by_id.get("isabah-volume-08-supplemental-witness-evidence") or {}
    supplemental_verification = supplemental_artifact.get("verification") or {}
    if (
        supplemental_artifact.get("role") != "quality_evidence"
        or supplemental_artifact.get("language") != "mul"
        or supplemental_artifact.get("state") != "verified_local"
        or supplemental_verification.get("evidence_count")
        != int(witness_evidence.get("supplemental_records", 0))
        or supplemental_verification.get("scan_pages")
        != list(witness_evidence.get("supplemental_scans") or [])
    ):
        raise RuntimeError("Source bundle supplemental witness evidence is stale or invalid")
    if by_id.get("isabah-volume-08-structured-english", {}).get("sha256") != units_sha:
        raise RuntimeError("Source bundle structured-English hash is stale")
    presentation_sha = sha256(presentation_path)
    if by_id.get("isabah-volume-08-english-review-presentation", {}).get("sha256") != presentation_sha:
        raise RuntimeError("Source bundle presentation hash is stale")
    names_sha = sha256(name_review_path)
    if by_id.get("isabah-volume-08-name-review", {}).get("sha256") != names_sha:
        raise RuntimeError("Source bundle name-review hash is stale")

    published = dict(candidate)
    published["published_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    published["pipeline_complete"] = True
    published["pipeline_artifacts"] = {
        "structured_english_sha256": units_sha,
        "review_presentation_sha256": presentation_sha,
        "name_review_sha256": names_sha,
        "name_candidates": extraction.get("candidate_count", 0),
        "name_mentions": extraction.get("mention_count", 0),
        "source_bundle_sha256": sha256(bundle_path),
        "textual_witnesses": len(required_textual_witnesses),
        "collateral_witnesses": 2,
        "alternative_editions": 2,
        "supplemental_witness_records": int(witness_evidence.get("supplemental_records", 0)),
    }
    return published


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + ".tmp")
    pending.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pending.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--units", required=True, type=Path)
    parser.add_argument("--presentation", required=True, type=Path)
    parser.add_argument("--name-review", required=True, type=Path)
    parser.add_argument("--name-index", required=True, type=Path)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--aligned-source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    published = validate(
        candidate_path=args.candidate.resolve(), units_path=args.units.resolve(),
        presentation_path=args.presentation.resolve(), name_review_path=args.name_review.resolve(),
        name_index_path=args.name_index.resolve(), bundle_path=args.bundle.resolve(),
        aligned_source_path=args.aligned_source.resolve(),
    )
    atomic_json(args.output.resolve(), published)
    print(json.dumps({"ready_for_human_review": True, "output": str(args.output), **published["pipeline_artifacts"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

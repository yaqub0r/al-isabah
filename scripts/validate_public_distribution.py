#!/usr/bin/env python3
"""Independently validate a v2 public distribution and exact release closure."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from public_boundary import (
    boundary_errors,
    exact_keys,
    safe_error,
    sha256_file,
    sha256_text_file,
    summarize,
)
from validate_public_proposal import KEYS as PROPOSAL_KEYS, RECORD_KEYS
from validate_current_release_closure import (
    CURRENT_CLOSURE,
    validate as validate_closure,
)


ROOT = Path(__file__).resolve().parents[1]
COMMIT = re.compile(r"^[a-f0-9]{40}$")
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,199}$")
UTC_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")
FULL_BOOK_CLOSURE_ID = "issue-0100-full-book-public-working-closure-v1"
SUPPORTED_CLOSURES = (
    ROOT / "compliance/publication/issue-0026.release-closure.v1.json",
    ROOT / "compliance/publication/issue-0053.release-closure.v1.json",
    ROOT / "compliance/publication/issue-0070.release-closure.v1.json",
    CURRENT_CLOSURE,
)
MANIFEST_KEYS = {"schemaVersion", "distributionId", "publicationStatus", "canonicalPromotion", "work", "repository", "generatedAt", "rights", "packets", "authorities", "counts", "duplicatePrintedEntryNumbers", "files", "releaseClosure"}
COUNT_KEYS = {"entries", "machinePassed", "needsAttention", "humanReviewed"}
WORK_KEYS = {"id", "titleArabic", "titleEnglish"}
REPOSITORY_KEYS = {"url", "commit"}
RIGHTS_MATRIX_PATH = "compliance/rights-matrix.al-isabah.v1.json"


def proposal_bindings(closure: dict[str, Any]) -> list[dict[str, Any]]:
    proposals = closure.get("proposals")
    if isinstance(proposals, list):
        return proposals
    proposal = closure.get("publicProposal")
    review = closure.get("publicReview")
    projection = closure.get("projection")
    if not all(isinstance(item, dict) for item in (proposal, review, projection)):
        return []
    proposal_document = json.loads((ROOT / proposal["path"]).read_text(encoding="utf-8"))
    return [
        {
            "proposalId": proposal_document["proposalId"],
            "publicProposal": proposal,
            "publicReview": review,
            "projection": projection,
        }
    ]


def expected_manifest_rights(closure: dict[str, Any]) -> dict[str, Any] | None:
    binding = closure.get("rights")
    if not isinstance(binding, dict) or binding.get("path") != RIGHTS_MATRIX_PATH:
        return None
    path = ROOT / RIGHTS_MATRIX_PATH
    if not path.is_file() or binding.get("sha256") != sha256_text_file(path):
        return None
    rights_matrix = json.loads(path.read_text(encoding="utf-8"))
    license_record = rights_matrix["public_content_license"]
    if (
        binding.get("matrixId") != rights_matrix.get("matrix_id")
        or binding.get("license") != license_record.get("spdx")
    ):
        return None
    return {
        "matrixId": rights_matrix["matrix_id"],
        "license": {
            "spdx": license_record["spdx"],
            "url": license_record["url"],
        },
        "softwareLicenseGranted": license_record["software_license_granted"],
        "attribution": rights_matrix["attribution"],
        "excludedMaterial": rights_matrix["exclusions"],
    }


def expected_manifest_authorities(
    closure: dict[str, Any], proposals: list[dict[str, Any]]
) -> list[dict[str, Any]] | None:
    authority_map: dict[str, dict[str, Any]] = {}
    for item in proposals:
        proposal_binding = item.get("publicProposal")
        if not isinstance(proposal_binding, dict):
            return None
        relative = proposal_binding.get("path")
        if not isinstance(relative, str):
            return None
        path = ROOT / relative
        if (
            not path.is_file()
            or proposal_binding.get("sha256") != sha256_file(path)
        ):
            return None
        proposal = json.loads(path.read_text(encoding="utf-8"))
        authority = proposal.get("sourceAuthority")
        if not isinstance(authority, dict) or not isinstance(
            authority.get("sourceId"), str
        ):
            return None
        previous = authority_map.get(authority["sourceId"])
        if previous is not None and previous != authority:
            return None
        authority_map[authority["sourceId"]] = authority

    authorities = [authority_map[key] for key in sorted(authority_map)]
    closure_authorities = closure.get("sourceAuthorities")
    if not isinstance(closure_authorities, list):
        singular = closure.get("sourceAuthority")
        if not isinstance(singular, dict):
            return None
        closure_authorities = [singular]
    flattened = []
    for authority in authorities:
        license_record = authority.get("license")
        if not isinstance(license_record, dict):
            return None
        flattened.append(
            {
                "sourceId": authority["sourceId"],
                "commit": authority.get("commit"),
                "artifactSha256": authority.get("sha256"),
                "license": license_record.get("spdx"),
                "attributionRequired": bool(license_record.get("attribution")),
            }
        )
    if closure_authorities != flattened:
        return None
    return authorities


def record_key_errors(record: dict[str, Any], base: str) -> list[str]:
    allowed_keys = RECORD_KEYS | ({"bodyState"} if "bodyState" in record else set())
    errors = exact_keys(record, allowed_keys, base)
    if "bodyState" in record and (
        record.get("bodyState") != "title-only"
        or record.get("arabic") != ""
        or record.get("english") != ""
    ):
        errors.append(safe_error(f"{base}.bodyState", "consumer-contract-mismatch"))
    if (
        record.get("arabic") == ""
        and record.get("english") == ""
        and record.get("bodyState") != "title-only"
    ):
        errors.append(safe_error(f"{base}.bodyState", "missing-field"))
    errors.extend(exact_keys(record.get("title"), PROPOSAL_KEYS["title"], f"{base}.title"))
    errors.extend(exact_keys(record.get("source"), PROPOSAL_KEYS["source"], f"{base}.source"))
    errors.extend(exact_keys(record.get("policy"), PROPOSAL_KEYS["policy"], f"{base}.policy"))
    errors.extend(exact_keys(record.get("source", {}).get("license"), PROPOSAL_KEYS["license"], f"{base}.source.license"))
    for index, page in enumerate(record.get("pages", [])):
        errors.extend(exact_keys(page, PROPOSAL_KEYS["page"], f"{base}.pages[{index}]"))
    for index, context in enumerate(record.get("precedingMaterial", [])):
        context_path = f"{base}.precedingMaterial[{index}]"
        errors.extend(exact_keys(context, PROPOSAL_KEYS["context"], context_path))
        errors.extend(exact_keys(context.get("heading"), PROPOSAL_KEYS["heading"], f"{context_path}.heading"))
        for child_index, page in enumerate(context.get("pages", [])):
            errors.extend(exact_keys(page, PROPOSAL_KEYS["page"], f"{context_path}.pages[{child_index}]"))
        for child_index, finding in enumerate(context.get("unresolved", [])):
            errors.extend(exact_keys(finding, PROPOSAL_KEYS["finding"], f"{context_path}.unresolved[{child_index}]"))
    for index, name in enumerate(record.get("names", [])):
        errors.extend(exact_keys(name, PROPOSAL_KEYS["name"], f"{base}.names[{index}]"))
    for index, finding in enumerate(record.get("unresolved", [])):
        errors.extend(exact_keys(finding, PROPOSAL_KEYS["finding"], f"{base}.unresolved[{index}]"))
    for index, formula in enumerate(record.get("formulas", [])):
        errors.extend(exact_keys(formula, PROPOSAL_KEYS["formula"], f"{base}.formulas[{index}]"))
    return errors


def full_book_coverage_errors(
    *,
    ordinals: list[Any],
    unique_id_count: int,
    expected_count: int,
    file_volumes: list[Any],
    volume_three_ordinals: list[Any],
    owned_structural_ids: list[Any],
    inherited_structural_ids: list[Any],
) -> list[str]:
    errors: list[str] = []
    if (
        ordinals != list(range(1, 12304))
        or unique_id_count != 12303
        or expected_count != 12303
    ):
        errors.append(safe_error("$.output.records", "full-book-source-coverage-mismatch"))
    if file_volumes != list(range(1, 9)):
        errors.append(safe_error("$.manifest.files", "volume-inventory-mismatch"))
    if volume_three_ordinals != list(range(3035, 4526)):
        errors.append(safe_error("$.output.records.volume-03", "volume-coverage-mismatch"))
    if (
        len(owned_structural_ids) != 1382
        or len(set(owned_structural_ids)) != 1382
        or len(inherited_structural_ids) != 23
        or len(set(inherited_structural_ids)) != 23
    ):
        errors.append(safe_error("$.output.records", "structural-coverage-mismatch"))
    return errors


def validate(root: Path) -> list[str]:
    errors: list[str] = []
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        return [safe_error("$.manifest", "missing-file")]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        return [safe_error(f"$.manifest.line[{getattr(error, 'lineno', 0)}]", "invalid-json")]
    errors.extend(exact_keys(manifest, MANIFEST_KEYS, "$.manifest"))
    errors.extend(exact_keys(manifest.get("counts"), COUNT_KEYS, "$.manifest.counts"))
    errors.extend(exact_keys(manifest.get("work"), WORK_KEYS, "$.manifest.work"))
    errors.extend(
        exact_keys(
            manifest.get("repository"), REPOSITORY_KEYS, "$.manifest.repository"
        )
    )
    errors.extend(boundary_errors(manifest, "$.manifest"))
    if manifest.get("schemaVersion") != "2.0.0" or manifest.get("publicationStatus") != "public-working" or manifest.get("canonicalPromotion") != "blocked":
        errors.append(safe_error("$.manifest", "consumer-contract-mismatch"))
    generated_at = manifest.get("generatedAt")
    if not isinstance(generated_at, str) or not UTC_TIMESTAMP.fullmatch(generated_at):
        errors.append(safe_error("$.manifest.generatedAt", "timestamp-mismatch"))
    else:
        try:
            datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        except ValueError:
            errors.append(safe_error("$.manifest.generatedAt", "timestamp-mismatch"))
    work = manifest.get("work", {})
    if work != {
        "id": "ibn-hajar-al-isabah",
        "titleArabic": "الإصابة في تمييز الصحابة",
        "titleEnglish": "Al-Isabah fi Tamyiz al-Sahabah",
    }:
        errors.append(safe_error("$.manifest.work", "work-mismatch"))
    repository = manifest.get("repository", {})
    if not isinstance(repository, dict):
        repository = {}
    repository_commit = str(repository.get("commit", ""))
    if (
        repository.get("url") != "https://github.com/yaqub0r/al-isabah"
        or not COMMIT.fullmatch(repository_commit)
    ):
        errors.append(safe_error("$.manifest.repository", "repository-mismatch"))
    if manifest.get("distributionId") != (
        f"al-isabah-public-working-{repository_commit[:12]}"
    ):
        errors.append(safe_error("$.manifest.distributionId", "distribution-id-mismatch"))
    closure_copy = root / "release-closure.json"
    if not closure_copy.is_file():
        errors.append(safe_error("$.release-closure", "missing-file"))
        return errors
    try:
        closure = json.loads(closure_copy.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        errors.append(
            safe_error(
                f"$.release-closure.line[{getattr(error, 'lineno', 0)}]",
                "invalid-json",
            )
        )
        return errors
    closure_id = closure.get("closureId")
    supported_closure = next(
        (
            path
            for path in SUPPORTED_CLOSURES
            if json.loads(path.read_text(encoding="utf-8")).get("closureId")
            == closure_id
        ),
        None,
    )
    if (
        supported_closure is None
        or closure_copy.read_bytes() != supported_closure.read_bytes()
    ):
        errors.append(safe_error("$.release-closure", "closure-copy-mismatch"))
        return errors
    closure_binding = manifest.get("releaseClosure", {})
    if closure_binding != {
        "closureId": closure["closureId"],
        "sha256": sha256_file(supported_closure),
    }:
        errors.append(safe_error("$.manifest.releaseClosure", "closure-mismatch"))
    if closure_id == FULL_BOOK_CLOSURE_ID:
        closure_errors = validate_closure(CURRENT_CLOSURE)
        if closure_errors:
            errors.append(safe_error("$.manifest.releaseClosure", "closure-invalid"))
    if manifest.get("schemaVersion") != closure.get("consumerSchemaVersion"):
        errors.append(safe_error("$.manifest.schemaVersion", "consumer-contract-mismatch"))
    proposals = proposal_bindings(closure)
    manifest_authorities = manifest.get("authorities")
    authorities = {
        item.get("sourceId"): item
        for item in manifest_authorities
        if isinstance(item, dict)
    } if isinstance(manifest_authorities, list) else {}
    expected_authorities = expected_manifest_authorities(closure, proposals)
    if expected_authorities is None or manifest_authorities != expected_authorities:
        errors.append(safe_error("$.manifest.authorities", "source-mismatch"))
    expected_rights = expected_manifest_rights(closure)
    if expected_rights is None:
        errors.append(safe_error("$.release-closure.rights", "rights-mismatch"))
    elif manifest.get("rights") != expected_rights:
        errors.append(safe_error("$.manifest.rights", "rights-mismatch"))
    expected_packets = [
        {
            "packetId": item["proposalId"],
            "sha256": item["publicProposal"]["sha256"],
            "entryCount": item["projection"]["entryCount"],
        }
        for item in proposals
    ]
    if manifest.get("packets") != expected_packets:
        errors.append(safe_error("$.manifest.packets", "proposal-set-mismatch"))
    expected_paths: set[str] = set()
    seen: set[str] = set()
    printed: dict[int, list[str]] = {}
    count = 0
    machine_passed = 0
    needs_attention = 0
    human_reviewed = 0
    previous: tuple[int, str] | None = None
    all_records: list[dict[str, Any]] = []
    for item in manifest.get("files", []):
        relative = item.get("path")
        volume = item.get("volume")
        if not isinstance(volume, int) or relative != f"records/volume-{volume:02}.jsonl":
            errors.append(safe_error("$.manifest.files", "output-inventory-mismatch"))
            continue
        expected_paths.add(relative)
        path = root / relative
        if not path.is_file():
            errors.append(safe_error(f"$.output.{relative}", "missing-file"))
            continue
        if item.get("sha256") != sha256_file(path) or item.get("bytes") != path.stat().st_size:
            errors.append(safe_error(f"$.output.{relative}", "output-hash-mismatch"))
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
        if item.get("recordCount") != len(records):
            errors.append(safe_error(f"$.output.{relative}", "record-count-mismatch"))
        for index, record in enumerate(records):
            base = f"$.output.records[{index}]"
            count += 1
            all_records.append(record)
            errors.extend(record_key_errors(record, base))
            errors.extend(boundary_errors(record, base))
            record_id = record.get("id")
            if not isinstance(record_id, str) or not IDENTIFIER.fullmatch(record_id):
                errors.append(safe_error(f"{base}.id", "invalid-stable-id"))
                continue
            if record_id in seen:
                errors.append(safe_error(f"{base}.id", "duplicate-stable-id"))
            seen.add(record_id)
            order = (record.get("sourceOrdinal"), record_id)
            if previous is not None and order <= previous:
                errors.append(safe_error(base, "unstable-order"))
            previous = order
            printed.setdefault(int(record.get("printedEntryNumber", 0)), []).append(record_id)
            if record.get("machineAssessment") == "needs_attention":
                needs_attention += 1
            elif record.get("machineAssessment") != "passed":
                errors.append(safe_error(f"{base}.machineAssessment", "invalid-review-state"))
            if record.get("source", {}).get("authorityId") not in authorities:
                errors.append(safe_error(f"{base}.source.authorityId", "source-mismatch"))
            if record.get("volume") != volume:
                errors.append(safe_error(f"{base}.volume", "volume-shard-mismatch"))
            if record.get("machineAssessment") == "passed":
                machine_passed += 1
            if record.get("humanReview") in {"reviewed", "verified"}:
                human_reviewed += 1
    actual_paths = {path.relative_to(root).as_posix() for path in root.glob("records/*.jsonl")}
    if actual_paths != expected_paths:
        errors.append(safe_error("$.output.records", "output-inventory-mismatch"))
    counts = manifest.get("counts", {})
    expected_count = sum(
        item["projection"]["entryCount"] for item in proposals
    )
    if counts != {
        "entries": count,
        "machinePassed": machine_passed,
        "needsAttention": needs_attention,
        "humanReviewed": human_reviewed,
    } or count != expected_count:
        errors.append(safe_error("$.manifest.counts", "record-count-mismatch"))
    if closure_id == FULL_BOOK_CLOSURE_ID:
        file_volumes = [item.get("volume") for item in manifest.get("files", [])]
        volume_three = [record for record in all_records if record.get("volume") == 3]
        owned_structural = [
            item
            for record in all_records
            for item in record.get("precedingMaterial", [])
            if item.get("kind") != "continued_structural_heading"
        ]
        inherited_structural = [
            item
            for record in all_records
            for item in record.get("precedingMaterial", [])
            if item.get("kind") == "continued_structural_heading"
        ]
        errors.extend(
            full_book_coverage_errors(
                ordinals=[record.get("sourceOrdinal") for record in all_records],
                unique_id_count=len(seen),
                expected_count=expected_count,
                file_volumes=file_volumes,
                volume_three_ordinals=[
                    record.get("sourceOrdinal") for record in volume_three
                ],
                owned_structural_ids=[item.get("id") for item in owned_structural],
                inherited_structural_ids=[
                    item.get("id") for item in inherited_structural
                ],
            )
        )
    declared = {int(item["printedEntryNumber"]): item["recordIds"] for item in manifest.get("duplicatePrintedEntryNumbers", [])}
    actual = {number: ids for number, ids in printed.items() if len(ids) > 1}
    if declared != actual:
        errors.append(safe_error("$.manifest.duplicatePrintedEntryNumbers", "identity-mismatch"))
    expected_inventory = {
        item["path"]: item for item in closure["outputInventory"]
    }
    for relative, item in expected_inventory.items():
        path = root / relative
        if not path.is_file() or sha256_file(path) != item["sha256"] or path.stat().st_size != item["bytes"]:
            errors.append(safe_error(f"$.output.{relative}", "closure-output-mismatch"))
    expected_files = set(expected_inventory) | {"manifest.json", "release-closure.json"}
    actual_files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    }
    if actual_files != expected_files:
        errors.append(safe_error("$.output", "output-inventory-mismatch"))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    errors = validate(args.root.resolve())
    if errors:
        print(summarize(errors))
        for error in errors:
            print(error)
        return 1
    print("Al-Isabah public distribution v2 and exact release closure are valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

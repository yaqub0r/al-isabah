#!/usr/bin/env python3
"""Build and validate the cumulative full-book public-working release closure."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from build_public_review import review as expected_review
from public_boundary import (
    boundary_errors,
    canonical_json,
    safe_error,
    sha256_bytes,
    sha256_file,
    sha256_text_file,
    summarize,
)
from validate_compliance import validate_schema_instance, validate_translation_coverage
from validate_public_proposal import (
    order_sha256,
    records_sha256,
    validate as validate_proposal,
)
from validate_release_closure import CLOSURE as LEGACY_CLOSURE
from validate_release_closure import validate as validate_historical_closure


ROOT = Path(__file__).resolve().parents[1]
CURRENT_CLOSURE = (
    ROOT / "compliance" / "publication" / "issue-0100.release-closure.v1.json"
)
CURRENT_CLOSURE_SHA256 = (
    "42e6d6a092fa8495d9f685ee310de3d2d91a0cba24cde5639651e24cd8d34765"
)
CURRENT_CLOSURE_SCHEMA = ROOT / "schemas" / "current-release-closure.v2.schema.json"
PREVIOUS_CLOSURE = (
    ROOT / "compliance" / "publication" / "issue-0070.release-closure.v1.json"
)
PREVIOUS_CLOSURE_SHA256 = (
    "f7bd1156bb02ac66ad50cb16379e65adeb5710efef63816e1bd6be1d056a9135"
)
PROPOSAL_ROOT = ROOT / "content" / "public-proposals"
REGISTER = ROOT / "compliance" / "source-register.v1.json"
RIGHTS = ROOT / "compliance" / "rights-matrix.al-isabah.v1.json"
PROMOTION = ROOT / "compliance" / "promotions" / "available-data.v3.json"
PROMOTION_SCHEMA = (
    ROOT / "compliance" / "schemas" / "promotion-readiness.v3.schema.json"
)
COVERAGE = ROOT / "compliance" / "translation-coverage.v1.json"
GOVERNANCE_REFERENCE = (
    ROOT / "docs" / "contracts" / "translation-governance-reference.v12.json"
)
ACTIVE_POLICY = ROOT / "compliance" / "policy-binding.v12.json"
CURRENT_DISTRIBUTION_REVIEW_STATUS = (
    "approved-current-public-working-distribution-canonical-promotion-blocked"
)

ADMITTED_SLICES = (
    {"issue": 26, "proposalId": "issue-0026-public-proposal-v1", "scopeId": "volume-01", "volume": 1, "start": 1, "end": 1537, "ownedStructuralSegments": 194, "inheritedStructuralContexts": 0},
    {"issue": 70, "proposalId": "issue-0070-public-proposal-v1", "scopeId": "volume-02", "volume": 2, "start": 1538, "end": 3034, "ownedStructuralSegments": 228, "inheritedStructuralContexts": 4},
    {"issue": 80, "proposalId": "issue-0080-public-proposal-v1", "scopeId": "issue-0080-volume-03-quarter-01", "volume": 3, "start": 3035, "end": 3407, "ownedStructuralSegments": 13, "inheritedStructuralContexts": 3},
    {"issue": 82, "proposalId": "issue-0082-public-proposal-v1", "scopeId": "issue-0082-volume-03-quarter-02", "volume": 3, "start": 3408, "end": 3780, "ownedStructuralSegments": 36, "inheritedStructuralContexts": 1},
    {"issue": 84, "proposalId": "issue-0084-public-proposal-v1", "scopeId": "issue-0084-volume-03-final-half", "volume": 3, "start": 3781, "end": 4525, "ownedStructuralSegments": 135, "inheritedStructuralContexts": 2},
    {"issue": 86, "proposalId": "issue-0086-public-proposal-v1", "scopeId": "issue-0086-volume-04", "volume": 4, "start": 4526, "end": 6158, "ownedStructuralSegments": 34, "inheritedStructuralContexts": 4},
    {"issue": 85, "proposalId": "issue-0085-public-proposal-v1", "scopeId": "issue-0085-volume-05", "volume": 5, "start": 6159, "end": 7762, "ownedStructuralSegments": 197, "inheritedStructuralContexts": 2},
    {"issue": 91, "proposalId": "issue-0091-public-proposal-v1", "scopeId": "issue-0091-volume-06", "volume": 6, "start": 7763, "end": 9484, "ownedStructuralSegments": 205, "inheritedStructuralContexts": 4},
    {"issue": 96, "proposalId": "issue-0096-public-proposal-v1", "scopeId": "issue-0096-volume-07", "volume": 7, "start": 9485, "end": 11424, "ownedStructuralSegments": 201, "inheritedStructuralContexts": 3},
    {"issue": 98, "proposalId": "issue-0098-public-proposal-v1", "scopeId": "issue-0098-volume-08", "volume": 8, "start": 11425, "end": 12303, "ownedStructuralSegments": 139, "inheritedStructuralContexts": 0},
)
AGGREGATE_VOLUMES = {
    1: ("volume-01", 1537), 2: ("volume-02", 1497),
    3: ("volume-03", 1491), 4: ("volume-04", 1633),
    5: ("volume-05", 1604), 6: ("volume-06", 1722),
    7: ("volume-07", 1940), 8: ("volume-08", 879),
}
SUPPRESSED_INHERITED_PROPOSALS = {"issue-0098-public-proposal-v1"}


def _json_object(path: Path, location: str) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None, [safe_error(location, "invalid-json")]
    if not isinstance(value, dict):
        return None, [safe_error(location, "invalid-object")]
    return value, []


def canonical_hash(value: Any) -> str:
    return sha256_bytes(canonical_json(value))


def current_proposal_paths(
    coverage_path: Path = COVERAGE,
    register_path: Path = REGISTER,
) -> tuple[list[Path], list[str]]:
    """Resolve the exact non-overlapping proposal slices admitted by Issue 100."""

    coverage, errors = _json_object(coverage_path, "$.translationCoverage")
    register, register_errors = _json_object(register_path, "$.sourceRegister")
    errors.extend(register_errors)
    if coverage is None or register is None:
        return [], errors
    artifacts = {
        item.get("id"): item
        for item in register.get("artifacts", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    scopes = {
        item.get("scope_id"): item
        for item in coverage.get("scopes", [])
        if isinstance(item, dict) and isinstance(item.get("scope_id"), str)
    }
    if validate_translation_coverage(coverage, artifacts):
        errors.append(safe_error("$.translationCoverage", "coverage-state-mismatch"))

    admitted_ids = {item["proposalId"] for item in ADMITTED_SLICES}
    registered_current_ids = {
        artifact_id
        for artifact_id, artifact in artifacts.items()
        if artifact.get("review_status") == CURRENT_DISTRIBUTION_REVIEW_STATUS
    }
    if registered_current_ids != admitted_ids:
        errors.append(safe_error("$.sourceRegister", "current-proposal-set-mismatch"))
    historical = artifacts.get("issue-0053-public-proposal-v1", {})
    if historical.get("review_status") != "historical-reopened-scope-current-distribution-quarantined":
        errors.append(safe_error("$.sourceRegister.issue-0053", "quarantine-mismatch"))

    for volume, (scope_id, expected_count) in AGGREGATE_VOLUMES.items():
        scope = scopes.get(scope_id, {})
        completion = scope.get("agent_completion", {})
        if (
            scope.get("scope_kind") != "volume"
            or scope.get("volume") != volume
            or scope.get("workflow_conformance") != "current"
            or scope.get("public_working_status") != "available"
            or scope.get("canonical_promotion") != "blocked"
            or completion.get("status") != "agent_complete"
            or completion.get("locked_units") != expected_count
            or completion.get("translated_units") != expected_count
            or completion.get("remaining_agent_units") != 0
        ):
            errors.append(safe_error(f"$.translationCoverage.{scope_id}", "volume-state-mismatch"))

    paths: list[Path] = []
    for item in ADMITTED_SLICES:
        proposal_id = item["proposalId"]
        scope = scopes.get(item["scopeId"], {})
        completion = scope.get("agent_completion", {})
        evidence = completion.get("evidence", {})
        artifact = artifacts.get(proposal_id, {})
        integrity = artifact.get("integrity", {})
        path = PROPOSAL_ROOT / (
            proposal_id.removesuffix("-public-proposal-v1") + ".public-proposal.json"
        )
        if (
            scope.get("public_working_status") != "available"
            or scope.get("canonical_promotion") != "blocked"
            or completion.get("status") != "agent_complete"
            or evidence.get("source_register_artifact") != proposal_id
            or artifact.get("review_status") != CURRENT_DISTRIBUTION_REVIEW_STATUS
            or integrity.get("proposal_sha256") != evidence.get("sha256")
            or not path.is_file()
            or integrity.get("proposal_sha256") != sha256_file(path)
        ):
            errors.append(safe_error(f"$.proposals.{proposal_id}", "proposal-admission-mismatch"))
            continue
        proposal, proposal_errors = _json_object(path, f"$.proposals.{proposal_id}")
        errors.extend(proposal_errors)
        if proposal is None:
            continue
        records = proposal.get("records")
        ordinals = (
            [record.get("sourceOrdinal") for record in records]
            if isinstance(records, list) and all(isinstance(record, dict) for record in records)
            else []
        )
        if (
            proposal.get("proposalId") != proposal_id
            or ordinals != list(range(item["start"], item["end"] + 1))
            or any(record.get("volume") != item["volume"] for record in records or [])
        ):
            errors.append(safe_error(f"$.proposals.{proposal_id}", "slice-coverage-mismatch"))
            continue
        paths.append(path)
    return paths, errors


def public_review_path(proposal_path: Path) -> Path:
    return proposal_path.with_name(
        proposal_path.name.replace(".public-proposal.json", ".public-review.json")
    )


def output_review_path(proposal: dict[str, Any]) -> str:
    issue_id = proposal["proposalId"].removesuffix("-public-proposal-v1")
    return f"reviews/{issue_id}.json"


def file_binding(path: Path) -> dict[str, str]:
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": sha256_file(path)}


def text_file_binding(path: Path) -> dict[str, str]:
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": sha256_text_file(path)}


def policy_binding_path(proposal: dict[str, Any]) -> Path | None:
    expected_sha = proposal.get("policy", {}).get("bindingSha256")
    matches = [
        path
        for path in sorted((ROOT / "compliance").glob("policy-binding.v*.json"))
        if sha256_text_file(path) == expected_sha
    ]
    return matches[0] if len(matches) == 1 else None


def cumulative_record(proposal_id: str, record: dict[str, Any]) -> dict[str, Any]:
    """Return the cumulative display projection without mutating a proposal."""

    if proposal_id not in SUPPRESSED_INHERITED_PROPOSALS:
        return record
    projected = dict(record)
    projected["precedingMaterial"] = [
        item
        for item in record["precedingMaterial"]
        if item.get("kind") != "continued_structural_heading"
    ]
    return projected


def _page_owner(records: list[dict[str, Any]], volume: int, *, first: bool) -> dict[str, Any]:
    page_numbers = [
        page["page"]
        for record in records
        for page in record["pages"]
        if page["volume"] == volume
    ]
    page_number = min(page_numbers) if first else max(page_numbers)
    candidates = [
        record
        for record in records
        if any(
            page["volume"] == volume and page["page"] == page_number
            for page in record["pages"]
        )
    ]
    owner = (
        min(candidates, key=lambda item: item["sourceOrdinal"])
        if first
        else max(candidates, key=lambda item: item["sourceOrdinal"])
    )
    return {"page": page_number, "ownerSourceUnitId": owner["id"]}


def expected() -> tuple[dict[str, Any] | None, list[str]]:
    errors = validate_historical_closure(LEGACY_CLOSURE)
    if not PREVIOUS_CLOSURE.is_file() or sha256_file(PREVIOUS_CLOSURE) != PREVIOUS_CLOSURE_SHA256:
        errors.append(safe_error("$.previousClosure", "previous-closure-mismatch"))
    current_paths, readiness_errors = current_proposal_paths()
    errors.extend(readiness_errors)
    proposals: list[tuple[dict[str, Any], Path, dict[str, Any], Path, bytes, Path]] = []
    for spec, proposal_path in zip(ADMITTED_SLICES, current_paths, strict=False):
        if validate_proposal(proposal_path):
            errors.append(safe_error(f"$.proposals.{proposal_path.name}", "proposal-invalid"))
            continue
        proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
        review_path = public_review_path(proposal_path)
        review_bytes = canonical_json(expected_review(proposal_path))
        policy_path = policy_binding_path(proposal)
        if not review_path.is_file() or review_path.read_bytes() != review_bytes:
            errors.append(safe_error(f"$.proposals.{proposal['proposalId']}.publicReview", "review-projection-mismatch"))
            continue
        if policy_path is None:
            errors.append(safe_error(f"$.proposals.{proposal['proposalId']}.policyBinding", "policy-mismatch"))
            continue
        proposals.append((spec, proposal_path, proposal, review_path, review_bytes, policy_path))
    if errors:
        return None, errors
    if len(proposals) != len(ADMITTED_SLICES):
        return None, [safe_error("$.proposals", "proposal-set-mismatch")]

    raw_records: list[dict[str, Any]] = []
    projected_records: list[dict[str, Any]] = []
    records_by_volume: dict[int, list[dict[str, Any]]] = {}
    proposal_ids_by_volume: dict[int, list[str]] = {}
    proposal_entries: list[dict[str, Any]] = []
    authorities: dict[str, dict[str, Any]] = {}
    review_counts = {"machinePassed": 0, "needsAttention": 0, "humanReviewed": 0, "humanUnreviewed": 0}
    output_inventory: list[dict[str, Any]] = []
    for spec, proposal_path, proposal, review_path, review_bytes, policy_path in proposals:
        records = proposal["records"]
        raw_records.extend(records)
        cumulative = [cumulative_record(proposal["proposalId"], record) for record in records]
        projected_records.extend(cumulative)
        records_by_volume.setdefault(spec["volume"], []).extend(cumulative)
        proposal_ids_by_volume.setdefault(spec["volume"], []).append(proposal["proposalId"])
        proposal_entries.append(
            {
                "proposalId": proposal["proposalId"],
                "slice": {
                    "volume": spec["volume"],
                    "startSourceOrdinal": spec["start"],
                    "endSourceOrdinal": spec["end"],
                    "sourceUnitCount": spec["end"] - spec["start"] + 1,
                    "ownedStructuralSegmentCount": spec["ownedStructuralSegments"],
                    "inheritedDisplayContextCount": spec["inheritedStructuralContexts"],
                },
                "publicProposal": file_binding(proposal_path),
                "publicReview": file_binding(review_path),
                "policyBinding": text_file_binding(policy_path),
                "projection": {
                    "entryCount": len(records),
                    "orderSha256": order_sha256(records),
                    "userFacingSha256": proposal["baseline"]["userFacingSha256"],
                    "recordsSha256": records_sha256(records),
                },
            }
        )
        authority = proposal["sourceAuthority"]
        authorities[authority["sourceId"]] = {
            "sourceId": authority["sourceId"],
            "commit": authority["commit"],
            "artifactSha256": authority["sha256"],
            "license": authority["license"]["spdx"],
            "attributionRequired": True,
        }
        for key in review_counts:
            review_counts[key] += proposal["review"][key]
        output_inventory.append(
            {"path": output_review_path(proposal), "sha256": sha256_bytes(review_bytes), "bytes": len(review_bytes), "recordCount": 1}
        )

    if [record["sourceOrdinal"] for record in raw_records] != list(range(1, 12304)) or len({record["id"] for record in raw_records}) != 12303:
        return None, [safe_error("$.sourceUnitCoverage", "source-unit-coverage-mismatch")]

    volume_inventory: list[dict[str, Any]] = []
    for volume in range(1, 9):
        records = sorted(records_by_volume.get(volume, []), key=lambda item: (item["sourceOrdinal"], item["id"]))
        record_bytes = b"".join(canonical_json(item) for item in records)
        relative = f"records/volume-{volume:02}.jsonl"
        output_inventory.append({"path": relative, "sha256": sha256_bytes(record_bytes), "bytes": len(record_bytes), "recordCount": len(records)})
        volume_inventory.append(
            {
                "volume": volume,
                "proposalIds": proposal_ids_by_volume[volume],
                "outputPath": relative,
                "recordCount": len(records),
                "startSourceOrdinal": records[0]["sourceOrdinal"],
                "endSourceOrdinal": records[-1]["sourceOrdinal"],
                "firstSourceUnitId": records[0]["id"],
                "lastSourceUnitId": records[-1]["id"],
                "firstPage": _page_owner(projected_records, volume, first=True),
                "lastPage": _page_owner(projected_records, volume, first=False),
            }
        )

    owned = [
        {"sourceUnitId": record["id"], "structuralId": item["id"]}
        for record in raw_records
        for item in record["precedingMaterial"]
        if item["kind"] != "continued_structural_heading"
    ]
    inherited = [
        {"sourceUnitId": record["id"], "displayContextId": item["id"]}
        for record in projected_records
        for item in record["precedingMaterial"]
        if item["kind"] == "continued_structural_heading"
    ]
    raw_inherited_count = sum(
        item["kind"] == "continued_structural_heading"
        for record in raw_records
        for item in record["precedingMaterial"]
    )
    if (
        len(owned) != 1382
        or len({item["structuralId"] for item in owned}) != 1382
        or len(inherited) != 23
        or len({item["displayContextId"] for item in inherited}) != 23
        or raw_inherited_count - len(inherited) != 3
    ):
        return None, [safe_error("$.structuralCoverage", "structural-coverage-mismatch")]

    front_material = projected_records[0]["precedingMaterial"]
    terminal_material = projected_records[-1]["precedingMaterial"]
    rights = json.loads(RIGHTS.read_text(encoding="utf-8"))
    promotion = json.loads(PROMOTION.read_text(encoding="utf-8"))
    if validate_schema_instance(
        promotion, json.loads(PROMOTION_SCHEMA.read_text(encoding="utf-8"))
    ):
        return None, [safe_error("$.promotion", "promotion-decision-invalid")]
    promotion_release = promotion.get("public_working_release", {})
    if (
        promotion_release.get("status") != "approved-controlled-release"
        or promotion_release.get("eligible") is not True
        or promotion_release.get("canonical_promotion") != "blocked"
        or promotion.get("canonical_promotion", {}).get("status") != "blocked"
    ):
        return None, [safe_error("$.promotion", "promotion-decision-invalid")]
    closure = {
        "schemaVersion": "2.0.0",
        "closureId": "issue-0100-full-book-public-working-closure-v1",
        "issue": "https://github.com/yaqub0r/al-isabah/issues/100",
        "publicationStatus": "public-working",
        "canonicalPromotion": "blocked",
        "consumerSchemaVersion": "2.0.0",
        "proposals": proposal_entries,
        "sourceAuthorities": [authorities[key] for key in sorted(authorities)],
        "sourceRegister": text_file_binding(REGISTER),
        "translationCoverage": text_file_binding(COVERAGE),
        "governance": {"translationGovernanceReference": text_file_binding(GOVERNANCE_REFERENCE), "policyBinding": text_file_binding(ACTIVE_POLICY)},
        "rights": {
            "path": "compliance/rights-matrix.al-isabah.v1.json",
            "sha256": sha256_text_file(RIGHTS),
            "matrixId": rights["matrix_id"],
            "license": rights["public_content_license"]["spdx"],
            "exclusionsSha256": canonical_hash(rights["exclusions"]),
            "publicationDecisionSha256": canonical_hash(rights["publication_decision"]),
            "publicBoundaryDecisionSha256": canonical_hash(rights["public_boundary_decision"]),
            "followUpReviewSha256": canonical_hash(rights["follow_up_review"]),
        },
        "promotion": {
            "path": "compliance/promotions/available-data.v3.json",
            "sha256": sha256_text_file(PROMOTION),
            "manifestId": promotion["manifest_id"],
            "status": promotion_release["status"],
            "canonicalPromotion": promotion["canonical_promotion"]["status"],
        },
        "previousClosure": {**file_binding(PREVIOUS_CLOSURE), "closureId": "issue-0070-current-public-working-closure-v1"},
        "sourceUnitCoverage": {"sourceUnitCount": 12303, "firstSourceOrdinal": 1, "lastSourceOrdinal": 12303, "uniqueSourceUnitIdCount": 12303, "identityOrderSha256": order_sha256(raw_records)},
        "structuralCoverage": {
            "ownedStructuralSegmentCount": len(owned),
            "ownedStructuralIdsSha256": canonical_hash(owned),
            "inheritedDisplayContextCount": len(inherited),
            "inheritedDisplayContextIdsSha256": canonical_hash(inherited),
            "displayStructuralItemCount": len(owned) + len(inherited),
            "suppressedAdjacentRestatementCount": raw_inherited_count - len(inherited),
            "frontMaterial": {"ownerSourceUnitId": projected_records[0]["id"], "structuralItemCount": len(front_material), "structuralIdsSha256": canonical_hash([item["id"] for item in front_material])},
            "terminalMaterial": {"ownerSourceUnitId": projected_records[-1]["id"], "structuralItemCount": len(terminal_material), "structuralIdsSha256": canonical_hash([item["id"] for item in terminal_material]), "unownedTerminalMaterialCount": 0},
        },
        "volumeInventory": volume_inventory,
        "contentIntegrity": {
            "titleBodySha256": canonical_hash([{"id": record["id"], "title": record["title"], "arabic": record["arabic"], "english": record["english"]} for record in projected_records]),
            "formulaOccurrenceCount": sum(len(record["formulas"]) for record in projected_records),
            "formulaOccurrencesSha256": canonical_hash([{"id": record["id"], "formulas": record["formulas"]} for record in projected_records]),
            "nameMentionCount": sum(len(record["names"]) for record in projected_records),
            "nameMentionsSha256": canonical_hash([{"id": record["id"], "names": record["names"]} for record in projected_records]),
            "unresolvedAndReviewSha256": canonical_hash([{"id": record["id"], "machineAssessment": record["machineAssessment"], "unresolved": record["unresolved"], "humanReview": record["humanReview"]} for record in projected_records]),
        },
        "reviewDisclosure": {**review_counts, "managementState": "ongoing-nonterminal", "coverageAffectsEligibility": False, "terminalCompletionClaim": False},
        "supersededInputs": [
            {"id": "issue-0053-public-proposal-v1", "recordCount": 1497, "sha256": sha256_file(PROPOSAL_ROOT / "issue-0053.public-proposal.json"), "replacement": "issue-0070-public-proposal-v1", "decision": "excluded-superseded-public-proposal"},
            {"id": "legacy-volume-08-private-provisional", "recordCount": 1550, "replacement": "issue-0098-public-proposal-v1", "decision": "excluded-nonpublic-historical-evidence"},
        ],
        "publicationDecision": {
            "decision": "approved-for-controlled-public-working-release",
            "automaticPushPublication": False,
            "operation": "manual-dispatch-after-protected-merge",
            "immutableReleaseRequired": True,
            "commitAddressedTagPattern": "public-working-{repositoryCommit}",
            "assetNamePattern": "al-isabah-public-distribution-{repositoryCommit}.zip",
            "checksumAssetNamePattern": "al-isabah-public-distribution-{repositoryCommit}.zip.sha256",
            "previousReleaseRetainedForRollback": True,
        },
        "outputInventory": sorted(output_inventory, key=lambda item: item["path"]),
    }
    return closure, []


def validate(path: Path = CURRENT_CLOSURE) -> list[str]:
    if not path.is_file() or sha256_file(path) != CURRENT_CLOSURE_SHA256:
        return [safe_error("$", "current-closure-mismatch")]
    expected_closure, errors = expected()
    if errors:
        return errors
    try:
        closure = json.loads(path.read_text(encoding="utf-8"))
        schema = json.loads(CURRENT_CLOSURE_SCHEMA.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return [safe_error(f"$.line[{getattr(error, 'lineno', 0)}]", "invalid-json")]
    if validate_schema_instance(closure, schema):
        errors.append(safe_error("$", "closure-schema-mismatch"))
    errors.extend(boundary_errors(closure))
    if closure != expected_closure:
        errors.append(safe_error("$", "current-closure-mismatch"))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", type=Path, default=CURRENT_CLOSURE)
    parser.add_argument("--write", action="store_true", help="write the deterministic expected closure before validating it")
    args = parser.parse_args()
    path = args.path.resolve()
    if args.write:
        closure, errors = expected()
        if errors or closure is None:
            print(summarize(errors))
            for error in errors:
                print(error)
            return 1
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_bytes(canonical_json(closure))
        temporary.replace(path)
        print(f"Wrote deterministic current closure: sha256={sha256_file(path)}")
        return 0
    errors = validate(path)
    if errors:
        print(summarize(errors))
        for error in errors:
            print(error)
        return 1
    print(f"Current release closure valid: sha256={sha256_file(path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Validate the cumulative public-working distribution closure."""

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
from validate_public_proposal import (
    order_sha256,
    records_sha256,
    validate as validate_proposal,
)
from validate_release_closure import CLOSURE as LEGACY_CLOSURE
from validate_release_closure import validate as validate_historical_closure
from validate_compliance import validate_translation_coverage


ROOT = Path(__file__).resolve().parents[1]
CURRENT_CLOSURE = (
    ROOT / "compliance" / "publication" / "issue-0070.release-closure.v1.json"
)
CURRENT_CLOSURE_SHA256 = (
    "f7bd1156bb02ac66ad50cb16379e65adeb5710efef63816e1bd6be1d056a9135"
)
HISTORICAL_CLOSURE = (
    ROOT / "compliance" / "publication" / "issue-0053.release-closure.v1.json"
)
HISTORICAL_CLOSURE_SHA256 = (
    "64d41b0752b2de3d11a944d440c3816ab04313c512e2c9c74c2a1aa03981e081"
)
PROPOSAL_ROOT = ROOT / "content" / "public-proposals"
REGISTER = ROOT / "compliance" / "source-register.v1.json"
RIGHTS = ROOT / "compliance" / "rights-matrix.al-isabah.v1.json"
PROMOTION = ROOT / "compliance" / "promotions" / "available-data.v1.json"
COVERAGE = ROOT / "compliance" / "translation-coverage.v1.json"
CURRENT_DISTRIBUTION_REVIEW_STATUS = (
    "approved-current-public-working-distribution-canonical-promotion-blocked"
)
CURRENT_CLOSURE_SOURCE_REGISTER = {
    "path": "compliance/source-register.v1.json",
    "sha256": "5977720da752e04e523b0ac165b6368aff58be43efc93540ddd5f89b2f0c15e5",
}
CURRENT_CLOSURE_TRANSLATION_COVERAGE = {
    "path": "compliance/translation-coverage.v1.json",
    "sha256": "4699daa94705d2bd4895e19730d320f55c71ecf5e6f4cd5c6520a7e4b71182ae",
}


def _json_object(path: Path, location: str) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None, [safe_error(location, "invalid-json")]
    if not isinstance(value, dict):
        return None, [safe_error(location, "invalid-object")]
    return value, []


def current_proposal_paths(
    coverage_path: Path = COVERAGE,
    register_path: Path = REGISTER,
) -> tuple[list[Path], list[str]]:
    """Return only proposal artifacts admitted by current governed scope state."""

    coverage, errors = _json_object(coverage_path, "$.translationCoverage")
    register, register_errors = _json_object(register_path, "$.sourceRegister")
    errors.extend(register_errors)
    if coverage is None or register is None:
        return [], errors
    if (
        coverage.get("schema") != "al-isabah.translation-coverage.v1"
        or coverage.get("schema_version") != "1.1.0"
    ):
        errors.append(safe_error("$.translationCoverage", "coverage-contract-mismatch"))
        return [], errors

    artifacts = {
        item.get("id"): item
        for item in register.get("artifacts", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    scopes = coverage.get("scopes")
    if not isinstance(scopes, list):
        return [], errors + [safe_error("$.translationCoverage.scopes", "invalid-scope-inventory")]
    if validate_translation_coverage(coverage, artifacts):
        return [], errors + [safe_error("$.translationCoverage", "coverage-state-mismatch")]

    current: list[Path] = []
    admitted_ids: set[str] = set()
    seen_volumes: set[int] = set()
    for index, scope in enumerate(scopes):
        location = f"$.translationCoverage.scopes[{index}]"
        if not isinstance(scope, dict) or scope.get("scope_kind") not in {"volume", "cohort"}:
            errors.append(safe_error(location, "invalid-scope-inventory"))
            continue
        volume = scope.get("volume")
        if not isinstance(volume, int) or isinstance(volume, bool):
            errors.append(safe_error(f"{location}.volume", "invalid-scope-inventory"))
            continue
        if scope["scope_kind"] == "volume":
            if volume in seen_volumes:
                errors.append(safe_error(f"{location}.volume", "invalid-scope-inventory"))
                continue
            seen_volumes.add(volume)
        completion = scope.get("agent_completion")
        if not isinstance(completion, dict):
            errors.append(safe_error(f"{location}.agentCompletion", "invalid-scope-state"))
            continue
        is_current_ready = (
            completion.get("status") == "agent_complete"
            and completion.get("locked_units") == completion.get("translated_units")
            and completion.get("remaining_agent_units") == 0
            and scope.get("workflow_conformance") == "current"
            and scope.get("public_working_status") == "available"
        )
        if scope["scope_kind"] == "cohort":
            # A completed but non-admitted cohort is an overlapping coverage
            # view, not another published volume or an admission instruction.
            if is_current_ready:
                errors.append(safe_error(location, "cohort-publication-not-admitted"))
            continue
        if not is_current_ready:
            continue
        evidence = completion.get("evidence")
        if not isinstance(evidence, dict):
            errors.append(safe_error(f"{location}.agentCompletion.evidence", "missing-artifact"))
            continue
        proposal_id = evidence.get("source_register_artifact")
        artifact = artifacts.get(proposal_id)
        if (
            not isinstance(proposal_id, str)
            or not proposal_id.endswith("-public-proposal-v1")
            or not isinstance(artifact, dict)
            or artifact.get("review_status") != CURRENT_DISTRIBUTION_REVIEW_STATUS
        ):
            errors.append(safe_error(f"{location}.agentCompletion.evidence", "proposal-current-status-mismatch"))
            continue
        proposal_path = PROPOSAL_ROOT / f"{proposal_id.removesuffix('-public-proposal-v1')}.public-proposal.json"
        integrity = artifact.get("integrity", {})
        if (
            not proposal_path.is_file()
            or evidence.get("sha256") != integrity.get("proposal_sha256")
            or evidence.get("sha256") != sha256_file(proposal_path)
            or integrity.get("public_entries") != completion.get("locked_units")
        ):
            errors.append(safe_error(f"{location}.agentCompletion.evidence", "proposal-evidence-mismatch"))
            continue
        proposal, proposal_errors = _json_object(proposal_path, f"$.proposals.{proposal_id}")
        errors.extend(proposal_errors)
        if proposal is None:
            continue
        records = proposal.get("records")
        if (
            proposal.get("proposalId") != proposal_id
            or not isinstance(records, list)
            or len(records) != completion.get("locked_units")
            or any(not isinstance(record, dict) or record.get("volume") != volume for record in records)
        ):
            errors.append(safe_error(f"$.proposals.{proposal_id}", "scope-projection-mismatch"))
            continue
        admitted_ids.add(proposal_id)
        current.append(proposal_path)

    for artifact_id, artifact in artifacts.items():
        if (
            artifact.get("review_status") == CURRENT_DISTRIBUTION_REVIEW_STATUS
            and artifact_id not in admitted_ids
        ):
            errors.append(safe_error(f"$.sourceRegister.{artifact_id}", "unadmitted-current-proposal"))
    if not current:
        errors.append(safe_error("$.proposals", "missing-current-ready-artifact"))
    return sorted(current), errors


def public_review_path(proposal_path: Path) -> Path:
    return proposal_path.with_name(
        proposal_path.name.replace(".public-proposal.json", ".public-review.json")
    )


def output_review_path(proposal: dict[str, Any]) -> str:
    issue_id = proposal["proposalId"].removesuffix("-public-proposal-v1")
    return f"reviews/{issue_id}.json"


def file_binding(path: Path) -> dict[str, str]:
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": sha256_file(path),
    }


def text_file_binding(path: Path) -> dict[str, str]:
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": sha256_text_file(path),
    }


def expected() -> tuple[dict[str, Any] | None, list[str]]:
    errors = validate_historical_closure(LEGACY_CLOSURE)
    if (
        not HISTORICAL_CLOSURE.is_file()
        or sha256_text_file(HISTORICAL_CLOSURE) != HISTORICAL_CLOSURE_SHA256
    ):
        errors.append(safe_error("$.historicalClosure", "historical-closure-mismatch"))
    current_paths, readiness_errors = current_proposal_paths()
    errors.extend(readiness_errors)
    proposals: list[tuple[Path, dict[str, Any], Path, bytes]] = []
    for proposal_path in current_paths:
        proposal_errors = validate_proposal(proposal_path)
        if proposal_errors:
            errors.append(
                safe_error(
                    f"$.proposals.{proposal_path.name}",
                    "proposal-invalid",
                )
            )
            continue
        proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
        review_path = public_review_path(proposal_path)
        review_bytes = canonical_json(expected_review(proposal_path))
        if not review_path.is_file() or review_path.read_bytes() != review_bytes:
            errors.append(
                safe_error(
                    f"$.proposals.{proposal['proposalId']}.publicReview",
                    "review-projection-mismatch",
                )
            )
            continue
        proposals.append((proposal_path, proposal, review_path, review_bytes))
    if errors:
        return None, errors
    if not proposals:
        return None, [safe_error("$.proposals", "missing-artifact")]

    proposal_entries: list[dict[str, Any]] = []
    authorities: dict[str, dict[str, Any]] = {}
    records_by_volume: dict[int, list[dict[str, Any]]] = {}
    review_counts = {
        "machinePassed": 0,
        "needsAttention": 0,
        "humanReviewed": 0,
        "humanUnreviewed": 0,
    }
    output_inventory: list[dict[str, Any]] = []
    for proposal_path, proposal, review_path, review_bytes in proposals:
        records = proposal["records"]
        policy_path = (
            ROOT / "compliance" / "policy-binding.v1.json"
            if proposal["schemaVersion"] == "1.0.0"
            else ROOT / "compliance" / "policy-binding.v2.json"
        )
        proposal_entries.append(
            {
                "proposalId": proposal["proposalId"],
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
        for record in records:
            records_by_volume.setdefault(record["volume"], []).append(record)
        output_inventory.append(
            {
                "path": output_review_path(proposal),
                "sha256": sha256_bytes(review_bytes),
                "bytes": len(review_bytes),
                "recordCount": 1,
            }
        )

    for volume, records in sorted(records_by_volume.items()):
        records.sort(key=lambda item: (item["sourceOrdinal"], item["id"]))
        record_bytes = b"".join(canonical_json(item) for item in records)
        output_inventory.append(
            {
                "path": f"records/volume-{volume:02}.jsonl",
                "sha256": sha256_bytes(record_bytes),
                "bytes": len(record_bytes),
                "recordCount": len(records),
            }
        )

    rights = json.loads(RIGHTS.read_text(encoding="utf-8"))
    promotion = json.loads(PROMOTION.read_text(encoding="utf-8"))
    closure = {
        "schemaVersion": "1.0.0",
        "closureId": "issue-0070-current-public-working-closure-v1",
        "issue": "https://github.com/yaqub0r/al-isabah/issues/70",
        "publicationStatus": "public-working",
        "canonicalPromotion": "blocked",
        "consumerSchemaVersion": "2.0.0",
        "proposals": proposal_entries,
        "sourceAuthorities": [authorities[key] for key in sorted(authorities)],
        # The closure retains its last preserved and validated metadata
        # snapshot. Live ledgers are validated above and may add blocked
        # cohorts without rewriting this immutable closure output.
        "sourceRegister": CURRENT_CLOSURE_SOURCE_REGISTER,
        "translationCoverage": CURRENT_CLOSURE_TRANSLATION_COVERAGE,
        "rights": {
            "path": "compliance/rights-matrix.al-isabah.v1.json",
            "sha256": sha256_text_file(RIGHTS),
            "matrixId": rights["matrix_id"],
            "license": rights["public_content_license"]["spdx"],
        },
        "promotion": {
            "path": "compliance/promotions/available-data.v1.json",
            "sha256": sha256_text_file(PROMOTION),
            "status": promotion["status"],
        },
        # Preserve the superseded cumulative closure as immutable history while
        # current admission follows the governed proposal inventory above.
        "historicalClosure": text_file_binding(HISTORICAL_CLOSURE),
        "reviewCounts": review_counts,
        "outputInventory": sorted(output_inventory, key=lambda item: item["path"]),
    }
    return closure, []


def validate(path: Path = CURRENT_CLOSURE) -> list[str]:
    expected_closure, errors = expected()
    if errors:
        return errors
    if not path.is_file() or sha256_file(path) != CURRENT_CLOSURE_SHA256:
        return [safe_error("$", "current-closure-mismatch")]
    try:
        closure = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return [safe_error(f"$.line[{getattr(error, 'lineno', 0)}]", "invalid-json")]
    errors.extend(boundary_errors(closure))
    if closure != expected_closure:
        errors.append(safe_error("$", "current-closure-mismatch"))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", type=Path, default=CURRENT_CLOSURE)
    args = parser.parse_args()
    errors = validate(args.path.resolve())
    if errors:
        print(summarize(errors))
        for error in errors:
            print(error)
        return 1
    print(f"Current release closure valid: sha256={sha256_file(args.path.resolve())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

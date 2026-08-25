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
from validate_release_closure import CLOSURE as HISTORICAL_CLOSURE
from validate_release_closure import validate as validate_historical_closure


ROOT = Path(__file__).resolve().parents[1]
CURRENT_CLOSURE = (
    ROOT / "compliance" / "publication" / "issue-0053.release-closure.v1.json"
)
PROPOSAL_ROOT = ROOT / "content" / "public-proposals"
REGISTER = ROOT / "compliance" / "source-register.v1.json"
RIGHTS = ROOT / "compliance" / "rights-matrix.al-isabah.v1.json"
PROMOTION = ROOT / "compliance" / "promotions" / "available-data.v1.json"


def proposal_paths() -> list[Path]:
    return sorted(PROPOSAL_ROOT.glob("*.public-proposal.json"))


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
    errors = validate_historical_closure(HISTORICAL_CLOSURE)
    proposals: list[tuple[Path, dict[str, Any], Path, bytes]] = []
    for proposal_path in proposal_paths():
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
        "closureId": "issue-0053-public-working-closure-v1",
        "issue": "https://github.com/yaqub0r/al-isabah/issues/53",
        "publicationStatus": "public-working",
        "canonicalPromotion": "blocked",
        "consumerSchemaVersion": "2.0.0",
        "proposals": proposal_entries,
        "sourceAuthorities": [authorities[key] for key in sorted(authorities)],
        "sourceRegister": text_file_binding(REGISTER),
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
        # Bind canonical repository text so a Windows checkout with legacy
        # CRLF material cannot change the preserved closure identity.
        "historicalClosure": text_file_binding(HISTORICAL_CLOSURE),
        "reviewCounts": review_counts,
        "outputInventory": sorted(output_inventory, key=lambda item: item["path"]),
    }
    return closure, []


def validate(path: Path = CURRENT_CLOSURE) -> list[str]:
    expected_closure, errors = expected()
    if errors:
        return errors
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

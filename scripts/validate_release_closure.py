#!/usr/bin/env python3
"""Validate exact public-working release closure bindings."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from build_public_review import review as expected_review
from public_boundary import boundary_errors, canonical_json, exact_keys, safe_error, sha256_bytes, sha256_file, sha256_text_file, summarize
from validate_public_proposal import order_sha256, records_sha256, validate as validate_proposal


ROOT = Path(__file__).resolve().parents[1]
CLOSURE = ROOT / "compliance" / "publication" / "issue-0026.release-closure.v1.json"
PROPOSAL = ROOT / "content" / "public-proposals" / "issue-0026.public-proposal.json"
PUBLIC_REVIEW = ROOT / "content" / "public-proposals" / "issue-0026.public-review.json"
REGISTER = ROOT / "compliance" / "source-register.v1.json"
RIGHTS = ROOT / "compliance" / "rights-matrix.al-isabah.v1.json"
POLICY = ROOT / "compliance" / "policy-binding.v1.json"
PROMOTION = ROOT / "compliance" / "promotions" / "available-data.v1.json"
TOP_KEYS = {"schemaVersion", "closureId", "issue", "publicationStatus", "canonicalPromotion", "consumerSchemaVersion", "publicProposal", "publicReview", "projection", "sourceAuthority", "sourceRegister", "rights", "policyBinding", "promotion", "reviewCounts", "outputInventory", "historicalExposure"}
KEYS = {
    "file": {"path", "sha256"},
    "projection": {"entryCount", "orderSha256", "userFacingSha256", "recordsSha256"},
    "sourceAuthority": {"sourceId", "commit", "artifactSha256", "license", "attributionRequired"},
    "rights": {"path", "sha256", "matrixId", "license", "exclusionsSha256", "publicationDecisionSha256", "publicBoundaryDecisionSha256", "followUpReviewSha256"},
    "promotion": {"path", "sha256", "status"},
    "reviewCounts": {"machinePassed", "needsAttention", "humanReviewed", "humanUnreviewed"},
    "output": {"path", "sha256", "bytes", "recordCount"},
    "historicalExposure": {"decision", "historyPreserved", "releaseChanges", "sealedPrivateCopyPrerequisiteForFutureRewrite", "legalConclusion"},
}


def canonical_hash(value: Any) -> str:
    return sha256_bytes(canonical_json(value))


def validate(path: Path = CLOSURE) -> list[str]:
    try:
        closure = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return [safe_error(f"$.line[{getattr(error, 'lineno', 0)}]", "invalid-json")]
    errors = exact_keys(closure, TOP_KEYS, "$")
    for key in ("publicProposal", "publicReview", "sourceRegister", "policyBinding"):
        errors.extend(exact_keys(closure.get(key), KEYS["file"], f"$.{key}"))
    for key in ("projection", "sourceAuthority", "rights", "promotion", "reviewCounts", "historicalExposure"):
        errors.extend(exact_keys(closure.get(key), KEYS[key], f"$.{key}"))
    for index, item in enumerate(closure.get("outputInventory", [])):
        errors.extend(exact_keys(item, KEYS["output"], f"$.outputInventory[{index}]"))
    errors.extend(boundary_errors(closure))
    expected_constants = {
        "schemaVersion": "1.0.0",
        "closureId": "issue-0026-public-working-closure-v1",
        "issue": "https://github.com/yaqub0r/al-isabah/issues/35",
        "publicationStatus": "public-working",
        "canonicalPromotion": "blocked",
        "consumerSchemaVersion": "2.0.0",
    }
    for key, value in expected_constants.items():
        if closure.get(key) != value:
            errors.append(safe_error(f"$.{key}", "closure-mismatch"))
    proposal_errors = validate_proposal(PROPOSAL)
    if proposal_errors:
        errors.append(safe_error("$.publicProposal", "proposal-invalid"))
        return errors
    proposal = json.loads(PROPOSAL.read_text(encoding="utf-8"))
    records = proposal["records"]
    expected_files = {
        "publicProposal": ("content/public-proposals/issue-0026.public-proposal.json", PROPOSAL, sha256_file),
        "publicReview": ("content/public-proposals/issue-0026.public-review.json", PUBLIC_REVIEW, sha256_file),
        "sourceRegister": ("compliance/source-register.v1.json", REGISTER, sha256_text_file),
        "policyBinding": ("compliance/policy-binding.v1.json", POLICY, sha256_text_file),
    }
    for key, (expected_path, file_path, digest) in expected_files.items():
        binding = closure.get(key, {})
        if binding.get("path") != expected_path or binding.get("sha256") != digest(file_path):
            errors.append(safe_error(f"$.{key}", "file-binding-mismatch"))
    review_bytes = canonical_json(expected_review(PROPOSAL))
    if PUBLIC_REVIEW.read_bytes() != review_bytes:
        errors.append(safe_error("$.publicReview", "review-projection-mismatch"))
    projection = closure.get("projection", {})
    expected_projection = {
        "entryCount": len(records),
        "orderSha256": order_sha256(records),
        "userFacingSha256": proposal["baseline"]["userFacingSha256"],
        "recordsSha256": records_sha256(records),
    }
    if projection != expected_projection:
        errors.append(safe_error("$.projection", "projection-mismatch"))
    authority = proposal["sourceAuthority"]
    expected_authority = {
        "sourceId": authority["sourceId"],
        "commit": authority["commit"],
        "artifactSha256": authority["sha256"],
        "license": authority["license"]["spdx"],
        "attributionRequired": True,
    }
    if closure.get("sourceAuthority") != expected_authority:
        errors.append(safe_error("$.sourceAuthority", "source-mismatch"))
    rights = json.loads(RIGHTS.read_text(encoding="utf-8"))
    expected_rights = {
        "path": "compliance/rights-matrix.al-isabah.v1.json",
        "sha256": sha256_text_file(RIGHTS),
        "matrixId": rights["matrix_id"],
        "license": rights["public_content_license"]["spdx"],
        "exclusionsSha256": canonical_hash(rights["exclusions"]),
        "publicationDecisionSha256": canonical_hash(rights["publication_decision"]),
        "publicBoundaryDecisionSha256": canonical_hash(rights["public_boundary_decision"]),
        "followUpReviewSha256": canonical_hash(rights["follow_up_review"]),
    }
    if closure.get("rights") != expected_rights:
        errors.append(safe_error("$.rights", "rights-mismatch"))
    promotion = json.loads(PROMOTION.read_text(encoding="utf-8"))
    expected_promotion = {"path": "compliance/promotions/available-data.v1.json", "sha256": sha256_text_file(PROMOTION), "status": promotion["status"]}
    if closure.get("promotion") != expected_promotion or promotion["status"] != "blocked":
        errors.append(safe_error("$.promotion", "promotion-mismatch"))
    if closure.get("reviewCounts") != proposal["review"]:
        errors.append(safe_error("$.reviewCounts", "review-count-mismatch"))
    record_bytes = b"".join(canonical_json(item) for item in records)
    expected_inventory = [
        {"path": "records/volume-01.jsonl", "sha256": sha256_bytes(record_bytes), "bytes": len(record_bytes), "recordCount": len(records)},
        {"path": "review.json", "sha256": sha256_bytes(review_bytes), "bytes": len(review_bytes), "recordCount": 1},
    ]
    if closure.get("outputInventory") != expected_inventory:
        errors.append(safe_error("$.outputInventory", "output-inventory-mismatch"))
    expected_history = {"decision": "forward-remediation-no-history-rewrite", "historyPreserved": True, "releaseChanges": "none", "sealedPrivateCopyPrerequisiteForFutureRewrite": True, "legalConclusion": False}
    if closure.get("historicalExposure") != expected_history:
        errors.append(safe_error("$.historicalExposure", "historical-decision-mismatch"))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", type=Path, default=CLOSURE)
    args = parser.parse_args()
    errors = validate(args.path.resolve())
    if errors:
        print(summarize(errors))
        for error in errors:
            print(error)
        return 1
    print(f"Release closure valid: sha256={sha256_file(args.path.resolve())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

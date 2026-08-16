#!/usr/bin/env python3
"""One-way projection from an accepted v2 distribution into public-proposal.v1."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from public_boundary import canonical_json, sha256_bytes, sha256_text_file


ROOT = Path(__file__).resolve().parents[1]
NORMALIZED_SOURCE_ID = "openiti-cleaned-arabic-comparison"


FORMULA_KEYS = (
    "formulaId",
    "recordId",
    "observedArabic",
    "semanticClass",
    "targetRealization",
)


def finding(value: dict[str, Any]) -> dict[str, str]:
    return {
        "category": str(value.get("category") or "other"),
        "priority": str(value.get("priority") or "review"),
    }


def context(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": value["id"],
        "kind": value["kind"],
        "heading": value["heading"],
        "arabic": value["arabic"],
        "english": value["english"],
        "pages": value["pages"],
        "humanReview": value["humanReview"],
        "unresolved": [finding(item) for item in value["unresolved"]],
        "sourceSha256": value["sourceSha256"],
    }


def record(value: dict[str, Any]) -> dict[str, Any]:
    source = dict(value["source"])
    source["authorityId"] = NORMALIZED_SOURCE_ID
    return {
        "schemaVersion": value["schemaVersion"],
        "id": value["id"],
        "kind": value["kind"],
        "workId": value["workId"],
        "packetId": value["packetId"],
        "sourceOrdinal": value["sourceOrdinal"],
        "printedEntryNumber": value["printedEntryNumber"],
        "canonicalEntryId": value["canonicalEntryId"],
        "volume": value["volume"],
        "pages": value["pages"],
        "title": value["title"],
        "arabic": value["arabic"],
        "english": value["english"],
        "precedingMaterial": [context(item) for item in value["precedingMaterial"]],
        "names": value["names"],
        "unresolved": [finding(item) for item in value["unresolved"]],
        "formulas": [
            {key: item[key] for key in FORMULA_KEYS}
            for item in value["formulas"]
        ],
        "machineAssessment": value["machineAssessment"],
        "humanReview": value["humanReview"],
        "source": source,
        "policy": {
            "bindingSha256": sha256_text_file(ROOT / "compliance" / "policy-binding.v1.json")
        },
    }


def parity_projection(records: list[dict[str, Any]]) -> bytes:
    values = [
        {
            "id": item["id"],
            "sourceOrdinal": item["sourceOrdinal"],
            "title": item["title"],
            "arabic": item["arabic"],
            "english": item["english"],
            "precedingMaterial": [
                {
                    "id": context_item["id"],
                    "heading": context_item["heading"],
                    "arabic": context_item["arabic"],
                    "english": context_item["english"],
                }
                for context_item in item["precedingMaterial"]
            ],
        }
        for item in records
    ]
    return canonical_json(values)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("distribution", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    root = args.distribution.resolve()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    baseline: list[dict[str, Any]] = []
    for item in manifest["files"]:
        baseline.extend(
            json.loads(line)
            for line in (root / item["path"]).read_text(encoding="utf-8").splitlines()
            if line
        )
    records = [record(item) for item in baseline]
    authority = dict(manifest["authorities"][0])
    authority["sourceId"] = NORMALIZED_SOURCE_ID
    proposal = {
        "schemaVersion": "1.0.0",
        "proposalId": "issue-0026-public-proposal-v1",
        "workId": "ibn-hajar-al-isabah",
        "publicationStatus": "public-working",
        "canonicalPromotion": "blocked",
        "consumerSchemaVersion": "2.0.0",
        "sourceAuthority": authority,
        "rights": {
            "matrixId": manifest["rights"]["matrixId"],
            "allowedUseClassification": "approved-noncommercial-public-working",
            "statusCode": "public-working",
            "effectCode": "canonical-promotion-blocked",
        },
        "policy": records[0]["policy"],
        "review": {
            "machinePassed": sum(item["machineAssessment"] == "passed" for item in records),
            "needsAttention": sum(item["machineAssessment"] == "needs_attention" for item in records),
            "humanReviewed": sum(item["humanReview"] in {"reviewed", "verified"} for item in records),
            "humanUnreviewed": sum(item["humanReview"] not in {"reviewed", "verified"} for item in records),
        },
        "historicalEvidence": {
            "packetGitBlobSha1": "4f3ebf1ec42d17825f5957280b6d21636f05ee39",
            "packetGitBlobSha256": "809de448fdb9079bdea6fc88ad73c6d092db7c20222d353ab640e84232c4c526",
            "packetGitBlobBytes": 34475553,
            "reviewGitBlobSha1": "b1a9a8ebdd66d995cbe5d2c4750675306e373afd",
            "reviewSha256": "58efb42068837520494f4a90ee7555a440e93cbf98fd2388bf4429807e7453f1",
            "historyPreserved": True,
        },
        "baseline": {
            "distributionSchemaVersion": "2.0.0",
            "recordCount": len(baseline),
            "userFacingSha256": sha256_bytes(parity_projection(baseline)),
        },
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json(proposal))
    print(
        f"Projected {len(records)} records; "
        f"proposal-sha256={sha256_bytes(canonical_json(proposal))}; "
        f"user-facing-sha256={proposal['baseline']['userFacingSha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

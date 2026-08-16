#!/usr/bin/env python3
"""Build the deterministic, value-safe public review summary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from public_boundary import canonical_json, sha256_file
from validate_public_proposal import order_sha256, records_sha256, validate


ROOT = Path(__file__).resolve().parents[1]
PROPOSAL = ROOT / "content" / "public-proposals" / "issue-0026.public-proposal.json"


def review(proposal_path: Path = PROPOSAL) -> dict:
    errors = validate(proposal_path)
    if errors:
        raise ValueError("public proposal did not pass boundary validation")
    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    records = proposal["records"]
    return {
        "schemaVersion": "1.0.0",
        "proposalId": proposal["proposalId"],
        "proposalSha256": sha256_file(proposal_path),
        "projection": {
            "recordCount": len(records),
            "recordsSha256": records_sha256(records),
            "orderSha256": order_sha256(records),
            "userFacingSha256": proposal["baseline"]["userFacingSha256"],
        },
        "review": proposal["review"],
        "publicBoundary": {"status": "passed", "findingCount": 0},
        "decision": {
            "publicationStatus": "public-working",
            "canonicalPromotion": "blocked",
            "legalConclusion": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    data = canonical_json(review())
    if args.check:
        if not args.output.is_file() or args.output.read_bytes() != data:
            print("public review artifact differs from deterministic projection")
            return 1
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(data)
    print(f"Public review valid: sha256={sha256_file(args.output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

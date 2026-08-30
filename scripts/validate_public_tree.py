#!/usr/bin/env python3
"""Validate the current public tree without reading historical internal payloads."""

from __future__ import annotations

from pathlib import Path

from public_boundary import safe_error, summarize
from validate_current_release_closure import validate as validate_current_closure
from validate_public_proposal import validate as validate_proposal
from validate_release_closure import validate as validate_closure
from execution_governance import validate as validate_execution_governance


ROOT = Path(__file__).resolve().parents[1]
PROPOSAL_ROOT = ROOT / "content" / "public-proposals"
INTERNAL_ROOT = ROOT / "content" / "translation-proposals"


def validate() -> list[str]:
    errors: list[str] = []
    for path in INTERNAL_ROOT.glob("*"):
        if path.is_file() and path.name not in {".gitkeep", "README.md"}:
            errors.append(safe_error(f"$.tree.{path.name}", "prohibited-current-artifact"))
    proposals = sorted(PROPOSAL_ROOT.glob("*.public-proposal.json"))
    if not proposals:
        errors.append(safe_error("$.tree.publicProposals", "missing-artifact"))
    for proposal in proposals:
        errors.extend(validate_proposal(proposal))
    errors.extend(validate_closure())
    errors.extend(validate_current_closure())
    errors.extend(validate_execution_governance())
    return errors


def main() -> int:
    errors = validate()
    if errors:
        print(summarize(errors))
        for error in errors:
            print(error)
        return 1
    print("Current public tree satisfies every registered proposal boundary.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

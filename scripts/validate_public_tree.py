#!/usr/bin/env python3
"""Validate the current public tree without reading historical internal payloads."""

from __future__ import annotations

from pathlib import Path

from public_boundary import safe_error, summarize
from validate_public_proposal import validate as validate_proposal
from validate_release_closure import validate as validate_closure


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_CURRENT_FILES = (
    ROOT / "content" / "translation-proposals" / "issue-0026.packet.json",
    ROOT / "content" / "translation-proposals" / "issue-0026.review.md",
)


def validate() -> list[str]:
    errors: list[str] = []
    for path in FORBIDDEN_CURRENT_FILES:
        if path.exists():
            errors.append(safe_error(f"$.tree.{path.name}", "prohibited-current-artifact"))
    errors.extend(validate_proposal())
    errors.extend(validate_closure())
    return errors


def main() -> int:
    errors = validate()
    if errors:
        print(summarize(errors))
        for error in errors:
            print(error)
        return 1
    print("Current public tree satisfies the issue-0026 boundary.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

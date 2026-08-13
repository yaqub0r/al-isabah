#!/usr/bin/env python3
"""Validate the book-specific entry-title boundary profile."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "profiles" / "entry-title-decisions.v1.json"
GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
RELATIONSHIP_PROSE = re.compile(
    r"\b(?:the\s+)?(?:wife|mother|sister|daughter)\s+of\b|\b(?:mentioned|narrated)\b",
    re.IGNORECASE,
)


def load(path: Path = PROFILE) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: top level must be an object")
    return value


def _bilingual(value: object, location: str) -> list[str]:
    if not isinstance(value, dict):
        return [f"{location}: must be an object"]
    extra = sorted(set(value) - {"ar", "en"})
    errors = [f"{location}: unexpected fields: {', '.join(extra)}"] if extra else []
    for language in ("ar", "en"):
        text = value.get(language)
        if not isinstance(text, str) or not text.strip():
            errors.append(f"{location}.{language}: non-empty text is required")
        elif text != text.strip() or "\n" in text:
            errors.append(f"{location}.{language}: must be a single trimmed block")
    return errors


def validate(profile: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    expected = {
        "schemaVersion": "1.0.0",
        "contractId": "al-isabah-entry-title-structure",
        "workId": "ibn-hajar-al-isabah",
        "status": "active",
    }
    for key, value in expected.items():
        if profile.get(key) != value:
            errors.append(f"profile: {key} must be {value!r}")

    authority = profile.get("sourceAuthority")
    if not isinstance(authority, dict):
        errors.append("profile: sourceAuthority must be an object")
    else:
        if not GIT_SHA.fullmatch(str(authority.get("commit", ""))):
            errors.append("profile: sourceAuthority.commit must be a full Git SHA")
        for field in ("repository", "artifact", "license"):
            if not str(authority.get(field, "")).strip():
                errors.append(f"profile: sourceAuthority.{field} is required")

    decisions = profile.get("decisions")
    if not isinstance(decisions, list) or not decisions:
        return errors + ["profile: decisions must be a non-empty list"]

    seen: set[int] = set()
    allowed_roles = {"positive-reference", "corrective", "typography-reference"}
    for index, decision in enumerate(decisions):
        location = f"decision {index}"
        if not isinstance(decision, dict):
            errors.append(f"{location}: must be an object")
            continue
        number = decision.get("sourceEntryNumber")
        if not isinstance(number, int) or number < 1:
            errors.append(f"{location}: sourceEntryNumber must be positive")
        elif number in seen:
            errors.append(f"{location}: duplicate sourceEntryNumber {number}")
        else:
            seen.add(number)
        if decision.get("role") not in allowed_roles:
            errors.append(f"{location}: invalid role")
        if decision.get("bodyOpeningKind") not in {"lineage", "prose"}:
            errors.append(f"{location}: invalid bodyOpeningKind")
        errors.extend(_bilingual(decision.get("title"), f"{location}.title"))
        errors.extend(_bilingual(decision.get("bodyOpening"), f"{location}.bodyOpening"))
        title = decision.get("title")
        if isinstance(title, dict) and RELATIONSHIP_PROSE.search(str(title.get("en", ""))):
            errors.append(f"{location}.title.en: relationship or narration prose belongs in the body")
    return errors


def main() -> int:
    try:
        errors = validate(load())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        errors = [str(error)]
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("Entry-title decisions satisfy the active Al-Isabah contract.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

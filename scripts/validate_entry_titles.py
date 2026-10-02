#!/usr/bin/env python3
"""Validate the book-specific entry-title boundary profile."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "profiles" / "entry-title-decisions.v4.json"
GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RELATIONSHIP_PROSE = re.compile(
    r"\b(?:the\s+)?(?:wife|mother|sister|daughter)\s+of\b|\b(?:mentioned|narrated)\b",
    re.IGNORECASE,
)
BODY_BOUNDARY = " \t\r\n,،.;:—–-"
OPENITI_MILESTONE = re.compile(r"(?<![A-Za-z0-9_])ms[0-9]+(?![A-Za-z0-9_])")


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


def _text_binding(value: object, location: str) -> tuple[list[str], str]:
    """Validate one exact UTF-8 text/hash binding and return its text."""
    if not isinstance(value, dict):
        return [f"{location}: must be an object"], ""
    errors: list[str] = []
    if set(value) != {"text", "sha256"}:
        errors.append(f"{location}: fields must be text and sha256")
    text = value.get("text")
    if not isinstance(text, str) or not text.strip():
        errors.append(f"{location}.text: non-empty text is required")
        text = ""
    elif text != text.strip() or "\n" in text:
        errors.append(f"{location}.text: must be a single trimmed block")
    expected_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if not SHA256.fullmatch(str(value.get("sha256", ""))):
        errors.append(f"{location}.sha256: must be a SHA-256")
    elif value["sha256"] != expected_sha:
        errors.append(f"{location}.sha256: does not match the exact UTF-8 text")
    return errors, text


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _bilingual_text_binding(
    value: object, location: str
) -> tuple[list[str], dict[str, str]]:
    if not isinstance(value, dict):
        return [f"{location}: must be an object"], {"ar": "", "en": ""}
    errors = []
    if set(value) != {"ar", "en"}:
        errors.append(f"{location}: fields must be ar and en")
    texts: dict[str, str] = {}
    for language in ("ar", "en"):
        item_errors, text = _text_binding(value.get(language), f"{location}.{language}")
        errors.extend(item_errors)
        texts[language] = text
    return errors, texts


def source_prefixes(decision: dict[str, Any]) -> dict[str, str]:
    """Return exact source prefixes removed during public projection."""
    supply = decision.get("editorialSupply")
    if not isinstance(supply, dict):
        return dict(decision["title"])
    source_prefix = supply["sourcePrefix"]
    return {
        language: source_prefix[language]["text"]
        for language in ("ar", "en")
    }


def clean_source_heading_boundary(value: str) -> str:
    """Remove only OpenITI milestone controls from a source heading.

    The readable Arabic body was already derived from the same pinned source
    with these controls removed.  Cleaning the heading by the exact OpenITI
    token grammar lets the two views share one title boundary without changing
    any substantive Arabic byte.
    """
    without_markers = OPENITI_MILESTONE.sub(" ", value)
    return re.sub(r"[ \t]+", " ", without_markers).strip()


def governed_title_and_body(
    entry: dict[str, Any],
    decision: dict[str, Any],
    *,
    render_arabic: Any,
) -> tuple[dict[str, Any], str, str]:
    """Apply one exact title decision to already governed packet fields."""
    title = decision["title"]
    body_opening = decision["bodyOpening"]
    source_prefix = source_prefixes(decision)
    source_heading = clean_source_heading_boundary(
        render_arabic(entry["source"]["headingArabic"])
    )
    if not source_heading.startswith(source_prefix["ar"]):
        raise ValueError(
            f"source ordinal {entry['sourceOrdinal']} title decision does not "
            "match the pinned Arabic source prefix"
        )
    arabic = body_after_decided_title(
        render_arabic(entry["source"]["arabic"]),
        source_prefix["ar"],
        body_opening["ar"],
        location=f"source ordinal {entry['sourceOrdinal']} Arabic body",
    )
    english = body_after_decided_title(
        entry["adjudication"]["english"].strip(),
        source_prefix["en"],
        body_opening["en"],
        location=f"source ordinal {entry['sourceOrdinal']} English body",
    )
    return (
        {
            "arabic": title["ar"],
            "english": title["en"],
            "state": "needs_attention" if entry.get("unresolved") else "ready",
            "method": "profile-decision",
        },
        arabic,
        english,
    )


def _editorial_supply_errors(
    value: object,
    decision: dict[str, Any],
    profile: dict[str, Any],
    location: str,
) -> list[str]:
    """Validate a transparent, same-work-witness-bound subject-head supply."""
    if not isinstance(value, dict):
        return [f"{location}: must be an object"]
    expected_fields = {
        "kind",
        "sourcePrefix",
        "supply",
        "displayContinuation",
        "semanticScope",
        "witness",
    }
    errors: list[str] = []
    if set(value) != expected_fields:
        errors.append(f"{location}: fields do not match the editorial-supply contract")
    if value.get("kind") != "witness-bound-subject-head":
        errors.append(f"{location}.kind: unexpected editorial-supply kind")

    prefix_errors, prefix = _bilingual_text_binding(
        value.get("sourcePrefix"), f"{location}.sourcePrefix"
    )
    supply_errors, supplied = _bilingual_text_binding(
        value.get("supply"), f"{location}.supply"
    )
    errors.extend(prefix_errors)
    errors.extend(supply_errors)

    continuation = value.get("displayContinuation")
    errors.extend(_bilingual(continuation, f"{location}.displayContinuation"))
    if not isinstance(continuation, dict):
        continuation = {}
    if prefix["ar"] != continuation.get("ar"):
        errors.append(
            f"{location}.displayContinuation.ar: must preserve the exact Arabic source prefix"
        )
    if prefix["en"].casefold() != str(continuation.get("en", "")).casefold():
        errors.append(
            f"{location}.displayContinuation.en: may differ from the English source prefix only in case"
        )

    expected_title = {
        language: f"[{supplied[language]}] {continuation.get(language, '')}"
        for language in ("ar", "en")
    }
    if decision.get("title") != expected_title:
        errors.append(
            f"{location}: decision title must transparently bracket only the supplied subject head"
        )

    scope = value.get("semanticScope")
    expected_scope = {
        "kind": "personal-name",
        "equality": "reviewed-bilingual-equivalent-subject",
        "ar": f"{supplied['ar']} {continuation.get('ar', '')}",
        "en": f"{supplied['en']} {continuation.get('en', '')}",
    }
    if scope != expected_scope:
        errors.append(
            f"{location}.semanticScope: must prove equal unbracketed subject scope"
        )

    witness = value.get("witness")
    witness_fields = {
        "relation",
        "workId",
        "status",
        "role",
        "identity",
        "location",
        "retrievedAt",
        "passage",
        "evidence",
        "bindingSha256",
    }
    if not isinstance(witness, dict):
        return errors + [f"{location}.witness: must be an object"]
    if set(witness) != witness_fields:
        errors.append(f"{location}.witness: fields do not match the witness contract")
    if witness.get("relation") != "same-work-alternative-edition":
        errors.append(f"{location}.witness.relation: same-work evidence is required")
    if witness.get("workId") != profile.get("workId"):
        errors.append(f"{location}.witness.workId: must match the governed work")
    if witness.get("status") != "hit" or witness.get("role") != "alternative_edition":
        errors.append(f"{location}.witness: a resolved alternative-edition hit is required")
    for field in ("identity", "location"):
        if not isinstance(witness.get(field), str) or not witness[field].strip():
            errors.append(f"{location}.witness.{field}: non-empty text is required")
    if not ISO_DATE.fullmatch(str(witness.get("retrievedAt", ""))):
        errors.append(f"{location}.witness.retrievedAt: must be an ISO date")

    passage_errors, passage = _text_binding(
        witness.get("passage"), f"{location}.witness.passage"
    )
    errors.extend(passage_errors)
    if passage and not passage.startswith(f"({supplied['ar']}) {prefix['ar']}"):
        errors.append(
            f"{location}.witness.passage: must attest the supplied head before the exact Arabic prefix"
        )
    evidence = witness.get("evidence")
    if not isinstance(evidence, dict) or set(evidence) != {"kind", "sha256"}:
        errors.append(f"{location}.witness.evidence: fields must be kind and sha256")
    else:
        if evidence.get("kind") != "artifact":
            errors.append(f"{location}.witness.evidence.kind: must be artifact")
        if not SHA256.fullmatch(str(evidence.get("sha256", ""))):
            errors.append(f"{location}.witness.evidence.sha256: must be a SHA-256")
    witness_payload = {
        key: witness.get(key)
        for key in sorted(witness_fields - {"bindingSha256"})
    }
    if witness.get("bindingSha256") != _canonical_sha256(witness_payload):
        errors.append(
            f"{location}.witness.bindingSha256: does not match the exact witness record"
        )
    return errors


def decision_index(profile: dict[str, Any]) -> dict[int, dict[str, Any]]:
    """Return the exact governed decisions, keyed by printed entry number.

    The current profile contract makes printed entry number its decision key.
    Profile validation rejects duplicates before this index is suitable for a
    public projection.
    """
    errors = validate(profile)
    if errors:
        raise ValueError("entry-title decision profile is invalid")
    return {
        decision["sourceEntryNumber"]: decision
        for decision in profile["decisions"]
    }


def decision_for_entry(
    profile: dict[str, Any], source_entry_number: int
) -> dict[str, Any]:
    decision = decision_index(profile).get(source_entry_number)
    if decision is None:
        raise ValueError(
            f"source entry {source_entry_number} lacks a governed bilingual "
            "title/body decision"
        )
    return decision


def body_after_decided_title(
    text: str,
    title: str,
    body_opening: str,
    *,
    location: str,
) -> str:
    """Remove only an exact decided title and prove the retained body opening."""
    if not text.startswith(title):
        raise ValueError(f"{location}: decided title is not an exact text prefix")
    remainder = text[len(title):]
    if not remainder or remainder[0] not in BODY_BOUNDARY:
        raise ValueError(f"{location}: decided title has no exact body boundary")
    body = remainder.lstrip(BODY_BOUNDARY)
    if not body.startswith(body_opening):
        raise ValueError(
            f"{location}: decided moved text is not retained at the body opening"
        )
    return body


def validate(profile: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    expected = {
        "schemaVersion": "1.1.0",
        "contractId": "al-isabah-entry-title-structure",
        "workId": "ibn-hajar-al-isabah",
        "status": "active",
    }
    for key, value in expected.items():
        if profile.get(key) != value:
            errors.append(f"profile: {key} must be {value!r}")
    if set(profile) != {
        "schemaVersion",
        "contractId",
        "workId",
        "status",
        "sourceAuthority",
        "decisions",
    }:
        errors.append("profile: fields do not match the active title contract")

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
        allowed_fields = {
            "sourceEntryNumber",
            "role",
            "title",
            "bodyOpeningKind",
            "bodyOpening",
        }
        if "editorialSupply" in decision:
            allowed_fields.add("editorialSupply")
        if set(decision) != allowed_fields:
            errors.append(f"{location}: fields do not match the decision contract")
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
        if "editorialSupply" in decision:
            errors.extend(
                _editorial_supply_errors(
                    decision["editorialSupply"],
                    decision,
                    profile,
                    f"{location}.editorialSupply",
                )
            )
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

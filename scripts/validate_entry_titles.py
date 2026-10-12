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
PROFILE = ROOT / "profiles" / "entry-title-decisions.v10.json"
HISTORICAL_PROFILE = ROOT / "profiles" / "entry-title-decisions.v9.json"
SOURCE_BOUND_PROFILE = ROOT / "profiles" / "entry-title-decisions.v7.json"
SOURCE_BOUND_SUCCESSORS = (
    ROOT / "profiles" / "entry-title-decisions.v8.json",
    HISTORICAL_PROFILE,
)
GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SOURCE_UNIT_ID = re.compile(r"^openiti-5835c183-unit-([0-9]{6})$")
RELATIONSHIP_PROSE = re.compile(
    r"\b(?:the\s+)?(?:wife|mother|sister|daughter)\s+of\b|\b(?:mentioned|narrated)\b",
    re.IGNORECASE,
)
BODY_BOUNDARY = " \t\r\n,،.;:—–-"
OPENITI_MILESTONE = re.compile(
    r"(?<![A-Za-z0-9_])(?:ms[0-9]+|PageV[0-9]{2}P[0-9]{3})(?![A-Za-z0-9_])"
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
        elif OPENITI_MILESTONE.search(text):
            errors.append(
                f"{location}.{language}: OpenITI milestone controls are not display text"
            )
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
    if (
        entry.get("sourceEntryNumber") is not None
        and entry["sourceEntryNumber"] != decision.get("sourceEntryNumber")
    ):
        raise ValueError("title decision printed number does not match the source unit")
    source_unit_id = decision.get("sourceUnitId")
    if source_unit_id is not None:
        if entry.get("sourceUnitId") != source_unit_id:
            raise ValueError("title decision does not match the source unit")
        if entry.get("source", {}).get("rawSha256") != decision.get(
            "sourceRawSha256"
        ):
            raise ValueError("title decision does not match the source-unit raw hash")
    if decision.get("bodyOpeningKind") == "none":
        source_heading = clean_source_heading_boundary(
            render_arabic(entry["source"]["headingArabic"])
        )
        source_text = render_arabic(entry["source"]["arabic"]).strip()
        english_text = entry["adjudication"]["english"].strip()
        if (
            body_opening != {"ar": "", "en": ""}
            or source_heading != title["ar"]
            or source_text != title["ar"]
            or english_text != title["en"]
            or entry["source"].get("rawSha256")
            != decision.get("sourceRawSha256", decision.get("sourceUnitSha256"))
        ):
            raise ValueError(
                f"source ordinal {entry['sourceOrdinal']} is not an exact "
                "bilingual title-only source unit"
            )
        return (
            {
                "arabic": title["ar"],
                "english": title["en"],
                "state": "needs_attention" if entry.get("unresolved") else "ready",
                "method": "profile-decision",
            },
            "",
            "",
        )
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


def decision_index(profile: dict[str, Any]) -> dict[int | str, dict[str, Any]]:
    """Index exact source units and unambiguous printed-number fallbacks."""
    errors = validate(profile)
    if errors:
        raise ValueError("entry-title decision profile is invalid")
    by_number: dict[int, list[dict[str, Any]]] = {}
    indexed: dict[int | str, dict[str, Any]] = {}
    for decision in profile["decisions"]:
        by_number.setdefault(decision["sourceEntryNumber"], []).append(decision)
        if "sourceUnitId" in decision:
            indexed[decision["sourceUnitId"]] = decision
    for number, decisions in by_number.items():
        if len(decisions) == 1:
            indexed[number] = decisions[0]
    return indexed


def decision_for_entry(
    profile: dict[str, Any], source_entry_number: int, source_unit_id: str | None = None
) -> dict[str, Any]:
    indexed = decision_index(profile)
    decision = indexed.get(source_unit_id) if source_unit_id else None
    if decision is None:
        decision = indexed.get(source_entry_number)
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
    if not body_opening:
        raise ValueError(f"{location}: ordinary body opening cannot be empty")
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
    schema_version = profile.get("schemaVersion")
    expected = {
        "contractId": "al-isabah-entry-title-structure",
        "workId": "ibn-hajar-al-isabah",
        "status": "active",
    }
    if schema_version not in {"1.1.0", "1.2.0", "1.3.0"}:
        errors.append("profile: unsupported schemaVersion")
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

    historical_count = 0
    source_bound_start = 0
    if schema_version == "1.3.0":
        known_predecessors = [
            load(SOURCE_BOUND_PROFILE)["decisions"],
            *(load(path)["decisions"] for path in SOURCE_BOUND_SUCCESSORS),
        ]
        eligible = [
            candidate
            for candidate in known_predecessors
            if len(candidate) < len(decisions)
        ]
        historical = max(eligible, key=len) if eligible else known_predecessors[0]
        historical_count = len(historical)
        source_bound_start = len(load(SOURCE_BOUND_PROFILE)["decisions"])
        if decisions[:historical_count] != historical:
            errors.append("profile: immediate historical decisions must remain unchanged")

    seen_numbers: dict[int, list[dict[str, Any]]] = {}
    seen_units: set[str] = set()
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
        title_only = decision.get("bodyOpeningKind") == "none"
        source_bound = schema_version == "1.3.0" and index >= source_bound_start
        if source_bound:
            allowed_fields.update({"sourceUnitId", "sourceRawSha256"})
        elif title_only:
            allowed_fields.add("sourceUnitSha256")
        if "editorialSupply" in decision:
            allowed_fields.add("editorialSupply")
        if set(decision) != allowed_fields:
            errors.append(f"{location}: fields do not match the decision contract")
        number = decision.get("sourceEntryNumber")
        if not isinstance(number, int) or number < 1:
            errors.append(f"{location}: sourceEntryNumber must be positive")
        else:
            seen_numbers.setdefault(number, []).append(decision)
        if source_bound:
            source_unit_id = decision.get("sourceUnitId")
            match = SOURCE_UNIT_ID.fullmatch(str(source_unit_id))
            if match is None:
                errors.append(
                    f"{location}: sourceUnitId must be a pinned source-unit key"
                )
            elif int(match.group(1)) != 6159 + index - source_bound_start:
                errors.append(f"{location}: sourceUnitId must follow source order")
            elif source_unit_id in seen_units:
                errors.append(f"{location}: duplicate sourceUnitId {source_unit_id}")
            else:
                seen_units.add(source_unit_id)
            if not SHA256.fullmatch(str(decision.get("sourceRawSha256", ""))):
                errors.append(f"{location}: sourceRawSha256 must be a SHA-256")
        if decision.get("role") not in allowed_roles:
            errors.append(f"{location}: invalid role")
        if decision.get("bodyOpeningKind") not in {"lineage", "prose", "none"}:
            errors.append(f"{location}: invalid bodyOpeningKind")
        errors.extend(_bilingual(decision.get("title"), f"{location}.title"))
        if title_only:
            if schema_version not in {"1.2.0", "1.3.0"}:
                errors.append(
                    f"{location}: title-only mode requires profile schema 1.2.0 or later"
                )
            if decision.get("bodyOpening") != {"ar": "", "en": ""}:
                errors.append(f"{location}.bodyOpening: title-only opening must be exactly empty in both languages")
            raw_hash = (
                decision.get("sourceRawSha256")
                if source_bound
                else decision.get("sourceUnitSha256")
            )
            if not SHA256.fullmatch(str(raw_hash or "")):
                errors.append(f"{location}: title-only source hash must be a SHA-256")
            if "editorialSupply" in decision:
                errors.append(f"{location}: title-only mode cannot use editorialSupply")
        else:
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
    for number, matches in seen_numbers.items():
        if len(matches) > 1 and any("sourceUnitId" not in item for item in matches):
            errors.append(
                f"profile: duplicate sourceEntryNumber {number} needs distinct source-unit keys"
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

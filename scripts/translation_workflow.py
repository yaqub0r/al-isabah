#!/usr/bin/env python3
"""Prepare and validate distributed Al-Isabah translation contributions.

The CLI deliberately does not call an LLM API. It gives a Codex agent a
source-locked packet, verifies the required autonomous stages, renders the
human-review handoff, and prepares a public-safe pull-request artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from urllib.parse import urlparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "profiles" / "translation-source.v1.json"
DEFAULT_POLICY = ROOT / "compliance" / "policy-binding.v1.json"
DEFAULT_PACKET_SCHEMA = ROOT / "schemas" / "translation-work-packet.v1.schema.json"
RUNTIME_ROOT = ROOT / ".runtime" / "translation"
PROPOSAL_ROOT = ROOT / "content" / "translation-proposals"
REPOSITORY = "yaqub0r/al-isabah"
TOOL_VERSION = "1.2.0"
FORMULA_REGISTRY_VERSION = "1.2.0"

ASSIGNMENT_START = "<!-- al-isabah-translation-assignment:v1"
ASSIGNMENT_END = "-->"
ENTRY_RE = re.compile(r"^###\s+\$+\s+(\d+)\s+(.+?)\s*$")
STRUCTURE_RE = re.compile(r"^###\s+(\|+)\s*(.*?)\s*$")
EDITOR_RE = re.compile(r"^###\s+\|EDITOR\|\s*$")
OPENITI_CONTROL_RE = re.compile(r"^###\s+\|(PARATEXT|APPENDIX)\|\s*$")
PAGE_RE = re.compile(r"PageV(\d{2})P(\d{3})")
MILESTONE_RE = re.compile(r"\bms\d+\b")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
WINDOWS_PATH_RE = re.compile(r"(?:[A-Za-z]:\\|C:/Users/)", re.IGNORECASE)
PRIVATE_KEYS = {"object_key", "local_path", "private_url", "credential", "token"}
EXPECTED_POLICY_IDS = {
    "translation-quality-workflow",
    "al-isabah-translation-profile",
    "entry-title-structure",
    "translation-source-profile",
}
OPENITI_POETRY_MARKER_RE = re.compile(r"(?<!\S)%(?!\S)")
JSON_PATH_TOKEN_RE = re.compile(r"([A-Za-z][A-Za-z0-9_]*)|\[(\d+)\]")
PUBLIC_PROCESS_TERMS = (
    "pinned OpenITI",
    "pinned wording",
    "pinned text",
    "pinned unit",
)
UNRESOLVED_SEVERITIES = {"minor", "material", "blocking", "source_reported"}
WITNESS_ROLES = {
    "alternative_edition",
    "translation_witness",
    "collateral_work",
    "lexical_reference",
    "same_authority",
    "discovery_check",
}

# Longer forms must precede forms that they contain. The registry is kept in
# executable form so the packet can persist a per-occurrence semantic audit
# without relying on an application or database.
FORMULA_RULES = (
    {
        "source": "صلى الله عليه وعليهم صلاة خالدة ، وسلاما مؤبدا [ وسلم تسليما ]",
        "target": (
            "May God bless him and them with an everlasting blessing and grant "
            "them perpetual peace [and fullest peace]."
        ),
        "semanticClass": "contextual_prayer_and_peace_invocation",
        "referentScope": "the Prophet and his Companions",
        "grammaticalAgreement": "masculine singular and masculine plural",
        "expandedArabic": (
            "صلى الله عليه وعليهم صلاة خالدة ، وسلاما مؤبدا [ وسلم تسليما ]"
        ),
    },
    {
        "source": "صلى الله تعالى عليه وعلى آله وسلم",
        "target": "﵌",
        "semanticClass": "prophetic_blessing_with_family",
        "referentScope": "the Prophet and his family",
        "grammaticalAgreement": "masculine singular with family inclusion",
        "expandedArabic": "صلى الله تعالى عليه وعلى آله وسلم",
    },
    # The locked source has one transparent OCR substitution in the formula.
    {
        "source": "صلى الله علسه وسلم",
        "target": "ﷺ",
        "semanticClass": "prophetic_blessing",
        "referentScope": "the Prophet",
        "grammaticalAgreement": "masculine singular",
        "expandedArabic": "صلى الله عليه وسلم",
    },
    {
        "source": "صلى آله عليه وسلم",
        "target": "ﷺ",
        "semanticClass": "prophetic_blessing",
        "referentScope": "the Prophet",
        "grammaticalAgreement": "masculine singular",
        "expandedArabic": "صلى الله عليه وسلم",
    },
    {
        "source": "صلى الله عليه وعلى آله وسلم",
        "target": "﵌",
        "semanticClass": "prophetic_blessing_with_family",
        "referentScope": "the Prophet and his family",
        "grammaticalAgreement": "masculine singular with family inclusion",
        "expandedArabic": "صلى الله عليه وعلى آله وسلم",
    },
    {
        "source": "صلى الله عليه وآله وسلم",
        "target": "﵌",
        "semanticClass": "prophetic_blessing_with_family",
        "referentScope": "the Prophet and his family",
        "grammaticalAgreement": "masculine singular with family inclusion",
        "expandedArabic": "صلى الله عليه وآله وسلم",
    },
    {
        "source": "صلى الله عليه وسلم",
        "target": "ﷺ",
        "semanticClass": "prophetic_blessing",
        "referentScope": "the Prophet",
        "grammaticalAgreement": "masculine singular",
        "expandedArabic": "صلى الله عليه وسلم",
    },
    {
        "source": "رضي الله عنهما",
        "target": "﵄",
        "semanticClass": "divine_approval",
        "referentScope": "the two immediately preceding referents",
        "grammaticalAgreement": "dual",
        "expandedArabic": "رضي الله عنهما",
    },
    {
        "source": "رضي الله عنهم",
        "target": "﵃",
        "semanticClass": "divine_approval",
        "referentScope": "the immediately preceding group",
        "grammaticalAgreement": "masculine plural",
        "expandedArabic": "رضي الله عنهم",
    },
    {
        "source": "رضي الله عنهن",
        "target": "﵅",
        "semanticClass": "divine_approval",
        "referentScope": "the immediately preceding group",
        "grammaticalAgreement": "feminine plural",
        "expandedArabic": "رضي الله عنهن",
    },
    {
        "source": "رضي الله عنها",
        "target": "﵂",
        "semanticClass": "divine_approval",
        "referentScope": "the immediately preceding female referent",
        "grammaticalAgreement": "feminine singular",
        "expandedArabic": "رضي الله عنها",
    },
    {
        "source": "رضي الله عنه",
        "target": "﵁",
        "semanticClass": "divine_approval",
        "referentScope": "the immediately preceding male referent",
        "grammaticalAgreement": "masculine singular",
        "expandedArabic": "رضي الله عنه",
    },
    {
        "source": "رحمهم الله",
        "target": "﵏",
        "semanticClass": "mercy_invocation",
        "referentScope": "the immediately preceding group",
        "grammaticalAgreement": "plural",
        "expandedArabic": "رحمهم الله",
    },
    {
        "source": "رحمه الله",
        "target": "﵀",
        "semanticClass": "mercy_invocation",
        "referentScope": "the immediately preceding male referent",
        "grammaticalAgreement": "masculine singular",
        "expandedArabic": "رحمه الله",
    },
    {
        "source": "عليهما السلام",
        "target": "﵉",
        "semanticClass": "peace_invocation",
        "referentScope": "the two immediately preceding referents",
        "grammaticalAgreement": "dual",
        "expandedArabic": "عليهما السلام",
    },
    {
        "source": "عليهم السلام",
        "target": "﵈",
        "semanticClass": "peace_invocation",
        "referentScope": "the immediately preceding group",
        "grammaticalAgreement": "plural",
        "expandedArabic": "عليهم السلام",
    },
    {
        "source": "عليه الصلاة والسلام",
        "target": "﵊",
        "semanticClass": "prayer_and_peace_invocation",
        "referentScope": "the immediately preceding prophetic referent",
        "grammaticalAgreement": "masculine singular",
        "expandedArabic": "عليه الصلاة والسلام",
    },
    {
        "source": "عليه السلام",
        "target": "﵇",
        "semanticClass": "peace_invocation",
        "referentScope": "the immediately preceding prophetic referent",
        "grammaticalAgreement": "masculine singular",
        "expandedArabic": "عليه السلام",
    },
    {
        "source": "إن شاء الله تعالى",
        "target": "إن شاء الله تعالى",
        "semanticClass": "divine_will_qualification",
        "referentScope": "God",
        "grammaticalAgreement": "not_applicable",
        "expandedArabic": "إن شاء الله تعالى",
    },
    {
        "source": "إن شاء الله",
        "target": "إن شاء الله",
        "semanticClass": "divine_will_qualification",
        "referentScope": "God",
        "grammaticalAgreement": "not_applicable",
        "expandedArabic": "إن شاء الله",
    },
    {
        "source": "سبحانه وتعالى",
        "target": "سبحانه وتعالى",
        "semanticClass": "divine_exaltation",
        "referentScope": "God",
        "grammaticalAgreement": "not_applicable",
        "expandedArabic": "سبحانه وتعالى",
    },
    {
        "source": "تبارك وتعالى",
        "target": "﵎",
        "semanticClass": "divine_exaltation",
        "referentScope": "God",
        "grammaticalAgreement": "not_applicable",
        "expandedArabic": "تبارك وتعالى",
    },
    {
        "source": "والله أعلم",
        "target": "والله أعلم",
        "semanticClass": "divine_knowledge_qualification",
        "referentScope": "God",
        "grammaticalAgreement": "not_applicable",
        "expandedArabic": "والله أعلم",
    },
    {
        "source": "الله أعلم",
        "target": "الله أعلم",
        "semanticClass": "divine_knowledge_qualification",
        "referentScope": "God",
        "grammaticalAgreement": "not_applicable",
        "expandedArabic": "الله أعلم",
    },
    {
        "source": "عز وجل",
        "target": "﷿",
        "semanticClass": "divine_exaltation",
        "referentScope": "God",
        "grammaticalAgreement": "not_applicable",
        "expandedArabic": "عز وجل",
    },
)

# The compact display value never stands alone as the semantic record. Keep a
# target-language expansion for accessibility, search, copy, and review. This
# tuple is intentionally parallel to FORMULA_RULES, whose order is already
# semantically significant because longer source forms must be matched first.
FORMULA_ACCESSIBLE_ENGLISH = (
    "May God bless him and them with an everlasting blessing and grant them perpetual peace [and fullest peace].",
    "May God bless him and his family and grant them peace.",
    "May God bless him and grant him peace.",
    "May God bless him and grant him peace.",
    "May God bless him and his family and grant them peace.",
    "May God bless him and his family and grant them peace.",
    "May God bless him and grant him peace.",
    "May God be pleased with both of them.",
    "May God be pleased with them.",
    "May God be pleased with them.",
    "May God be pleased with her.",
    "May God be pleased with him.",
    "May God have mercy on them.",
    "May God have mercy on him.",
    "Peace be upon both of them.",
    "Peace be upon them.",
    "May blessings and peace be upon him.",
    "Peace be upon him.",
    "God willing, exalted is He.",
    "God willing.",
    "Glory be to Him, the Exalted.",
    "Blessed and exalted is He.",
    "And God knows best.",
    "God knows best.",
    "Mighty and majestic is He.",
)
if len(FORMULA_ACCESSIBLE_ENGLISH) != len(FORMULA_RULES):
    raise RuntimeError("formula accessibility registry is out of sync")
FORMULA_RULES = tuple(
    {**rule, "accessibleEnglish": accessible}
    for rule, accessible in zip(FORMULA_RULES, FORMULA_ACCESSIBLE_ENGLISH)
)


class WorkflowError(ValueError):
    """A deterministic translation-workflow failure."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def canonical_text_sha256(path: Path) -> str:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace(
        "\r", "\n"
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def bytes_sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def text_sha256(value: str) -> str:
    return bytes_sha256(value.encode("utf-8"))


def registered_occurrences(text: str, field: str) -> list[dict[str, Any]]:
    """Return non-overlapping formula occurrences, preferring longer forms."""
    if field == "target":
        values = sorted(
            {
                str(value)
                for rule in FORMULA_RULES
                for value in (rule["target"], rule["expandedArabic"])
            },
            key=len,
            reverse=True,
        )
    else:
        values = sorted({str(rule[field]) for rule in FORMULA_RULES}, key=len, reverse=True)
    pattern = re.compile("|".join(re.escape(value) for value in values))
    occurrences: list[dict[str, Any]] = []
    for match in pattern.finditer(text):
        value = match.group(0)
        if field == "target":
            rule = next(
                rule
                for rule in FORMULA_RULES
                if value in {rule["target"], rule["expandedArabic"]}
            )
        else:
            rule = next(rule for rule in FORMULA_RULES if rule[field] == value)
        occurrences.append(
            {
                "start": match.start(),
                "end": match.end(),
                "value": value,
                "rule": rule,
            }
        )
    return occurrences


def formula_inventory(packet: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Build the exact per-occurrence semantic formula inventory."""
    errors: list[str] = []
    occurrences: list[dict[str, Any]] = []

    def add_record(
        record_id: str,
        source_field: str,
        source_text: str | None,
        blind_text: str | None,
        adjudicated_text: str | None,
    ) -> None:
        if not source_text:
            return
        source_hits = registered_occurrences(source_text, "source")
        blind_hits = registered_occurrences(blind_text or "", "target")
        adjudicated_hits = registered_occurrences(adjudicated_text or "", "target")
        expected_classes = [
            (
                hit["rule"]["semanticClass"],
                hit["rule"]["referentScope"],
                hit["rule"]["grammaticalAgreement"],
                hit["rule"]["accessibleEnglish"],
            )
            for hit in source_hits
        ]
        blind_classes = [
            (
                hit["rule"]["semanticClass"],
                hit["rule"]["referentScope"],
                hit["rule"]["grammaticalAgreement"],
                hit["rule"]["accessibleEnglish"],
            )
            for hit in blind_hits
        ]
        adjudicated_classes = [
            (
                hit["rule"]["semanticClass"],
                hit["rule"]["referentScope"],
                hit["rule"]["grammaticalAgreement"],
                hit["rule"]["accessibleEnglish"],
            )
            for hit in adjudicated_hits
        ]
        if blind_classes != expected_classes:
            errors.append(
                f"{record_id}: blind devotional formulas do not match source order "
                f"({len(blind_classes)} target, {len(expected_classes)} source)"
            )
        if adjudicated_classes != expected_classes:
            errors.append(
                f"{record_id}: adjudicated devotional formulas do not match source order "
                f"({len(adjudicated_classes)} target, {len(expected_classes)} source)"
            )
        if blind_classes != expected_classes or adjudicated_classes != expected_classes:
            return
        for index, (source_hit, blind_hit, adjudicated_hit) in enumerate(
            zip(source_hits, blind_hits, adjudicated_hits), start=1
        ):
            rule = source_hit["rule"]
            occurrences.append(
                {
                    "formulaId": (
                        f"{record_id}-{source_field}-formula-{index:03d}"
                    ),
                    "recordId": record_id,
                    "sourceField": source_field,
                    "sourceStart": source_hit["start"],
                    "sourceEnd": source_hit["end"],
                    "observedArabic": source_hit["value"],
                    "semanticClass": rule["semanticClass"],
                    "referentScope": rule["referentScope"],
                    "grammaticalAgreement": rule["grammaticalAgreement"],
                    "expandedArabic": rule["expandedArabic"],
                    "targetRealization": adjudicated_hit["value"],
                    "accessibleEnglish": rule["accessibleEnglish"],
                    "blindStart": blind_hit["start"],
                    "blindEnd": blind_hit["end"],
                    "adjudicatedStart": adjudicated_hit["start"],
                    "adjudicatedEnd": adjudicated_hit["end"],
                }
            )

    for entry in packet.get("entries", []):
        if not isinstance(entry, dict):
            continue
        source = entry.get("source", {})
        for segment, translation in zip(
            source.get("precedingSegments", []),
            entry.get("precedingTranslations", []),
        ):
            if not isinstance(segment, dict) or not isinstance(translation, dict):
                continue
            record_id = str(segment.get("segmentId"))
            blind = translation.get("blindTranslation", {})
            adjudication = translation.get("adjudication", {})
            add_record(
                record_id,
                "headingArabic",
                segment.get("headingArabic"),
                blind.get("headingEnglish"),
                adjudication.get("headingEnglish"),
            )
            add_record(
                record_id,
                "arabic",
                segment.get("arabic"),
                blind.get("english"),
                adjudication.get("english"),
            )
        add_record(
            str(entry.get("sourceUnitId")),
            "arabic",
            source.get("arabic"),
            entry.get("blindTranslation", {}).get("english"),
            entry.get("adjudication", {}).get("english"),
        )
    formula_ids = [item["formulaId"] for item in occurrences]
    if len(formula_ids) != len(set(formula_ids)):
        errors.append("formula inventory: formula IDs must be globally unique")
    return (
        {
            "status": "complete",
            "registryVersion": FORMULA_REGISTRY_VERSION,
            "occurrences": occurrences,
        },
        errors,
    )


def validate_names(
    names: dict[str, Any],
    source: dict[str, Any],
    record_id: str,
    prefix: str,
    require_spans: bool,
) -> list[str]:
    """Validate one-person candidates and source-exact mention spans."""
    errors: list[str] = []
    candidates = names.get("candidates")
    mentions = names.get("mentions")
    if names.get("status") != "complete" or not isinstance(candidates, list):
        return [f"{prefix}: durable name candidates are incomplete"]
    if not isinstance(mentions, list):
        return [f"{prefix}: name mentions must be an array"]
    candidate_by_id: dict[str, dict[str, Any]] = {}
    source_fields = {
        "headingArabic": source.get("headingArabic") or "",
        "arabic": source.get("arabic") or "",
        "rawOpeniti": source.get("rawOpeniti") or "",
    }
    for candidate in candidates:
        if not isinstance(candidate, dict):
            errors.append(f"{prefix}: name candidate must be an object")
            continue
        candidate_id = candidate.get("candidateId")
        observed = candidate.get("observedArabic")
        proposed = candidate.get("proposedEnglish")
        if not isinstance(candidate_id, str) or not candidate_id:
            errors.append(f"{prefix}: name candidate ID is required")
            continue
        if candidate_id in candidate_by_id:
            errors.append(f"{prefix}: name candidate IDs must be unique")
        candidate_by_id[candidate_id] = candidate
        if not isinstance(observed, str) or not observed:
            errors.append(f"{prefix}: {candidate_id} has no observed Arabic")
        elif not any(observed in value for value in source_fields.values()):
            errors.append(f"{prefix}: {candidate_id} observed Arabic is not source-exact")
        if isinstance(observed, str) and ("؛" in observed or ";" in observed):
            errors.append(f"{prefix}: {candidate_id} bundles multiple observed names")
        if isinstance(observed, str) and any(
            marker in observed for marker in ("~~", "#META#", "PageV")
        ):
            errors.append(f"{prefix}: {candidate_id} observed Arabic leaks OpenITI markup")
        if not isinstance(proposed, str) or not proposed.strip():
            errors.append(f"{prefix}: {candidate_id} has no proposed English form")
        if not isinstance(candidate.get("aliases"), list) or not all(
            isinstance(alias, str) and alias.strip()
            for alias in candidate.get("aliases", [])
        ):
            errors.append(f"{prefix}: {candidate_id} aliases must be nonempty strings")
        if not isinstance(candidate.get("confidenceEvidence"), list) or not all(
            isinstance(item, str) and item.strip()
            for item in candidate.get("confidenceEvidence", [])
        ):
            errors.append(
                f"{prefix}: {candidate_id} confidence evidence must be strings"
            )
        if candidate.get("reviewState") not in {"unreviewed", "needs_attention"}:
            errors.append(f"{prefix}: {candidate_id} review state is invalid")
        if "observedVariants" in candidate and (
            not isinstance(candidate["observedVariants"], list)
            or not all(
                isinstance(variant, str) and variant.strip()
                for variant in candidate["observedVariants"]
            )
        ):
            errors.append(f"{prefix}: {candidate_id} observed variants are invalid")
        if candidate.get("entityType", "person") not in {"person", "collective"}:
            errors.append(f"{prefix}: {candidate_id} entity type is invalid")
    mentioned: set[str] = set()
    mention_ids: set[str] = set()
    for mention in mentions:
        if not isinstance(mention, dict):
            errors.append(f"{prefix}: name mention must be an object")
            continue
        candidate_id = mention.get("candidateId")
        candidate = candidate_by_id.get(str(candidate_id))
        if candidate is None:
            errors.append(f"{prefix}: name mention references an unknown candidate")
            continue
        mentioned.add(str(candidate_id))
        mention_id = mention.get("mentionId")
        if not isinstance(mention_id, str) or not mention_id:
            errors.append(f"{prefix}: name mention ID is required")
        elif mention_id in mention_ids:
            errors.append(f"{prefix}: name mention IDs must be unique")
        else:
            mention_ids.add(mention_id)
        if not isinstance(mention.get("originCandidateId"), str) or not mention[
            "originCandidateId"
        ]:
            errors.append(f"{prefix}: name mention origin is required")
        if mention.get("recordId") != record_id:
            errors.append(f"{prefix}: name mention references the wrong source record")
        if not mention.get("location"):
            errors.append(f"{prefix}: name mention location is required")
        if not require_spans:
            continue
        spans = mention.get("sourceSpans")
        if not isinstance(spans, list) or not spans:
            errors.append(f"{prefix}: {candidate_id} mention lacks exact source spans")
            continue
        if not any(
            isinstance(span, dict)
            and span.get("sourceField") in {"headingArabic", "arabic"}
            for span in spans
        ):
            errors.append(
                f"{prefix}: {candidate_id} has no readable-source mention span"
            )
        for span in spans:
            if not isinstance(span, dict):
                errors.append(f"{prefix}: {candidate_id} mention span must be an object")
                continue
            field = span.get("sourceField")
            start = span.get("start")
            end = span.get("end")
            if field not in source_fields or not isinstance(start, int) or not isinstance(end, int):
                errors.append(f"{prefix}: {candidate_id} mention span is incomplete")
                continue
            text = source_fields[str(field)]
            if start < 0 or end <= start or end > len(text):
                errors.append(f"{prefix}: {candidate_id} mention source span is invalid")
                continue
            observed_span = text[start:end]
            if observed_span != candidate.get("observedArabic"):
                errors.append(
                    f"{prefix}: {candidate_id} mention span does not match observed Arabic"
                )
            if span.get("sha256") != text_sha256(observed_span):
                errors.append(f"{prefix}: {candidate_id} mention span hash is invalid")
    missing = set(candidate_by_id) - mentioned
    if missing:
        errors.append(f"{prefix}: every name candidate requires a mention")
    return errors


def validate_witness(
    witness: dict[str, Any], findings: list[Any], prefix: str, strict: bool
) -> list[str]:
    errors: list[str] = []
    results = witness.get("results")
    requires_witness = any(
        isinstance(finding, dict) and finding.get("requiresWitness") is True
        for finding in findings
    )
    if witness.get("status") not in {"complete", "not_required"}:
        errors.append(f"{prefix}: witness resolution is not final")
    if requires_witness and witness.get("status") != "complete":
        errors.append(f"{prefix}: material critique requires witness resolution")
    if not isinstance(results, list):
        return errors + [f"{prefix}: witness results must be an array"]
    if witness.get("status") == "complete" and not results:
        errors.append(f"{prefix}: completed witness resolution requires evidence")
    if witness.get("status") == "not_required" and results:
        errors.append(f"{prefix}: not-required witness resolution cannot contain results")
    canonical = {
        "status",
        "query",
        "witnessRole",
        "witnessIdentity",
        "passage",
        "passageSha256",
        "location",
        "evidenceKind",
        "evidenceSha256",
        "decision",
        "retrievedAt",
    }
    for index, result in enumerate(results, start=1):
        result_prefix = f"{prefix}, witness result {index}"
        if not isinstance(result, dict) or result.get("status") not in {"hit", "no_match"}:
            errors.append(f"{result_prefix}: status must be hit or no_match")
            continue
        if not strict:
            continue
        if set(result) != canonical:
            errors.append(f"{result_prefix}: provenance fields are not canonical")
            continue
        for field in ("query", "witnessIdentity", "passage", "location", "decision", "retrievedAt"):
            if not isinstance(result.get(field), str) or not result[field].strip():
                errors.append(f"{result_prefix}: {field} is required")
        if result.get("witnessRole") not in WITNESS_ROLES:
            errors.append(f"{result_prefix}: witnessRole is unclassified")
        if result.get("evidenceKind") not in {"passage", "artifact", "search_log"}:
            errors.append(f"{result_prefix}: evidenceKind is invalid")
        if not SHA256_RE.fullmatch(str(result.get("passageSha256", ""))):
            errors.append(f"{result_prefix}: passageSha256 is required")
        elif isinstance(result.get("passage"), str) and text_sha256(result["passage"]) != result["passageSha256"]:
            errors.append(f"{result_prefix}: passageSha256 does not match passage")
        if not SHA256_RE.fullmatch(str(result.get("evidenceSha256", ""))):
            errors.append(f"{result_prefix}: evidenceSha256 is required")
        elif (
            result.get("evidenceKind") == "passage"
            and result.get("evidenceSha256") != result.get("passageSha256")
        ):
            errors.append(
                f"{result_prefix}: passage evidence hash must match passageSha256"
            )
        retrieved_at = result.get("retrievedAt")
        if isinstance(retrieved_at, str) and retrieved_at.strip():
            try:
                datetime.fromisoformat(retrieved_at.replace("Z", "+00:00"))
            except ValueError:
                errors.append(f"{result_prefix}: retrievedAt must be an ISO date or time")
    return errors


def validate_unresolved(
    unresolved: Any, prefix: str, strict: bool
) -> list[str]:
    if not isinstance(unresolved, list):
        return [f"{prefix}: unresolved findings must be an array"]
    if not strict:
        return []
    errors: list[str] = []
    expected = {"kind", "description", "severity", "location", "disposition"}
    for index, finding in enumerate(unresolved, start=1):
        item_prefix = f"{prefix}, unresolved item {index}"
        if not isinstance(finding, dict) or set(finding) != expected:
            errors.append(f"{item_prefix}: fields are not canonical")
            continue
        for field in ("kind", "description", "location", "disposition"):
            if not isinstance(finding.get(field), str) or not finding[field].strip():
                errors.append(f"{item_prefix}: {field} is required")
        if finding.get("severity") not in UNRESOLVED_SEVERITIES:
            errors.append(f"{item_prefix}: severity is unclassified")
    return errors


def validate_uncertainty_witness_alignment(
    unresolved: Any, witness: dict[str, Any], prefix: str
) -> list[str]:
    """Material uncertainty cannot bypass the witness gate."""
    if not isinstance(unresolved, list):
        return []
    material = any(
        isinstance(item, dict) and item.get("severity") in {"material", "blocking"}
        for item in unresolved
    )
    if not material:
        return []
    results = witness.get("results")
    if witness.get("status") != "complete" or not isinstance(results, list) or not results:
        return [f"{prefix}: material unresolved finding requires completed witness evidence"]
    return []


def validate_public_english(value: str | None, prefix: str) -> list[str]:
    if not value:
        return []
    errors: list[str] = []
    if OPENITI_POETRY_MARKER_RE.search(value):
        errors.append(f"{prefix}: raw OpenITI poetry marker leaked into English")
    for term in PUBLIC_PROCESS_TERMS:
        if term.lower() in value.lower():
            errors.append(f"{prefix}: internal process language leaked into English")
    return errors


def validate_schema_instance(
    value: Any,
    schema: dict[str, Any],
    root_schema: dict[str, Any] | None = None,
    path: str = "$",
) -> list[str]:
    """Validate the JSON-Schema subset used by the translation packet.

    The workflow intentionally has no third-party runtime dependency. Keeping
    this small validator beside the declared schema prevents the CLI from
    accepting additional properties or shapes that its own schema rejects.
    """
    root = root_schema or schema
    if "$ref" in schema:
        reference = schema["$ref"]
        if not isinstance(reference, str) or not reference.startswith("#/"):
            return [f"{path}: unsupported schema reference {reference!r}"]
        target: Any = root
        for token in reference[2:].split("/"):
            target = target[token.replace("~1", "/").replace("~0", "~")]
        return validate_schema_instance(value, target, root, path)

    if "anyOf" in schema:
        alternatives = [
            validate_schema_instance(value, branch, root, path)
            for branch in schema["anyOf"]
        ]
        if not any(not errors for errors in alternatives):
            return [f"{path}: value does not match any allowed schema"]

    errors: list[str] = []
    expected_type = schema.get("type")
    if expected_type:
        expected_types = (
            expected_type if isinstance(expected_type, list) else [expected_type]
        )
        matches = any(
            (
                kind == "object"
                and isinstance(value, dict)
                or kind == "array"
                and isinstance(value, list)
                or kind == "string"
                and isinstance(value, str)
                or kind == "integer"
                and isinstance(value, int)
                and not isinstance(value, bool)
                or kind == "number"
                and isinstance(value, (int, float))
                and not isinstance(value, bool)
                or kind == "boolean"
                and isinstance(value, bool)
                or kind == "null"
                and value is None
            )
            for kind in expected_types
        )
        if not matches:
            return [f"{path}: expected schema type {expected_type!r}"]

    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: value must equal {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: value is outside the declared enum")

    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            errors.append(f"{path}: string is shorter than minLength")
        pattern = schema.get("pattern")
        if pattern and re.search(pattern, value) is None:
            errors.append(f"{path}: string does not match the declared pattern")
        format_name = schema.get("format")
        if format_name == "date-time":
            if not re.fullmatch(
                r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})",
                value,
            ):
                errors.append(f"{path}: value is not an ISO date-time")
            else:
                try:
                    datetime.fromisoformat(value.replace("Z", "+00:00"))
                except ValueError:
                    errors.append(f"{path}: value is not an ISO date-time")
        elif format_name == "uri":
            parsed = urlparse(value)
            if not parsed.scheme or not (
                parsed.netloc or parsed.scheme.lower() in {"mailto", "urn"}
            ):
                errors.append(f"{path}: value is not an absolute URI")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: number is below the declared minimum")

    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errors.append(f"{path}: array is shorter than minItems")
        if schema.get("uniqueItems"):
            encoded = [
                json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                for item in value
            ]
            if len(encoded) != len(set(encoded)):
                errors.append(f"{path}: array items must be unique")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                errors.extend(
                    validate_schema_instance(item, item_schema, root, f"{path}[{index}]")
                )

    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for required in schema.get("required", []):
            if required not in value:
                errors.append(f"{path}: missing required property {required!r}")
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in properties:
                    errors.append(f"{path}: unexpected property {key!r}")
        for key, child_schema in properties.items():
            if key in value:
                errors.extend(
                    validate_schema_instance(
                        value[key], child_schema, root, f"{path}.{key}"
                    )
                )
    return errors


def present_openiti_arabic(value: str) -> str:
    """Turn OpenITI poetry delimiters into visible line boundaries."""
    return OPENITI_POETRY_MARKER_RE.sub("<br />\n", value)


def json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkflowError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise WorkflowError(f"{path}: top level must be an object")
    return value


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="wb", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        temporary = Path(handle.name)
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def validate_source_manifest(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if manifest.get("schemaVersion") != "1.0.0":
        errors.append("source manifest: schemaVersion must be 1.0.0")
    if manifest.get("workId") != "ibn-hajar-al-isabah":
        errors.append("source manifest: workId must be ibn-hajar-al-isabah")
    if manifest.get("sourceId") != "openiti-jk000533-5835c183":
        errors.append("source manifest: sourceId is not the approved authority")
    download = manifest.get("download")
    if not isinstance(download, dict):
        errors.append("source manifest: download must be an object")
        return errors
    url = download.get("url")
    if not isinstance(url, str) or not url.startswith("https://raw.githubusercontent.com/"):
        errors.append("source manifest: URL must use raw.githubusercontent.com over HTTPS")
    filename = download.get("filename")
    if (
        not isinstance(filename, str)
        or not filename
        or Path(filename).name != filename
    ):
        errors.append("source manifest: filename must be a safe basename")
    if not isinstance(download.get("bytes"), int) or download["bytes"] < 1:
        errors.append("source manifest: bytes must be positive")
    if not SHA256_RE.fullmatch(str(download.get("sha256", ""))):
        errors.append("source manifest: sha256 must be a SHA-256")
    source = manifest.get("sourceRevision")
    if not isinstance(source, dict) or not re.fullmatch(
        r"[0-9a-f]{40}", str(source.get("commit", ""))
    ):
        errors.append("source manifest: sourceRevision.commit must be a full Git SHA")
    if manifest.get("license", {}).get("spdx") != "CC-BY-NC-SA-4.0":
        errors.append("source manifest: expected CC-BY-NC-SA-4.0")
    inventory = manifest.get("inventory")
    if not isinstance(inventory, dict):
        errors.append("source manifest: inventory must be an object")
    else:
        for field in ("sourceUnits", "uniquePrintedEntryNumbers"):
            if not isinstance(inventory.get(field), int) or inventory[field] < 1:
                errors.append(f"source manifest: inventory.{field} must be positive")
        duplicates = inventory.get("duplicatedPrintedEntryNumbers")
        if not isinstance(duplicates, list) or not all(
            isinstance(number, int) and number > 0 for number in duplicates
        ):
            errors.append(
                "source manifest: duplicatedPrintedEntryNumbers must be an integer array"
            )
    return errors


def default_source_path(manifest: dict[str, Any]) -> Path:
    return RUNTIME_ROOT / "sources" / manifest["download"]["filename"]


def verify_source(path: Path, manifest: dict[str, Any]) -> list[str]:
    errors = validate_source_manifest(manifest)
    if errors:
        return errors
    if not path.is_file():
        return [f"source: missing {path}"]
    expected = manifest["download"]
    size = path.stat().st_size
    if size != expected["bytes"]:
        errors.append(f"source: expected {expected['bytes']} bytes, found {size}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != expected["sha256"]:
        errors.append("source: SHA-256 does not match the pinned authority")
    return errors


def hydrate_source(
    manifest_path: Path,
    destination: Path | None = None,
    from_file: Path | None = None,
) -> Path:
    manifest = load_json(manifest_path)
    errors = validate_source_manifest(manifest)
    if errors:
        raise WorkflowError("\n".join(errors))
    target = destination or default_source_path(manifest)
    if target.exists() and not verify_source(target, manifest):
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="wb", dir=target.parent, prefix=f".{target.name}.", delete=False
    ) as handle:
        temporary = Path(handle.name)
        if from_file is not None:
            with from_file.open("rb") as source_handle:
                shutil.copyfileobj(source_handle, handle)
        else:
            request = urllib.request.Request(
                manifest["download"]["url"],
                headers={"User-Agent": "al-isabah-translation-workflow/1"},
            )
            with urllib.request.urlopen(request, timeout=90) as response:
                shutil.copyfileobj(response, handle)
        handle.flush()
        os.fsync(handle.fileno())
    errors = verify_source(temporary, manifest)
    if errors:
        temporary.unlink(missing_ok=True)
        raise WorkflowError("\n".join(errors))
    os.replace(temporary, target)
    return target


def source_locations(
    raw_lines: Iterable[str], fallback: tuple[int, int] | None
) -> list[dict[str, int]]:
    locations: list[dict[str, int]] = []
    seen: set[tuple[int, int]] = set()
    if fallback is not None:
        seen.add(fallback)
        locations.append({"volume": fallback[0], "page": fallback[1]})
    for line in raw_lines:
        for volume, page in PAGE_RE.findall(line):
            key = (int(volume), int(page))
            if key not in seen:
                seen.add(key)
                locations.append({"volume": key[0], "page": key[1]})
    return locations


def readable_arabic(number: int, raw_lines: list[str]) -> tuple[str, list[str]]:
    paragraphs: list[str] = []
    structure: list[str] = []
    for index, raw in enumerate(raw_lines):
        line = raw.strip()
        if index == 0:
            match = ENTRY_RE.match(line)
            if not match or int(match.group(1)) != number:
                raise WorkflowError(f"entry {number}: malformed opening marker")
            line = match.group(2)
        elif line.startswith("###"):
            structure.append(line)
            continue
        continuation = line.startswith("~~")
        if continuation:
            line = line[2:]
        elif line.startswith("# "):
            line = line[2:]
        line = PAGE_RE.sub(" ", line)
        line = MILESTONE_RE.sub(" ", line)
        line = re.sub(r"\s*\|\s*", " ", line)
        line = re.sub(r"\s+", " ", line).strip()
        if not line:
            continue
        if continuation and paragraphs:
            paragraphs[-1] = f"{paragraphs[-1]} {line}"
        else:
            paragraphs.append(line)
    return "\n\n".join(paragraphs), structure


def readable_openiti_prose(raw_lines: list[str]) -> str:
    """Remove OpenITI layout syntax while preserving substantive prose order."""
    paragraphs: list[str] = []
    for raw in raw_lines:
        line = raw.strip()
        continuation = line.startswith("~~")
        if continuation:
            line = line[2:]
        elif line.startswith("# "):
            line = line[2:]
        line = PAGE_RE.sub(" ", line)
        line = MILESTONE_RE.sub(" ", line)
        line = re.sub(r"\s*\|\s*", " ", line)
        line = re.sub(r"\s+", " ", line).strip()
        if not line:
            continue
        if continuation and paragraphs:
            paragraphs[-1] = f"{paragraphs[-1]} {line}"
        else:
            paragraphs.append(line)
    return "\n\n".join(paragraphs)


def preceding_segment(
    raw_lines: list[str],
    line_start: int,
    start_page: tuple[int, int] | None,
    following_ordinal: int,
    segment_index: int,
) -> dict[str, Any] | None:
    """Create one source-locked unit occurring immediately before an entry.

    OpenITI container metadata and its explicit paratext classes are removed by
    the caller before this function receives substantive book text.
    """
    first = raw_lines[0].strip()
    structure_match = STRUCTURE_RE.match(first)
    heading_level: int | None = None
    heading_arabic: str | None = None
    kind = "front_matter" if following_ordinal == 1 else "interstitial_prose"
    body_lines = raw_lines
    if structure_match:
        heading_level = len(structure_match.group(1))
        marker_text = structure_match.group(2).strip()
        kind = "structural_heading"
        heading_arabic = marker_text
        body_lines = raw_lines[1:]
    arabic = readable_openiti_prose(body_lines)
    if not heading_arabic and not arabic:
        return None
    raw = "\n".join(raw_lines) + "\n"
    return {
        "segmentId": (
            f"openiti-5835c183-before-unit-{following_ordinal:06d}-"
            f"segment-{segment_index:03d}"
        ),
        "kind": kind,
        "lineStart": line_start,
        "lineEnd": line_start + len(raw_lines) - 1,
        "locations": source_locations(raw_lines, start_page),
        "rawOpeniti": raw,
        "rawSha256": bytes_sha256(raw.encode("utf-8")),
        "headingLevel": heading_level,
        "headingArabic": heading_arabic,
        "arabic": arabic,
    }


def source_scope_exclusions(path: Path) -> list[dict[str, Any]]:
    """Record non-book container material excluded before parsing source text."""
    lines = path.read_text(encoding="utf-8").splitlines()
    try:
        end_index = lines.index("#META#Header#End#")
    except ValueError as exc:
        raise WorkflowError("source: OpenITI metadata terminator is missing") from exc
    raw = "\n".join(lines[: end_index + 1]) + "\n"
    exclusions = [
        {
            "kind": "openiti_metadata",
            "lineStart": 1,
            "lineEnd": end_index + 1,
            "rawSha256": bytes_sha256(raw.encode("utf-8")),
            "reason": "OpenITI container metadata, not authored book text",
        }
    ]
    index = end_index + 1
    while index < len(lines):
        if EDITOR_RE.match(lines[index]):
            range_end = index + 1
            while range_end < len(lines) and not lines[range_end].startswith("###"):
                range_end += 1
            raw = "\n".join(lines[index:range_end]) + "\n"
            exclusions.append(
                {
                    "kind": "modern_paratext",
                    "lineStart": index + 1,
                    "lineEnd": range_end,
                    "rawSha256": bytes_sha256(raw.encode("utf-8")),
                    "reason": (
                        "OpenITI EDITOR section; explicitly outside the authored "
                        "main-text translation scope"
                    ),
                }
            )
            index = range_end
            continue
        control = OPENITI_CONTROL_RE.match(lines[index])
        if control is None:
            index += 1
            continue
        raw = f"{lines[index]}\n"
        exclusions.append(
            {
                "kind": "openiti_control",
                "lineStart": index + 1,
                "lineEnd": index + 1,
                "rawSha256": bytes_sha256(raw.encode("utf-8")),
                "reason": (
                    f"OpenITI {control.group(1)} control marker; the following "
                    "source text remains in translation scope"
                ),
            }
        )
        index += 1
    return exclusions


def parse_openiti_entries(path: Path) -> list[dict[str, Any]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    entries: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    current_page: tuple[int, int] | None = None
    pending: dict[str, Any] | None = None
    pending_segments: list[dict[str, Any]] = []
    metadata_complete = False
    skipping_editor = False

    def finish_pending(end_line: int) -> None:
        nonlocal pending
        if pending is None:
            return
        while pending["rawLines"] and not pending["rawLines"][-1].strip():
            pending["rawLines"].pop()
        if pending["rawLines"]:
            pending["lineEnd"] = end_line
            pending_segments.append(pending)
        pending = None

    def finish(end_line: int) -> None:
        nonlocal current
        if current is None:
            return
        number = current["number"]
        ordinal = len(entries) + 1
        raw_lines = current["rawLines"]
        raw = "\n".join(raw_lines) + "\n"
        heading_match = ENTRY_RE.match(raw_lines[0])
        assert heading_match is not None
        arabic, inline_structure = readable_arabic(number, raw_lines)
        if inline_structure:
            raise WorkflowError(
                f"entry {number}: structural marker was not split from entry source"
            )
        entries.append({
            "sourceOrdinal": ordinal,
            "sourceEntryNumber": number,
            "sourceUnitId": f"openiti-5835c183-unit-{ordinal:06d}",
            "lineStart": current["lineStart"],
            "lineEnd": end_line,
            "locations": source_locations(raw_lines, current["startPage"]),
            "rawOpeniti": raw,
            "rawSha256": bytes_sha256(raw.encode("utf-8")),
            "headingArabic": heading_match.group(2).strip(),
            "arabic": arabic,
            "precedingSegments": current["precedingSegments"],
        })
        current = None

    for line_number, line in enumerate(lines, start=1):
        if not metadata_complete:
            if line == "#META#Header#End#":
                metadata_complete = True
            continue
        for volume, page in PAGE_RE.findall(line):
            current_page = (int(volume), int(page))
        if skipping_editor and not line.startswith("###"):
            continue
        if skipping_editor:
            skipping_editor = False
        if EDITOR_RE.match(line):
            finish(line_number - 1)
            finish_pending(line_number - 1)
            skipping_editor = True
            continue
        if OPENITI_CONTROL_RE.match(line):
            finish(line_number - 1)
            finish_pending(line_number - 1)
            continue
        match = ENTRY_RE.match(line)
        if match:
            finish(line_number - 1)
            finish_pending(line_number - 1)
            number = int(match.group(1))
            ordinal = len(entries) + 1
            material: list[dict[str, Any]] = []
            for segment in pending_segments:
                source_segment = preceding_segment(
                    segment["rawLines"],
                    segment["lineStart"],
                    segment["startPage"],
                    ordinal,
                    len(material) + 1,
                )
                if source_segment is not None:
                    material.append(source_segment)
            current = {
                "number": number,
                "lineStart": line_number,
                "startPage": current_page,
                "rawLines": [line],
                "precedingSegments": material,
            }
            pending_segments = []
        elif line.startswith("###"):
            finish(line_number - 1)
            finish_pending(line_number - 1)
            pending = {
                "lineStart": line_number,
                "startPage": current_page,
                "rawLines": [line],
            }
        elif current is not None:
            current["rawLines"].append(line)
        elif pending is not None:
            pending["rawLines"].append(line)
        elif line.strip():
            pending = {
                "lineStart": line_number,
                "startPage": current_page,
                "rawLines": [line],
            }
    finish(len(lines))
    if not metadata_complete:
        raise WorkflowError("source: OpenITI metadata terminator is missing")
    if not entries:
        raise WorkflowError("source: no OpenITI entry markers were found")
    return entries


def validate_source_inventory(
    entries: list[dict[str, Any]], manifest: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    inventory = manifest.get("inventory")
    if not isinstance(inventory, dict):
        return ["source manifest: inventory is required"]
    printed: dict[int, int] = {}
    for entry in entries:
        number = entry["sourceEntryNumber"]
        printed[number] = printed.get(number, 0) + 1
    duplicates = sorted(number for number, count in printed.items() if count > 1)
    if len(entries) != inventory.get("sourceUnits"):
        errors.append("source inventory: source-unit count differs from manifest")
    if len(printed) != inventory.get("uniquePrintedEntryNumbers"):
        errors.append("source inventory: unique printed-number count differs from manifest")
    if duplicates != inventory.get("duplicatedPrintedEntryNumbers"):
        errors.append("source inventory: duplicate printed-number set differs from manifest")
    return errors


def assignment_marker(value: dict[str, Any]) -> str:
    return f"{ASSIGNMENT_START}\n{json.dumps(value, sort_keys=True)}\n{ASSIGNMENT_END}"


def parse_assignment(body: str) -> dict[str, Any] | None:
    start = body.find(ASSIGNMENT_START)
    if start < 0:
        return None
    end = body.find(ASSIGNMENT_END, start)
    if end < 0:
        raise WorkflowError("assignment issue: marker is not closed")
    payload = body[start + len(ASSIGNMENT_START) : end].strip()
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise WorkflowError(f"assignment issue: invalid marker JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise WorkflowError("assignment issue: marker JSON must be an object")
    required = {
        "schemaVersion": "1.0.0",
        "workId": "ibn-hajar-al-isabah",
        "sourceId": "openiti-jk000533-5835c183",
        "contractId": "translation-quality-workflow",
    }
    for key, expected in required.items():
        if value.get(key) != expected:
            raise WorkflowError(f"assignment issue: {key} must be {expected}")
    start_unit = value.get("startUnit")
    end_unit = value.get("endUnit")
    if not isinstance(start_unit, int) or not isinstance(end_unit, int):
        raise WorkflowError("assignment issue: source-unit bounds must be integers")
    if start_unit < 1 or end_unit < start_unit:
        raise WorkflowError("assignment issue: invalid source-unit range")
    return value


def issue_assignees(issue: dict[str, Any]) -> list[str]:
    values = issue.get("assignees", [])
    return [
        item["login"]
        for item in values
        if isinstance(item, dict) and isinstance(item.get("login"), str)
    ]


def parse_claims(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for issue in issues:
        marker = parse_assignment(str(issue.get("body", "")))
        if marker is None:
            continue
        claims.append(
            {
                "number": issue.get("number"),
                "url": issue.get("url"),
                "state": str(issue.get("state", "")).upper(),
                "assignees": issue_assignees(issue),
                **marker,
            }
        )
    return claims


def overlapping_claims(
    claims: list[dict[str, Any]],
    start_unit: int,
    end_unit: int,
    exclude_issue: int | None = None,
) -> list[dict[str, Any]]:
    return [
        claim
        for claim in claims
        if claim.get("state") == "OPEN"
        and claim.get("number") != exclude_issue
        and start_unit <= claim["endUnit"]
        and claim["startUnit"] <= end_unit
    ]


def validate_live_assignment(
    packet: dict[str, Any], issue: dict[str, Any], claims: list[dict[str, Any]]
) -> list[str]:
    errors: list[str] = []
    assignment = packet.get("assignment", {})
    issue_number = assignment.get("issueNumber")
    if issue.get("number") != issue_number:
        errors.append("live assignment: issue number differs from packet")
        return errors
    if str(issue.get("state", "")).upper() != "OPEN":
        errors.append("live assignment: issue is not open")
    marker = parse_assignment(str(issue.get("body", "")))
    if marker is None:
        errors.append("live assignment: issue marker is missing")
        return errors
    if marker.get("startUnit") != assignment.get("startUnit") or marker.get(
        "endUnit"
    ) != assignment.get("endUnit"):
        errors.append("live assignment: claimed source-unit range changed")
    if sorted(issue_assignees(issue)) != sorted(assignment.get("claimedBy", [])):
        errors.append("live assignment: assignees changed; prepare a new packet")
    overlaps = overlapping_claims(
        claims,
        assignment.get("startUnit", 0),
        assignment.get("endUnit", 0),
        exclude_issue=issue_number,
    )
    if overlaps:
        errors.append(
            "live assignment: overlaps open claim(s): "
            + ", ".join(f"#{item['number']}" for item in overlaps)
        )
    return errors


def run_gh(arguments: list[str]) -> str:
    try:
        result = subprocess.run(
            ["gh", *arguments],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except FileNotFoundError as exc:
        raise WorkflowError("GitHub CLI (gh) is required for live assignment claims") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "gh failed").strip()
        raise WorkflowError(detail) from exc
    return result.stdout.strip()


def load_issues(path: Path | None = None) -> list[dict[str, Any]]:
    if path is not None:
        value = json.loads(path.read_text(encoding="utf-8"))
    else:
        value = json.loads(
            run_gh(
                [
                    "issue",
                    "list",
                    "--repo",
                    REPOSITORY,
                    "--state",
                    "open",
                    "--limit",
                    "1000",
                    "--json",
                    "number,url,state,body,assignees",
                ]
            )
        )
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise WorkflowError("assignment issue list must be an array of objects")
    return value


def load_issue(number: int, path: Path | None = None) -> dict[str, Any]:
    if path is not None:
        value = json.loads(path.read_text(encoding="utf-8"))
    else:
        value = json.loads(
            run_gh(
                [
                    "issue",
                    "view",
                    str(number),
                    "--repo",
                    REPOSITORY,
                    "--json",
                    "number,url,state,body,assignees,createdAt",
                ]
            )
        )
    if not isinstance(value, dict):
        raise WorkflowError("assignment issue must be an object")
    return value


def policy_snapshot(policy_path: Path) -> dict[str, Any]:
    policy = load_json(policy_path)
    if policy.get("schema") != "al-isabah.local-policy-binding.v1":
        raise WorkflowError("policy binding has an unexpected schema")
    authority = policy.get("authority", {})
    if authority.get("repository") != "https://github.com/yaqub0r/al-isabah":
        raise WorkflowError("policy binding is not owned by Al-Isabah")
    if authority.get("scope") != "repository-local":
        raise WorkflowError("policy binding is not repository-local")
    contracts = policy.get("contracts")
    if not isinstance(contracts, list) or not contracts:
        raise WorkflowError("policy binding contains no local contracts")
    ids = {
        contract.get("id")
        for contract in contracts
        if isinstance(contract, dict)
    }
    if ids != EXPECTED_POLICY_IDS:
        raise WorkflowError("policy binding does not contain every required policy")
    for contract in contracts:
        path = ROOT / str(contract.get("path", ""))
        if not path.is_file():
            raise WorkflowError(f"policy binding local file is missing: {path}")
        if canonical_text_sha256(path) != contract.get("sha256"):
            raise WorkflowError(f"policy binding hash is stale: {contract.get('id')}")
    return {
        "bindingPath": "compliance/policy-binding.v1.json",
        "bindingSha256": canonical_text_sha256(policy_path),
        "contracts": contracts,
    }


def pending_preceding_translation(
    segment: dict[str, Any], policy_sha256: str
) -> dict[str, Any]:
    return {
        "segmentId": segment["segmentId"],
        "blindTranslation": {
            "status": "pending",
            "runId": None,
            "model": None,
            "reasoning": None,
            "policySha256": policy_sha256,
            "headingEnglish": None,
            "english": None,
        },
        "independentCritique": {
            "status": "pending",
            "runId": None,
            "model": None,
            "findings": [],
        },
        "witnessResolution": {"status": "pending", "results": []},
        "adjudication": {
            "status": "pending",
            "headingEnglish": None,
            "english": None,
            "decisions": [],
        },
        "names": {"status": "pending", "candidates": [], "mentions": []},
        "unresolved": [],
        "humanReview": {"status": "unreviewed"},
    }


def build_packet(
    issue: dict[str, Any],
    claims: list[dict[str, Any]],
    source_path: Path,
    manifest_path: Path = DEFAULT_MANIFEST,
    policy_path: Path = DEFAULT_POLICY,
) -> dict[str, Any]:
    number = issue.get("number")
    if not isinstance(number, int):
        raise WorkflowError("assignment issue number is required")
    if str(issue.get("state", "")).upper() != "OPEN":
        raise WorkflowError("assignment issue must be open")
    marker = parse_assignment(str(issue.get("body", "")))
    if marker is None:
        raise WorkflowError("issue is not a translation assignment")
    assignees = issue_assignees(issue)
    if not assignees:
        raise WorkflowError("assignment issue must have at least one assignee")
    overlaps = overlapping_claims(
        claims, marker["startUnit"], marker["endUnit"], exclude_issue=number
    )
    if overlaps:
        numbers = ", ".join(f"#{item['number']}" for item in overlaps)
        raise WorkflowError(f"assignment overlaps open claim(s): {numbers}")

    manifest = load_json(manifest_path)
    errors = verify_source(source_path, manifest)
    if errors:
        raise WorkflowError("\n".join(errors))
    parsed = parse_openiti_entries(source_path)
    inventory_errors = validate_source_inventory(parsed, manifest)
    if inventory_errors:
        raise WorkflowError("\n".join(inventory_errors))
    if marker["endUnit"] > len(parsed):
        raise WorkflowError(
            f"source has {len(parsed)} units; assignment ends at {marker['endUnit']}"
        )
    selected = parsed[marker["startUnit"] - 1 : marker["endUnit"]]
    policy = policy_snapshot(policy_path)
    assignment = {
        "repository": REPOSITORY,
        "issueNumber": number,
        "issueUrl": issue.get("url"),
        "stateAtPreparation": "OPEN",
        "claimedBy": assignees,
        "startUnit": marker["startUnit"],
        "endUnit": marker["endUnit"],
        "printedEntryStart": selected[0]["sourceEntryNumber"],
        "printedEntryEnd": selected[-1]["sourceEntryNumber"],
        "createdAt": issue.get("createdAt"),
    }
    try:
        relative_manifest = manifest_path.resolve().relative_to(ROOT.resolve())
    except ValueError as exc:
        raise WorkflowError("source manifest must be tracked inside the repository") from exc
    source = {
        "manifestPath": str(relative_manifest).replace("\\", "/"),
        "manifestSha256": canonical_text_sha256(manifest_path),
        "sourceId": manifest["sourceId"],
        "repository": manifest["sourceRevision"]["repository"],
        "commit": manifest["sourceRevision"]["commit"],
        "path": manifest["sourceRevision"]["path"],
        "sha256": manifest["download"]["sha256"],
        "license": manifest["license"],
    }
    fingerprint = bytes_sha256(
        json_bytes({"assignment": assignment, "source": source, "policy": policy})
    )
    entries = []
    for source_entry in selected:
        entries.append(
            {
                "sourceOrdinal": source_entry["sourceOrdinal"],
                "sourceEntryNumber": source_entry["sourceEntryNumber"],
                "sourceUnitId": source_entry["sourceUnitId"],
                "canonicalEntryId": None,
                "source": source_entry,
                "precedingTranslations": [
                    pending_preceding_translation(
                        segment, policy["bindingSha256"]
                    )
                    for segment in source_entry["precedingSegments"]
                ],
                "blindTranslation": {
                    "status": "pending",
                    "runId": None,
                    "model": None,
                    "reasoning": None,
                    "policySha256": policy["bindingSha256"],
                    "english": None,
                },
                "independentCritique": {
                    "status": "pending",
                    "runId": None,
                    "model": None,
                    "findings": [],
                },
                "witnessResolution": {"status": "pending", "results": []},
                "adjudication": {"status": "pending", "english": None, "decisions": []},
                "names": {"status": "pending", "candidates": [], "mentions": []},
                "unresolved": [],
                "humanReview": {"status": "unreviewed"},
            }
        )
    return {
        "schemaVersion": "1.2.0",
        "packetId": f"isabah-translation-issue-{number}",
        "workId": "ibn-hajar-al-isabah",
        "toolVersion": TOOL_VERSION,
        "runId": f"translation-run-{fingerprint[:16]}",
        "assignment": assignment,
        "authority": source,
        "policy": policy,
        "scope": {
            "precedingMaterialOwnership": "following_source_unit",
            "excludedRanges": source_scope_exclusions(source_path),
        },
        "entries": entries,
        "formulaInventory": {
            "status": "pending",
            "registryVersion": FORMULA_REGISTRY_VERSION,
            "occurrences": [],
        },
        "postRunRepairAudit": {
            "status": "not_required",
            "basePacketSha256": None,
            "artifactSha256": None,
            "runId": None,
            "operations": [],
        },
        "reviewPresentation": {"status": "pending", "path": None, "sha256": None},
        "machineReadiness": {
            "status": "pending",
            "validatedAt": None,
            "validatorVersion": TOOL_VERSION,
        },
    }


def private_data_errors(value: Any, location: str = "$") -> list[str]:
    errors: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_location = f"{location}.{key}"
            if key.lower() in PRIVATE_KEYS:
                errors.append(f"{child_location}: private field is prohibited")
            errors.extend(private_data_errors(child, child_location))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            errors.extend(private_data_errors(child, f"{location}[{index}]"))
    elif isinstance(value, str) and WINDOWS_PATH_RE.search(value):
        errors.append(f"{location}: local absolute path is prohibited")
    return errors


def json_path_value(root: object, path: str) -> object:
    if not path.startswith("$."):
        raise WorkflowError(f"unsupported repair field path: {path}")
    current = root
    tokens = JSON_PATH_TOKEN_RE.findall(path[2:])
    if not tokens:
        raise WorkflowError(f"empty repair field path: {path}")
    for name, index in tokens:
        token: str | int = name if name else int(index)
        current = current[token]  # type: ignore[index]
    return current


def normalized_repair_record_kind(value: str) -> str:
    if value == "biography":
        return "entry"
    if value in {"entry", "structural"}:
        return value
    raise WorkflowError(f"unsupported repair record kind: {value}")


def validate_post_run_repair_audit(packet: dict[str, Any]) -> list[str]:
    audit = packet.get("postRunRepairAudit", {})
    status = audit.get("status")
    operations = audit.get("operations")
    if status == "not_required":
        if operations != [] or any(
            audit.get(field) is not None
            for field in ("basePacketSha256", "artifactSha256", "runId")
        ):
            return ["packet: not-required post-run repair audit must be empty"]
        return []
    if status != "complete" or not isinstance(operations, list) or not operations:
        return ["packet: post-run repair audit is incomplete"]
    if not all(
        SHA256_RE.fullmatch(str(audit.get(field, "")))
        for field in ("basePacketSha256", "artifactSha256")
    ):
        return ["packet: post-run repair audit hashes are invalid"]
    if not re.fullmatch(
        r"translation-repair-run-[0-9a-f]{16}", str(audit.get("runId", ""))
    ):
        return ["packet: post-run repair run ID is invalid"]

    errors: list[str] = []
    repair_ids: list[str] = []
    last_hash_by_path: dict[str, str] = {}
    for index, operation in enumerate(operations):
        prefix = f"packet post-run repair operation {index + 1}"
        repair_id = operation.get("repairId")
        if isinstance(repair_id, str):
            repair_ids.append(repair_id)
        path = operation.get("fieldPath")
        if not isinstance(path, str) or not (
            ".blindTranslation." in path or ".adjudication." in path
        ):
            errors.append(f"{prefix}: target must be blind or adjudicated output")
            continue
        path_tokens: list[str | int] = [
            name if name else int(array_index)
            for name, array_index in JSON_PATH_TOKEN_RE.findall(path[2:])
        ]
        try:
            entry_index = int(path_tokens[1])
            entry = packet["entries"][entry_index]
            if "precedingTranslations" in path_tokens:
                translation_token = path_tokens.index("precedingTranslations")
                translation_index = int(path_tokens[translation_token + 1])
                owner = entry["precedingTranslations"][translation_index]
                expected_kind = "structural"
                expected_segment_id = owner["segmentId"]
            else:
                expected_kind = "entry"
                expected_segment_id = None
            expected_stage = (
                "blind_translation"
                if ".blindTranslation." in path
                else "adjudication"
            )
        except (KeyError, IndexError, TypeError, ValueError):
            errors.append(f"{prefix}: field path owner is invalid")
            continue
        if operation.get("sourceUnitId") != entry.get("sourceUnitId"):
            errors.append(f"{prefix}: source unit metadata does not match field path")
        if operation.get("recordKind") != expected_kind:
            errors.append(f"{prefix}: record kind does not match field path")
        if operation.get("segmentId") != expected_segment_id:
            errors.append(f"{prefix}: segment metadata does not match field path")
        if operation.get("targetStage") != expected_stage:
            errors.append(f"{prefix}: target stage does not match field path")
        old_hash = operation.get("oldTextSha256")
        new_hash = operation.get("newTextSha256")
        if path in last_hash_by_path and old_hash != last_hash_by_path[path]:
            errors.append(f"{prefix}: repair hash chain is broken")
        last_hash_by_path[path] = str(new_hash)
    if len(repair_ids) != len(set(repair_ids)):
        errors.append("packet: post-run repair IDs must be unique")
    for path, expected_hash in last_hash_by_path.items():
        try:
            current = json_path_value(packet, path)
        except (KeyError, IndexError, TypeError, WorkflowError):
            errors.append(f"packet: post-run repair target is missing: {path}")
            continue
        if not isinstance(current, str) or text_sha256(current) != expected_hash:
            errors.append(f"packet: post-run repair target drifted: {path}")
    return errors


def validate_preceding_translation(
    translation: dict[str, Any],
    source: dict[str, Any],
    current_policy_sha256: str,
    prefix: str,
) -> list[str]:
    errors: list[str] = []
    blind = translation.get("blindTranslation", {})
    source_has_heading = bool(source.get("headingArabic"))
    source_has_body = bool(source.get("arabic"))
    if blind.get("status") != "complete":
        errors.append(f"{prefix}: blind translation is incomplete")
    if source_has_heading and not blind.get("headingEnglish"):
        errors.append(f"{prefix}: blind structural heading is untranslated")
    if source_has_body and not blind.get("english"):
        errors.append(f"{prefix}: blind substantive prose is untranslated")
    if not all(blind.get(field) for field in ("runId", "model", "reasoning")):
        errors.append(f"{prefix}: blind translation provenance is incomplete")
    if blind.get("policySha256") != current_policy_sha256:
        errors.append(f"{prefix}: blind translation used a stale policy")

    critique = translation.get("independentCritique", {})
    if critique.get("status") != "complete" or not critique.get("runId"):
        errors.append(f"{prefix}: independent critique is incomplete")
    if critique.get("runId") == blind.get("runId"):
        errors.append(f"{prefix}: critique must use a distinct run")
    if not isinstance(critique.get("findings"), list):
        errors.append(f"{prefix}: critique findings must be an array")

    findings = critique.get("findings", [])
    errors.extend(
        validate_witness(
            translation.get("witnessResolution", {}),
            findings if isinstance(findings, list) else [],
            prefix,
            strict=True,
        )
    )

    adjudication = translation.get("adjudication", {})
    if adjudication.get("status") != "complete":
        errors.append(f"{prefix}: adjudication is incomplete")
    if source_has_heading and not adjudication.get("headingEnglish"):
        errors.append(f"{prefix}: adjudicated structural heading is untranslated")
    if source_has_body and not adjudication.get("english"):
        errors.append(f"{prefix}: adjudicated substantive prose is untranslated")
    if not isinstance(adjudication.get("decisions"), list):
        errors.append(f"{prefix}: adjudication decisions must be an array")
    errors.extend(
        validate_public_english(blind.get("headingEnglish"), f"{prefix}, blind heading")
    )
    errors.extend(validate_public_english(blind.get("english"), f"{prefix}, blind"))
    errors.extend(
        validate_public_english(
            adjudication.get("headingEnglish"), f"{prefix}, adjudicated heading"
        )
    )
    errors.extend(
        validate_public_english(adjudication.get("english"), f"{prefix}, adjudicated")
    )

    errors.extend(
        validate_names(
            translation.get("names", {}),
            source,
            str(source.get("segmentId")),
            prefix,
            require_spans=True,
        )
    )
    unresolved = translation.get("unresolved")
    errors.extend(validate_unresolved(unresolved, prefix, strict=True))
    errors.extend(
        validate_uncertainty_witness_alignment(
            unresolved, translation.get("witnessResolution", {}), prefix
        )
    )
    if translation.get("humanReview", {}).get("status") != "unreviewed":
        errors.append(f"{prefix}: machine-ready work must remain human-unreviewed")
    return errors


def validate_entry_shard_output(
    output: dict[str, Any], current_policy_sha256: str, prefix: str
) -> list[str]:
    """Validate one completed biography output before merging a worker shard."""
    errors: list[str] = []
    expected = {
        "sourceOrdinal",
        "sourceUnitId",
        "blindTranslation",
        "independentCritique",
        "witnessResolution",
        "adjudication",
        "names",
        "unresolved",
        "humanReview",
    }
    if set(output) != expected:
        errors.append(f"{prefix}: shard output fields are incomplete or unexpected")

    blind = output.get("blindTranslation", {})
    if blind.get("status") != "complete" or not blind.get("english"):
        errors.append(f"{prefix}: blind translation is incomplete")
    if not all(blind.get(field) for field in ("runId", "model", "reasoning")):
        errors.append(f"{prefix}: blind translation provenance is incomplete")
    if blind.get("policySha256") != current_policy_sha256:
        errors.append(f"{prefix}: blind translation used a stale policy")

    critique = output.get("independentCritique", {})
    if critique.get("status") != "complete" or not critique.get("runId"):
        errors.append(f"{prefix}: independent critique is incomplete")
    if critique.get("runId") == blind.get("runId"):
        errors.append(f"{prefix}: critique must use a distinct run")
    findings = critique.get("findings")
    if not isinstance(findings, list):
        errors.append(f"{prefix}: critique findings must be an array")
        findings = []

    errors.extend(
        validate_witness(
            output.get("witnessResolution", {}), findings, prefix, strict=True
        )
    )

    adjudication = output.get("adjudication", {})
    if adjudication.get("status") != "complete" or not adjudication.get("english"):
        errors.append(f"{prefix}: adjudication is incomplete")
    if not isinstance(adjudication.get("decisions"), list):
        errors.append(f"{prefix}: adjudication decisions must be an array")
    errors.extend(validate_public_english(blind.get("english"), f"{prefix}, blind"))
    errors.extend(
        validate_public_english(adjudication.get("english"), f"{prefix}, adjudicated")
    )

    names = output.get("names", {})
    candidates = names.get("candidates")
    mentions = names.get("mentions")
    if (
        names.get("status") != "complete"
        or not isinstance(candidates, list)
        or not candidates
    ):
        errors.append(f"{prefix}: durable name candidates are incomplete")
        candidates = []
    candidate_ids: list[str] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            errors.append(f"{prefix}: name candidate must be an object")
            continue
        required_candidate = {
            "candidateId",
            "observedArabic",
            "proposedEnglish",
            "aliases",
            "confidenceEvidence",
            "reviewState",
        }
        if not required_candidate.issubset(candidate):
            errors.append(f"{prefix}: name candidate provenance is incomplete")
        candidate_id = candidate.get("candidateId")
        if not isinstance(candidate_id, str) or not candidate_id:
            errors.append(f"{prefix}: name candidate ID is required")
        else:
            candidate_ids.append(candidate_id)
        if not isinstance(candidate.get("aliases"), list) or not isinstance(
            candidate.get("confidenceEvidence"), list
        ):
            errors.append(f"{prefix}: name aliases and evidence must be arrays")
    if len(candidate_ids) != len(set(candidate_ids)):
        errors.append(f"{prefix}: name candidate IDs must be unique")
    if not isinstance(mentions, list):
        errors.append(f"{prefix}: name mentions must be an array")
    else:
        mentioned_ids: set[str] = set()
        for mention in mentions:
            if not isinstance(mention, dict):
                errors.append(f"{prefix}: name mention must be an object")
                continue
            candidate_id = mention.get("candidateId")
            mentioned_ids.add(str(candidate_id))
            if candidate_id not in candidate_ids:
                errors.append(f"{prefix}: name mention references an unknown candidate")
            if mention.get("recordId") != output.get("sourceUnitId"):
                errors.append(f"{prefix}: name mention references the wrong source unit")
            if not mention.get("location"):
                errors.append(f"{prefix}: name mention location is required")
            spans = mention.get("sourceSpans")
            if not isinstance(spans, list) or not spans:
                errors.append(f"{prefix}: name mention exact source spans are required")
        if set(candidate_ids) - mentioned_ids:
            errors.append(f"{prefix}: every name candidate requires a mention")

    unresolved = output.get("unresolved")
    errors.extend(validate_unresolved(unresolved, prefix, strict=True))
    errors.extend(
        validate_uncertainty_witness_alignment(
            unresolved, output.get("witnessResolution", {}), prefix
        )
    )
    if output.get("humanReview", {}).get("status") != "unreviewed":
        errors.append(f"{prefix}: machine work must remain human-unreviewed")
    errors.extend(private_data_errors(output, prefix))
    return errors


def merge_entry_shard(packet_path: Path, shard_path: Path) -> int:
    """Atomically merge one complete, non-overlapping worker shard."""
    packet = load_json(packet_path)
    shard = load_json(shard_path)
    errors: list[str] = []
    if packet.get("postRunRepairAudit", {}).get("status") == "complete":
        errors.append(
            "packet: cannot merge a shard after post-run repairs; rebuild from the "
            "pre-repair packet"
        )
    if packet.get("schemaVersion") != "1.2.0":
        errors.append("packet: entry shards require packet schema 1.2.0")
    if shard.get("schemaVersion") != "1.0.0":
        errors.append("shard: schemaVersion must be 1.0.0")
    if shard.get("packetId") != packet.get("packetId"):
        errors.append("shard: packetId does not match the target packet")
    assignment = packet.get("assignment", {})
    if shard.get("issueNumber") != assignment.get("issueNumber"):
        errors.append("shard: issueNumber does not match the target packet")
    start = shard.get("startUnit")
    end = shard.get("endUnit")
    if not isinstance(start, int) or not isinstance(end, int) or end < start:
        errors.append("shard: source-unit range is invalid")
        start = 1
        end = 0
    if start < assignment.get("startUnit", 1) or end > assignment.get("endUnit", 0):
        errors.append("shard: source-unit range is outside the assignment")
    outputs = shard.get("entries")
    if not isinstance(outputs, list):
        errors.append("shard: entries must be an array")
        outputs = []
    expected_ordinals = list(range(start, end + 1))
    actual_ordinals = [
        output.get("sourceOrdinal") if isinstance(output, dict) else None
        for output in outputs
    ]
    if actual_ordinals != expected_ordinals:
        errors.append("shard: entries must exactly and uniquely cover the declared range")

    packet_entries = {
        entry.get("sourceOrdinal"): entry
        for entry in packet.get("entries", [])
        if isinstance(entry, dict)
    }
    pending_updates: list[tuple[dict[str, Any], dict[str, Any]]] = []
    policy_sha256 = packet.get("policy", {}).get("bindingSha256", "")
    for output in outputs:
        if not isinstance(output, dict):
            errors.append("shard: every entry output must be an object")
            continue
        ordinal = output.get("sourceOrdinal")
        prefix = f"shard source unit {ordinal}"
        target = packet_entries.get(ordinal)
        if target is None:
            errors.append(f"{prefix}: source unit is absent from the packet")
            continue
        if output.get("sourceUnitId") != target.get("sourceUnitId"):
            errors.append(f"{prefix}: sourceUnitId does not match the packet")
        errors.extend(validate_entry_shard_output(output, policy_sha256, prefix))
        errors.extend(
            validate_names(
                output.get("names", {}),
                target.get("source", {}),
                str(output.get("sourceUnitId")),
                prefix,
                require_spans=True,
            )
        )
        pending_updates.append((target, output))
    if errors:
        raise WorkflowError("\n".join(errors))

    output_fields = {
        "blindTranslation",
        "independentCritique",
        "witnessResolution",
        "adjudication",
        "names",
        "unresolved",
        "humanReview",
    }
    for target, output in pending_updates:
        for field in output_fields:
            target[field] = output[field]
    packet["formulaInventory"] = {
        "status": "pending",
        "registryVersion": FORMULA_REGISTRY_VERSION,
        "occurrences": [],
    }
    packet["reviewPresentation"] = {"status": "pending", "path": None, "sha256": None}
    packet["machineReadiness"]["status"] = "pending"
    packet["machineReadiness"]["validatedAt"] = None
    atomic_write(packet_path, json_bytes(packet))
    return len(pending_updates)


def merge_preceding_shard(packet_path: Path, shard_path: Path) -> int:
    """Atomically merge structural translations for one or more source units."""
    packet = load_json(packet_path)
    shard = load_json(shard_path)
    errors: list[str] = []
    if packet.get("postRunRepairAudit", {}).get("status") == "complete":
        errors.append(
            "packet: cannot merge a shard after post-run repairs; rebuild from the "
            "pre-repair packet"
        )
    single_envelope = {
        "schemaVersion",
        "packetId",
        "issueNumber",
        "sourceOrdinal",
        "precedingTranslations",
    }
    multi_envelope = {
        "schemaVersion",
        "packetId",
        "issueNumber",
        "startUnit",
        "endUnit",
        "sourceUnits",
    }
    if packet.get("schemaVersion") != "1.2.0" or shard.get("schemaVersion") != "1.1.0":
        errors.append(
            "structural shard: packet must use schema 1.2.0 and shard schema 1.1.0"
        )
    if shard.get("packetId") != packet.get("packetId"):
        errors.append("structural shard: packetId does not match the target packet")
    assignment = packet.get("assignment", {})
    if shard.get("issueNumber") != assignment.get("issueNumber"):
        errors.append("structural shard: issueNumber does not match the target packet")

    packet_entries = {
        entry.get("sourceOrdinal"): entry
        for entry in packet.get("entries", [])
        if isinstance(entry, dict)
    }
    work_items: list[dict[str, Any]] = []
    if set(shard) == single_envelope:
        work_items = [
            {
                "sourceOrdinal": shard.get("sourceOrdinal"),
                "precedingTranslations": shard.get("precedingTranslations"),
            }
        ]
    elif set(shard) == multi_envelope:
        start = shard.get("startUnit")
        end = shard.get("endUnit")
        if not isinstance(start, int) or not isinstance(end, int) or end < start:
            errors.append("structural shard: source-unit range is invalid")
            start = 1
            end = 0
        if (
            start < assignment.get("startUnit", 1)
            or end > assignment.get("endUnit", 0)
        ):
            errors.append("structural shard: source-unit range is outside the assignment")
        candidate_items = shard.get("sourceUnits")
        if not isinstance(candidate_items, list):
            errors.append("structural shard: sourceUnits must be an array")
            candidate_items = []
        work_items = [item for item in candidate_items if isinstance(item, dict)]
        if len(work_items) != len(candidate_items) or any(
            set(item) != {"sourceOrdinal", "precedingTranslations"}
            for item in work_items
        ):
            errors.append("structural shard: every sourceUnits item has an invalid shape")
        expected_ordinals = [
            ordinal
            for ordinal in range(start, end + 1)
            if packet_entries.get(ordinal, {})
            .get("source", {})
            .get("precedingSegments")
        ]
        actual_ordinals = [item.get("sourceOrdinal") for item in work_items]
        if actual_ordinals != expected_ordinals:
            errors.append(
                "structural shard: sourceUnits must exactly cover every structural "
                "owner in the declared range"
            )
    else:
        errors.append("structural shard: envelope fields are incomplete or unexpected")

    policy_sha256 = packet.get("policy", {}).get("bindingSha256", "")
    pending_updates: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    merged_segments = 0
    for item in work_items:
        ordinal = item.get("sourceOrdinal")
        prefix = f"structural shard source unit {ordinal}"
        if not isinstance(ordinal, int) or not (
            assignment.get("startUnit", 1) <= ordinal <= assignment.get("endUnit", 0)
        ):
            errors.append(f"{prefix}: sourceOrdinal is outside the assignment")
            continue
        target = packet_entries.get(ordinal)
        if target is None:
            errors.append(f"{prefix}: source unit is absent from the packet")
            continue
        sources = target.get("source", {}).get("precedingSegments", [])
        translations = item.get("precedingTranslations")
        if not isinstance(translations, list):
            errors.append(f"{prefix}: precedingTranslations must be an array")
            translations = []
        source_ids = [source.get("segmentId") for source in sources]
        translation_ids = [
            translation.get("segmentId") if isinstance(translation, dict) else None
            for translation in translations
        ]
        if (
            not all(isinstance(segment_id, str) for segment_id in translation_ids)
            or translation_ids != source_ids
            or len(set(translation_ids)) != len(translation_ids)
        ):
            errors.append(
                f"{prefix}: translations must exactly and uniquely cover source segments"
            )
        for source, translation in zip(sources, translations):
            if not isinstance(translation, dict):
                errors.append(f"{prefix}: every translation must be an object")
                continue
            segment_prefix = f"structural shard {source.get('segmentId', '?')}"
            errors.extend(
                validate_preceding_translation(
                    translation, source, policy_sha256, segment_prefix
                )
            )
            errors.extend(private_data_errors(translation, segment_prefix))
        pending_updates.append((target, translations))
        merged_segments += len(translations)
    if errors:
        raise WorkflowError("\n".join(errors))

    for target, translations in pending_updates:
        target["precedingTranslations"] = translations
    packet["formulaInventory"] = {
        "status": "pending",
        "registryVersion": FORMULA_REGISTRY_VERSION,
        "occurrences": [],
    }
    packet["reviewPresentation"] = {"status": "pending", "path": None, "sha256": None}
    packet["machineReadiness"]["status"] = "pending"
    packet["machineReadiness"]["validatedAt"] = None
    atomic_write(packet_path, json_bytes(packet))
    return merged_segments


def validate_packet(packet: dict[str, Any], machine_ready: bool = False) -> list[str]:
    errors: list[str] = []
    packet_schema = load_json(DEFAULT_PACKET_SCHEMA)
    errors.extend(
        f"packet schema: {error}"
        for error in validate_schema_instance(packet, packet_schema)
    )
    errors.extend(validate_post_run_repair_audit(packet))
    if packet.get("schemaVersion") != "1.2.0":
        errors.append("packet: schemaVersion must be 1.2.0")
    if packet.get("toolVersion") != TOOL_VERSION:
        errors.append(f"packet: toolVersion must be {TOOL_VERSION}")
    if packet.get("workId") != "ibn-hajar-al-isabah":
        errors.append("packet: unexpected workId")
    assignment = packet.get("assignment")
    if not isinstance(assignment, dict):
        errors.append("packet: assignment is required")
        return errors
    if assignment.get("stateAtPreparation") != "OPEN" or not assignment.get("claimedBy"):
        errors.append("packet: work must come from an open, assigned issue")
    start = assignment.get("startUnit")
    end = assignment.get("endUnit")
    entries = packet.get("entries")
    if not isinstance(start, int) or not isinstance(end, int) or end < start:
        errors.append("packet: invalid assignment range")
        return errors
    if not isinstance(entries, list):
        errors.append("packet: entries must be an array")
        return errors
    ordinals = [entry.get("sourceOrdinal") for entry in entries if isinstance(entry, dict)]
    if ordinals != list(range(start, end + 1)):
        errors.append("packet: source units must exactly cover the assigned range in order")
    current_policy = policy_snapshot(DEFAULT_POLICY)
    if packet.get("policy", {}).get("bindingSha256") != current_policy["bindingSha256"]:
        errors.append("packet: policy binding is stale")
    authority = packet.get("authority", {})
    manifest_name = authority.get("manifestPath")
    if not isinstance(manifest_name, str) or not manifest_name:
        errors.append("packet: source manifest path is missing")
        manifest_path = DEFAULT_MANIFEST
    else:
        manifest_path = (ROOT / manifest_name).resolve()
        try:
            manifest_path.relative_to(ROOT.resolve())
        except ValueError:
            errors.append("packet: source manifest resolves outside the repository")
            manifest_path = DEFAULT_MANIFEST
    if not manifest_path.is_file():
        errors.append("packet: source manifest file is missing")
        manifest_path = DEFAULT_MANIFEST
    manifest = load_json(manifest_path)
    if authority.get("manifestSha256") != canonical_text_sha256(manifest_path):
        errors.append("packet: source manifest is stale")
    if authority.get("sha256") != manifest["download"]["sha256"]:
        errors.append("packet: source authority hash is stale")
    scope = packet.get("scope", {})
    if scope.get("precedingMaterialOwnership") != "following_source_unit":
        errors.append("packet: preceding-material ownership rule is missing")
    exclusions = scope.get("excludedRanges")
    if not isinstance(exclusions, list) or not any(
        isinstance(item, dict) and item.get("kind") == "openiti_metadata"
        for item in exclusions or []
    ):
        errors.append("packet: OpenITI metadata exclusion must be explicit")
    inventory = packet.get("formulaInventory")
    if not isinstance(inventory, dict) or inventory.get("status") not in {
        "pending",
        "complete",
    }:
        errors.append("packet: formula inventory state is missing")

    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"entries[{index}]: must be an object")
            continue
        prefix = (
            f"source unit {entry.get('sourceOrdinal', index)} "
            f"(printed entry {entry.get('sourceEntryNumber', '?')})"
        )
        source = entry.get("source", {})
        raw = source.get("rawOpeniti")
        if not isinstance(raw, str) or not raw:
            errors.append(f"{prefix}: raw OpenITI source is required")
        elif bytes_sha256(raw.encode("utf-8")) != source.get("rawSha256"):
            errors.append(f"{prefix}: source hash does not match raw OpenITI")
        if (
            not source.get("headingArabic")
            or not source.get("arabic")
            or not source.get("locations")
        ):
            errors.append(
                f"{prefix}: Arabic heading, readable source, and locations are required"
            )
        preceding = source.get("precedingSegments")
        translations = entry.get("precedingTranslations")
        if not isinstance(preceding, list) or not isinstance(translations, list):
            errors.append(f"{prefix}: preceding source and translation arrays are required")
            preceding = []
            translations = []
        source_ids = [
            segment.get("segmentId")
            for segment in preceding
            if isinstance(segment, dict)
        ]
        translation_ids = [
            item.get("segmentId")
            for item in translations
            if isinstance(item, dict)
        ]
        if len(source_ids) != len(preceding) or len(translation_ids) != len(translations):
            errors.append(f"{prefix}: preceding segments must be objects with IDs")
        elif source_ids != translation_ids or len(set(source_ids)) != len(source_ids):
            errors.append(
                f"{prefix}: preceding translations must exactly cover source segments"
            )
        previous_end = 0
        for segment_index, segment in enumerate(preceding):
            if not isinstance(segment, dict):
                continue
            segment_prefix = f"{prefix}, preceding segment {segment_index + 1}"
            segment_raw = segment.get("rawOpeniti")
            if not isinstance(segment_raw, str) or not segment_raw:
                errors.append(f"{segment_prefix}: raw OpenITI source is required")
            elif bytes_sha256(segment_raw.encode("utf-8")) != segment.get("rawSha256"):
                errors.append(f"{segment_prefix}: source hash does not match raw OpenITI")
            if not segment.get("headingArabic") and not segment.get("arabic"):
                errors.append(f"{segment_prefix}: substantive Arabic is required")
            readable = f"{segment.get('headingArabic') or ''} {segment.get('arabic') or ''}"
            if "#META#" in readable or "OpenITI" in readable or "PARATEXT" in readable:
                errors.append(f"{segment_prefix}: container metadata leaked into Arabic")
            line_start = segment.get("lineStart")
            line_end = segment.get("lineEnd")
            if (
                not isinstance(line_start, int)
                or not isinstance(line_end, int)
                or line_start <= previous_end
                or line_end < line_start
                or line_end >= source.get("lineStart", 0)
            ):
                errors.append(f"{segment_prefix}: source lines are invalid or out of order")
            else:
                previous_end = line_end
        if machine_ready:
            for segment_source, translation in zip(preceding, translations):
                if isinstance(segment_source, dict) and isinstance(translation, dict):
                    segment_prefix = (
                        f"{prefix}, preceding segment {segment_source.get('segmentId', '?')}"
                    )
                    errors.extend(
                        validate_preceding_translation(
                            translation,
                            segment_source,
                            current_policy["bindingSha256"],
                            segment_prefix,
                        )
                    )
        if not machine_ready:
            continue

        blind = entry.get("blindTranslation", {})
        if blind.get("status") != "complete" or not blind.get("english"):
            errors.append(f"{prefix}: blind translation is incomplete")
        if not all(blind.get(field) for field in ("runId", "model", "reasoning")):
            errors.append(f"{prefix}: blind translation provenance is incomplete")
        if blind.get("policySha256") != current_policy["bindingSha256"]:
            errors.append(f"{prefix}: blind translation used a stale policy")

        critique = entry.get("independentCritique", {})
        if critique.get("status") != "complete" or not critique.get("runId"):
            errors.append(f"{prefix}: independent critique is incomplete")
        if critique.get("runId") == blind.get("runId"):
            errors.append(f"{prefix}: critique must use a distinct run")
        if not isinstance(critique.get("findings"), list):
            errors.append(f"{prefix}: critique findings must be an array")

        findings = critique.get("findings", [])
        errors.extend(
            validate_witness(
                entry.get("witnessResolution", {}),
                findings if isinstance(findings, list) else [],
                prefix,
                strict=True,
            )
        )

        adjudication = entry.get("adjudication", {})
        if adjudication.get("status") != "complete" or not adjudication.get("english"):
            errors.append(f"{prefix}: adjudication is incomplete")
        if not isinstance(adjudication.get("decisions"), list):
            errors.append(f"{prefix}: adjudication decisions must be an array")
        errors.extend(validate_public_english(blind.get("english"), f"{prefix}, blind"))
        errors.extend(
            validate_public_english(
                adjudication.get("english"), f"{prefix}, adjudicated"
            )
        )

        errors.extend(
            validate_names(
                entry.get("names", {}),
                source,
                str(entry.get("sourceUnitId")),
                prefix,
                require_spans=True,
            )
        )
        unresolved = entry.get("unresolved")
        errors.extend(validate_unresolved(unresolved, prefix, strict=True))
        errors.extend(
            validate_uncertainty_witness_alignment(
                unresolved, entry.get("witnessResolution", {}), prefix
            )
        )
        if entry.get("humanReview", {}).get("status") != "unreviewed":
            errors.append(f"{prefix}: machine-ready work must remain human-unreviewed")

    if machine_ready:
        candidate_ids: list[str] = []
        mention_ids: list[str] = []
        for entry in entries:
            owners = [entry, *entry.get("precedingTranslations", [])]
            for owner in owners:
                names = owner.get("names", {})
                candidate_ids.extend(
                    candidate.get("candidateId")
                    for candidate in names.get("candidates", [])
                    if isinstance(candidate, dict)
                    and isinstance(candidate.get("candidateId"), str)
                )
                mention_ids.extend(
                    mention.get("mentionId")
                    for mention in names.get("mentions", [])
                    if isinstance(mention, dict)
                    and isinstance(mention.get("mentionId"), str)
                )
        if len(candidate_ids) != len(set(candidate_ids)):
            errors.append("packet: name candidate IDs must be globally unique")
        if len(mention_ids) != len(set(mention_ids)):
            errors.append("packet: name mention IDs must be globally unique")
        expected_inventory, inventory_errors = formula_inventory(packet)
        errors.extend(inventory_errors)
        if packet.get("formulaInventory") != expected_inventory:
            errors.append("packet: formula inventory is missing, stale, or incomplete")
        presentation = packet.get("reviewPresentation", {})
        presentation_path = presentation.get("path")
        if (
            presentation.get("status") != "ready"
            or not isinstance(presentation_path, str)
            or not presentation_path
            or Path(presentation_path).name != presentation_path
            or not SHA256_RE.fullmatch(str(presentation.get("sha256", "")))
        ):
            errors.append("packet: review presentation is not ready")
        readiness = packet.get("machineReadiness", {})
        if readiness.get("status") != "ready" or not readiness.get("validatedAt"):
            errors.append("packet: machine readiness is not finalized")
        if readiness.get("validatorVersion") != TOOL_VERSION:
            errors.append("packet: machine readiness used a stale validator")
    errors.extend(private_data_errors(packet))
    return errors


def render_review(packet: dict[str, Any]) -> str:
    authority = packet["authority"]
    source_url = (
        f"{authority['repository']}/blob/{authority['commit']}/{authority['path']}"
    )
    lines = [
        f"# Al-Isabah translation review — issue #{packet['assignment']['issueNumber']}",
        "",
        f"- Packet: `{packet['packetId']}`",
        f"- Source: [{authority['sourceId']}]({source_url}) at `{authority['commit']}`",
        f"- Source license: [{authority['license']['spdx']}]({authority['license']['url']})",
        f"- Source attribution: {authority['license']['attribution']}",
        f"- Source units: {packet['assignment']['startUnit']}–{packet['assignment']['endUnit']}",
        "- Printed entries: "
        f"{packet['assignment']['printedEntryStart']}–"
        f"{packet['assignment']['printedEntryEnd']}",
        "- Machine state: ready for human review",
        "- Human review: unreviewed",
        f"- Formula occurrences audited: {len(packet['formulaInventory']['occurrences'])}",
        "",
        "> English is a machine-ready candidate, not a canonical or human-approved translation.",
        "",
    ]
    formula_key: dict[tuple[str, str, str], None] = {}
    for occurrence in packet["formulaInventory"]["occurrences"]:
        formula_key[
            (
                occurrence["targetRealization"],
                occurrence["accessibleEnglish"],
                occurrence["expandedArabic"],
            )
        ] = None
    if formula_key:
        lines.extend(["## Formula key", ""])
        for realization, accessible, expanded_arabic in formula_key:
            lines.append(
                f"- `{realization}` — {accessible} "
                f"_(expanded Arabic: {expanded_arabic})_"
            )
        lines.append("")
    for entry in packet["entries"]:
        for segment, translation in zip(
            entry["source"]["precedingSegments"],
            entry["precedingTranslations"],
        ):
            adjudication = translation["adjudication"]
            heading_english = adjudication.get("headingEnglish")
            heading_arabic = segment.get("headingArabic")
            if heading_english:
                level = min((segment.get("headingLevel") or 1) + 1, 6)
                lines.extend([f"{'#' * level} {heading_english}", ""])
            else:
                label = (
                    "Front matter"
                    if segment["kind"] == "front_matter"
                    else "Interstitial prose"
                )
                lines.extend(
                    [
                        f"## {label} before source unit {entry['sourceOrdinal']}",
                        "",
                    ]
                )
            if adjudication.get("english"):
                lines.extend([adjudication["english"].strip(), ""])
            lines.extend(["<div dir=\"rtl\" lang=\"ar\">", ""])
            if heading_arabic:
                lines.extend([f"**{heading_arabic}**", ""])
            if segment.get("arabic"):
                lines.extend([present_openiti_arabic(segment["arabic"].strip()), ""])
            lines.extend(
                [
                    "</div>",
                    "",
                    f"- Structural source SHA-256: `{segment['rawSha256']}`",
                    "- Structural human review: `unreviewed`",
                    "",
                ]
            )
        lines.extend(
            [
                f"## Source unit {entry['sourceOrdinal']} · "
                f"printed entry {entry['sourceEntryNumber']}",
                "",
                "### English candidate",
                "",
                entry["adjudication"]["english"].strip(),
                "",
                "### Arabic authority",
                "",
                '<div dir="rtl" lang="ar">',
                "",
                present_openiti_arabic(entry["source"]["arabic"].strip()),
                "",
                "</div>",
                "",
                "### Evidence state",
                "",
                f"- Source SHA-256: `{entry['source']['rawSha256']}`",
                "- Source locations: "
                + ", ".join(
                    f"volume {item['volume']}, page {item['page']}"
                    for item in entry["source"]["locations"]
                ),
                f"- Critique findings: {len(entry['independentCritique']['findings'])}",
                f"- Witness resolution: `{entry['witnessResolution']['status']}`",
                f"- Name candidates: {len(entry['names']['candidates'])}",
                f"- Unresolved findings: {len(entry['unresolved'])}",
                "",
            ]
        )
        if entry["unresolved"]:
            lines.extend(["#### Unresolved", ""])
            for finding in entry["unresolved"]:
                lines.append(
                    f"- **{finding['severity']} — {finding['kind']}**: "
                    f"{finding['description']} "
                    f"_(location: {finding['location']}; "
                    f"disposition: {finding['disposition']})_"
                )
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def finalize_packet(packet_path: Path, presentation_path: Path | None = None) -> Path:
    packet = load_json(packet_path)
    packet["formulaInventory"], formula_errors = formula_inventory(packet)
    if formula_errors:
        raise WorkflowError("\n".join(formula_errors))
    packet["reviewPresentation"] = {"status": "pending", "path": None, "sha256": None}
    packet["machineReadiness"] = {
        "status": "pending",
        "validatedAt": None,
        "validatorVersion": TOOL_VERSION,
    }
    errors = validate_packet(packet, machine_ready=False)
    readiness_candidate = {
        **packet,
        "reviewPresentation": {
            "status": "ready",
            "path": "pending.review.md",
            "sha256": "0" * 64,
        },
        "machineReadiness": {
            "status": "ready",
            "validatedAt": utc_now(),
            "validatorVersion": TOOL_VERSION,
        },
    }
    stage_errors = [
        error
        for error in validate_packet(readiness_candidate, machine_ready=True)
        if "review presentation" not in error and "machine readiness" not in error
    ]
    errors.extend(stage_errors)
    if errors:
        raise WorkflowError("\n".join(dict.fromkeys(errors)))
    output = presentation_path or packet_path.with_suffix(".review.md")
    if output.parent.resolve() != packet_path.parent.resolve():
        raise WorkflowError("presentation must remain beside its packet until submission")
    presentation = render_review(packet).encode("utf-8")
    atomic_write(output, presentation)
    packet["reviewPresentation"] = {
        "status": "ready",
        "path": output.name,
        "sha256": bytes_sha256(presentation),
    }
    packet["machineReadiness"] = {
        "status": "ready",
        "validatedAt": utc_now(),
        "validatorVersion": TOOL_VERSION,
    }
    final_errors = validate_packet(packet, machine_ready=True)
    if final_errors:
        raise WorkflowError("\n".join(final_errors))
    atomic_write(packet_path, json_bytes(packet))
    return output


def submit_packet(
    packet_path: Path,
    output_root: Path = PROPOSAL_ROOT,
    allow_test_fixture: bool = False,
) -> tuple[Path, Path]:
    packet = load_json(packet_path)
    if (
        not allow_test_fixture
        and packet.get("authority", {}).get("manifestPath")
        != "profiles/translation-source.v1.json"
    ):
        raise WorkflowError("submission: only the active production source manifest is allowed")
    errors = validate_packet(packet, machine_ready=True)
    if errors:
        raise WorkflowError("\n".join(errors))
    presentation = packet_path.parent / str(packet["reviewPresentation"]["path"])
    if not presentation.is_file():
        raise WorkflowError("submission: review presentation file is missing")
    if bytes_sha256(presentation.read_bytes()) != packet["reviewPresentation"]["sha256"]:
        raise WorkflowError("submission: review presentation hash does not match")
    expected_presentation = render_review(packet).encode("utf-8")
    if presentation.read_bytes() != expected_presentation:
        raise WorkflowError("submission: review presentation does not match packet")
    issue_number = packet["assignment"]["issueNumber"]
    target_packet = output_root / f"issue-{issue_number:04d}.packet.json"
    target_review = output_root / f"issue-{issue_number:04d}.review.md"
    if target_packet.exists() or target_review.exists():
        raise WorkflowError("submission: target already exists; never overwrite a proposal")
    submitted = json.loads(json.dumps(packet))
    submitted["reviewPresentation"]["path"] = target_review.name
    atomic_write(target_packet, json_bytes(submitted))
    atomic_write(target_review, presentation.read_bytes())
    return target_packet, target_review


def command_doctor(args: argparse.Namespace) -> int:
    errors: list[str] = []
    manifest = load_json(args.manifest)
    errors.extend(validate_source_manifest(manifest))
    try:
        policy_snapshot(args.policy)
    except WorkflowError as exc:
        errors.append(str(exc))
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", ".runtime/translation/probe"], cwd=ROOT
    ).returncode == 0
    if not ignored:
        errors.append("doctor: .runtime translation artifacts are not ignored by Git")
    if not args.offline and shutil.which("gh") is None:
        errors.append("doctor: GitHub CLI (gh) is required for claims")
    if errors:
        raise WorkflowError("\n".join(errors))
    print("Translation workflow is ready; local policies and source manifest are valid.")
    return 0


def command_hydrate(args: argparse.Namespace) -> int:
    path = hydrate_source(args.manifest, args.output, args.from_file)
    print(f"Hydrated and verified {path}")
    return 0


def command_locate(args: argparse.Namespace) -> int:
    manifest = load_json(args.manifest)
    source = args.source or default_source_path(manifest)
    errors = verify_source(source, manifest)
    if errors:
        raise WorkflowError("\n".join(errors))
    entries = parse_openiti_entries(source)
    inventory_errors = validate_source_inventory(entries, manifest)
    if inventory_errors:
        raise WorkflowError("\n".join(inventory_errors))
    matches = [
        entry for entry in entries if entry["sourceEntryNumber"] == args.entry
    ]
    if not matches:
        raise WorkflowError(f"printed entry {args.entry} was not found")
    for entry in matches:
        locations = ", ".join(
            f"V{item['volume']:02d}P{item['page']:03d}"
            for item in entry["locations"]
        )
        heading = entry["headingArabic"]
        print(
            f"source unit {entry['sourceOrdinal']}: printed entry {args.entry}; "
            f"{locations}; {heading}"
        )
    return 0


def command_claim(args: argparse.Namespace) -> int:
    manifest = load_json(args.manifest)
    if args.issues_json is not None and manifest.get("status") != "test-fixture":
        raise WorkflowError("claim: offline issue data is allowed only with a test fixture")
    source = args.source or default_source_path(manifest)
    errors = verify_source(source, manifest)
    if errors:
        raise WorkflowError("\n".join(errors))
    entries = parse_openiti_entries(source)
    inventory_errors = validate_source_inventory(entries, manifest)
    if inventory_errors:
        raise WorkflowError("\n".join(inventory_errors))
    if args.start_unit < 1 or args.end_unit < args.start_unit:
        raise WorkflowError("claim: invalid source-unit range")
    if args.end_unit > len(entries):
        raise WorkflowError(f"source has only {len(entries)} source units")
    claims = parse_claims(load_issues(args.issues_json))
    overlaps = overlapping_claims(claims, args.start_unit, args.end_unit)
    if overlaps:
        raise WorkflowError(
            "claim overlaps open issue(s): "
            + ", ".join(f"#{item['number']}" for item in overlaps)
        )
    marker = {
        "schemaVersion": "1.0.0",
        "workId": "ibn-hajar-al-isabah",
        "sourceId": manifest["sourceId"],
        "contractId": "translation-quality-workflow",
        "startUnit": args.start_unit,
        "endUnit": args.end_unit,
    }
    first = entries[args.start_unit - 1]["sourceEntryNumber"]
    last = entries[args.end_unit - 1]["sourceEntryNumber"]
    body = (
        "## Translation assignment\n\n"
        f"Translate source units {args.start_unit}–{args.end_unit} "
        f"(printed entries {first}–{last}) under the repository-local "
        "translation contract and profile. Human review remains the final gate.\n\n"
        f"{assignment_marker(marker)}\n"
    )
    if args.dry_run:
        print(body)
        return 0
    command = [
        "issue",
        "create",
        "--repo",
        REPOSITORY,
        "--title",
        f"Translate Al-Isabah source units {args.start_unit}–{args.end_unit}",
        "--body",
        body,
        "--assignee",
        args.assignee,
    ]
    url = run_gh(command)
    match = re.search(r"/issues/(\d+)$", url)
    if not match:
        raise WorkflowError(f"claim was created but its issue number was not recognized: {url}")
    issue_number = int(match.group(1))
    post_claims = parse_claims(load_issues())
    collisions = overlapping_claims(
        post_claims, args.start_unit, args.end_unit, exclude_issue=issue_number
    )
    if collisions:
        raise WorkflowError(
            f"claim {url} was created but overlaps "
            + ", ".join(f"#{item['number']}" for item in collisions)
            + "; do not begin until the collision is resolved"
        )
    print(url)
    return 0


def command_status(args: argparse.Namespace) -> int:
    claims = parse_claims(load_issues(args.issues_json))
    if not claims:
        print("No open translation assignments.")
        return 0
    for claim in sorted(claims, key=lambda item: item["startUnit"]):
        assignees = ",".join(claim["assignees"]) or "unassigned"
        print(
            f"#{claim['number']} source units {claim['startUnit']}-{claim['endUnit']} "
            f"[{assignees}] {claim['url']}"
        )
    return 0


def command_prepare(args: argparse.Namespace) -> int:
    manifest = load_json(args.manifest)
    if (args.issue_json is not None or args.issues_json is not None) and manifest.get(
        "status"
    ) != "test-fixture":
        raise WorkflowError("prepare: offline issue data is allowed only with a test fixture")
    issue = load_issue(args.issue, args.issue_json)
    claims = parse_claims(load_issues(args.issues_json))
    source = args.source or default_source_path(manifest)
    packet = build_packet(issue, claims, source, args.manifest, args.policy)
    output = args.output or RUNTIME_ROOT / "packets" / f"issue-{args.issue:04d}.json"
    atomic_write(output, json_bytes(packet))
    print(f"Prepared {output}")
    return 0


def command_validate(args: argparse.Namespace) -> int:
    packet = load_json(args.packet)
    errors = validate_packet(packet, machine_ready=args.machine_ready)
    if errors:
        raise WorkflowError("\n".join(errors))
    state = "machine-ready" if args.machine_ready else "prepared"
    print(f"Packet is valid at the {state} stage.")
    return 0


def command_merge_shard(args: argparse.Namespace) -> int:
    merged = merge_entry_shard(args.packet, args.shard)
    print(f"Merged {merged} source-unit outputs into {args.packet}")
    return 0


def command_merge_structure_shard(args: argparse.Namespace) -> int:
    merged = merge_preceding_shard(args.packet, args.shard)
    print(f"Merged {merged} structural outputs into {args.packet}")
    return 0


def command_render(args: argparse.Namespace) -> int:
    output = finalize_packet(args.packet, args.output)
    print(f"Rendered and finalized {output}")
    return 0


def command_submit(args: argparse.Namespace) -> int:
    current = load_json(args.packet)
    issue_number = current.get("assignment", {}).get("issueNumber")
    if not isinstance(issue_number, int):
        raise WorkflowError("submission: packet assignment issue is missing")
    issue = load_issue(issue_number)
    claims = parse_claims(load_issues())
    live_errors = validate_live_assignment(current, issue, claims)
    if live_errors:
        raise WorkflowError("\n".join(live_errors))
    packet, review = submit_packet(args.packet, args.output_root)
    print(f"Prepared submission {packet} and {review}")
    return 0


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    subparsers = value.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="validate the local workflow")
    doctor.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    doctor.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    doctor.add_argument("--offline", action="store_true")
    doctor.set_defaults(func=command_doctor)

    hydrate = subparsers.add_parser("hydrate", help="download and verify the source")
    hydrate.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    hydrate.add_argument("--output", type=Path)
    hydrate.add_argument("--from-file", type=Path)
    hydrate.set_defaults(func=command_hydrate)

    locate = subparsers.add_parser("locate", help="map a printed entry to source units")
    locate.add_argument("--entry", type=int, required=True)
    locate.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    locate.add_argument("--source", type=Path)
    locate.set_defaults(func=command_locate)

    claim = subparsers.add_parser("claim", help="create a non-overlapping assignment issue")
    claim.add_argument("--start-unit", type=int, required=True)
    claim.add_argument("--end-unit", type=int, required=True)
    claim.add_argument("--assignee", default="@me")
    claim.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    claim.add_argument("--source", type=Path)
    claim.add_argument("--issues-json", type=Path)
    claim.add_argument("--dry-run", action="store_true")
    claim.set_defaults(func=command_claim)

    status = subparsers.add_parser("status", help="list open translation claims")
    status.add_argument("--issues-json", type=Path)
    status.set_defaults(func=command_status)

    prepare = subparsers.add_parser("prepare", help="prepare a claimed source packet")
    prepare.add_argument("--issue", type=int, required=True)
    prepare.add_argument("--issue-json", type=Path)
    prepare.add_argument("--issues-json", type=Path)
    prepare.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    prepare.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    prepare.add_argument("--source", type=Path)
    prepare.add_argument("--output", type=Path)
    prepare.set_defaults(func=command_prepare)

    validate = subparsers.add_parser("validate", help="validate a translation packet")
    validate.add_argument("--packet", type=Path, required=True)
    validate.add_argument("--machine-ready", action="store_true")
    validate.set_defaults(func=command_validate)

    merge_shard = subparsers.add_parser(
        "merge-shard", help="validate and atomically merge an entry-worker shard"
    )
    merge_shard.add_argument("--packet", type=Path, required=True)
    merge_shard.add_argument("--shard", type=Path, required=True)
    merge_shard.set_defaults(func=command_merge_shard)

    merge_structure = subparsers.add_parser(
        "merge-structure-shard",
        help="validate and atomically merge one source unit's structural outputs",
    )
    merge_structure.add_argument("--packet", type=Path, required=True)
    merge_structure.add_argument("--shard", type=Path, required=True)
    merge_structure.set_defaults(func=command_merge_structure_shard)

    render = subparsers.add_parser("render", help="render and finalize machine-ready work")
    render.add_argument("--packet", type=Path, required=True)
    render.add_argument("--output", type=Path)
    render.set_defaults(func=command_render)

    submit = subparsers.add_parser("submit", help="prepare tracked pull-request artifacts")
    submit.add_argument("--packet", type=Path, required=True)
    submit.add_argument("--output-root", type=Path, default=PROPOSAL_ROOT)
    submit.set_defaults(func=command_submit)
    return value


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = parser().parse_args(argv)
    try:
        return args.func(args)
    except WorkflowError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

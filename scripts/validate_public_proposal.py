#!/usr/bin/env python3
"""Validate public-proposal.v1/v2 artifacts and their repository bindings."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from project_public_proposal import parity_projection
from public_boundary import (
    boundary_errors,
    canonical_json,
    exact_keys,
    safe_error,
    sha256_bytes,
    sha256_file,
    sha256_text_file,
    summarize,
)
from schema_validation import validate_schema_instance
import validate_entry_titles as title_contract


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROPOSAL = (
    ROOT / "content" / "public-proposals" / "issue-0070.public-proposal.json"
)
FORMULA_REGISTRY_PATH = ROOT / "profiles" / "honorific-formulas.v1.json"
# Immutable release-closure v1 provenance for the quarantined 1.1 proposal.
# Only this exact proposal/version/hash tuple may use a superseded v2 snapshot.
HISTORICAL_POLICY_BINDINGS = {
    (
        "1.1.0",
        "issue-0053-public-proposal-v1",
    ): "081b4d5903575710d9d7f21db6f978a0e7922b2e93431c1eab2f1a010e3f9ccf",
    (
        "1.2.0",
        "issue-0070-public-proposal-v1",
    ): "20a74b3643a65e621efe02402e59944223f1424f75d67e1af94476d6f233bd6f",
    (
        "1.2.0",
        "issue-0080-public-proposal-v1",
    ): "a89774893a9c623814f51a942c0c43056a0f6ffb8b979a43bc6bdb6e317c3f91",
    (
        "1.2.0",
        "issue-0082-public-proposal-v1",
    ): "faf1078753c33c278098e71d0392a2af1e955320f090660da24ba64bc1831692",
    (
        "1.3.0",
        "issue-0086-public-proposal-v1",
    ): "9c82594b8d3a857baf54ba112ecf860e8a59b3f378381ab42db3819b1220cf34",
}
PINNED_TITLE_PROFILE_BINDINGS = {
    ("1.2.0", "issue-0070-public-proposal-v1"): {
        "profileId": "entry-title-decisions.v3",
        "profileSha256": "dc5f80db7c897b4ecf0df5b5fa1bce7ce7388d05fe6607f6a6cdb9e092934afc",
    },
    ("1.2.0", "issue-0080-public-proposal-v1"): {
        "profileId": "entry-title-decisions.v4",
        "profileSha256": "f177c6c9fba1702aae911c0dba024e9e24b1093016b62066a573f63e6afff2a3",
    },
    ("1.2.0", "issue-0082-public-proposal-v1"): {
        "profileId": "entry-title-decisions.v5",
        "profileSha256": "3f338cf5e748d142c3de86d9926db5f97b727de3790a92be7afb9bcc9d1d8221",
    },
    ("1.2.0", "issue-0084-public-proposal-v1"): {
        "profileId": "entry-title-decisions.v6",
        "profileSha256": "09014c9e78befd5dcd490e1452b91b0ec099982253ec13297e98fc74de41a6e6",
    },
    ("1.3.0", "issue-0086-public-proposal-v1"): {
        "profileId": "entry-title-decisions.v7",
        "profileSha256": "a31e8ef7670f30577f70ba5c930c8c6b8803fc9bfce8eec3a362f4ac8c097a52",
    },
    ("1.3.0", "issue-0085-public-proposal-v1"): {
        "profileId": "entry-title-decisions.v8",
        "profileSha256": "fa797cd530a5be7c9be4045c03b35fd08d28aaa75eb9c45b0a1523d2644d8cf9",
    },
}
SOURCE_DERIVED_NAME_ID_PROPOSALS = {
    "issue-0080-public-proposal-v1",
    "issue-0082-public-proposal-v1",
    "issue-0084-public-proposal-v1",
    "issue-0086-public-proposal-v1",
    "issue-0085-public-proposal-v1",
}
ARABIC_SCRIPT_RE = re.compile(
    r"[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff\ufb50-\ufdff\ufe70-\ufeff]"
)
ARABIC_LITERAL_RE = re.compile(
    r"[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff\ufb50-\ufdff\ufe70-\ufeff]+"
    r"(?:[ \t]+[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff\ufb50-\ufdff\ufe70-\ufeff]+)*"
)
PUBLIC_PROCESS_RE = re.compile(
    r"\b(?:pinned|OpenITI|ACO|Variant English renderings?)\b",
    re.IGNORECASE,
)
FORMULA_RULES = tuple(
    json.loads(FORMULA_REGISTRY_PATH.read_text(encoding="utf-8"))["entries"]
)
FORMULA_V14_SOURCES = {
    "بسم الله الرحمن الرحيم",
    "صلى الله عليه وسلم واله وسلم",
    "صلى الله عليه وسلم وسلم",
    "عليها السلام",
    "والله المستعان",
    "فالله أعلم",
    "فالله اعلم",
    "ولله الحمد",
    "تعالى",
}
FORMULA_V15_SOURCES = {
    "صلى الله عليه وسلم وعلى آله وسلم",
    "صلى الله عليه وسلم وآله",
    "صلى الله عيه وآله وسلم",
    "صلى الله عليه وسلم وآوله وسلم",
    "صلى الله علي وآله وسلم",
    "صلى الله عليه وسلم وآله سلم",
    "صلى الله عيله وآله وسلم",
    "صلى الله عله وآله وسلم",
    "صلى الله عليه وسلم وآله ولم",
    "صلى الله عيله وسلم",
}
FORMULA_V16_SOURCES = {
    "والله الموفق",
    "ان شاء الله تعالى",
    "ان شاء الله",
    "نسأل الله التوفيق",
    "والله عنده حسن المآب",
    "والله سبحانه وتعالى اعلم",
    "وبالله التوفيق",
    "اللهم صل على النبي والوصي",
    "رحم الله عائشة",
    "رحم الله هشاما",
    "رحم الله عبادا",
    "رحم الله لبيدا",
    "رحم الله عروة",
    "رحم الله قسا",
    "يرحمك الله",
    "صلى الله عليه وسلم وأله وسلم",
    "صلى الله عليه وسلم آله وسلم",
    "صل الله عليه وآله وسلم",
    "صلى الله",
}
LEGACY_FORMULA_RULES = tuple(
    rule
    for rule in FORMULA_RULES
    if rule["source"]
    not in FORMULA_V14_SOURCES | FORMULA_V15_SOURCES | FORMULA_V16_SOURCES
)
CONTEXTUAL_FORMULA_SOURCES = {"بسم الله الرحمن الرحيم"}
SHA1 = re.compile(r"^[a-f0-9]{40}$")
SHA256 = re.compile(r"^[a-f0-9]{64}$")
COMMIT = SHA1
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,199}$")
PROPOSAL_ID = re.compile(r"^issue-[0-9]{4}-public-proposal-v1$")
TITLE_PROFILE_ID = re.compile(r"^entry-title-decisions\.v[0-9]+$")
COMMON_TOP_KEYS = {
    "schemaVersion", "proposalId", "workId", "publicationStatus",
    "canonicalPromotion", "consumerSchemaVersion", "sourceAuthority", "rights",
    "policy", "review", "baseline", "records",
}
LEGACY_TOP_KEYS = COMMON_TOP_KEYS | {"historicalEvidence"}
PACKET_SET_TOP_KEYS = COMMON_TOP_KEYS | {"evidenceBinding"}
CURRENT_TOP_KEYS = PACKET_SET_TOP_KEYS | {"entryTitleDecisions", "sliceContext"}
RECORD_KEYS = {
    "schemaVersion", "id", "kind", "workId", "packetId", "sourceOrdinal",
    "printedEntryNumber", "canonicalEntryId", "volume", "pages", "title",
    "arabic", "english", "precedingMaterial", "names", "unresolved", "formulas",
    "machineAssessment", "humanReview", "source", "policy",
}
KEYS = {
    "sourceAuthority": {"sourceId", "commit", "sha256", "license"},
    "rights": {"matrixId", "allowedUseClassification", "statusCode", "effectCode"},
    "policy": {"bindingSha256"},
    "review": {"machinePassed", "needsAttention", "humanReviewed", "humanUnreviewed"},
    "historicalEvidence": {"packetGitBlobSha1", "packetGitBlobSha256", "packetGitBlobBytes", "reviewGitBlobSha1", "reviewSha256", "historyPreserved"},
    "evidenceBinding": {"kind", "packetCount", "packetSetSha256", "reviewCount", "reviewSetSha256", "recordProjectionSha256"},
    "entryTitleDecisions": {"profileId", "profileSha256", "coveredRecordCount"},
    "sliceContext": {"state", "beforeSourceOrdinal", "sourceProposalId", "sourceProposalSha256", "contexts"},
    "sliceContextItem": {"sourceOccurrenceId", "displayContextId"},
    "baseline": {"distributionSchemaVersion", "recordCount", "userFacingSha256"},
    "license": {"spdx", "url", "attribution"},
    "page": {"volume", "page"},
    "title": {"arabic", "english", "state", "method"},
    "context": {"id", "kind", "heading", "arabic", "english", "pages", "humanReview", "unresolved", "sourceSha256"},
    "heading": {"arabic", "english", "level"},
    "name": {"id", "arabic", "english", "aliases", "kind", "reviewState"},
    "finding": {"category", "priority"},
    "formula": {"formulaId", "recordId", "observedArabic", "semanticClass", "targetRealization"},
    "source": {"authorityId", "commit", "artifactSha256", "exactTextSha256", "license"},
}


def parse(path: Path) -> tuple[Any | None, list[str]]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), []
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        location = getattr(error, "lineno", 0)
        return None, [safe_error(f"$.line[{location}]", "invalid-json")]


def nested_key_errors(proposal: dict[str, Any]) -> list[str]:
    schema_version = proposal.get("schemaVersion")
    legacy = schema_version == "1.0.0"
    top_keys = (
        LEGACY_TOP_KEYS
        if legacy
        else CURRENT_TOP_KEYS
        if schema_version in {"1.2.0", "1.3.0"}
        else PACKET_SET_TOP_KEYS
    )
    errors = exact_keys(proposal, top_keys, "$")
    top_objects = ["sourceAuthority", "rights", "policy", "review", "baseline"]
    top_objects.append("historicalEvidence" if legacy else "evidenceBinding")
    if schema_version in {"1.2.0", "1.3.0"}:
        top_objects.extend(["entryTitleDecisions", "sliceContext"])
    for key in top_objects:
        errors.extend(exact_keys(proposal.get(key), KEYS[key], f"$.{key}"))
    authority = proposal.get("sourceAuthority", {})
    errors.extend(exact_keys(authority.get("license"), KEYS["license"], "$.sourceAuthority.license"))
    if schema_version in {"1.2.0", "1.3.0"}:
        for index, context in enumerate(proposal.get("sliceContext", {}).get("contexts", [])):
            errors.extend(
                exact_keys(
                    context,
                    KEYS["sliceContextItem"],
                    f"$.sliceContext.contexts[{index}]",
                )
            )
    for index, record in enumerate(proposal.get("records", [])):
        base = f"$.records[{index}]"
        record_keys = RECORD_KEYS
        if schema_version == "1.3.0" and "bodyState" in record:
            record_keys = RECORD_KEYS | {"bodyState"}
        errors.extend(exact_keys(record, record_keys, base))
        errors.extend(exact_keys(record.get("title"), KEYS["title"], f"{base}.title"))
        errors.extend(exact_keys(record.get("source"), KEYS["source"], f"{base}.source"))
        errors.extend(exact_keys(record.get("policy"), KEYS["policy"], f"{base}.policy"))
        source = record.get("source", {})
        errors.extend(exact_keys(source.get("license"), KEYS["license"], f"{base}.source.license"))
        for page_index, page in enumerate(record.get("pages", [])):
            errors.extend(exact_keys(page, KEYS["page"], f"{base}.pages[{page_index}]"))
        for context_index, context in enumerate(record.get("precedingMaterial", [])):
            context_path = f"{base}.precedingMaterial[{context_index}]"
            errors.extend(exact_keys(context, KEYS["context"], context_path))
            errors.extend(exact_keys(context.get("heading"), KEYS["heading"], f"{context_path}.heading"))
            for page_index, page in enumerate(context.get("pages", [])):
                errors.extend(exact_keys(page, KEYS["page"], f"{context_path}.pages[{page_index}]"))
            for finding_index, finding in enumerate(context.get("unresolved", [])):
                errors.extend(exact_keys(finding, KEYS["finding"], f"{context_path}.unresolved[{finding_index}]"))
        for name_index, name in enumerate(record.get("names", [])):
            errors.extend(exact_keys(name, KEYS["name"], f"{base}.names[{name_index}]"))
        for finding_index, finding in enumerate(record.get("unresolved", [])):
            errors.extend(exact_keys(finding, KEYS["finding"], f"{base}.unresolved[{finding_index}]"))
        for formula_index, formula in enumerate(record.get("formulas", [])):
            errors.extend(exact_keys(formula, KEYS["formula"], f"{base}.formulas[{formula_index}]"))
    return errors


def order_sha256(records: list[dict[str, Any]]) -> str:
    return sha256_bytes(canonical_json([
        {"id": item["id"], "sourceOrdinal": item["sourceOrdinal"]}
        for item in records
    ]))


def records_sha256(records: list[dict[str, Any]]) -> str:
    return sha256_bytes(b"".join(canonical_json(item) for item in records))


def _title_decision_errors(proposal: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    binding = proposal.get("entryTitleDecisions", {})
    expected_binding = PINNED_TITLE_PROFILE_BINDINGS.get(
        (proposal.get("schemaVersion"), proposal.get("proposalId"))
    )
    if proposal.get("schemaVersion") == "1.3.0" and expected_binding is None:
        return [safe_error("$.entryTitleDecisions", "title-profile-mismatch")]
    if expected_binding is not None and any(
        binding.get(key) != value for key, value in expected_binding.items()
    ):
        return [safe_error("$.entryTitleDecisions", "title-profile-mismatch")]
    profile_id = binding.get("profileId")
    if not isinstance(profile_id, str) or not TITLE_PROFILE_ID.fullmatch(profile_id):
        return [safe_error("$.entryTitleDecisions.profileId", "title-profile-mismatch")]
    profile_path = ROOT / "profiles" / f"{profile_id}.json"
    if (
        not profile_path.is_file()
        or binding.get("profileSha256") != sha256_file(profile_path)
    ):
        return [safe_error("$.entryTitleDecisions", "title-profile-mismatch")]
    try:
        profile = title_contract.load(profile_path)
        decisions = title_contract.decision_index(profile)
    except (OSError, ValueError, json.JSONDecodeError):
        return [safe_error("$.entryTitleDecisions", "title-profile-mismatch")]
    records = proposal.get("records", [])
    if binding.get("coveredRecordCount") != len(records):
        errors.append(
            safe_error(
                "$.entryTitleDecisions.coveredRecordCount",
                "title-decision-coverage-mismatch",
            )
        )
    for index, record in enumerate(records):
        base = f"$.records[{index}]"
        number = record.get("printedEntryNumber")
        if not isinstance(number, int):
            errors.append(
                safe_error(
                    f"{base}.printedEntryNumber",
                    "missing-title-body-decision",
                )
            )
            continue
        decision = decisions.get(record.get("id")) or decisions.get(number)
        if decision is None:
            errors.append(
                safe_error(f"{base}.title", "missing-title-body-decision")
            )
            continue
        if decision.get("sourceEntryNumber") != number:
            errors.append(
                safe_error(f"{base}.printedEntryNumber", "title-decision-mismatch")
            )
        if "sourceUnitId" in decision and (
            record.get("id") != decision["sourceUnitId"]
            or record.get("source", {}).get("exactTextSha256")
            != decision.get("sourceRawSha256")
        ):
            errors.append(safe_error(base, "title-source-unit-mismatch"))
        expected_title = {
            "arabic": decision["title"]["ar"],
            "english": decision["title"]["en"],
        }
        title = record.get("title", {})
        if (
            {key: title.get(key) for key in ("arabic", "english")}
            != expected_title
            or title.get("method") != "profile-decision"
        ):
            errors.append(safe_error(f"{base}.title", "title-decision-mismatch"))
        if decision["bodyOpeningKind"] == "none":
            if (
                proposal.get("schemaVersion") != "1.3.0"
                or record.get("bodyState") != "title-only"
                or record.get("arabic") != ""
                or record.get("english") != ""
                or record.get("source", {}).get("exactTextSha256")
                != decision.get("sourceRawSha256", decision.get("sourceUnitSha256"))
            ):
                errors.append(safe_error(base, "title-only-body-mismatch"))
        elif (
            "bodyState" in record
            or not str(record.get("arabic", "")).startswith(
                decision["bodyOpening"]["ar"]
            )
            or not str(record.get("english", "")).startswith(
                decision["bodyOpening"]["en"]
            )
        ):
            errors.append(safe_error(base, "title-body-opening-mismatch"))
    return errors


def _active_heading_contexts(
    source_proposal: dict[str, Any], before_source_ordinal: int
) -> list[dict[str, Any]]:
    active: list[dict[str, Any]] = []
    for record in source_proposal.get("records", []):
        ordinal = record.get("sourceOrdinal")
        if not isinstance(ordinal, int) or ordinal >= before_source_ordinal:
            break
        for context in record.get("precedingMaterial", []):
            if context.get("kind") != "structural_heading":
                continue
            level = context.get("heading", {}).get("level")
            if not isinstance(level, int) or level < 1:
                return []
            active = [
                item
                for item in active
                if item["heading"]["level"] < level
            ]
            active.append(context)
    return active


def _continued_context(
    source_context: dict[str, Any], first_source_ordinal: int
) -> dict[str, Any]:
    return {
        "id": (
            f"continued-before-unit-{first_source_ordinal:06d}-from-"
            f"{source_context['id']}"
        ),
        "kind": "continued_structural_heading",
        "heading": source_context["heading"],
        "arabic": "",
        "english": "",
        "pages": source_context["pages"],
        "humanReview": source_context["humanReview"],
        "unresolved": source_context["unresolved"],
        "sourceSha256": source_context["sourceSha256"],
    }


def _slice_context_errors(proposal: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    records = proposal.get("records", [])
    if not records:
        return [safe_error("$.sliceContext", "missing-inherited-slice-context")]
    first_ordinal = records[0].get("sourceOrdinal")
    binding = proposal.get("sliceContext", {})
    displayed_continued = [
        (record_index, context)
        for record_index, record in enumerate(records)
        for context in record.get("precedingMaterial", [])
        if context.get("kind") == "continued_structural_heading"
    ]
    if first_ordinal == 1:
        if binding != {
            "state": "root",
            "beforeSourceOrdinal": 1,
            "sourceProposalId": None,
            "sourceProposalSha256": None,
            "contexts": [],
        } or displayed_continued:
            errors.append(safe_error("$.sliceContext", "invalid-root-context"))
        return errors
    if (
        binding.get("state") != "continued"
        or binding.get("beforeSourceOrdinal") != first_ordinal
        or not binding.get("contexts")
    ):
        return [safe_error("$.sliceContext", "missing-inherited-slice-context")]
    source_proposal_id = binding.get("sourceProposalId")
    if not isinstance(source_proposal_id, str) or not PROPOSAL_ID.fullmatch(
        source_proposal_id
    ):
        return [safe_error("$.sliceContext.sourceProposalId", "context-source-mismatch")]
    source_filename = (
        source_proposal_id.removesuffix("-public-proposal-v1") + ".public-proposal.json"
    )
    source_path = ROOT / "content" / "public-proposals" / source_filename
    if (
        not source_path.is_file()
        or binding.get("sourceProposalSha256") != sha256_file(source_path)
    ):
        return [safe_error("$.sliceContext", "context-source-mismatch")]
    source_proposal, parse_errors = parse(source_path)
    if parse_errors or not isinstance(source_proposal, dict):
        return [safe_error("$.sliceContext", "context-source-mismatch")]
    if validate(source_path, require_current=False):
        return [safe_error("$.sliceContext", "context-source-mismatch")]
    source_ordinals = [
        item.get("sourceOrdinal")
        for item in source_proposal.get("records", [])
        if isinstance(item, dict) and isinstance(item.get("sourceOrdinal"), int)
    ]
    if (
        source_proposal.get("sourceAuthority") != proposal.get("sourceAuthority")
        or max(source_ordinals, default=0) != first_ordinal - 1
    ):
        errors.append(safe_error("$.sliceContext", "context-source-mismatch"))
        return errors
    active = _active_heading_contexts(source_proposal, first_ordinal)
    expected_bindings: list[dict[str, str]] = []
    expected_displayed: list[dict[str, Any]] = []
    for source_context in active:
        display = _continued_context(source_context, first_ordinal)
        expected_bindings.append(
            {
                "sourceOccurrenceId": source_context["id"],
                "displayContextId": display["id"],
            }
        )
        expected_displayed.append(display)
    if not active or binding.get("contexts") != expected_bindings:
        errors.append(safe_error("$.sliceContext.contexts", "active-context-mismatch"))
    first_contexts = records[0].get("precedingMaterial", [])
    if first_contexts[: len(expected_displayed)] != expected_displayed:
        errors.append(
            safe_error(
                "$.records[0].precedingMaterial",
                "continued-context-mismatch",
            )
        )
    if (
        [context for _, context in displayed_continued] != expected_displayed
        or any(record_index != 0 for record_index, _ in displayed_continued)
    ):
        errors.append(safe_error("$.records", "misplaced-continued-context"))
    return errors


def current_readiness_errors(proposal: dict[str, Any]) -> list[str]:
    if proposal.get("schemaVersion") not in {"1.2.0", "1.3.0"}:
        return [safe_error("$.schemaVersion", "historical-proposal-not-current")]
    return _title_decision_errors(proposal) + _slice_context_errors(proposal)


def public_english_errors(
    value: Any,
    formulas: Any,
    record_id: Any,
    path: str,
    allowed_arabic_literals: list[str] | None = None,
) -> list[str]:
    if not isinstance(value, str):
        return []
    errors: list[str] = []
    if PUBLIC_PROCESS_RE.search(value):
        errors.append(safe_error(path, "internal-process-language"))
    residual = value
    targets = [
        formula.get("targetRealization")
        for formula in formulas
        if isinstance(formula, dict)
        and formula.get("recordId") == record_id
        and isinstance(formula.get("targetRealization"), str)
        and formula["targetRealization"]
    ] if isinstance(formulas, list) else []
    for target in sorted(targets, key=len, reverse=True):
        location = residual.find(target)
        if location < 0:
            errors.append(safe_error(path, "missing-declared-formula-target"))
            continue
        residual = residual[:location] + residual[location + len(target):]
    for literal in sorted(allowed_arabic_literals or [], key=len, reverse=True):
        location = residual.find(literal)
        if location >= 0:
            residual = residual[:location] + residual[location + len(literal):]
    if ARABIC_SCRIPT_RE.search(residual):
        errors.append(safe_error(path, "undeclared-arabic-in-english"))
    return errors


def governed_arabic_literals(
    value: str | None,
    rules: tuple[dict[str, Any], ...] = FORMULA_RULES,
) -> list[str]:
    """Return exact Arabic spans, preserving spaces inside a governed literal."""
    formula_literals = {
        str(formula_value)
        for rule in rules
        for formula_value in (rule["source"], rule["target"], rule["expandedArabic"])
    }
    def is_formula_literal(literal: str) -> bool:
        pattern = re.compile(
            r"(?<![\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff\ufb50-\ufdff\ufe70-\ufeff])"
            + re.escape(literal)
            + r"(?![\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff\ufb50-\ufdff\ufe70-\ufeff])"
        )
        return any(pattern.search(formula_literal) for formula_literal in formula_literals)

    return [
        literal
        for literal in ARABIC_LITERAL_RE.findall(value or "")
        if not is_formula_literal(literal)
    ]


def registered_formula_occurrences(
    text: str,
    field: str,
    rules: tuple[dict[str, Any], ...] = FORMULA_RULES,
    *,
    include_contextual: bool = False,
) -> list[dict[str, Any]]:
    """Return registry-bound non-overlapping formula occurrences in source order."""
    effective_rules = tuple(
        rule
        for rule in rules
        if include_contextual
        or str(rule["source"]) not in CONTEXTUAL_FORMULA_SOURCES
    )
    if field == "target":
        values = sorted(
            {
                str(value)
                for rule in effective_rules
                for value in (rule["target"], rule["expandedArabic"])
            },
            key=len,
            reverse=True,
        )
    else:
        values = sorted(
            {str(rule["source"]) for rule in effective_rules},
            key=len,
            reverse=True,
        )
    pattern = re.compile("|".join(re.escape(value) for value in values))
    occurrences: list[dict[str, Any]] = []
    for match in pattern.finditer(text):
        value = match.group(0)
        if field == "target":
            rule = next(
                item
                for item in effective_rules
                if value in {item["target"], item["expandedArabic"]}
            )
        else:
            rule = next(item for item in effective_rules if value == item["source"])
        if (
            field == "source"
            and rule["source"] == "صلى الله عليه وسلم وآله"
            and re.match(r"\s+رجلا(?:\s|$)", text[match.end() :]) is not None
        ):
            value = "صلى الله عليه وسلم"
            rule = next(
                item for item in effective_rules if item["source"] == value
            )
        if (
            field == "source"
            and rule["source"] == "تعالى"
            and re.search(r"(?:الله|لله|قوله|قال)\s*$", text[: match.start()]) is None
        ):
            continue
        if rule["source"] == "والله عنده حسن المآب" and text[
            match.end() :
        ].strip(" \t\r\n.,;:!?؟،؛—–"):
            continue
        if rule["source"] == "صلى الله":
            prefix = text[: match.start()]
            suffix = text[match.end() :]
            if field == "source":
                has_prophetic_referent = re.search(
                    r"(?:رسول الله|النبي)\s*$", prefix
                )
            else:
                has_prophetic_referent = re.search(
                    r"(?:Messenger of (?:God|Allah)|Prophet)\s*$", prefix,
                    flags=re.IGNORECASE,
                )
            has_formula_continuation = re.match(
                r"\s+(?:تعالى|عليه|عيه|علي|عيله|عله|على|و?آله|واله)",
                suffix,
            )
            if has_prophetic_referent is None or has_formula_continuation is not None:
                continue
        occurrences.append({"value": value, "rule": rule})
    return occurrences


def formulas_for_scope(
    formulas: Any, record_id: Any, source_field: str
) -> list[dict[str, Any]]:
    if not isinstance(formulas, list) or not isinstance(record_id, str):
        return []
    prefix = f"{record_id}-{source_field}-formula-"
    return [
        item
        for item in formulas
        if isinstance(item, dict)
        and item.get("recordId") == record_id
        and str(item.get("formulaId", "")).startswith(prefix)
    ]


def expected_scope_formulas(
    record_id: Any,
    source_field: str,
    source: Any,
    english: Any,
    rules: tuple[dict[str, Any], ...] = FORMULA_RULES,
    *,
    include_contextual: bool = False,
) -> tuple[list[dict[str, Any]], bool]:
    if source is None and english is None:
        return [], True
    if not (
        isinstance(record_id, str)
        and isinstance(source, str)
        and isinstance(english, str)
    ):
        return [], False
    source_hits = registered_formula_occurrences(
        source, "source", rules, include_contextual=include_contextual
    )
    target_hits = registered_formula_occurrences(
        english, "target", rules, include_contextual=include_contextual
    )
    if len(source_hits) != len(target_hits):
        return [], False
    expected: list[dict[str, Any]] = []
    valid = True
    for index, (source_hit, target_hit) in enumerate(
        zip(source_hits, target_hits), start=1
    ):
        source_rule = source_hit["rule"]
        target_rule = target_hit["rule"]
        expected.append(
            {
                "formulaId": f"{record_id}-{source_field}-formula-{index:03d}",
                "recordId": record_id,
                "observedArabic": source_hit["value"],
                "semanticClass": source_rule["semanticClass"],
                "targetRealization": target_hit["value"],
            }
        )
        if (
            target_rule["semanticClass"] != source_rule["semanticClass"]
            or target_rule["referentScope"] != source_rule["referentScope"]
            or target_rule["grammaticalAgreement"]
            != source_rule["grammaticalAgreement"]
        ):
            valid = False
    return expected, valid


def public_formula_errors(
    record: dict[str, Any],
    base: str,
    rules: tuple[dict[str, Any], ...] = FORMULA_RULES,
) -> list[str]:
    """Recompute every public formula from its exact source and English field."""
    formulas = record.get("formulas")
    if not isinstance(formulas, list):
        return []
    expected: list[dict[str, Any]] = []
    valid = True
    for context in record.get("precedingMaterial", []):
        if not isinstance(context, dict):
            continue
        heading = context.get("heading", {})
        if isinstance(heading, dict):
            scope, scope_valid = expected_scope_formulas(
                context.get("id"),
                "headingArabic",
                heading.get("arabic"),
                heading.get("english"),
                rules,
                include_contextual=True,
            )
            expected.extend(scope)
            valid = valid and scope_valid
        scope, scope_valid = expected_scope_formulas(
            context.get("id"),
            "arabic",
            context.get("arabic"),
            context.get("english"),
            rules,
            include_contextual=True,
        )
        expected.extend(scope)
        valid = valid and scope_valid
    title = record.get("title", {})
    if isinstance(title, dict):
        scope, scope_valid = expected_scope_formulas(
            record.get("id"),
            "titleArabic",
            title.get("arabic"),
            title.get("english"),
            rules,
            include_contextual=True,
        )
        expected.extend(scope)
        valid = valid and scope_valid
    scope, scope_valid = expected_scope_formulas(
        record.get("id"),
        "arabic",
        record.get("arabic"),
        record.get("english"),
        rules,
        include_contextual=any(
            isinstance(formula, dict)
            and formula.get("recordId") == record.get("id")
            and formula.get("observedArabic") in CONTEXTUAL_FORMULA_SOURCES
            for formula in formulas
        ),
    )
    expected.extend(scope)
    valid = valid and scope_valid
    if formulas != expected or not valid:
        return [safe_error(f"{base}.formulas", "formula-inventory-mismatch")]
    return []


def record_semantic_errors(
    record: dict[str, Any],
    base: str,
    *,
    enforce_public_english: bool = False,
    allowed_arabic_literals: list[str] | None = None,
    formula_rules: tuple[dict[str, Any], ...] = FORMULA_RULES,
) -> list[str]:
    errors: list[str] = []
    if record.get("kind") != "entry" or record.get("workId") != "ibn-hajar-al-isabah":
        errors.append(safe_error(base, "consumer-contract-mismatch"))
    for key in ("sourceOrdinal", "printedEntryNumber", "volume"):
        if not isinstance(record.get(key), int) or record[key] < 1:
            errors.append(safe_error(f"{base}.{key}", "invalid-integer"))
    title = record.get("title", {})
    if not all(isinstance(title.get(key), str) and title[key].strip() for key in ("arabic", "english")):
        errors.append(safe_error(f"{base}.title", "incomplete-bilingual-content"))
    if title.get("state") not in {"ready", "needs_attention"} or title.get("method") not in {"primary-name-candidate", "opening-fallback", "profile-decision"}:
        errors.append(safe_error(f"{base}.title", "invalid-title-state"))
    for page_path, pages in [(f"{base}.pages", record.get("pages", []))] + [
        (f"{base}.precedingMaterial[{index}].pages", context.get("pages", []))
        for index, context in enumerate(record.get("precedingMaterial", []))
    ]:
        if not isinstance(pages, list):
            errors.append(safe_error(page_path, "expected-array"))
            continue
        for index, page in enumerate(pages):
            if not isinstance(page.get("volume"), int) or page["volume"] < 1 or not isinstance(page.get("page"), int) or page["page"] < 1:
                errors.append(safe_error(f"{page_path}[{index}]", "invalid-page"))
    for index, context in enumerate(record.get("precedingMaterial", [])):
        context_path = f"{base}.precedingMaterial[{index}]"
        if not all(isinstance(context.get(key), str) for key in ("id", "kind", "arabic", "english")):
            errors.append(safe_error(context_path, "invalid-context"))
        if context.get("humanReview") not in {"unreviewed", "in_review", "reviewed", "verified"}:
            errors.append(safe_error(f"{context_path}.humanReview", "invalid-review-state"))
        if not SHA256.fullmatch(str(context.get("sourceSha256", ""))):
            errors.append(safe_error(f"{context_path}.sourceSha256", "invalid-hash"))
        heading = context.get("heading", {})
        if any(not isinstance(heading.get(key), (str, int, type(None))) for key in ("arabic", "english", "level")):
            errors.append(safe_error(f"{context_path}.heading", "invalid-heading"))
    for collection_name in ("unresolved",):
        for index, finding in enumerate(record.get(collection_name, [])):
            if not all(isinstance(finding.get(key), str) and finding[key] for key in ("category", "priority")):
                errors.append(safe_error(f"{base}.{collection_name}[{index}]", "invalid-finding"))
    for context_index, context in enumerate(record.get("precedingMaterial", [])):
        for index, finding in enumerate(context.get("unresolved", [])):
            if not all(isinstance(finding.get(key), str) and finding[key] for key in ("category", "priority")):
                errors.append(safe_error(f"{base}.precedingMaterial[{context_index}].unresolved[{index}]", "invalid-finding"))
    for index, name in enumerate(record.get("names", [])):
        for key in KEYS["name"]:
            value = name.get(key)
            if not (isinstance(value, str) or isinstance(value, list) and all(isinstance(item, str) for item in value)):
                errors.append(safe_error(f"{base}.names[{index}].{key}", "invalid-name-field"))
    for index, formula in enumerate(record.get("formulas", [])):
        if not all(isinstance(formula.get(key), str) and formula[key] for key in KEYS["formula"]):
            errors.append(safe_error(f"{base}.formulas[{index}]", "invalid-formula"))
    if enforce_public_english:
        formulas = record.get("formulas", [])
        errors.extend(public_formula_errors(record, base, formula_rules))
        title = record.get("title", {})
        if isinstance(title, dict):
            errors.extend(
                public_english_errors(
                    title.get("english"),
                    formulas_for_scope(
                        formulas, record.get("id"), "titleArabic"
                    ),
                    record.get("id"),
                    f"{base}.title.english",
                    allowed_arabic_literals,
                )
            )
        entry_formulas = formulas_for_scope(formulas, record.get("id"), "arabic")
        errors.extend(
            public_english_errors(
                record.get("english"),
                entry_formulas,
                record.get("id"),
                f"{base}.english",
                allowed_arabic_literals,
            )
        )
        for index, context in enumerate(record.get("precedingMaterial", [])):
            if not isinstance(context, dict):
                continue
            errors.extend(
                public_english_errors(
                    context.get("english"),
                    formulas_for_scope(
                        formulas, context.get("id"), "arabic"
                    ),
                    context.get("id"),
                    f"{base}.precedingMaterial[{index}].english",
                )
            )
            heading = context.get("heading", {})
            if isinstance(heading, dict):
                errors.extend(
                    public_english_errors(
                        heading.get("english"),
                        formulas_for_scope(
                            formulas, context.get("id"), "headingArabic"
                        ),
                        context.get("id"),
                        f"{base}.precedingMaterial[{index}].heading.english",
                    )
                )
    source = record.get("source", {})
    if not COMMIT.fullmatch(str(source.get("commit", ""))):
        errors.append(safe_error(f"{base}.source.commit", "invalid-commit"))
    for key in ("artifactSha256", "exactTextSha256"):
        if not SHA256.fullmatch(str(source.get(key, ""))):
            errors.append(safe_error(f"{base}.source.{key}", "invalid-hash"))
    license_record = source.get("license", {})
    if license_record.get("spdx") != "CC-BY-NC-SA-4.0" or license_record.get("url") != "https://creativecommons.org/licenses/by-nc-sa/4.0/" or not str(license_record.get("attribution", "")).strip():
        errors.append(safe_error(f"{base}.source.license", "license-mismatch"))
    if record.get("machineAssessment") not in {"passed", "needs_attention"} or record.get("humanReview") not in {"unreviewed", "in_review", "reviewed", "verified"}:
        errors.append(safe_error(base, "invalid-review-state"))
    return errors


def validate(
    path: Path = DEFAULT_PROPOSAL,
    *,
    require_current: bool = False,
) -> list[str]:
    proposal, errors = parse(path)
    if proposal is None:
        return errors
    if not isinstance(proposal, dict):
        return [safe_error("$", "expected-object")]
    if proposal.get("schemaVersion") == "1.3.0":
        schema = json.loads(
            (ROOT / "schemas" / "public-proposal.v2.schema.json").read_text(
                encoding="utf-8"
            )
        )
        if validate_schema_instance(proposal, schema):
            errors.append(safe_error("$", "schema-mismatch"))
    errors.extend(nested_key_errors(proposal))
    errors.extend(boundary_errors(proposal))
    schema_version = proposal.get("schemaVersion")
    expected = {
        "workId": "ibn-hajar-al-isabah",
        "publicationStatus": "public-working",
        "canonicalPromotion": "blocked",
        "consumerSchemaVersion": "2.1.0" if schema_version == "1.3.0" else "2.0.0",
    }
    for key, value in expected.items():
        if proposal.get(key) != value:
            errors.append(safe_error(f"$.{key}", "contract-mismatch"))
    if schema_version not in {"1.0.0", "1.1.0", "1.2.0", "1.3.0"}:
        errors.append(safe_error("$.schemaVersion", "contract-mismatch"))
    proposal_id = proposal.get("proposalId")
    if not isinstance(proposal_id, str) or not PROPOSAL_ID.fullmatch(proposal_id):
        errors.append(safe_error("$.proposalId", "contract-mismatch"))
    if schema_version == "1.0.0" and proposal_id != "issue-0026-public-proposal-v1":
        errors.append(safe_error("$.proposalId", "contract-mismatch"))
    records = proposal.get("records", [])
    if not isinstance(records, list) or not records:
        errors.append(safe_error("$.records", "record-count-mismatch"))
        return errors
    if schema_version == "1.0.0" and len(records) != 1537:
        errors.append(safe_error("$.records", "record-count-mismatch"))
    seen: set[str] = set()
    previous: tuple[int, str] | None = None
    enforce_public_english = (
        schema_version in {"1.2.0", "1.3.0"}
        and (schema_version, str(proposal_id)) not in HISTORICAL_POLICY_BINDINGS
    )
    active_title_decisions: dict[int, dict[str, Any]] = {}
    if enforce_public_english:
        profile_id = proposal.get("entryTitleDecisions", {}).get("profileId")
        profile_path = ROOT / "profiles" / f"{profile_id}.json"
        try:
            active_title_decisions = title_contract.decision_index(
                title_contract.load(profile_path)
            )
        except (OSError, ValueError, json.JSONDecodeError):
            active_title_decisions = {}
    for index, record in enumerate(records):
        base = f"$.records[{index}]"
        if not isinstance(record, dict):
            errors.append(safe_error(base, "expected-object"))
            continue
        record_id = record.get("id")
        if not isinstance(record_id, str) or not IDENTIFIER.fullmatch(record_id):
            errors.append(safe_error(f"{base}.id", "invalid-stable-id"))
            continue
        if record_id in seen:
            errors.append(safe_error(f"{base}.id", "duplicate-stable-id"))
        seen.add(record_id)
        ordinal = record.get("sourceOrdinal")
        if not isinstance(ordinal, int):
            errors.append(safe_error(f"{base}.sourceOrdinal", "invalid-order"))
        else:
            current = (ordinal, record_id)
            if previous is not None and current <= previous:
                errors.append(safe_error(base, "unstable-order"))
            previous = current
        record_version = "2.1.0" if schema_version == "1.3.0" else "2.0.0"
        if record.get("schemaVersion") != record_version or record.get("kind") != "entry":
            errors.append(safe_error(base, "consumer-contract-mismatch"))
        formula_rules = (
            FORMULA_RULES if schema_version == "1.3.0" else LEGACY_FORMULA_RULES
        )
        active_title_decision = (
            active_title_decisions.get(record.get("id"))
            or active_title_decisions.get(record.get("printedEntryNumber"), {})
        )
        allowed_title_literals = governed_arabic_literals(
            "\n".join(
                str(active_title_decision.get(field, {}).get("en", ""))
                for field in ("title", "bodyOpening")
            ),
            formula_rules,
        )
        errors.extend(
            record_semantic_errors(
                record,
                base,
                enforce_public_english=enforce_public_english,
                allowed_arabic_literals=allowed_title_literals,
                formula_rules=formula_rules,
            )
        )
        title_only = schema_version == "1.3.0" and record.get("bodyState") == "title-only"
        if title_only:
            if record.get("arabic") != "" or record.get("english") != "":
                errors.append(safe_error(base, "title-only-body-mismatch"))
        elif not str(record.get("arabic", "")).strip() or not str(record.get("english", "")).strip():
            errors.append(safe_error(base, "incomplete-bilingual-content"))
        if record.get("source", {}).get("authorityId") != "openiti-cleaned-arabic-comparison":
            errors.append(safe_error(f"{base}.source.authorityId", "source-mismatch"))
        if record.get("source", {}).get("artifactSha256") != proposal.get("sourceAuthority", {}).get("sha256"):
            errors.append(safe_error(f"{base}.source.artifactSha256", "source-mismatch"))
        if record.get("policy") != proposal.get("policy"):
            errors.append(safe_error(f"{base}.policy", "policy-mismatch"))
        if proposal_id in SOURCE_DERIVED_NAME_ID_PROPOSALS:
            for name_index, name in enumerate(record.get("names", []), start=1):
                expected_name_id = f"{record_id}-name-{name_index:03d}"
                if not isinstance(name, dict) or name.get("id") != expected_name_id:
                    errors.append(
                        safe_error(
                            f"{base}.names[{name_index - 1}].id",
                            "invalid-stable-name-id",
                        )
                    )
    baseline = proposal.get("baseline", {})
    if baseline.get("recordCount") != len(records):
        errors.append(safe_error("$.baseline.recordCount", "record-count-mismatch"))
    if baseline.get("userFacingSha256") != sha256_bytes(parity_projection(records)):
        errors.append(safe_error("$.baseline.userFacingSha256", "user-facing-drift"))
    review = proposal.get("review", {})
    counts = {
        "machinePassed": sum(item.get("machineAssessment") == "passed" for item in records),
        "needsAttention": sum(item.get("machineAssessment") == "needs_attention" for item in records),
        "humanReviewed": sum(item.get("humanReview") in {"reviewed", "verified"} for item in records),
        "humanUnreviewed": sum(item.get("humanReview") not in {"reviewed", "verified"} for item in records),
    }
    if review != counts:
        errors.append(safe_error("$.review", "review-count-mismatch"))
    authority = proposal.get("sourceAuthority", {})
    if not COMMIT.fullmatch(str(authority.get("commit", ""))) or not SHA256.fullmatch(str(authority.get("sha256", ""))):
        errors.append(safe_error("$.sourceAuthority", "source-mismatch"))
    authority_license = authority.get("license", {})
    if authority_license.get("spdx") != "CC-BY-NC-SA-4.0" or authority_license.get("url") != "https://creativecommons.org/licenses/by-nc-sa/4.0/" or not str(authority_license.get("attribution", "")).strip():
        errors.append(safe_error("$.sourceAuthority.license", "license-mismatch"))
    register = json.loads((ROOT / "compliance" / "source-register.v1.json").read_text(encoding="utf-8"))
    source = next((item for item in register["artifacts"] if item.get("id") == authority.get("sourceId")), None)
    if source is None or source.get("classification") != "approved-for-publication" or source.get("review_status") != "approved-for-public-working-edition":
        errors.append(safe_error("$.sourceAuthority.sourceId", "source-register-mismatch"))
    elif authority.get("commit") != source.get("source_revision", {}).get("commit") or authority.get("sha256") != source.get("integrity", {}).get("sha256"):
        errors.append(safe_error("$.sourceAuthority", "source-register-mismatch"))
    proposal_artifact = next(
        (
            item
            for item in register["artifacts"]
            if item.get("id") == proposal.get("proposalId")
        ),
        None,
    )
    if (
        proposal_artifact is None
        or proposal_artifact.get("classification") != "approved-for-publication"
        or proposal_artifact.get("integrity", {}).get("proposal_sha256")
        != sha256_file(path)
        or proposal_artifact.get("integrity", {}).get("public_entries")
        != len(records)
    ):
        errors.append(safe_error("$.proposalId", "proposal-register-mismatch"))
    historical_policy_hash = HISTORICAL_POLICY_BINDINGS.get(
        (schema_version, str(proposal_id))
    )
    if schema_version == "1.0.0":
        policy_hash = sha256_text_file(
            ROOT / "compliance" / "policy-binding.v1.json"
        )
    elif historical_policy_hash is not None:
        policy_hash = historical_policy_hash
    elif schema_version == "1.3.0":
        successor_policy = ROOT / "compliance" / "policy-binding.v9.json"
        policy_hash = (
            sha256_text_file(successor_policy)
            if successor_policy.is_file()
            else None
        )
    else:
        policy_hash = sha256_text_file(
            ROOT / "compliance" / "policy-binding.v7.json"
        )
    if proposal.get("policy", {}).get("bindingSha256") != policy_hash:
        errors.append(safe_error("$.policy.bindingSha256", "policy-mismatch"))
    rights = json.loads((ROOT / "compliance" / "rights-matrix.al-isabah.v1.json").read_text(encoding="utf-8"))
    if proposal.get("rights", {}).get("matrixId") != rights.get("matrix_id"):
        errors.append(safe_error("$.rights.matrixId", "rights-mismatch"))
    if schema_version == "1.0.0":
        history = proposal.get("historicalEvidence", {})
        expected_history = {
            "packetGitBlobSha1": "4f3ebf1ec42d17825f5957280b6d21636f05ee39",
            "packetGitBlobSha256": "809de448fdb9079bdea6fc88ad73c6d092db7c20222d353ab640e84232c4c526",
            "packetGitBlobBytes": 34475553,
            "reviewGitBlobSha1": "b1a9a8ebdd66d995cbe5d2c4750675306e373afd",
            "reviewSha256": "58efb42068837520494f4a90ee7555a440e93cbf98fd2388bf4429807e7453f1",
            "historyPreserved": True,
        }
        if history != expected_history:
            errors.append(safe_error("$.historicalEvidence", "historical-evidence-mismatch"))
    else:
        evidence = proposal.get("evidenceBinding", {})
        for key in ("packetSetSha256", "reviewSetSha256", "recordProjectionSha256"):
            if not SHA256.fullmatch(str(evidence.get(key, ""))):
                errors.append(safe_error(f"$.evidenceBinding.{key}", "invalid-hash"))
        if (
            evidence.get("kind") != "machine-ready-packet-set"
            or not isinstance(evidence.get("packetCount"), int)
            or evidence.get("packetCount", 0) < 1
            or evidence.get("reviewCount") != evidence.get("packetCount")
        ):
            errors.append(safe_error("$.evidenceBinding", "evidence-binding-mismatch"))
        if evidence.get("recordProjectionSha256") != records_sha256(records):
            errors.append(safe_error("$.evidenceBinding.recordProjectionSha256", "projection-mismatch"))
    if schema_version in {"1.2.0", "1.3.0"} or require_current:
        errors.extend(current_readiness_errors(proposal))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", type=Path, default=DEFAULT_PROPOSAL)
    parser.add_argument(
        "--allow-historical",
        action="store_true",
        help="validate an immutable 1.0/1.1 artifact without claiming current readiness",
    )
    args = parser.parse_args()
    errors = validate(
        args.path.resolve(),
        require_current=not args.allow_historical,
    )
    if errors:
        print(summarize(errors))
        for error in errors:
            print(error)
        return 1
    proposal = json.loads(args.path.read_text(encoding="utf-8"))
    print(
        f"Public proposal valid: records={len(proposal['records'])}; "
        f"proposal-sha256={sha256_file(args.path)}; "
        f"order-sha256={order_sha256(proposal['records'])}; "
        f"user-facing-sha256={proposal['baseline']['userFacingSha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

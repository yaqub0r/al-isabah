#!/usr/bin/env python3
"""Validate public-proposal.v1 and its repository bindings."""

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
import validate_entry_titles as title_contract


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROPOSAL = (
    ROOT / "content" / "public-proposals" / "issue-0070.public-proposal.json"
)
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
}
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
        if schema_version == "1.2.0"
        else PACKET_SET_TOP_KEYS
    )
    errors = exact_keys(proposal, top_keys, "$")
    top_objects = ["sourceAuthority", "rights", "policy", "review", "baseline"]
    top_objects.append("historicalEvidence" if legacy else "evidenceBinding")
    if schema_version == "1.2.0":
        top_objects.extend(["entryTitleDecisions", "sliceContext"])
    for key in top_objects:
        errors.extend(exact_keys(proposal.get(key), KEYS[key], f"$.{key}"))
    authority = proposal.get("sourceAuthority", {})
    errors.extend(exact_keys(authority.get("license"), KEYS["license"], "$.sourceAuthority.license"))
    if schema_version == "1.2.0":
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
        errors.extend(exact_keys(record, RECORD_KEYS, base))
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
    seen_numbers: set[int] = set()
    for index, record in enumerate(records):
        base = f"$.records[{index}]"
        number = record.get("printedEntryNumber")
        if not isinstance(number, int) or number in seen_numbers:
            errors.append(
                safe_error(
                    f"{base}.printedEntryNumber",
                    "ambiguous-title-decision-key",
                )
            )
            continue
        seen_numbers.add(number)
        decision = decisions.get(number)
        if decision is None:
            errors.append(
                safe_error(f"{base}.title", "missing-title-body-decision")
            )
            continue
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
        if not str(record.get("arabic", "")).startswith(
            decision["bodyOpening"]["ar"]
        ) or not str(record.get("english", "")).startswith(
            decision["bodyOpening"]["en"]
        ):
            errors.append(
                safe_error(base, "title-body-opening-mismatch")
            )
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
    if proposal.get("schemaVersion") != "1.2.0":
        return [safe_error("$.schemaVersion", "historical-proposal-not-current")]
    return _title_decision_errors(proposal) + _slice_context_errors(proposal)


def record_semantic_errors(record: dict[str, Any], base: str) -> list[str]:
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
    errors.extend(nested_key_errors(proposal))
    errors.extend(boundary_errors(proposal))
    schema_version = proposal.get("schemaVersion")
    expected = {
        "workId": "ibn-hajar-al-isabah",
        "publicationStatus": "public-working",
        "canonicalPromotion": "blocked",
        "consumerSchemaVersion": "2.0.0",
    }
    for key, value in expected.items():
        if proposal.get(key) != value:
            errors.append(safe_error(f"$.{key}", "contract-mismatch"))
    if schema_version not in {"1.0.0", "1.1.0", "1.2.0"}:
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
        if record.get("schemaVersion") != "2.0.0" or record.get("kind") != "entry":
            errors.append(safe_error(base, "consumer-contract-mismatch"))
        errors.extend(record_semantic_errors(record, base))
        if not str(record.get("arabic", "")).strip() or not str(record.get("english", "")).strip():
            errors.append(safe_error(base, "incomplete-bilingual-content"))
        if record.get("source", {}).get("authorityId") != "openiti-cleaned-arabic-comparison":
            errors.append(safe_error(f"{base}.source.authorityId", "source-mismatch"))
        if record.get("source", {}).get("artifactSha256") != proposal.get("sourceAuthority", {}).get("sha256"):
            errors.append(safe_error(f"{base}.source.artifactSha256", "source-mismatch"))
        if record.get("policy") != proposal.get("policy"):
            errors.append(safe_error(f"{base}.policy", "policy-mismatch"))
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
    else:
        policy_hash = sha256_text_file(
            ROOT / "compliance" / "policy-binding.v3.json"
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
    if schema_version == "1.2.0" or require_current:
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

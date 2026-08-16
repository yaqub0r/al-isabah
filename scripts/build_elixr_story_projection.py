#!/usr/bin/env python3
"""Build the text-free Khadijah story projection from a pinned public release."""

from __future__ import annotations

import argparse
import copy
import json
import re
from pathlib import Path
from typing import Any

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


ROOT = Path(__file__).resolve().parents[1]
ADMISSION = ROOT / "profiles" / "story-projections" / "khadijah.v1.json"
PROPOSAL = ROOT / "content" / "public-proposals" / "issue-0026.public-proposal.json"
CLOSURE = ROOT / "compliance" / "publication" / "issue-0026.release-closure.v1.json"
RIGHTS = ROOT / "compliance" / "rights-matrix.al-isabah.v1.json"
OUTPUT = ROOT / "content" / "story-projections" / "khadijah.elixr-approved-story-projection.v1.json"
SCHEMA = ROOT / "schemas" / "elixr-approved-story-projection.v1.schema.json"
POLICY = ROOT / "compliance" / "policy-binding.v1.json"
REPOSITORY = "https://github.com/yaqub0r/al-isabah"
EXCLUDED_MATERIAL = [
    "arabic-source-body",
    "blind-drafts-and-critiques",
    "credentials-and-filesystem-paths",
    "dialogue",
    "english-translation-body",
    "model-traces-and-prompts",
    "private-notes-and-locators",
    "quotations-and-excerpts",
    "restricted-witness-expression",
    "unknown-fields",
]

EXPECTED_RELEASE = {
    "repositoryCommit": "278e4e43f983ff7733368557516406f1f53211dc",
    "releaseTag": "public-working-278e4e43f983ff7733368557516406f1f53211dc",
    "immutable": True,
    "distributionId": "al-isabah-public-working-278e4e43f983",
    "assetName": "al-isabah-public-distribution-278e4e43f983ff7733368557516406f1f53211dc.zip",
    "assetSha256": "41c3ffd1b665a7e9af689c5540b668907cb6b84f4fae23033ab418209d1e1329",
    "proposalId": "issue-0026-public-proposal-v1",
    "proposalSha256": "d3724903dd3ffd8030390415464fcbc9728274f971dd2b774e6384ecda30359c",
    "closureId": "issue-0026-public-working-closure-v1",
    "closureSha256": "3dba70776b97ae72d690e2db3f993eee39878754678bba329c4248f460738274",
}
EXPECTED_CANDIDATES = {
    "openiti-5835c183-unit-000097": {
        "recordSha256": "d1dae602518ab9bf68365e6cfc4b25cae4f8c62911d5b4893cb74078f8dbe433",
        "decision": "admitted",
        "storyUseTier": "attributed_disputed_report",
        "rationaleCodes": [
            "competing-genealogical-attributions",
            "transmission-chain-criticism",
        ],
    },
    "openiti-5835c183-unit-000171": {
        "recordSha256": "f260428cbcaf23356d29e0fa953c47c78a667c2f4c46f17cade87da53dd439da",
        "decision": "admitted",
        "storyUseTier": "factual_spine",
        "rationaleCodes": ["machine-passed-no-unresolved-findings"],
    },
    "openiti-5835c183-unit-000399": {
        "recordSha256": "c32808e95e4db9ac44d68d00a02a111f43a26d270c3e2e0b19b5c6d5de4d9b03",
        "decision": "admitted",
        "storyUseTier": "attributed_disputed_report",
        "rationaleCodes": [
            "competing-maternal-attributions",
            "missing-corroboration",
            "source-author-rejection",
        ],
    },
    "openiti-5835c183-unit-000795": {
        "recordSha256": "80c18e957eab34b3ca73fd7716b95d0bb3c2ee882a0530983f259c8afc4807fb",
        "decision": "admitted",
        "storyUseTier": "attributed_disputed_report",
        "rationaleCodes": [
            "competing-journey-contexts",
            "identity-and-religious-affiliation-ambiguity",
            "transmission-and-interpolation-qualification",
            "chronology-uncertainty",
        ],
    },
}
EXPECTED_UNCERTAINTY_CODES = [
    "source-reported-genealogical-uncertainty",
    "source-reported-killer-variant",
    "otherwise-unattested-maternal-attribution",
    "identity-religion-and-chronology",
    "hadith-interpolation",
    "companion-status",
]
EXPECTED_CLAIM_IDS = {
    "isabah-claim-al-aswad-nephew-of-khadijah-v1",
    "isabah-claim-al-aswad-migration-one-v1",
    "isabah-claim-al-aswad-migration-two-v1",
    "isabah-claim-asad-nephew-of-khadijah-v1",
    "isabah-claim-asad-son-of-nawfal-v1",
    "isabah-claim-nawfal-brother-of-khadijah-v1",
    "isabah-claim-khadijah-mother-of-ibrahim-v1",
    "isabah-claim-mariya-mother-of-ibrahim-v1",
    "isabah-claim-abu-talib-commercial-journey-v1",
    "isabah-claim-khadijah-commercial-journey-v1",
}
STORY_UNSUITABILITY_RATIONALE_CODES = {
    "chronology-ambiguity-prevents-safe-story-use",
    "identity-ambiguity-prevents-safe-story-use",
    "interpolation-prevents-safe-story-use",
    "unresolvable-claim-identity",
    "unsupported-causal-sequence",
}

TOP_KEYS = {
    "schemaVersion", "admissionId", "projectionId", "workId", "sourceRelease",
    "rights", "candidateRecords", "persons", "events", "relationships",
    "attestedClaims", "inferredClaims", "ambiguitySets", "review", "lifecycle",
}
KEYS = {
    "sourceRelease": set(EXPECTED_RELEASE),
    "rights": {
        "matrixId", "matrixSha256", "license", "licenseUrl", "useClassification",
        "softwareLicenseGranted", "attribution",
    },
    "candidateRecord": {
        "recordId", "sourceOrdinal", "recordSha256", "decision", "storyUseTier",
        "rationaleCodes", "machineAssessment", "humanReview", "uncertaintyCodes",
    },
    "person": {"id", "roles", "sourceBindings"},
    "sourceBinding": {"recordId", "sourceNameId"},
    "event": {"id", "type", "temporalStatus", "participantRoles", "sourceRecordIds"},
    "participantRole": {"personId", "role"},
    "relationship": {"id", "type", "subjectPersonId", "objectPersonId", "sourceRecordIds"},
    "claim": {
        "id", "claimType", "subjectId", "predicate", "objectId", "assertionClass",
        "sourceReportExistence", "sourceCriticalStatus", "evidentiaryStrength",
        "transmissionStrength", "storyUseTier", "storyAttributionRequired",
        "rationaleCodes", "factualAmbiguityCodes", "sourceRecordIds", "status",
        "correctionOfClaimId", "supersedesClaimIds", "supersededByClaimId",
    },
    "ambiguitySet": {
        "id", "memberClaimIds", "presentationMode", "resolutionStatus",
        "rationaleCodes", "sourceRecordIds",
    },
    "review": {"coverage", "confidence", "humanReviewEffect", "releaseClassEffect", "uncertaintyCodes"},
    "lifecycle": {"status", "correctsProjectionId", "supersedesProjectionIds", "supersededByProjectionId"},
}
PROHIBITED_PROJECTION_KEY_FRAGMENTS = {
    "arabic", "english", "dialogue", "prose", "quote", "excerpt", "draft",
    "critique", "model", "prompt", "response", "reasoning", "trace", "witness",
    "ocr", "raw", "note", "credential", "private", "filesystem", "path",
}
STABLE_ID = re.compile(r"^isabah-(person|event|relationship|claim)-[a-z0-9-]+-v1$")
AMBIGUITY_ID = re.compile(r"^isabah-ambiguity-[a-z0-9-]+-v1$")


class ProjectionError(RuntimeError):
    """Raised when a story projection cannot be produced safely."""


def parse(path: Path) -> tuple[Any | None, list[str]]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), []
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return None, [safe_error(f"$.line[{getattr(error, 'lineno', 0)}]", "invalid-json")]


def normalized_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def projection_boundary_errors(value: Any, path: str = "$") -> list[str]:
    errors = boundary_errors(value, path) if path == "$" else []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            normalized = normalized_key(str(key))
            if any(fragment in normalized for fragment in PROHIBITED_PROJECTION_KEY_FRAGMENTS):
                errors.append(safe_error(child_path, "story-projection-prohibited-field"))
            errors.extend(projection_boundary_errors(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            errors.extend(projection_boundary_errors(child, f"{path}[{index}]"))
    return errors


def record_sha256(record: dict[str, Any]) -> str:
    return sha256_bytes(canonical_json(record))


def nested_key_errors(admission: dict[str, Any]) -> list[str]:
    errors = exact_keys(admission, TOP_KEYS, "$")
    for key in ("sourceRelease", "rights", "review", "lifecycle"):
        errors.extend(exact_keys(admission.get(key), KEYS[key], f"$.{key}"))
    for index, item in enumerate(admission.get("candidateRecords", [])):
        errors.extend(exact_keys(item, KEYS["candidateRecord"], f"$.candidateRecords[{index}]"))
    for index, person in enumerate(admission.get("persons", [])):
        base = f"$.persons[{index}]"
        errors.extend(exact_keys(person, KEYS["person"], base))
        for binding_index, binding in enumerate(person.get("sourceBindings", [])):
            errors.extend(exact_keys(binding, KEYS["sourceBinding"], f"{base}.sourceBindings[{binding_index}]"))
    for index, event in enumerate(admission.get("events", [])):
        base = f"$.events[{index}]"
        errors.extend(exact_keys(event, KEYS["event"], base))
        for role_index, role in enumerate(event.get("participantRoles", [])):
            errors.extend(exact_keys(role, KEYS["participantRole"], f"{base}.participantRoles[{role_index}]"))
    for index, relationship in enumerate(admission.get("relationships", [])):
        errors.extend(exact_keys(relationship, KEYS["relationship"], f"$.relationships[{index}]"))
    for collection in ("attestedClaims", "inferredClaims"):
        for index, claim in enumerate(admission.get(collection, [])):
            errors.extend(exact_keys(claim, KEYS["claim"], f"$.{collection}[{index}]"))
    for index, ambiguity in enumerate(admission.get("ambiguitySets", [])):
        errors.extend(exact_keys(ambiguity, KEYS["ambiguitySet"], f"$.ambiguitySets[{index}]"))
    return errors


def _unique_ids(items: list[dict[str, Any]], path: str) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        identifier = item.get("id")
        if not isinstance(identifier, str) or not STABLE_ID.fullmatch(identifier):
            errors.append(safe_error(f"{path}[{index}].id", "invalid-stable-id"))
        elif identifier in seen:
            errors.append(safe_error(f"{path}[{index}].id", "duplicate-stable-id"))
        else:
            seen.add(identifier)
    return errors


def admission_errors(admission: dict[str, Any]) -> list[str]:
    errors = nested_key_errors(admission) + projection_boundary_errors(admission)
    expected_top = {
        "schemaVersion": "1.0.0",
        "admissionId": "al-isabah-khadijah-elixr-story-source-admission-v1",
        "projectionId": "al-isabah-khadijah-elixr-approved-story-projection-v1",
        "workId": "ibn-hajar-al-isabah",
    }
    for key, expected in expected_top.items():
        if admission.get(key) != expected:
            errors.append(safe_error(f"$.{key}", "contract-mismatch"))
    if admission.get("sourceRelease") != EXPECTED_RELEASE:
        errors.append(safe_error("$.sourceRelease", "release-mismatch"))

    proposal, proposal_errors = parse(PROPOSAL)
    closure, closure_errors = parse(CLOSURE)
    rights, rights_errors = parse(RIGHTS)
    errors.extend(proposal_errors + closure_errors + rights_errors)
    if not isinstance(proposal, dict) or not isinstance(closure, dict) or not isinstance(rights, dict):
        return errors

    if sha256_file(PROPOSAL) != EXPECTED_RELEASE["proposalSha256"]:
        errors.append(safe_error("$.sourceRelease.proposalSha256", "proposal-mismatch"))
    if sha256_text_file(CLOSURE) != EXPECTED_RELEASE["closureSha256"]:
        errors.append(safe_error("$.sourceRelease.closureSha256", "closure-mismatch"))
    if closure.get("closureId") != EXPECTED_RELEASE["closureId"] or closure.get("publicProposal", {}).get("sha256") != EXPECTED_RELEASE["proposalSha256"]:
        errors.append(safe_error("$.sourceRelease", "closure-mismatch"))
    authority = proposal.get("sourceAuthority", {})
    if (
        authority.get("sourceId") != "openiti-cleaned-arabic-comparison"
        or authority.get("commit") != "5835c183b8bbf4ea454d5c1be2b168b669403771"
        or authority.get("sha256") != "bc9db8134c8278973967c91c00324531833f643fc0fb2c8ebe318c9ed4469eea"
        or proposal.get("policy", {}).get("bindingSha256")
        != sha256_text_file(POLICY)
        or proposal.get("consumerSchemaVersion") != "2.0.0"
    ):
        errors.append(safe_error("$.sourceRelease", "source-authority-mismatch"))

    expected_rights = {
        "matrixId": rights.get("matrix_id"),
        "matrixSha256": sha256_text_file(RIGHTS),
        "license": rights.get("public_content_license", {}).get("spdx"),
        "licenseUrl": rights.get("public_content_license", {}).get("url"),
        "useClassification": rights.get("publication_decision", {}).get("public_reading"),
        "softwareLicenseGranted": rights.get("public_content_license", {}).get("software_license_granted"),
        "attribution": rights.get("attribution"),
    }
    if admission.get("rights") != expected_rights:
        errors.append(safe_error("$.rights", "rights-mismatch"))
    if closure.get("rights", {}).get("matrixId") != expected_rights["matrixId"] or closure.get("rights", {}).get("license") != expected_rights["license"]:
        errors.append(safe_error("$.rights", "closure-rights-mismatch"))

    records = {record.get("id"): record for record in proposal.get("records", []) if isinstance(record, dict)}
    candidates = admission.get("candidateRecords", [])
    candidate_ids = [item.get("recordId") for item in candidates if isinstance(item, dict)]
    if candidate_ids != list(EXPECTED_CANDIDATES):
        errors.append(safe_error("$.candidateRecords", "candidate-inventory-mismatch"))
    for index, candidate in enumerate(candidates):
        base = f"$.candidateRecords[{index}]"
        record = records.get(candidate.get("recordId"))
        expected = EXPECTED_CANDIDATES.get(candidate.get("recordId"))
        if record is None or expected is None:
            errors.append(safe_error(base, "source-record-mismatch"))
            continue
        actual_uncertainty = [item.get("category") for item in record.get("unresolved", [])]
        if candidate.get("recordSha256") != record_sha256(record) or candidate.get("recordSha256") != expected["recordSha256"]:
            errors.append(safe_error(f"{base}.recordSha256", "source-record-hash-mismatch"))
        if candidate.get("decision") != expected["decision"]:
            errors.append(safe_error(f"{base}.decision", "admission-decision-mismatch"))
        if candidate.get("sourceOrdinal") != record.get("sourceOrdinal"):
            errors.append(safe_error(f"{base}.sourceOrdinal", "source-record-mismatch"))
        if candidate.get("machineAssessment") != record.get("machineAssessment") or candidate.get("humanReview") != record.get("humanReview"):
            errors.append(safe_error(base, "review-state-mismatch"))
        if candidate.get("uncertaintyCodes") != actual_uncertainty:
            errors.append(safe_error(f"{base}.uncertaintyCodes", "uncertainty-mismatch"))
        if candidate.get("storyUseTier") != expected["storyUseTier"]:
            errors.append(safe_error(f"{base}.storyUseTier", "story-use-tier-mismatch"))
        if candidate.get("rationaleCodes") != expected["rationaleCodes"]:
            errors.append(safe_error(f"{base}.rationaleCodes", "admission-rationale-mismatch"))

    admitted = {item.get("recordId") for item in candidates if item.get("decision") == "admitted"}
    if admitted != set(EXPECTED_CANDIDATES):
        errors.append(safe_error("$.candidateRecords", "admitted-source-mismatch"))
    factual_spine_record = records.get("openiti-5835c183-unit-000171", {})
    if factual_spine_record.get("machineAssessment") != "passed" or factual_spine_record.get("unresolved") != []:
        errors.append(safe_error("$.candidateRecords", "factual-spine-source-not-ready"))

    for collection in ("persons", "events", "relationships", "attestedClaims", "inferredClaims"):
        errors.extend(_unique_ids(admission.get(collection, []), f"$.{collection}"))
    persons = {item.get("id"): item for item in admission.get("persons", [])}
    events = {item.get("id"): item for item in admission.get("events", [])}
    relationships = {item.get("id"): item for item in admission.get("relationships", [])}
    source_names = {
        (record_id, name.get("id"))
        for record_id in admitted
        for name in records.get(record_id, {}).get("names", [])
    }
    for index, person in enumerate(admission.get("persons", [])):
        if not person.get("roles") or len(person.get("roles", [])) != len(set(person.get("roles", []))):
            errors.append(safe_error(f"$.persons[{index}].roles", "invalid-role-set"))
        for binding_index, binding in enumerate(person.get("sourceBindings", [])):
            if (binding.get("recordId"), binding.get("sourceNameId")) not in source_names:
                errors.append(safe_error(f"$.persons[{index}].sourceBindings[{binding_index}]", "source-name-mismatch"))
    participant_roles = {
        "migrant", "commissioning_principal", "traveler", "companion",
        "caravan_leader", "encountered_person",
    }
    for index, event in enumerate(admission.get("events", [])):
        if event.get("type") not in {"migration", "commercial_journey"} or event.get("temporalStatus") not in {"unstated", "relative_only"}:
            errors.append(safe_error(f"$.events[{index}]", "event-contract-mismatch"))
        if set(event.get("sourceRecordIds", [])) - admitted:
            errors.append(safe_error(f"$.events[{index}].sourceRecordIds", "unadmitted-source"))
        for role_index, role in enumerate(event.get("participantRoles", [])):
            if role.get("personId") not in persons or role.get("role") not in participant_roles:
                errors.append(safe_error(f"$.events[{index}].participantRoles[{role_index}]", "participant-role-mismatch"))
    for index, relationship in enumerate(admission.get("relationships", [])):
        if relationship.get("type") not in {"nephew_of", "mother_of", "son_of", "brother_of"} or relationship.get("subjectPersonId") not in persons or relationship.get("objectPersonId") not in persons:
            errors.append(safe_error(f"$.relationships[{index}]", "relationship-contract-mismatch"))
        if set(relationship.get("sourceRecordIds", [])) - admitted:
            errors.append(safe_error(f"$.relationships[{index}].sourceRecordIds", "unadmitted-source"))
    all_claims = admission.get("attestedClaims", []) + admission.get("inferredClaims", [])
    claim_ids = {item.get("id") for item in all_claims}
    if claim_ids != EXPECTED_CLAIM_IDS or admission.get("inferredClaims") != []:
        errors.append(safe_error("$.attestedClaims", "claim-inventory-mismatch"))
    for collection, expected_class in (("attestedClaims", "attested"), ("inferredClaims", "inferred")):
        for index, claim in enumerate(admission.get(collection, [])):
            base = f"$.{collection}[{index}]"
            if claim.get("assertionClass") != expected_class:
                errors.append(safe_error(f"{base}.assertionClass", "assertion-class-mismatch"))
            if claim.get("sourceReportExistence") != "attested_in_source":
                errors.append(safe_error(f"{base}.sourceReportExistence", "source-report-existence-mismatch"))
            if claim.get("subjectId") not in persons:
                errors.append(safe_error(f"{base}.subjectId", "claim-subject-mismatch"))
            if claim.get("claimType") == "relationship":
                relationship = relationships.get(claim.get("objectId"), {})
                if (
                    relationship.get("type") != claim.get("predicate")
                    or relationship.get("subjectPersonId") != claim.get("subjectId")
                ):
                    errors.append(safe_error(base, "claim-object-mismatch"))
            elif claim.get("claimType") == "event_participation":
                event = events.get(claim.get("objectId"), {})
                participants = {role.get("personId") for role in event.get("participantRoles", [])}
                if claim.get("predicate") != "participated_in" or claim.get("subjectId") not in participants:
                    errors.append(safe_error(base, "claim-object-mismatch"))
            else:
                errors.append(safe_error(f"{base}.claimType", "claim-type-mismatch"))
            if set(claim.get("sourceRecordIds", [])) - admitted:
                errors.append(safe_error(f"{base}.sourceRecordIds", "unadmitted-source"))
            referenced = set(claim.get("supersedesClaimIds", []))
            for value in (claim.get("correctionOfClaimId"), claim.get("supersededByClaimId")):
                if value is not None:
                    referenced.add(value)
            if referenced - claim_ids:
                errors.append(safe_error(base, "claim-lifecycle-mismatch"))
            if claim.get("status") == "active" and referenced:
                errors.append(safe_error(base, "active-claim-has-lifecycle-link"))
            tier = claim.get("storyUseTier")
            critical = claim.get("sourceCriticalStatus")
            ambiguity = claim.get("factualAmbiguityCodes")
            attribution = claim.get("storyAttributionRequired")
            if tier == "factual_spine" and (
                claim.get("sourceRecordIds") != ["openiti-5835c183-unit-000171"]
                or critical != "unqualified"
                or claim.get("evidentiaryStrength") != "source_supported"
                or claim.get("transmissionStrength") != "source_supported"
                or ambiguity != []
                or attribution is not False
            ):
                errors.append(safe_error(base, "invalid-factual-spine"))
            if tier == "attributed_disputed_report" and (
                attribution is not True
                or critical not in {"qualified", "disputed", "rejected"}
                or not ambiguity
            ):
                errors.append(safe_error(base, "invalid-attributed-disputed-report"))
            if (critical != "unqualified" or ambiguity) and attribution is not True and tier != "factual_spine":
                errors.append(safe_error(base, "missing-story-attribution"))
            if tier == "not_suitable_for_story" and not (
                set(claim.get("rationaleCodes", [])) & STORY_UNSUITABILITY_RATIONALE_CODES
            ):
                errors.append(safe_error(base, "unsupported-story-exclusion"))

    ambiguity_sets = admission.get("ambiguitySets", [])
    seen_ambiguities: set[str] = set()
    expected_ambiguity_members = {
        "isabah-ambiguity-asad-genealogy-v1": {
            "isabah-claim-asad-nephew-of-khadijah-v1",
            "isabah-claim-asad-son-of-nawfal-v1",
            "isabah-claim-nawfal-brother-of-khadijah-v1",
        },
        "isabah-ambiguity-ibrahim-maternal-attribution-v1": {
            "isabah-claim-khadijah-mother-of-ibrahim-v1",
            "isabah-claim-mariya-mother-of-ibrahim-v1",
        },
        "isabah-ambiguity-bahira-journey-context-v1": {
            "isabah-claim-abu-talib-commercial-journey-v1",
            "isabah-claim-khadijah-commercial-journey-v1",
        },
    }
    for index, ambiguity in enumerate(ambiguity_sets):
        base = f"$.ambiguitySets[{index}]"
        identifier = ambiguity.get("id")
        if not isinstance(identifier, str) or not AMBIGUITY_ID.fullmatch(identifier):
            errors.append(safe_error(f"{base}.id", "invalid-ambiguity-id"))
        elif identifier in seen_ambiguities:
            errors.append(safe_error(f"{base}.id", "duplicate-ambiguity-id"))
        else:
            seen_ambiguities.add(identifier)
        if set(ambiguity.get("memberClaimIds", [])) != expected_ambiguity_members.get(identifier, set()):
            errors.append(safe_error(f"{base}.memberClaimIds", "ambiguity-membership-mismatch"))
        if set(ambiguity.get("memberClaimIds", [])) - claim_ids:
            errors.append(safe_error(f"{base}.memberClaimIds", "ambiguity-membership-mismatch"))
        if ambiguity.get("resolutionStatus") != "unresolved" or ambiguity.get("presentationMode") not in {"parallel_attributed_reports", "qualified_ambiguity_context"}:
            errors.append(safe_error(base, "ambiguity-presentation-mismatch"))
        if set(ambiguity.get("sourceRecordIds", [])) - admitted:
            errors.append(safe_error(f"{base}.sourceRecordIds", "unadmitted-source"))
    if seen_ambiguities != set(expected_ambiguity_members):
        errors.append(safe_error("$.ambiguitySets", "ambiguity-inventory-mismatch"))

    review = admission.get("review", {})
    if review != {
        "coverage": "partial",
        "confidence": "unscored",
        "humanReviewEffect": "per_record_metadata",
        "releaseClassEffect": "none",
        "uncertaintyCodes": EXPECTED_UNCERTAINTY_CODES,
    }:
        errors.append(safe_error("$.review", "review-contract-mismatch"))
    lifecycle = admission.get("lifecycle", {})
    if lifecycle != {
        "status": "active",
        "correctsProjectionId": None,
        "supersedesProjectionIds": [],
        "supersededByProjectionId": None,
    }:
        errors.append(safe_error("$.lifecycle", "projection-lifecycle-mismatch"))
    return errors


def build(admission_path: Path = ADMISSION) -> dict[str, Any]:
    admission, errors = parse(admission_path)
    if not isinstance(admission, dict):
        raise ProjectionError(summarize(errors))
    errors.extend(admission_errors(admission))
    if errors:
        raise ProjectionError(summarize(errors))
    proposal = json.loads(PROPOSAL.read_text(encoding="utf-8"))
    records = {record["id"]: record for record in proposal["records"]}
    admitted = [item for item in admission["candidateRecords"] if item["decision"] == "admitted"]
    source_records = []
    for item in admitted:
        record = records[item["recordId"]]
        source_records.append({
            "recordId": record["id"],
            "sourceOrdinal": record["sourceOrdinal"],
            "printedEntryNumber": record["printedEntryNumber"],
            "recordSha256": item["recordSha256"],
            "authorityUnitSha256": record["source"]["exactTextSha256"],
            "volume": record["volume"],
            "pages": [page["page"] for page in record["pages"]],
            "machineAssessment": record["machineAssessment"],
            "humanReview": record["humanReview"],
            "uncertaintyCodes": [finding["category"] for finding in record["unresolved"]],
        })
    projection = {
        "schemaVersion": "1.0.0",
        "projectionId": admission["projectionId"],
        "workId": admission["workId"],
        "producer": {
            "authorityId": "al-isabah",
            "repository": REPOSITORY,
            "role": "canonical-source-and-release-authority",
            "generatorId": "al-isabah-elixr-story-projection-builder-v1",
        },
        "contract": {
            "schemaId": "al-isabah.elixr-approved-story-projection.v1",
            "schemaVersion": "1.0.0",
            "schemaSha256": sha256_text_file(SCHEMA),
        },
        "publicationStatus": "public-working",
        "canonicalPromotion": "blocked",
        "scope": {
            "cohortId": "khadijah-public-working-seed-v1",
            "selection": "narrow-explicit-record-allowlist",
            "coverage": admission["review"]["coverage"],
            "sourceRecordCount": len(source_records),
            "personCount": len(admission["persons"]),
            "eventCount": len(admission["events"]),
            "relationshipCount": len(admission["relationships"]),
            "attestedClaimCount": len(admission["attestedClaims"]),
            "inferredClaimCount": len(admission["inferredClaims"]),
            "ambiguitySetCount": len(admission["ambiguitySets"]),
        },
        "sourceRelease": {
            **copy.deepcopy(admission["sourceRelease"]),
            "distributionSchemaVersion": "2.0.0",
            "sourceAuthorityId": "openiti-cleaned-arabic-comparison",
            "sourceAuthorityCommit": "5835c183b8bbf4ea454d5c1be2b168b669403771",
            "sourceArtifactSha256": "bc9db8134c8278973967c91c00324531833f643fc0fb2c8ebe318c9ed4469eea",
            "policyBindingSha256": sha256_text_file(POLICY),
        },
        "rights": {
            **copy.deepcopy(admission["rights"]),
            "canonicalPromotion": "blocked",
            "excludedMaterial": copy.deepcopy(EXCLUDED_MATERIAL),
        },
        "sourceRecords": source_records,
        "persons": copy.deepcopy(admission["persons"]),
        "events": copy.deepcopy(admission["events"]),
        "relationships": copy.deepcopy(admission["relationships"]),
        "claims": {
            "attested": copy.deepcopy(admission["attestedClaims"]),
            "inferred": copy.deepcopy(admission["inferredClaims"]),
        },
        "ambiguitySets": copy.deepcopy(admission["ambiguitySets"]),
        "review": {
            "coverage": admission["review"]["coverage"],
            "confidence": admission["review"]["confidence"],
            "sourceRecordCount": len(source_records),
            "machinePassed": sum(item["machineAssessment"] == "passed" for item in source_records),
            "needsAttention": sum(item["machineAssessment"] == "needs_attention" for item in source_records),
            "humanReviewed": sum(item["humanReview"] in {"reviewed", "verified"} for item in source_records),
            "humanReviewEffect": admission["review"]["humanReviewEffect"],
            "releaseClassEffect": admission["review"]["releaseClassEffect"],
            "uncertaintyCodes": copy.deepcopy(admission["review"]["uncertaintyCodes"]),
        },
        "lifecycle": copy.deepcopy(admission["lifecycle"]),
        "integrity": {
            "algorithm": "sha256",
            "canonicalization": "json-sort-keys-utf8-lf-v1",
            "admissionId": admission["admissionId"],
            "admissionSha256": sha256_text_file(admission_path),
            "proposalSha256": sha256_file(PROPOSAL),
            "closureSha256": sha256_text_file(CLOSURE),
            "rightsMatrixSha256": sha256_text_file(RIGHTS),
            "schemaSha256": sha256_text_file(SCHEMA),
            "sourceRecordSetSha256": sha256_bytes(canonical_json(source_records)),
            "claimSetSha256": sha256_bytes(canonical_json({
                "attested": admission["attestedClaims"],
                "inferred": admission["inferredClaims"],
            })),
            "ambiguitySetSha256": sha256_bytes(canonical_json(admission["ambiguitySets"])),
        },
    }
    payload = {key: value for key, value in projection.items() if key != "integrity"}
    projection["integrity"]["payloadSha256"] = sha256_bytes(canonical_json(payload))
    boundary = projection_boundary_errors(projection)
    if boundary:
        raise ProjectionError(summarize(boundary))
    return projection


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--admission", type=Path, default=ADMISSION)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        payload = canonical_json(build(args.admission.resolve()))
    except ProjectionError as error:
        print(error)
        return 1
    output = args.output.resolve()
    if args.check:
        if not output.is_file() or output.read_bytes() != payload:
            print("Elixr story projection is stale or missing.")
            return 1
        print(f"Elixr story projection is deterministic: sha256={sha256_bytes(payload)}")
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(payload)
    print(f"Built Elixr story projection: sha256={sha256_bytes(payload)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

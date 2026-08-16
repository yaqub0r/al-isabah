#!/usr/bin/env python3
"""Validate the closed, text-free Elixr-approved story projection."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import build_elixr_story_projection as builder
from public_boundary import canonical_json, exact_keys, safe_error, sha256_bytes, sha256_text_file, summarize


OUTPUT = builder.OUTPUT
TOP_KEYS = {
    "schemaVersion", "projectionId", "workId", "producer", "contract",
    "publicationStatus", "canonicalPromotion", "scope", "sourceRelease", "rights",
    "sourceRecords", "persons", "events", "relationships", "claims", "review",
    "ambiguitySets", "lifecycle", "integrity",
}
KEYS = {
    "producer": {"authorityId", "repository", "role", "generatorId"},
    "contract": {"schemaId", "schemaVersion", "schemaSha256"},
    "scope": {
        "cohortId", "selection", "coverage", "sourceRecordCount", "personCount",
        "eventCount", "relationshipCount", "attestedClaimCount", "inferredClaimCount",
        "ambiguitySetCount",
    },
    "sourceRelease": {
        "repositoryCommit", "releaseTag", "immutable", "distributionId", "assetName",
        "assetSha256", "proposalId", "proposalSha256", "closureId", "closureSha256",
        "distributionSchemaVersion", "sourceAuthorityId", "sourceAuthorityCommit",
        "sourceArtifactSha256", "policyBindingSha256",
    },
    "rights": {
        "matrixId", "matrixSha256", "license", "licenseUrl", "useClassification",
        "softwareLicenseGranted", "attribution", "canonicalPromotion", "excludedMaterial",
    },
    "sourceRecord": {
        "recordId", "sourceOrdinal", "printedEntryNumber", "recordSha256",
        "authorityUnitSha256", "volume", "pages", "machineAssessment", "humanReview",
        "uncertaintyCodes",
    },
    "person": {"id", "roles", "sourceBindings"},
    "sourceBinding": {"recordId", "sourceNameId"},
    "event": {"id", "type", "temporalStatus", "participantRoles", "sourceRecordIds"},
    "participantRole": {"personId", "role"},
    "relationship": {"id", "type", "subjectPersonId", "objectPersonId", "sourceRecordIds"},
    "claims": {"attested", "inferred"},
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
    "review": {
        "coverage", "confidence", "sourceRecordCount", "machinePassed", "needsAttention",
        "humanReviewed", "humanReviewEffect", "releaseClassEffect", "uncertaintyCodes",
    },
    "lifecycle": {"status", "correctsProjectionId", "supersedesProjectionIds", "supersededByProjectionId"},
    "integrity": {
        "algorithm", "canonicalization", "admissionId", "admissionSha256",
        "proposalSha256", "closureSha256", "rightsMatrixSha256", "schemaSha256",
        "sourceRecordSetSha256", "claimSetSha256", "ambiguitySetSha256",
        "payloadSha256",
    },
}


def nested_key_errors(projection: dict[str, Any]) -> list[str]:
    errors = exact_keys(projection, TOP_KEYS, "$")
    for key in ("producer", "contract", "scope", "sourceRelease", "rights", "claims", "review", "lifecycle", "integrity"):
        errors.extend(exact_keys(projection.get(key), KEYS[key], f"$.{key}"))
    for index, record in enumerate(projection.get("sourceRecords", [])):
        errors.extend(exact_keys(record, KEYS["sourceRecord"], f"$.sourceRecords[{index}]"))
    for index, person in enumerate(projection.get("persons", [])):
        base = f"$.persons[{index}]"
        errors.extend(exact_keys(person, KEYS["person"], base))
        for binding_index, binding in enumerate(person.get("sourceBindings", [])):
            errors.extend(exact_keys(binding, KEYS["sourceBinding"], f"{base}.sourceBindings[{binding_index}]"))
    for index, event in enumerate(projection.get("events", [])):
        base = f"$.events[{index}]"
        errors.extend(exact_keys(event, KEYS["event"], base))
        for role_index, role in enumerate(event.get("participantRoles", [])):
            errors.extend(exact_keys(role, KEYS["participantRole"], f"{base}.participantRoles[{role_index}]"))
    for index, relationship in enumerate(projection.get("relationships", [])):
        errors.extend(exact_keys(relationship, KEYS["relationship"], f"$.relationships[{index}]"))
    claims = projection.get("claims", {})
    for collection in ("attested", "inferred"):
        for index, claim in enumerate(claims.get(collection, [])):
            errors.extend(exact_keys(claim, KEYS["claim"], f"$.claims.{collection}[{index}]"))
    for index, ambiguity in enumerate(projection.get("ambiguitySets", [])):
        errors.extend(exact_keys(ambiguity, KEYS["ambiguitySet"], f"$.ambiguitySets[{index}]"))
    return errors


def semantic_errors(projection: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    expected_top = {
        "schemaVersion": "1.0.0",
        "projectionId": "al-isabah-khadijah-elixr-approved-story-projection-v1",
        "workId": "ibn-hajar-al-isabah",
        "publicationStatus": "public-working",
        "canonicalPromotion": "blocked",
    }
    for key, expected in expected_top.items():
        if projection.get(key) != expected:
            errors.append(safe_error(f"$.{key}", "contract-mismatch"))
    if projection.get("producer") != {
        "authorityId": "al-isabah",
        "repository": builder.REPOSITORY,
        "role": "canonical-source-and-release-authority",
        "generatorId": "al-isabah-elixr-story-projection-builder-v1",
    }:
        errors.append(safe_error("$.producer", "producer-mismatch"))
    if projection.get("contract") != {
        "schemaId": "al-isabah.elixr-approved-story-projection.v1",
        "schemaVersion": "1.0.0",
        "schemaSha256": sha256_text_file(builder.SCHEMA),
    }:
        errors.append(safe_error("$.contract", "schema-mismatch"))

    release = projection.get("sourceRelease", {})
    expected_release = {
        **builder.EXPECTED_RELEASE,
        "distributionSchemaVersion": "2.0.0",
        "sourceAuthorityId": "openiti-cleaned-arabic-comparison",
        "sourceAuthorityCommit": "5835c183b8bbf4ea454d5c1be2b168b669403771",
        "sourceArtifactSha256": "bc9db8134c8278973967c91c00324531833f643fc0fb2c8ebe318c9ed4469eea",
        "policyBindingSha256": sha256_text_file(builder.POLICY),
    }
    if release != expected_release:
        errors.append(safe_error("$.sourceRelease", "release-mismatch"))
    if release.get("immutable") is not True:
        errors.append(safe_error("$.sourceRelease.immutable", "mutable-source-release"))

    rights = projection.get("rights", {})
    if rights.get("canonicalPromotion") != "blocked" or rights.get("excludedMaterial") != builder.EXCLUDED_MATERIAL:
        errors.append(safe_error("$.rights", "rights-mismatch"))
    records = projection.get("sourceRecords", [])
    record_ids = {item.get("recordId") for item in records if isinstance(item, dict)}
    if record_ids != set(builder.EXPECTED_CANDIDATES):
        errors.append(safe_error("$.sourceRecords", "source-record-mismatch"))
    for index, record in enumerate(records):
        if not isinstance(record.get("pages"), list) or not record.get("pages") or any(not isinstance(page, int) or page < 1 for page in record.get("pages", [])):
            errors.append(safe_error(f"$.sourceRecords[{index}].pages", "invalid-safe-locator"))
    factual_record = next((item for item in records if item.get("recordId") == "openiti-5835c183-unit-000171"), {})
    if factual_record.get("machineAssessment") != "passed" or factual_record.get("uncertaintyCodes") != []:
        errors.append(safe_error("$.sourceRecords", "factual-spine-source-not-ready"))

    persons = {item.get("id"): item for item in projection.get("persons", [])}
    events = {item.get("id"): item for item in projection.get("events", [])}
    relationships = {item.get("id"): item for item in projection.get("relationships", [])}
    for index, person in enumerate(projection.get("persons", [])):
        for binding_index, binding in enumerate(person.get("sourceBindings", [])):
            if binding.get("recordId") not in record_ids:
                errors.append(safe_error(f"$.persons[{index}].sourceBindings[{binding_index}]", "unadmitted-source"))
    for index, event in enumerate(projection.get("events", [])):
        if event.get("type") not in {"migration", "commercial_journey"} or event.get("temporalStatus") not in {"unstated", "relative_only"}:
            errors.append(safe_error(f"$.events[{index}]", "event-contract-mismatch"))
        if set(event.get("sourceRecordIds", [])) - record_ids:
            errors.append(safe_error(f"$.events[{index}].sourceRecordIds", "unadmitted-source"))
        for role_index, role in enumerate(event.get("participantRoles", [])):
            if role.get("personId") not in persons:
                errors.append(safe_error(f"$.events[{index}].participantRoles[{role_index}]", "participant-role-mismatch"))
    for index, relationship in enumerate(projection.get("relationships", [])):
        if relationship.get("subjectPersonId") not in persons or relationship.get("objectPersonId") not in persons:
            errors.append(safe_error(f"$.relationships[{index}]", "relationship-contract-mismatch"))
        if set(relationship.get("sourceRecordIds", [])) - record_ids:
            errors.append(safe_error(f"$.relationships[{index}].sourceRecordIds", "unadmitted-source"))
    claims = projection.get("claims", {})
    all_claim_ids = {
        item.get("id")
        for collection in ("attested", "inferred")
        for item in claims.get(collection, [])
    }
    for collection, expected_class in (("attested", "attested"), ("inferred", "inferred")):
        for index, claim in enumerate(claims.get(collection, [])):
            base = f"$.claims.{collection}[{index}]"
            if claim.get("assertionClass") != expected_class:
                errors.append(safe_error(f"{base}.assertionClass", "assertion-class-mismatch"))
            if claim.get("sourceReportExistence") != "attested_in_source":
                errors.append(safe_error(f"{base}.sourceReportExistence", "source-report-existence-mismatch"))
            if claim.get("subjectId") not in persons:
                errors.append(safe_error(f"{base}.subjectId", "claim-subject-mismatch"))
            if claim.get("claimType") == "relationship":
                relationship = relationships.get(claim.get("objectId"), {})
                if relationship.get("type") != claim.get("predicate") or relationship.get("subjectPersonId") != claim.get("subjectId"):
                    errors.append(safe_error(f"{base}.objectId", "claim-object-mismatch"))
            elif claim.get("claimType") == "event_participation":
                event = events.get(claim.get("objectId"), {})
                participants = {role.get("personId") for role in event.get("participantRoles", [])}
                if claim.get("predicate") != "participated_in" or claim.get("subjectId") not in participants:
                    errors.append(safe_error(f"{base}.objectId", "claim-object-mismatch"))
            else:
                errors.append(safe_error(f"{base}.claimType", "claim-type-mismatch"))
            if set(claim.get("sourceRecordIds", [])) - record_ids:
                errors.append(safe_error(f"{base}.sourceRecordIds", "unadmitted-source"))
            lifecycle_ids = set(claim.get("supersedesClaimIds", []))
            for key in ("correctionOfClaimId", "supersededByClaimId"):
                if claim.get(key) is not None:
                    lifecycle_ids.add(claim[key])
            if lifecycle_ids - all_claim_ids:
                errors.append(safe_error(base, "claim-lifecycle-mismatch"))
            if claim.get("status") != "active" or lifecycle_ids:
                errors.append(safe_error(base, "unavailable-or-superseded-assertion"))
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
                set(claim.get("rationaleCodes", [])) & builder.STORY_UNSUITABILITY_RATIONALE_CODES
            ):
                errors.append(safe_error(base, "unsupported-story-exclusion"))

    if all_claim_ids != builder.EXPECTED_CLAIM_IDS or claims.get("inferred") != []:
        errors.append(safe_error("$.claims", "claim-inventory-mismatch"))
    ambiguities = projection.get("ambiguitySets", [])
    ambiguity_ids: set[str] = set()
    for index, ambiguity in enumerate(ambiguities):
        base = f"$.ambiguitySets[{index}]"
        identifier = ambiguity.get("id")
        if identifier in ambiguity_ids:
            errors.append(safe_error(f"{base}.id", "duplicate-ambiguity-id"))
        ambiguity_ids.add(identifier)
        if set(ambiguity.get("memberClaimIds", [])) - all_claim_ids:
            errors.append(safe_error(f"{base}.memberClaimIds", "ambiguity-membership-mismatch"))
        if ambiguity.get("resolutionStatus") != "unresolved" or ambiguity.get("presentationMode") not in {"parallel_attributed_reports", "qualified_ambiguity_context"}:
            errors.append(safe_error(base, "ambiguity-presentation-mismatch"))
        if set(ambiguity.get("sourceRecordIds", [])) - record_ids:
            errors.append(safe_error(f"{base}.sourceRecordIds", "unadmitted-source"))
    if ambiguity_ids != {
        "isabah-ambiguity-asad-genealogy-v1",
        "isabah-ambiguity-ibrahim-maternal-attribution-v1",
        "isabah-ambiguity-bahira-journey-context-v1",
    }:
        errors.append(safe_error("$.ambiguitySets", "ambiguity-inventory-mismatch"))
    lifecycle = projection.get("lifecycle", {})
    if lifecycle.get("status") != "active" or lifecycle.get("supersededByProjectionId") is not None:
        errors.append(safe_error("$.lifecycle", "unavailable-or-superseded-projection"))

    review = projection.get("review", {})
    counts = {
        "sourceRecordCount": len(records),
        "machinePassed": sum(item.get("machineAssessment") == "passed" for item in records),
        "needsAttention": sum(item.get("machineAssessment") == "needs_attention" for item in records),
        "humanReviewed": sum(item.get("humanReview") in {"reviewed", "verified"} for item in records),
    }
    for key, value in counts.items():
        if review.get(key) != value:
            errors.append(safe_error(f"$.review.{key}", "review-count-mismatch"))
    if review.get("humanReviewEffect") != "per_record_metadata" or review.get("releaseClassEffect") != "none":
        errors.append(safe_error("$.review", "review-contract-mismatch"))

    scope = projection.get("scope", {})
    expected_scope = {
        "cohortId": "khadijah-public-working-seed-v1",
        "selection": "narrow-explicit-record-allowlist",
        "coverage": "partial",
        "sourceRecordCount": len(records),
        "personCount": len(projection.get("persons", [])),
        "eventCount": len(projection.get("events", [])),
        "relationshipCount": len(projection.get("relationships", [])),
        "attestedClaimCount": len(claims.get("attested", [])),
        "inferredClaimCount": len(claims.get("inferred", [])),
        "ambiguitySetCount": len(ambiguities),
    }
    if scope != expected_scope:
        errors.append(safe_error("$.scope", "scope-mismatch"))

    integrity = projection.get("integrity", {})
    payload = {key: value for key, value in projection.items() if key != "integrity"}
    expected_integrity = {
        "algorithm": "sha256",
        "canonicalization": "json-sort-keys-utf8-lf-v1",
        "admissionId": "al-isabah-khadijah-elixr-story-source-admission-v1",
        "admissionSha256": sha256_text_file(builder.ADMISSION),
        "proposalSha256": builder.sha256_file(builder.PROPOSAL),
        "closureSha256": sha256_text_file(builder.CLOSURE),
        "rightsMatrixSha256": sha256_text_file(builder.RIGHTS),
        "schemaSha256": sha256_text_file(builder.SCHEMA),
        "sourceRecordSetSha256": sha256_bytes(canonical_json(records)),
        "claimSetSha256": sha256_bytes(canonical_json(claims)),
        "ambiguitySetSha256": sha256_bytes(canonical_json(ambiguities)),
        "payloadSha256": sha256_bytes(canonical_json(payload)),
    }
    if integrity != expected_integrity:
        errors.append(safe_error("$.integrity", "integrity-mismatch"))
    return errors


def validate(path: Path = OUTPUT) -> list[str]:
    projection, errors = builder.parse(path)
    if not isinstance(projection, dict):
        return errors or [safe_error("$", "expected-object")]
    errors.extend(nested_key_errors(projection))
    errors.extend(builder.projection_boundary_errors(projection))
    errors.extend(semantic_errors(projection))
    try:
        expected = builder.build()
    except builder.ProjectionError:
        errors.append(safe_error("$", "source-admission-invalid"))
    else:
        if canonical_json(projection) != canonical_json(expected):
            errors.append(safe_error("$", "deterministic-projection-mismatch"))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", type=Path, default=OUTPUT)
    args = parser.parse_args()
    errors = validate(args.path.resolve())
    if errors:
        print(summarize(errors))
        for error in errors:
            print(error)
        return 1
    payload = canonical_json(builder.build())
    print(f"Elixr-approved story projection valid: sha256={sha256_bytes(payload)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

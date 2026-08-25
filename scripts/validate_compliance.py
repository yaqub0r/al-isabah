#!/usr/bin/env python3
"""Validate Al-Isabah compliance and promotion metadata without dependencies."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REGISTER_PATH = ROOT / "compliance" / "source-register.v1.json"
PROMOTION_PATH = ROOT / "compliance" / "promotions" / "available-data.v1.json"
POLICY_PATH = ROOT / "compliance" / "policy-binding.v2.json"
LEGACY_POLICY_PATH = ROOT / "compliance" / "policy-binding.v1.json"
COVERAGE_PATH = ROOT / "compliance" / "translation-coverage.v1.json"
RETIREMENT_PATH = ROOT / "compliance" / "research-retirement.v1.json"
RIGHTS_MATRIX_PATH = ROOT / "compliance" / "rights-matrix.al-isabah.v1.json"
GOVERNANCE_REFERENCE_PATH = (
    ROOT / "docs" / "contracts" / "translation-governance-reference.v1.json"
)
FORMULA_REGISTRY_PATH = ROOT / "profiles" / "honorific-formulas.v1.json"

CLASSIFICATIONS = {
    "approved-for-publication",
    "external-reference",
    "private-reference",
    "permission-required",
    "unresolved",
    "prohibited",
}
PUBLIC_CLASSIFICATION = "approved-for-publication"
GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
WINDOWS_PATH = re.compile(r"(?:[A-Za-z]:\\|C:/Users/)", re.IGNORECASE)
PRIVATE_KEYS = {"object_key", "local_path", "private_url", "credential", "token"}
REQUIRED_REVIEWS = {
    "source_compliance",
    "translation_quality",
    "human_scholarly",
    "canonical_repository",
}
REQUIRED_POLICIES = {
    "translation-quality-workflow": "docs/contracts/translation-quality-workflow.md",
    "al-isabah-translation-profile": "docs/translation-profiles/al-isabah.md",
    "entry-title-structure": "docs/contracts/entry-title-structure.md",
    "translation-source-profile": "profiles/translation-source.v1.json",
}
REQUIRED_GOVERNANCE_ARTIFACTS = {
    "policy-binding": (
        "compliance/policy-binding.v2.json",
        "active",
        None,
    ),
    "translation-quality-workflow": (
        "docs/contracts/translation-quality-workflow.md",
        "active",
        None,
    ),
    "al-isabah-translation-profile": (
        "docs/translation-profiles/al-isabah.md",
        "active",
        None,
    ),
    "entry-title-structure": (
        "docs/contracts/entry-title-structure.md",
        "active",
        None,
    ),
    "translation-source-profile": (
        "profiles/translation-source.v1.json",
        "active",
        "1.0.0",
    ),
    "honorific-formula-registry": (
        "profiles/honorific-formulas.v1.json",
        "active",
        "1.2.0",
    ),
    "translation-coverage": (
        "compliance/translation-coverage.v1.json",
        "active",
        "1.0.0",
    ),
    "translation-coverage-schema": (
        "compliance/schemas/translation-coverage.v1.schema.json",
        "active",
        "1.0.0",
    ),
    "public-distribution-contract": (
        "docs/architecture/public-distribution.md",
        "reference",
        None,
    ),
    "public-distribution-v2": (
        "schemas/public-distribution.v2.schema.json",
        "active",
        "2.0.0",
    ),
    "public-distribution-v1": (
        "schemas/public-distribution.v1.schema.json",
        "rollback-only",
        "1.0.0",
    ),
}
REQUIRED_DEPRECATED_CONSUMER_AUTHORITIES = {
    (
        "docs/contracts/translation-quality-workflow.md",
        None,
    ),
    ("docs/translation-profiles/al-isabah.md", None),
    ("packages/release-model/src/honorifics.registry.json", None),
    (
        "docs/contracts/contracts.registry.json",
        "contracts[id=translation-quality-workflow]",
    ),
    (
        "tools/contracts/check-contract-ack.node-test.mjs",
        "translation-quality-workflow expectations",
    ),
    (
        ".github/workflows/application-validate.yml",
        "docs/translation-profiles/al-isabah.md path filters",
    ),
    (
        "docs/contracts/INDEX.md",
        "translation-quality-workflow row and Al-Isabah book-profile section",
    ),
}
SEMVER = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
REQUIRED_TRANSLATION_CONTROLS = {
    "source_authority",
    "public_output",
    "honorific_preservation",
    "translation_lineage",
}
TRANSLATION_CONTROL_STATES = {"blocked", "incomplete", "passed"}
WORKING_PUBLICATION_GATES = {
    "source_authority",
    "public_output",
    "honorific_preservation",
    "canonical_human_review",
}
REQUIRED_RIGHTS_SOURCES = {
    "openiti-cleaned-arabic-comparison",
    "aco-1905-1907-arabic-candidate",
    "dki-1995-arabic-edition",
    "usul-shamela-dki-reader-text",
    "urdu-modern-translation-witness",
}
PUBLIC_CORPUS_ID = "al-isabah-public-working-corpus-openiti-5835c18-v1"
OPENITI_COMMIT = "5835c183b8bbf4ea454d5c1be2b168b669403771"
OPENITI_SHA256 = "bc9db8134c8278973967c91c00324531833f643fc0fb2c8ebe318c9ed4469eea"
LEGACY_POLICY_SHA256 = "f1ca5fa8303b13e70bbd92aeeb8e5d2a05ba037cf951043b5043262dd2d591e5"
AGENT_COMPLETE_REQUIREMENTS = [
    "all-applicable-autonomous-stages-exhausted",
    "locked-scope-has-structured-english",
    "machine-validation-complete",
    "review-presentation-ready",
    "zero-remaining-agent-units",
]
AGENT_REOPEN_TRIGGERS = [
    "locked-scope-expanded",
    "bound-source-or-policy-stale",
    "machine-actionable-substantive-defect",
]
REQUIRED_COMPLETION_SCOPES = {
    "volume-01": {
        "volume": 1,
        "artifact": "issue-0026-public-proposal-v1",
        "units": 1537,
        "workflow_conformance": "current",
        "public_working_status": "available",
    },
    "volume-08": {
        "volume": 8,
        "artifact": "volume-08-structured-english",
        "units": 1550,
        "workflow_conformance": "legacy_audit_required",
        "public_working_status": "blocked",
    },
}


class ComplianceError(ValueError):
    """Raised when compliance metadata is internally inconsistent."""


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ComplianceError(f"{path}: top level must be an object")
    return value


def canonical_text_sha256(path: Path) -> str:
    """Hash UTF-8 policy text with platform-independent LF line endings."""
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _walk(value: Any, location: str = "$") -> list[str]:
    errors: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_location = f"{location}.{key}"
            if key.lower() in PRIVATE_KEYS:
                errors.append(f"{child_location}: private field is not allowed")
            errors.extend(_walk(child, child_location))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            errors.extend(_walk(child, f"{location}[{index}]"))
    elif isinstance(value, str) and WINDOWS_PATH.search(value):
        errors.append(f"{location}: local filesystem path is not allowed")
    return errors


def validate_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy.get("schema") != "al-isabah.local-policy-binding.v2":
        errors.append("policy: unexpected schema")
    if policy.get("supersedes") != "compliance/policy-binding.v1.json":
        errors.append("policy: v2 must supersede the immutable v1 binding")
    if canonical_text_sha256(LEGACY_POLICY_PATH) != LEGACY_POLICY_SHA256:
        errors.append("policy: immutable v1 release binding has changed")
    authority = policy.get("authority")
    if not isinstance(authority, dict):
        errors.append("policy: authority must be an object")
    else:
        if authority.get("repository") != "https://github.com/yaqub0r/al-isabah":
            errors.append("policy: authority repository must be Al-Isabah")
        if authority.get("scope") != "repository-local":
            errors.append("policy: authority scope must be repository-local")

    policies: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(policy.get("contracts", [])):
        if not isinstance(item, dict):
            errors.append(f"policy.contracts[{index}]: must be an object")
            continue
        policy_id = item.get("id")
        if not isinstance(policy_id, str) or not policy_id:
            errors.append(f"policy.contracts[{index}]: id is required")
            continue
        if policy_id in policies:
            errors.append(f"policy.contracts[{index}]: duplicate id {policy_id}")
        policies[policy_id] = item

    if set(policies) != set(REQUIRED_POLICIES):
        errors.append("policy: all required local translation policies are required")

    for policy_id, expected_path in REQUIRED_POLICIES.items():
        item = policies.get(policy_id)
        if item is None:
            continue
        relative_path = item.get("path")
        if relative_path != expected_path:
            errors.append(f"policy: {policy_id} must use {expected_path}")
            continue
        candidate = (ROOT / expected_path).resolve()
        try:
            candidate.relative_to(ROOT.resolve())
        except ValueError:
            errors.append(f"policy: {policy_id} resolves outside the repository")
            continue
        if not candidate.is_file():
            errors.append(f"policy: {policy_id} local file is missing")
            continue
        expected_sha = item.get("sha256")
        if not isinstance(expected_sha, str) or not re.fullmatch(
            r"[0-9a-f]{64}", expected_sha
        ):
            errors.append(f"policy: {policy_id} sha256 must be a SHA-256")
            continue
        actual_sha = canonical_text_sha256(candidate)
        if actual_sha != expected_sha:
            errors.append(f"policy: {policy_id} sha256 does not match local file")
    errors.extend(_walk(policy, "policy"))
    return errors


def validate_formula_registry(registry: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if set(registry) != {
        "schema",
        "registryVersion",
        "contractId",
        "profileId",
        "entries",
    }:
        errors.append("formula registry: fields do not match the v1 contract")
    if registry.get("schema") != "al-isabah.honorific-formula-registry.v1":
        errors.append("formula registry: unexpected schema")
    if not SEMVER.fullmatch(str(registry.get("registryVersion", ""))):
        errors.append("formula registry: registryVersion must be semantic")
    if registry.get("contractId") != "translation-quality-workflow":
        errors.append("formula registry: governing contract is incorrect")
    if registry.get("profileId") != "al-isabah-translation-profile":
        errors.append("formula registry: governing profile is incorrect")

    required_fields = {
        "source",
        "target",
        "semanticClass",
        "referentScope",
        "grammaticalAgreement",
        "expandedArabic",
        "accessibleEnglish",
    }
    entries = registry.get("entries")
    if not isinstance(entries, list) or not entries:
        errors.append("formula registry: entries must be a non-empty list")
        entries = []
    seen_sources: set[str] = set()
    for index, entry in enumerate(entries):
        location = f"formula registry.entries[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{location}: must be an object")
            continue
        if set(entry) != required_fields:
            errors.append(f"{location}: fields do not match the v1 contract")
            continue
        for field in required_fields:
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                errors.append(f"{location}.{field}: must be a non-empty string")
        source = entry.get("source")
        if isinstance(source, str):
            if source in seen_sources:
                errors.append(f"{location}.source: duplicate formula source")
            seen_sources.add(source)
    errors.extend(_walk(registry, "formula_registry"))
    return errors


def validate_translation_coverage(
    coverage: dict[str, Any], artifacts: dict[str, dict[str, Any]]
) -> list[str]:
    errors: list[str] = []
    expected_top_level = {
        "schema",
        "schema_version",
        "status_id",
        "work_id",
        "policy_binding",
        "semantics",
        "scopes",
    }
    if set(coverage) != expected_top_level:
        errors.append("translation coverage: fields do not match the v1 contract")
    if coverage.get("schema") != "al-isabah.translation-coverage.v1":
        errors.append("translation coverage: unexpected schema")
    if coverage.get("schema_version") != "1.0.0":
        errors.append("translation coverage: unexpected schema version")
    if coverage.get("work_id") != "ibn-hajar-al-isabah":
        errors.append("translation coverage: unexpected work")
    if coverage.get("policy_binding") != "compliance/policy-binding.v2.json":
        errors.append("translation coverage: policy binding is incorrect")
    if not re.fullmatch(
        r"translation-coverage-[0-9]{4}-[0-9]{2}-[0-9]{2}",
        str(coverage.get("status_id", "")),
    ):
        errors.append("translation coverage: status ID is invalid")

    expected_semantics = {
        "completion_scope": "locked-volume-or-cohort-revision",
        "agent_complete_requirements": AGENT_COMPLETE_REQUIREMENTS,
        "human_review_relation": "independent-ongoing-management-state",
        "human_review_edits_reopen_completion": False,
        "reopen_triggers": AGENT_REOPEN_TRIGGERS,
    }
    if coverage.get("semantics") != expected_semantics:
        errors.append("translation coverage: completion semantics are incorrect")

    scopes: dict[str, dict[str, Any]] = {}
    raw_scopes = coverage.get("scopes")
    if not isinstance(raw_scopes, list):
        errors.append("translation coverage: scopes must be a list")
        raw_scopes = []
    expected_scope_fields = {
        "scope_id",
        "scope_kind",
        "label",
        "volume",
        "agent_completion",
        "human_review",
        "workflow_conformance",
        "public_working_status",
        "canonical_promotion",
    }
    expected_completion_fields = {
        "status",
        "locked_units",
        "translated_units",
        "remaining_agent_units",
        "basis",
        "evidence",
    }
    expected_evidence_fields = {"source_register_artifact", "sha256"}
    expected_review_fields = {
        "management_state",
        "reviewed_units",
        "unreviewed_units",
    }
    for index, scope in enumerate(raw_scopes):
        location = f"translation coverage.scopes[{index}]"
        if not isinstance(scope, dict):
            errors.append(f"{location}: must be an object")
            continue
        if set(scope) != expected_scope_fields:
            errors.append(f"{location}: fields do not match the v1 contract")
        scope_id = scope.get("scope_id")
        if not isinstance(scope_id, str) or not scope_id:
            errors.append(f"{location}.scope_id: is required")
            continue
        if scope_id in scopes:
            errors.append(f"{location}.scope_id: duplicate {scope_id}")
        scopes[scope_id] = scope
        if scope.get("scope_kind") not in {"volume", "cohort"}:
            errors.append(f"{location}.scope_kind: is invalid")
        if not isinstance(scope.get("label"), str) or not scope["label"].strip():
            errors.append(f"{location}.label: is required")
        if not isinstance(scope.get("volume"), int) or not 1 <= scope["volume"] <= 8:
            errors.append(f"{location}.volume: must be between 1 and 8")

        completion = scope.get("agent_completion")
        if not isinstance(completion, dict):
            errors.append(f"{location}.agent_completion: must be an object")
            completion = {}
        elif set(completion) != expected_completion_fields:
            errors.append(
                f"{location}.agent_completion: fields do not match the v1 contract"
            )
        status = completion.get("status")
        if status not in {"not_started", "in_progress", "agent_complete", "reopened"}:
            errors.append(f"{location}.agent_completion.status: is invalid")
        counts = [
            completion.get("locked_units"),
            completion.get("translated_units"),
            completion.get("remaining_agent_units"),
        ]
        if not all(isinstance(value, int) and not isinstance(value, bool) and value >= 0 for value in counts):
            errors.append(f"{location}.agent_completion: counts must be non-negative integers")
        elif counts[1] + counts[2] != counts[0]:
            errors.append(f"{location}.agent_completion: translated and remaining units must equal locked units")
        if status == "agent_complete" and (
            completion.get("translated_units") != completion.get("locked_units")
            or completion.get("remaining_agent_units") != 0
        ):
            errors.append(
                f"{location}.agent_completion: agent_complete requires full coverage and zero remaining agent units"
            )
        if not isinstance(completion.get("basis"), str) or not completion["basis"].strip():
            errors.append(f"{location}.agent_completion.basis: is required")

        evidence = completion.get("evidence")
        if not isinstance(evidence, dict):
            errors.append(f"{location}.agent_completion.evidence: must be an object")
            evidence = {}
        elif set(evidence) != expected_evidence_fields:
            errors.append(
                f"{location}.agent_completion.evidence: fields do not match the v1 contract"
            )
        artifact_id = evidence.get("source_register_artifact")
        artifact = artifacts.get(str(artifact_id))
        if artifact is None:
            errors.append(f"{location}.agent_completion.evidence: artifact is not registered")
        else:
            integrity = artifact.get("integrity", {})
            registered_sha = integrity.get("sha256", integrity.get("proposal_sha256"))
            if evidence.get("sha256") != registered_sha:
                errors.append(f"{location}.agent_completion.evidence: hash differs from source register")

        review = scope.get("human_review")
        if not isinstance(review, dict):
            errors.append(f"{location}.human_review: must be an object")
            review = {}
        elif set(review) != expected_review_fields:
            errors.append(f"{location}.human_review: fields do not match the v1 contract")
        if review.get("management_state") != "ongoing":
            errors.append(f"{location}.human_review.management_state: must remain ongoing")
        review_counts = [review.get("reviewed_units"), review.get("unreviewed_units")]
        if not all(isinstance(value, int) and not isinstance(value, bool) and value >= 0 for value in review_counts):
            errors.append(f"{location}.human_review: counts must be non-negative integers")
        elif isinstance(completion.get("locked_units"), int) and sum(review_counts) != completion["locked_units"]:
            errors.append(f"{location}.human_review: review coverage must equal locked units")
        if scope.get("workflow_conformance") not in {"current", "legacy_audit_required"}:
            errors.append(f"{location}.workflow_conformance: is invalid")
        if scope.get("public_working_status") not in {"available", "blocked"}:
            errors.append(f"{location}.public_working_status: is invalid")
        if scope.get("canonical_promotion") not in {"blocked", "eligible", "promoted"}:
            errors.append(f"{location}.canonical_promotion: is invalid")

    if set(scopes) != set(REQUIRED_COMPLETION_SCOPES):
        errors.append("translation coverage: exact current volume inventory is required")
    for scope_id, expected in REQUIRED_COMPLETION_SCOPES.items():
        scope = scopes.get(scope_id)
        if scope is None:
            continue
        completion = scope.get("agent_completion", {})
        evidence = completion.get("evidence", {})
        if (
            scope.get("scope_kind") != "volume"
            or scope.get("volume") != expected["volume"]
            or completion.get("status") != "agent_complete"
            or completion.get("locked_units") != expected["units"]
            or completion.get("translated_units") != expected["units"]
            or completion.get("remaining_agent_units") != 0
            or evidence.get("source_register_artifact") != expected["artifact"]
            or scope.get("workflow_conformance") != expected["workflow_conformance"]
            or scope.get("public_working_status") != expected["public_working_status"]
        ):
            errors.append(f"translation coverage: {scope_id} completion evidence is incorrect")

    errors.extend(_walk(coverage, "translation_coverage"))
    return errors


def validate_translation_governance(
    reference: dict[str, Any],
    registry: dict[str, Any],
    policy: dict[str, Any],
) -> list[str]:
    errors = validate_formula_registry(registry)
    expected_top_level = {
        "schema",
        "referenceVersion",
        "authority",
        "integrity",
        "governanceArtifacts",
        "releaseSemantics",
        "consumerBoundary",
        "deprecatedConsumerAuthorities",
    }
    if set(reference) != expected_top_level:
        errors.append("governance reference: fields do not match the v1 contract")
    if reference.get("schema") != "al-isabah.translation-governance-reference.v1":
        errors.append("governance reference: unexpected schema")
    if not SEMVER.fullmatch(str(reference.get("referenceVersion", ""))):
        errors.append("governance reference: referenceVersion must be semantic")

    authority = reference.get("authority")
    expected_authority = {
        "repository": "https://github.com/yaqub0r/al-isabah",
        "repositoryPath": "docs/contracts/translation-governance-reference.v1.json",
        "requiredPin": "immutable-repository-commit",
    }
    if authority != expected_authority:
        errors.append("governance reference: authority or pinning rule is incorrect")
    if reference.get("integrity") != {
        "algorithm": "sha256",
        "textNormalization": "utf-8-lf",
    }:
        errors.append("governance reference: integrity rule is incorrect")

    artifacts: dict[str, dict[str, Any]] = {}
    raw_artifacts = reference.get("governanceArtifacts")
    if not isinstance(raw_artifacts, list):
        errors.append("governance reference: governanceArtifacts must be a list")
        raw_artifacts = []
    for index, artifact in enumerate(raw_artifacts):
        location = f"governance reference.governanceArtifacts[{index}]"
        if not isinstance(artifact, dict):
            errors.append(f"{location}: must be an object")
            continue
        artifact_id = artifact.get("id")
        if not isinstance(artifact_id, str) or not artifact_id:
            errors.append(f"{location}.id: is required")
            continue
        if artifact_id in artifacts:
            errors.append(f"{location}.id: duplicate {artifact_id}")
        artifacts[artifact_id] = artifact

    if set(artifacts) != set(REQUIRED_GOVERNANCE_ARTIFACTS):
        errors.append("governance reference: exact v1 artifact set is required")
    for artifact_id, (path, status, version) in REQUIRED_GOVERNANCE_ARTIFACTS.items():
        artifact = artifacts.get(artifact_id)
        if artifact is None:
            continue
        expected_fields = {"id", "path", "sha256", "status"}
        if version is not None:
            expected_fields.add("version")
        if set(artifact) != expected_fields:
            errors.append(f"governance reference: {artifact_id} fields are incorrect")
        if artifact.get("path") != path or artifact.get("status") != status:
            errors.append(f"governance reference: {artifact_id} metadata is incorrect")
        if artifact.get("version") != version:
            errors.append(f"governance reference: {artifact_id} version is incorrect")
        if not SHA256.fullmatch(str(artifact.get("sha256", ""))):
            errors.append(f"governance reference: {artifact_id} hash is invalid")
        candidate = (ROOT / path).resolve()
        try:
            candidate.relative_to(ROOT.resolve())
        except ValueError:
            errors.append(f"governance reference: {artifact_id} resolves outside the repository")
            continue
        if not candidate.is_file():
            errors.append(f"governance reference: {artifact_id} file is missing")
            continue
        actual_sha = canonical_text_sha256(candidate)
        if artifact.get("sha256") != actual_sha:
            errors.append(f"governance reference: {artifact_id} hash is stale")

    policy_contracts = {
        item.get("id"): item
        for item in policy.get("contracts", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    for policy_id in REQUIRED_POLICIES:
        policy_item = policy_contracts.get(policy_id)
        artifact = artifacts.get(policy_id)
        if policy_item is None or artifact is None:
            continue
        if (
            artifact.get("path") != policy_item.get("path")
            or artifact.get("sha256") != policy_item.get("sha256")
        ):
            errors.append(
                f"governance reference: {policy_id} differs from the local policy binding"
            )
    registry_artifact = artifacts.get("honorific-formula-registry", {})
    if registry_artifact.get("version") != registry.get("registryVersion"):
        errors.append("governance reference: formula registry version is stale")

    expected_release_semantics = {
        "agentCompletionScope": "locked-volume-or-cohort-revision",
        "agentCompletionIndependentOfHumanReview": True,
        "humanReviewScope": "per-record-metadata-and-confidence",
        "humanReviewChangesReleaseClass": False,
        "immutableCycleChangeKinds": [
            "incremental-translation",
            "correction",
            "review-coverage",
        ],
        "correctionMode": "new-immutable-release-with-supersession",
    }
    if reference.get("releaseSemantics") != expected_release_semantics:
        errors.append("governance reference: release semantics are incorrect")

    expected_boundary = {
        "allowed": [
            "verify-and-ingest-checksum-pinned-releases",
            "manage-private-evidence-without-exporting-it-upstream",
            "provide-review-and-reader-interfaces",
            "store-and-present-release-and-review-metadata",
        ],
        "prohibited": [
            "define-al-isabah-translation-policy",
            "treat-a-local-copy-as-governing",
            "change-release-class-from-human-review",
            "rewrite-or-mutate-an-immutable-release",
        ],
    }
    if reference.get("consumerBoundary") != expected_boundary:
        errors.append("governance reference: consumer boundary is incorrect")

    deprecated = reference.get("deprecatedConsumerAuthorities")
    if not isinstance(deprecated, list):
        errors.append("governance reference: deprecated authorities must be a list")
        deprecated = []
    found_deprecations: set[tuple[str, str | None]] = set()
    for index, item in enumerate(deprecated):
        location = f"governance reference.deprecatedConsumerAuthorities[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{location}: must be an object")
            continue
        if item.get("consumerRepository") != "https://github.com/yaqub0r/sabiqah":
            errors.append(f"{location}: consumer repository is incorrect")
        key = (str(item.get("path", "")), item.get("selector"))
        if key in found_deprecations:
            errors.append(f"{location}: duplicate deprecation")
        found_deprecations.add(key)
        for field in ("path", "kind", "replacement"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                errors.append(f"{location}.{field}: must be a non-empty string")
    if found_deprecations != REQUIRED_DEPRECATED_CONSUMER_AUTHORITIES:
        errors.append("governance reference: exact Sabiqah authority inventory is required")

    errors.extend(_walk(reference, "governance_reference"))
    return errors


def validate_register(register: dict[str, Any]) -> tuple[list[str], dict[str, dict[str, Any]]]:
    errors: list[str] = []
    artifacts: dict[str, dict[str, Any]] = {}
    if register.get("schema") != "al-isabah.source-compliance-register.v1":
        errors.append("register: unexpected schema")
    if register.get("policy_binding") != "compliance/policy-binding.v1.json":
        errors.append("register: policy binding must use the repository-relative v1 path")

    for index, artifact in enumerate(register.get("artifacts", [])):
        location = f"register.artifacts[{index}]"
        if not isinstance(artifact, dict):
            errors.append(f"{location}: artifact must be an object")
            continue
        artifact_id = artifact.get("id")
        if not isinstance(artifact_id, str) or not artifact_id:
            errors.append(f"{location}: id is required")
            continue
        if artifact_id in artifacts:
            errors.append(f"{location}: duplicate id {artifact_id}")
        artifacts[artifact_id] = artifact
        if artifact.get("classification") not in CLASSIFICATIONS:
            errors.append(f"{location}: invalid classification")
        for field in (
            "kind",
            "title",
            "rights_basis",
            "review_status",
        ):
            if not isinstance(artifact.get(field), str) or not artifact[field].strip():
                errors.append(f"{location}: {field} is required")
        for field in ("allowed_actions", "prohibited_public_actions"):
            values = artifact.get(field)
            if not isinstance(values, list) or not values or not all(
                isinstance(value, str) and value.strip() for value in values
            ):
                errors.append(f"{location}: {field} must be a non-empty string list")
        dependencies = artifact.get("depends_on", [])
        if not isinstance(dependencies, list):
            errors.append(f"{location}: depends_on must be a list")
            dependencies = []
        for dependency in dependencies:
            if not isinstance(dependency, str):
                errors.append(f"{location}: dependency ids must be strings")
    for artifact_id, artifact in artifacts.items():
        for dependency in artifact.get("depends_on", []):
            if dependency not in artifacts:
                errors.append(f"register: {artifact_id} has unknown dependency {dependency}")
            if dependency == artifact_id:
                errors.append(f"register: {artifact_id} depends on itself")
        for comparison in artifact.get("private_comparison_inputs", []):
            if comparison not in artifacts:
                errors.append(
                    f"register: {artifact_id} has unknown private comparison input {comparison}"
                )
    public_corpus = artifacts.get(PUBLIC_CORPUS_ID)
    if public_corpus:
        integrity = public_corpus.get("integrity", {})
        for field in ("manifest_sha256", "quarantine_sha256"):
            if not re.fullmatch(r"[0-9a-f]{64}", str(integrity.get(field, ""))):
                errors.append(f"register: public working corpus {field} must be a SHA-256")
        public_entries = integrity.get("public_entries")
        quarantined = integrity.get("quarantined_records")
        source_inventory = integrity.get("source_inventory")
        translated_entries = integrity.get("translated_entries")
        arabic_only_entries = integrity.get("arabic_only_entries")
        excluded_contextual_passages = integrity.get(
            "excluded_contextual_passages"
        )
        if not all(
            isinstance(value, int) and value >= 0
            for value in (
                public_entries,
                quarantined,
                source_inventory,
                translated_entries,
                arabic_only_entries,
                excluded_contextual_passages,
            )
        ):
            errors.append("register: public working corpus counts must be non-negative integers")
        elif public_entries + quarantined != source_inventory:
            errors.append(
                "register: public and quarantined working records must equal source inventory"
            )
        elif translated_entries + arabic_only_entries != public_entries:
            errors.append(
                "register: translated and Arabic-only entries must equal public entries"
            )
        elif excluded_contextual_passages != quarantined:
            errors.append(
                "register: quarantine must contain only excluded contextual passages"
            )
    errors.extend(_walk(register, "register"))
    return errors, artifacts


def _dependency_closure(
    artifact_id: str,
    artifacts: dict[str, dict[str, Any]],
    seen: set[str] | None = None,
) -> set[str]:
    seen = set() if seen is None else seen
    if artifact_id in seen:
        return seen
    seen.add(artifact_id)
    artifact = artifacts.get(artifact_id)
    if artifact:
        for dependency in artifact.get("depends_on", []):
            _dependency_closure(dependency, artifacts, seen)
    return seen


def validate_promotion(
    promotion: dict[str, Any], artifacts: dict[str, dict[str, Any]]
) -> list[str]:
    errors: list[str] = []
    if promotion.get("schema") != "al-isabah.promotion-readiness.v1":
        errors.append("promotion: unexpected schema")
    if promotion.get("rights_matrix") != "compliance/rights-matrix.al-isabah.v1.json":
        errors.append("promotion: rights matrix must use the repository-relative v1 path")
    eligible = promotion.get("public_release_eligible")
    status = promotion.get("status")
    blockers = promotion.get("blockers")
    if eligible not in (True, False):
        errors.append("promotion: public_release_eligible must be boolean")
    if status not in {"blocked", "eligible"}:
        errors.append("promotion: status must be blocked or eligible")
    if not isinstance(blockers, list):
        errors.append("promotion: blockers must be a list")
        blockers = []
    if eligible and status != "eligible":
        errors.append("promotion: eligible=true requires status=eligible")
    if not eligible and status != "blocked":
        errors.append("promotion: eligible=false requires status=blocked")
    if eligible and blockers:
        errors.append("promotion: eligible release cannot retain blockers")
    if not eligible and not blockers:
        errors.append("promotion: blocked release must identify at least one blocker")

    working = promotion.get("working_publication")
    if not isinstance(working, dict):
        errors.append("promotion: working_publication must be an object")
        working = {}
    working_artifact_id = working.get("artifact")
    working_artifact = artifacts.get(str(working_artifact_id))
    if working_artifact is None:
        errors.append("promotion: working publication artifact is not registered")
    elif working_artifact.get("classification") != PUBLIC_CLASSIFICATION:
        errors.append("promotion: working publication artifact is not public-approved")
    if working.get("status") != "public-working":
        errors.append("promotion: working publication status must be public-working")
    if working.get("canonical_promotion") != "blocked":
        errors.append("promotion: working publication cannot imply canonical promotion")
    working_gates = working.get("gates")
    if not isinstance(working_gates, dict) or set(working_gates) != WORKING_PUBLICATION_GATES:
        errors.append("promotion: working publication must contain exactly the required gates")
        working_gates = {}
    for gate in ("source_authority", "public_output", "honorific_preservation"):
        if working_gates.get(gate) != "passed":
            errors.append(f"promotion: public working gate {gate} must pass")
    if working_gates.get("canonical_human_review") not in {"incomplete", "passed"}:
        errors.append("promotion: canonical_human_review has an invalid state")
    if working_artifact:
        integrity = working_artifact.get("integrity", {})
        if working.get("corpus_id") != integrity.get("corpus_id"):
            errors.append("promotion: working corpus ID differs from its register")
        if working.get("public_entries") != integrity.get("public_entries"):
            errors.append("promotion: working public count differs from its register")
        if working.get("quarantined_records") != integrity.get("quarantined_records"):
            errors.append("promotion: working quarantine count differs from its register")

    translation_quality = promotion.get("translation_quality")
    if not isinstance(translation_quality, dict):
        errors.append("promotion: translation_quality must be an object")
        translation_quality = {}
    elif set(translation_quality) != REQUIRED_TRANSLATION_CONTROLS:
        errors.append(
            "promotion: translation_quality must contain exactly the required controls"
        )
    for control in REQUIRED_TRANSLATION_CONTROLS:
        if translation_quality.get(control) not in TRANSLATION_CONTROL_STATES:
            errors.append(
                f"promotion: translation_quality.{control} has an invalid state"
            )
    if (
        translation_quality.get("public_output") == "passed"
        and translation_quality.get("source_authority") != "passed"
    ):
        errors.append(
            "promotion: public_output cannot pass before source_authority passes"
        )
    if eligible and any(
        translation_quality.get(control) != "passed"
        for control in REQUIRED_TRANSLATION_CONTROLS
    ):
        errors.append(
            "promotion: eligible release requires every translation-quality control to pass"
        )

    direct_dependencies: set[str] = set()
    revisions = promotion.get("candidate_revisions")
    if not isinstance(revisions, list) or not revisions:
        errors.append("promotion: candidate_revisions must be non-empty")
        revisions = []
    for index, revision in enumerate(revisions):
        if not isinstance(revision, dict):
            errors.append(f"promotion.candidate_revisions[{index}]: must be an object")
            continue
        commit = revision.get("commit")
        if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
            errors.append(
                f"promotion.candidate_revisions[{index}]: commit must be a full Git SHA"
            )
        dependencies = revision.get("dependencies")
        if not isinstance(dependencies, list) or not dependencies:
            errors.append(
                f"promotion.candidate_revisions[{index}]: dependencies must be non-empty"
            )
            continue
        for dependency in dependencies:
            if not isinstance(dependency, str):
                errors.append(
                    f"promotion.candidate_revisions[{index}]: dependency ids must be strings"
                )
                continue
            direct_dependencies.add(dependency)
            if dependency not in artifacts:
                errors.append(
                    f"promotion.candidate_revisions[{index}]: unknown dependency {dependency}"
                )

    closure: set[str] = set()
    for dependency in direct_dependencies:
        _dependency_closure(dependency, artifacts, closure)
    non_public = sorted(
        artifact_id
        for artifact_id in closure
        if artifacts.get(artifact_id, {}).get("classification") != PUBLIC_CLASSIFICATION
    )
    if eligible and non_public:
        errors.append(
            "promotion: eligible release depends on non-approved artifacts: "
            + ", ".join(non_public)
        )
    reviews = promotion.get("reviews")
    if eligible and (
        not isinstance(reviews, dict)
        or set(reviews) != REQUIRED_REVIEWS
        or any(reviews.get(review) != "approved" for review in REQUIRED_REVIEWS)
    ):
        errors.append("promotion: eligible release requires every review to be approved")
    errors.extend(_walk(promotion, "promotion"))
    return errors


def validate_retirement(retirement: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if retirement.get("schema") != "al-isabah.research-retirement.v1":
        errors.append("retirement: unexpected schema")
    if retirement.get("decision") != "retained-in-private-research":
        errors.append("retirement: candidate research must remain private")
    if retirement.get("publication_status") != "blocked":
        errors.append("retirement: legacy candidate content must remain blocked")
    source = retirement.get("legacy_source")
    if not isinstance(source, dict) or not GIT_SHA.fullmatch(str(source.get("commit", ""))):
        errors.append("retirement: legacy source commit must be a full Git SHA")
    elif source.get("repository") != "https://github.com/yaqub0r/al-isabah":
        errors.append("retirement: legacy source repository is incorrect")
    snapshot = retirement.get("external_private_snapshot")
    if not isinstance(snapshot, dict):
        errors.append("retirement: private snapshot metadata is required")
    else:
        if snapshot.get("archive_format") != "canonical-git-tree-tar-v1":
            errors.append("retirement: archive format must be canonical-git-tree-tar-v1")
        for field in ("archive_sha256", "review_corpus_manifest_sha256"):
            if not re.fullmatch(r"[0-9a-f]{64}", str(snapshot.get(field, ""))):
                errors.append(f"retirement: {field} must be a SHA-256")
        for field in ("archive_bytes", "review_corpus_files", "entry_count", "passage_count"):
            if not isinstance(snapshot.get(field), int) or snapshot[field] < 1:
                errors.append(f"retirement: {field} must be positive")
    errors.extend(_walk(retirement, "retirement"))
    return errors


def validate_rights_matrix(
    matrix: dict[str, Any], artifacts: dict[str, dict[str, Any]]
) -> list[str]:
    errors: list[str] = []
    if matrix.get("schema") != "al-isabah.book-rights-matrix.v1":
        errors.append("rights matrix: unexpected schema")
    if matrix.get("work_id") != "ibn-hajar-al-isabah":
        errors.append("rights matrix: unexpected work")
    for field in ("matrix_id", "title", "reviewed_on"):
        if not isinstance(matrix.get(field), str) or not matrix[field].strip():
            errors.append(f"rights matrix: {field} is required")

    sources: dict[str, dict[str, Any]] = {}
    for index, source in enumerate(matrix.get("source_editions", [])):
        location = f"rights matrix.source_editions[{index}]"
        if not isinstance(source, dict):
            errors.append(f"{location}: must be an object")
            continue
        source_id = source.get("source_id")
        if not isinstance(source_id, str) or not source_id:
            errors.append(f"{location}: source_id is required")
            continue
        if source_id in sources:
            errors.append(f"{location}: duplicate source_id {source_id}")
        sources[source_id] = source
        if source_id not in artifacts:
            errors.append(f"{location}: unknown source register id {source_id}")
        for field in ("edition", "publication_role", "rights_basis"):
            if not isinstance(source.get(field), str) or not source[field].strip():
                errors.append(f"{location}: {field} is required")
        for field in ("allowed_uses", "exclusions"):
            values = source.get(field)
            if not isinstance(values, list) or not values or not all(
                isinstance(value, str) and value.strip() for value in values
            ):
                errors.append(f"{location}: {field} must be a non-empty string list")
    if set(sources) != REQUIRED_RIGHTS_SOURCES:
        errors.append("rights matrix: all required source editions are required")

    openiti = sources.get("openiti-cleaned-arabic-comparison", {})
    if openiti.get("source_revision") != OPENITI_COMMIT:
        errors.append("rights matrix: OpenITI source revision is not pinned")
    if openiti.get("sha256") != OPENITI_SHA256:
        errors.append("rights matrix: OpenITI artifact hash is not pinned")
    if openiti.get("publication_role") != "arabic-publication-base":
        errors.append("rights matrix: OpenITI must be the Arabic publication base")
    if sources.get("aco-1905-1907-arabic-candidate", {}).get(
        "publication_role"
    ) != "independent-public-domain-visual-witness":
        errors.append("rights matrix: ACO must remain an independent visual witness")
    for source_id in (
        "dki-1995-arabic-edition",
        "usul-shamela-dki-reader-text",
        "urdu-modern-translation-witness",
    ):
        if sources.get(source_id, {}).get("publication_role") != "private-reference-only":
            errors.append(f"rights matrix: {source_id} must remain private-reference-only")

    license_record = matrix.get("public_content_license")
    if not isinstance(license_record, dict):
        errors.append("rights matrix: public_content_license must be an object")
    else:
        if license_record.get("spdx") != "CC-BY-NC-SA-4.0":
            errors.append("rights matrix: public content license must be CC BY-NC-SA 4.0")
        if license_record.get("software_license_granted") is not False:
            errors.append("rights matrix: software must remain outside the content grant")
    for field in ("attribution", "exclusions"):
        values = matrix.get(field)
        if not isinstance(values, list) or not values or not all(
            isinstance(value, str) and value.strip() for value in values
        ):
            errors.append(f"rights matrix: {field} must be a non-empty string list")
    decision = matrix.get("publication_decision", {})
    if decision.get("public_reuse") != "approved-under-cc-by-nc-sa-4.0":
        errors.append("rights matrix: public reuse decision is not approved")
    follow_up = matrix.get("follow_up_review", {})
    if follow_up.get("status") not in {"required-on-change", "scheduled", "complete"}:
        errors.append("rights matrix: follow-up review status is invalid")
    triggers = follow_up.get("triggers")
    if not isinstance(triggers, list) or not triggers:
        errors.append("rights matrix: follow-up review triggers are required")
    errors.extend(_walk(matrix, "rights_matrix"))
    return errors


def validate_all(
    policy: dict[str, Any],
    register: dict[str, Any],
    promotion: dict[str, Any],
    retirement: dict[str, Any] | None = None,
    rights_matrix: dict[str, Any] | None = None,
    governance_reference: dict[str, Any] | None = None,
    formula_registry: dict[str, Any] | None = None,
    translation_coverage: dict[str, Any] | None = None,
) -> list[str]:
    errors = validate_policy(policy)
    governance_reference = (
        load_json(GOVERNANCE_REFERENCE_PATH)
        if governance_reference is None
        else governance_reference
    )
    formula_registry = (
        load_json(FORMULA_REGISTRY_PATH)
        if formula_registry is None
        else formula_registry
    )
    errors.extend(
        validate_translation_governance(
            governance_reference,
            formula_registry,
            policy,
        )
    )
    register_errors, artifacts = validate_register(register)
    errors.extend(register_errors)
    translation_coverage = (
        load_json(COVERAGE_PATH)
        if translation_coverage is None
        else translation_coverage
    )
    errors.extend(validate_translation_coverage(translation_coverage, artifacts))
    errors.extend(validate_promotion(promotion, artifacts))
    if retirement is not None:
        errors.extend(validate_retirement(retirement))
    if rights_matrix is not None:
        errors.extend(validate_rights_matrix(rights_matrix, artifacts))
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", type=Path, default=POLICY_PATH)
    parser.add_argument("--register", type=Path, default=REGISTER_PATH)
    parser.add_argument("--promotion", type=Path, default=PROMOTION_PATH)
    parser.add_argument("--retirement", type=Path, default=RETIREMENT_PATH)
    parser.add_argument("--rights-matrix", type=Path, default=RIGHTS_MATRIX_PATH)
    parser.add_argument(
        "--governance-reference",
        type=Path,
        default=GOVERNANCE_REFERENCE_PATH,
    )
    parser.add_argument(
        "--formula-registry",
        type=Path,
        default=FORMULA_REGISTRY_PATH,
    )
    parser.add_argument(
        "--translation-coverage",
        type=Path,
        default=COVERAGE_PATH,
    )
    args = parser.parse_args(argv)

    policy = load_json(args.policy)
    register = load_json(args.register)
    promotion = load_json(args.promotion)
    retirement = load_json(args.retirement)
    rights_matrix = load_json(args.rights_matrix)
    governance_reference = load_json(args.governance_reference)
    formula_registry = load_json(args.formula_registry)
    translation_coverage = load_json(args.translation_coverage)
    errors = validate_all(
        policy,
        register,
        promotion,
        retirement,
        rights_matrix,
        governance_reference,
        formula_registry,
        translation_coverage,
    )
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print(
        "Compliance records are internally consistent; promotion status: "
        f"{promotion.get('status')}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

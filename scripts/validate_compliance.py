#!/usr/bin/env python3
"""Validate Al-Isabah compliance and promotion metadata without dependencies."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REGISTER_PATH = ROOT / "compliance" / "source-register.v1.json"
PROMOTION_PATH = ROOT / "compliance" / "promotions" / "available-data.v1.json"
POLICY_PATH = ROOT / "compliance" / "policy-binding.v1.json"
RETIREMENT_PATH = ROOT / "compliance" / "research-retirement.v1.json"

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
    "human_scholarly",
    "canonical_repository",
}


class ComplianceError(ValueError):
    """Raised when compliance metadata is internally inconsistent."""


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ComplianceError(f"{path}: top level must be an object")
    return value


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
    if policy.get("schema") != "al-isabah.compliance-policy-binding.v1":
        errors.append("policy: unexpected schema")
    authority = policy.get("authority")
    if not isinstance(authority, dict) or not GIT_SHA.fullmatch(
        str(authority.get("commit", ""))
    ):
        errors.append("policy: authority commit must be a full Git SHA")
    elif authority.get("repository") != "https://github.com/yaqub0r/sabiqah":
        errors.append("policy: authority repository must be the Sabiqah repository")
    contracts = {
        item.get("id"): item.get("path")
        for item in policy.get("contracts", [])
        if isinstance(item, dict)
    }
    required = {
        "content-source-compliance": "docs/contracts/content-source-compliance.md",
        "canonical-book-promotion": "docs/contracts/canonical-book-promotion.md",
    }
    if contracts != required:
        errors.append("policy: both pinned Sabiqah contracts are required")
    errors.extend(_walk(policy, "policy"))
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
    if retirement.get("decision") != "retained-in-sabiqah-private-research":
        errors.append("retirement: candidate research must be retained in Sabiqah")
    if retirement.get("publication_status") != "blocked":
        errors.append("retirement: legacy candidate content must remain blocked")
    source = retirement.get("legacy_source")
    if not isinstance(source, dict) or not GIT_SHA.fullmatch(str(source.get("commit", ""))):
        errors.append("retirement: legacy source commit must be a full Git SHA")
    elif source.get("repository") != "https://github.com/yaqub0r/al-isabah":
        errors.append("retirement: legacy source repository is incorrect")
    snapshot = retirement.get("sabiqah_snapshot")
    if not isinstance(snapshot, dict):
        errors.append("retirement: Sabiqah snapshot metadata is required")
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


def validate_all(
    policy: dict[str, Any],
    register: dict[str, Any],
    promotion: dict[str, Any],
    retirement: dict[str, Any] | None = None,
) -> list[str]:
    errors = validate_policy(policy)
    register_errors, artifacts = validate_register(register)
    errors.extend(register_errors)
    errors.extend(validate_promotion(promotion, artifacts))
    if retirement is not None:
        errors.extend(validate_retirement(retirement))
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", type=Path, default=POLICY_PATH)
    parser.add_argument("--register", type=Path, default=REGISTER_PATH)
    parser.add_argument("--promotion", type=Path, default=PROMOTION_PATH)
    parser.add_argument("--retirement", type=Path, default=RETIREMENT_PATH)
    args = parser.parse_args(argv)

    policy = load_json(args.policy)
    register = load_json(args.register)
    promotion = load_json(args.promotion)
    retirement = load_json(args.retirement)
    errors = validate_all(policy, register, promotion, retirement)
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

#!/usr/bin/env python3
"""Build or verify the v13 consumer governance reference deterministically."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_REFERENCE = ROOT / "docs/contracts/translation-governance-reference.v12.json"
PREVIOUS_SCHEMA = ROOT / "schemas/translation-governance-reference.v12.schema.json"
CURRENT_REFERENCE = ROOT / "docs/contracts/translation-governance-reference.v13.json"
CURRENT_SCHEMA = ROOT / "schemas/translation-governance-reference.v13.schema.json"

ADDITIONAL_ARTIFACTS = (
    {
        "id": "promotion-readiness",
        "path": "compliance/promotions/available-data.v3.json",
        "status": "active",
        "version": "3.0.0",
    },
    {
        "id": "promotion-readiness-schema",
        "path": "compliance/schemas/promotion-readiness.v3.schema.json",
        "status": "active",
        "version": "3.0.0",
    },
    {
        "id": "current-release-closure",
        "path": "compliance/publication/issue-0100.release-closure.v1.json",
        "status": "active",
        "version": "2.0.0",
    },
    {
        "id": "current-release-closure-schema",
        "path": "schemas/current-release-closure.v2.schema.json",
        "status": "active",
        "version": "2.0.0",
    },
    {
        "id": "book-rights-matrix",
        "path": "compliance/rights-matrix.al-isabah.v1.json",
        "status": "active",
        "version": "1.0.0",
    },
)


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def canonical_text_sha256(path: Path) -> str:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def serialized_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: top level must be an object")
    return value


def expected_schema() -> dict[str, Any]:
    schema = copy.deepcopy(load(PREVIOUS_SCHEMA))
    schema["$id"] = (
        "https://github.com/yaqub0r/al-isabah/"
        "schemas/translation-governance-reference.v13.schema.json"
    )
    schema["title"] = "Al-Isabah translation governance reference v13"
    properties = schema["properties"]
    properties["schema"]["const"] = "al-isabah.translation-governance-reference.v13"
    properties["referenceVersion"]["const"] = "13.0.0"
    properties["supersedes"]["properties"]["path"]["const"] = (
        "docs/contracts/translation-governance-reference.v12.json"
    )
    properties["supersedes"]["properties"]["referenceVersion"]["const"] = "12.0.0"
    properties["authority"]["properties"]["repositoryPath"]["const"] = (
        "docs/contracts/translation-governance-reference.v13.json"
    )
    return schema


def expected_reference(schema: dict[str, Any]) -> dict[str, Any]:
    reference = copy.deepcopy(load(PREVIOUS_REFERENCE))
    reference["schema"] = "al-isabah.translation-governance-reference.v13"
    reference["referenceVersion"] = "13.0.0"
    reference["supersedes"] = {
        "path": "docs/contracts/translation-governance-reference.v12.json",
        "referenceVersion": "12.0.0",
        "sha256": canonical_text_sha256(PREVIOUS_REFERENCE),
    }
    reference["authority"]["repositoryPath"] = (
        "docs/contracts/translation-governance-reference.v13.json"
    )

    artifacts = []
    for old in reference["governanceArtifacts"]:
        artifact = copy.deepcopy(old)
        if artifact["id"] == "governance-reference-schema":
            artifact.update(
                path="schemas/translation-governance-reference.v13.schema.json",
                sha256=serialized_sha256(schema),
                version="13.0.0",
            )
        else:
            artifact["sha256"] = canonical_text_sha256(ROOT / artifact["path"])
        if artifact["id"] == "promotion-readiness":
            artifact["id"] = "historical-promotion-readiness-v2"
            artifact["status"] = "reference"
        elif artifact["id"] == "promotion-readiness-schema":
            artifact["id"] = "historical-promotion-readiness-schema-v2"
            artifact["status"] = "reference"
        artifacts.append(artifact)

    for configured in ADDITIONAL_ARTIFACTS:
        artifact = dict(configured)
        artifact["sha256"] = canonical_text_sha256(ROOT / artifact["path"])
        artifacts.append(artifact)
    reference["governanceArtifacts"] = artifacts
    return reference


def write_if_changed(path: Path, data: bytes) -> None:
    if path.is_file() and path.read_bytes() == data:
        return
    path.write_bytes(data)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="write the expected v13 files")
    args = parser.parse_args()

    schema = expected_schema()
    reference = expected_reference(schema)
    expected = {
        CURRENT_SCHEMA: canonical_bytes(schema),
        CURRENT_REFERENCE: canonical_bytes(reference),
    }
    if args.write:
        for path, data in expected.items():
            write_if_changed(path, data)
        return 0

    stale = [str(path.relative_to(ROOT)) for path, data in expected.items() if not path.is_file() or path.read_bytes() != data]
    if stale:
        print("stale governance outputs: " + ", ".join(stale))
        print("run: python scripts/build_translation_governance_reference.py --write")
        return 1
    print("translation governance reference v13: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

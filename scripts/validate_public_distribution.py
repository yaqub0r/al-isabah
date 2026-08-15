#!/usr/bin/env python3
"""Validate an Al-Isabah public distribution independently of its builder."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


SHA256 = re.compile(r"^[a-f0-9]{64}$")
COMMIT = re.compile(r"^[a-f0-9]{40}$")
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,199}$")
UTC_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")
FORBIDDEN_MARKERS = (
    "sabiqah",
    "firstlight",
    "elixir",
    "usul.ai",
    "lastpass",
    "r2.cloudflarestorage.com",
    "aws_access_key_id",
    "aws_secret_access_key",
    "schema.json",
    "/api/",
)
FORBIDDEN_FIELDS = {
    "api",
    "api_url",
    "bucket",
    "credential",
    "endpoint",
    "local_path",
    "object_key",
    "private_path",
    "private_url",
    "schema_path",
    "source_path",
    "storage_location",
    "token",
}


def public_boundary_errors(value: Any, location: str = "$") -> list[str]:
    errors: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_location = f"{location}.{key}"
            if key.casefold() in FORBIDDEN_FIELDS:
                errors.append(f"{child_location}: private field is not allowed")
            errors.extend(public_boundary_errors(child, child_location))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            errors.extend(public_boundary_errors(child, f"{location}[{index}]"))
    elif isinstance(value, str):
        folded = value.casefold()
        for marker in FORBIDDEN_MARKERS:
            if marker in folded:
                errors.append(f"{location}: private marker {marker!r} is not allowed")
    return errors


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(root: Path) -> list[str]:
    errors: list[str] = []
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        return ["manifest.json is missing"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schemaVersion") != "2.0.0":
        errors.append("manifest: unsupported schema version")
    if manifest.get("publicationStatus") != "public-working":
        errors.append("manifest: publication status must be public-working")
    if manifest.get("canonicalPromotion") != "blocked":
        errors.append("manifest: canonical promotion must remain blocked")
    generated_at = manifest.get("generatedAt")
    if not isinstance(generated_at, str) or not UTC_TIMESTAMP.fullmatch(generated_at):
        errors.append("manifest: generated timestamp must use UTC Z form")
    else:
        try:
            datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        except ValueError:
            errors.append("manifest: generated timestamp is invalid")
    repository = manifest.get("repository", {})
    if repository.get("url") != "https://github.com/yaqub0r/al-isabah":
        errors.append("manifest: wrong repository authority")
    if not COMMIT.fullmatch(str(repository.get("commit", ""))):
        errors.append("manifest: invalid repository commit")
    rights = manifest.get("rights", {})
    if rights.get("license", {}).get("spdx") != "CC-BY-NC-SA-4.0":
        errors.append("manifest: public content license must be CC BY-NC-SA 4.0")
    if rights.get("softwareLicenseGranted") is not False:
        errors.append("manifest: public content terms must not grant a software license")
    if not rights.get("attribution"):
        errors.append("manifest: public content attribution is required")
    if not rights.get("excludedMaterial"):
        errors.append("manifest: excluded material must be declared")
    authorities = {
        item.get("sourceId"): item for item in manifest.get("authorities", [])
    }
    if not authorities:
        errors.append("manifest: no approved source authority")
    for authority_id, authority in authorities.items():
        if not authority_id or authority.get("license", {}).get("spdx") != "CC-BY-NC-SA-4.0":
            errors.append(f"authority {authority_id}: license is not approved")
        if not SHA256.fullmatch(str(authority.get("sha256", ""))):
            errors.append(f"authority {authority_id}: invalid artifact hash")
    seen: set[str] = set()
    printed: dict[int, list[str]] = {}
    count = 0
    needs_attention = 0
    expected_paths = set()
    for file in manifest.get("files", []):
        relative = file.get("path")
        if not isinstance(relative, str) or not re.fullmatch(r"records/volume-\d{2}\.jsonl", relative):
            errors.append("manifest: unsafe record path")
            continue
        expected_paths.add(relative)
        path = root / relative
        if not path.is_file():
            errors.append(f"manifest: missing {relative}")
            continue
        if file.get("sha256") != digest(path) or not SHA256.fullmatch(str(file.get("sha256", ""))):
            errors.append(f"manifest: hash mismatch for {relative}")
        if file.get("bytes") != path.stat().st_size:
            errors.append(f"manifest: byte count mismatch for {relative}")
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
        if file.get("recordCount") != len(records):
            errors.append(f"manifest: record count mismatch for {relative}")
        previous = None
        for record in records:
            count += 1
            record_id = record.get("id")
            if not isinstance(record_id, str) or not IDENTIFIER.fullmatch(record_id):
                errors.append(f"{relative}: invalid stable record ID")
                continue
            if record_id in seen:
                errors.append(f"duplicate stable record ID: {record_id}")
            seen.add(record_id)
            order = (record.get("sourceOrdinal"), record_id)
            if previous is not None and order <= previous:
                errors.append(f"{relative}: records are not in stable source order")
            previous = order
            printed.setdefault(int(record.get("printedEntryNumber", 0)), []).append(record_id)
            if record.get("schemaVersion") != "2.0.0" or record.get("kind") != "entry":
                errors.append(f"{record_id}: unsupported record contract")
            if record.get("source", {}).get("authorityId") not in authorities:
                errors.append(f"{record_id}: unknown source authority")
            forbidden_source_fields = {"repository", "path", "lineStart", "lineEnd"}
            if forbidden_source_fields.intersection(record.get("source", {})):
                errors.append(f"{record_id}: source file locations are not public fields")
            if set(record.get("policy", {})) != {"bindingSha256"}:
                errors.append(f"{record_id}: policy internals are not public fields")
            if not record.get("title", {}).get("arabic") or not record.get("title", {}).get("english"):
                errors.append(f"{record_id}: bilingual title is incomplete")
            if not str(record.get("arabic", "")).strip() or not str(record.get("english", "")).strip():
                errors.append(f"{record_id}: bilingual body is incomplete")
            if record.get("machineAssessment") == "needs_attention":
                needs_attention += 1
            elif record.get("machineAssessment") != "passed":
                errors.append(f"{record_id}: invalid machine assessment")
            if record.get("humanReview") not in {"unreviewed", "in_review", "reviewed", "verified"}:
                errors.append(f"{record_id}: invalid human review state")
    actual_paths = {
        path.relative_to(root).as_posix() for path in root.glob("records/*.jsonl")
    }
    if actual_paths != expected_paths:
        errors.append("manifest: record file inventory differs from disk")
    counts = manifest.get("counts", {})
    if counts.get("entries") != count:
        errors.append("manifest: entry count differs")
    if counts.get("needsAttention") != needs_attention:
        errors.append("manifest: needs-attention count differs")
    declared_duplicates = {
        int(item["printedEntryNumber"]): item["recordIds"]
        for item in manifest.get("duplicatePrintedEntryNumbers", [])
    }
    actual_duplicates = {number: ids for number, ids in printed.items() if len(ids) > 1}
    if declared_duplicates != actual_duplicates:
        errors.append("manifest: duplicate printed-entry inventory differs")
    errors.extend(public_boundary_errors(manifest, "manifest"))
    for path in sorted(root.glob("records/*.jsonl")):
        records = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line
        ]
        errors.extend(public_boundary_errors(records, path.name))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    errors = validate(args.root.resolve())
    if errors:
        for error in errors:
            print(error)
        return 1
    print("Al-Isabah public distribution is valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

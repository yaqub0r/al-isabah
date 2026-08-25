#!/usr/bin/env python3
"""Independently validate a v2 public distribution and exact release closure."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from public_boundary import boundary_errors, exact_keys, safe_error, sha256_file, summarize
from validate_public_proposal import KEYS as PROPOSAL_KEYS, RECORD_KEYS
from validate_current_release_closure import (
    CURRENT_CLOSURE,
    validate as validate_closure,
)


COMMIT = re.compile(r"^[a-f0-9]{40}$")
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,199}$")
UTC_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")
MANIFEST_KEYS = {"schemaVersion", "distributionId", "publicationStatus", "canonicalPromotion", "work", "repository", "generatedAt", "rights", "packets", "authorities", "counts", "duplicatePrintedEntryNumbers", "files", "releaseClosure"}


def record_key_errors(record: dict[str, Any], base: str) -> list[str]:
    errors = exact_keys(record, RECORD_KEYS, base)
    errors.extend(exact_keys(record.get("title"), PROPOSAL_KEYS["title"], f"{base}.title"))
    errors.extend(exact_keys(record.get("source"), PROPOSAL_KEYS["source"], f"{base}.source"))
    errors.extend(exact_keys(record.get("policy"), PROPOSAL_KEYS["policy"], f"{base}.policy"))
    errors.extend(exact_keys(record.get("source", {}).get("license"), PROPOSAL_KEYS["license"], f"{base}.source.license"))
    for index, page in enumerate(record.get("pages", [])):
        errors.extend(exact_keys(page, PROPOSAL_KEYS["page"], f"{base}.pages[{index}]"))
    for index, context in enumerate(record.get("precedingMaterial", [])):
        context_path = f"{base}.precedingMaterial[{index}]"
        errors.extend(exact_keys(context, PROPOSAL_KEYS["context"], context_path))
        errors.extend(exact_keys(context.get("heading"), PROPOSAL_KEYS["heading"], f"{context_path}.heading"))
        for child_index, page in enumerate(context.get("pages", [])):
            errors.extend(exact_keys(page, PROPOSAL_KEYS["page"], f"{context_path}.pages[{child_index}]"))
        for child_index, finding in enumerate(context.get("unresolved", [])):
            errors.extend(exact_keys(finding, PROPOSAL_KEYS["finding"], f"{context_path}.unresolved[{child_index}]"))
    for index, name in enumerate(record.get("names", [])):
        errors.extend(exact_keys(name, PROPOSAL_KEYS["name"], f"{base}.names[{index}]"))
    for index, finding in enumerate(record.get("unresolved", [])):
        errors.extend(exact_keys(finding, PROPOSAL_KEYS["finding"], f"{base}.unresolved[{index}]"))
    for index, formula in enumerate(record.get("formulas", [])):
        errors.extend(exact_keys(formula, PROPOSAL_KEYS["formula"], f"{base}.formulas[{index}]"))
    return errors


def validate(root: Path) -> list[str]:
    errors: list[str] = []
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        return [safe_error("$.manifest", "missing-file")]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        return [safe_error(f"$.manifest.line[{getattr(error, 'lineno', 0)}]", "invalid-json")]
    errors.extend(exact_keys(manifest, MANIFEST_KEYS, "$.manifest"))
    errors.extend(boundary_errors(manifest, "$.manifest"))
    if manifest.get("schemaVersion") != "2.0.0" or manifest.get("publicationStatus") != "public-working" or manifest.get("canonicalPromotion") != "blocked":
        errors.append(safe_error("$.manifest", "consumer-contract-mismatch"))
    generated_at = manifest.get("generatedAt")
    if not isinstance(generated_at, str) or not UTC_TIMESTAMP.fullmatch(generated_at):
        errors.append(safe_error("$.manifest.generatedAt", "timestamp-mismatch"))
    else:
        try:
            datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        except ValueError:
            errors.append(safe_error("$.manifest.generatedAt", "timestamp-mismatch"))
    repository = manifest.get("repository", {})
    if repository.get("url") != "https://github.com/yaqub0r/al-isabah" or not COMMIT.fullmatch(str(repository.get("commit", ""))):
        errors.append(safe_error("$.manifest.repository", "repository-mismatch"))
    closure = json.loads(CURRENT_CLOSURE.read_text(encoding="utf-8"))
    closure_binding = manifest.get("releaseClosure", {})
    if closure_binding != {
        "closureId": closure["closureId"],
        "sha256": sha256_file(CURRENT_CLOSURE),
    }:
        errors.append(safe_error("$.manifest.releaseClosure", "closure-mismatch"))
    closure_errors = validate_closure(CURRENT_CLOSURE)
    if closure_errors:
        errors.append(safe_error("$.manifest.releaseClosure", "closure-invalid"))
    if not (root / "release-closure.json").is_file() or (root / "release-closure.json").read_bytes() != CURRENT_CLOSURE.read_bytes():
        errors.append(safe_error("$.release-closure", "closure-copy-mismatch"))
    authorities = {item.get("sourceId"): item for item in manifest.get("authorities", [])}
    expected_authorities = {
        item["sourceId"]
        for item in closure.get("sourceAuthorities", [])
    }
    if set(authorities) != expected_authorities:
        errors.append(safe_error("$.manifest.authorities", "source-mismatch"))
    expected_packets = [
        {
            "packetId": item["proposalId"],
            "sha256": item["publicProposal"]["sha256"],
            "entryCount": item["projection"]["entryCount"],
        }
        for item in closure.get("proposals", [])
    ]
    if manifest.get("packets") != expected_packets:
        errors.append(safe_error("$.manifest.packets", "proposal-set-mismatch"))
    expected_paths: set[str] = set()
    seen: set[str] = set()
    printed: dict[int, list[str]] = {}
    count = 0
    machine_passed = 0
    needs_attention = 0
    human_reviewed = 0
    previous: tuple[int, str] | None = None
    for item in manifest.get("files", []):
        relative = item.get("path")
        volume = item.get("volume")
        if not isinstance(volume, int) or relative != f"records/volume-{volume:02}.jsonl":
            errors.append(safe_error("$.manifest.files", "output-inventory-mismatch"))
            continue
        expected_paths.add(relative)
        path = root / relative
        if not path.is_file():
            errors.append(safe_error(f"$.output.{relative}", "missing-file"))
            continue
        if item.get("sha256") != sha256_file(path) or item.get("bytes") != path.stat().st_size:
            errors.append(safe_error(f"$.output.{relative}", "output-hash-mismatch"))
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
        if item.get("recordCount") != len(records):
            errors.append(safe_error(f"$.output.{relative}", "record-count-mismatch"))
        for index, record in enumerate(records):
            base = f"$.output.records[{index}]"
            count += 1
            errors.extend(record_key_errors(record, base))
            errors.extend(boundary_errors(record, base))
            record_id = record.get("id")
            if not isinstance(record_id, str) or not IDENTIFIER.fullmatch(record_id):
                errors.append(safe_error(f"{base}.id", "invalid-stable-id"))
                continue
            if record_id in seen:
                errors.append(safe_error(f"{base}.id", "duplicate-stable-id"))
            seen.add(record_id)
            order = (record.get("sourceOrdinal"), record_id)
            if previous is not None and order <= previous:
                errors.append(safe_error(base, "unstable-order"))
            previous = order
            printed.setdefault(int(record.get("printedEntryNumber", 0)), []).append(record_id)
            if record.get("machineAssessment") == "needs_attention":
                needs_attention += 1
            elif record.get("machineAssessment") != "passed":
                errors.append(safe_error(f"{base}.machineAssessment", "invalid-review-state"))
            if record.get("source", {}).get("authorityId") not in authorities:
                errors.append(safe_error(f"{base}.source.authorityId", "source-mismatch"))
            if record.get("volume") != volume:
                errors.append(safe_error(f"{base}.volume", "volume-shard-mismatch"))
            if record.get("machineAssessment") == "passed":
                machine_passed += 1
            if record.get("humanReview") in {"reviewed", "verified"}:
                human_reviewed += 1
    actual_paths = {path.relative_to(root).as_posix() for path in root.glob("records/*.jsonl")}
    if actual_paths != expected_paths:
        errors.append(safe_error("$.output.records", "output-inventory-mismatch"))
    counts = manifest.get("counts", {})
    expected_count = sum(
        item["projection"]["entryCount"] for item in closure.get("proposals", [])
    )
    if counts != {
        "entries": count,
        "machinePassed": machine_passed,
        "needsAttention": needs_attention,
        "humanReviewed": human_reviewed,
    } or count != expected_count:
        errors.append(safe_error("$.manifest.counts", "record-count-mismatch"))
    declared = {int(item["printedEntryNumber"]): item["recordIds"] for item in manifest.get("duplicatePrintedEntryNumbers", [])}
    actual = {number: ids for number, ids in printed.items() if len(ids) > 1}
    if declared != actual:
        errors.append(safe_error("$.manifest.duplicatePrintedEntryNumbers", "identity-mismatch"))
    expected_inventory = {
        item["path"]: item for item in closure["outputInventory"]
    }
    for relative, item in expected_inventory.items():
        path = root / relative
        if not path.is_file() or sha256_file(path) != item["sha256"] or path.stat().st_size != item["bytes"]:
            errors.append(safe_error(f"$.output.{relative}", "closure-output-mismatch"))
    expected_files = set(expected_inventory) | {"manifest.json", "release-closure.json"}
    actual_files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    }
    if actual_files != expected_files:
        errors.append(safe_error("$.output", "output-inventory-mismatch"))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    errors = validate(args.root.resolve())
    if errors:
        print(summarize(errors))
        for error in errors:
            print(error)
        return 1
    print("Al-Isabah public distribution v2 and exact release closure are valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

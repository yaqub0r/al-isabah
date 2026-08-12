#!/usr/bin/env python3
"""Validate publication-ready canonical entries and their stable identifier ledger."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content"
ENTRY_ID = re.compile(r"^isabah-entry-([0-9]{8})$")
SEGMENT_ID = re.compile(r"^(isabah-entry-[0-9]{8})-segment-([0-9]{4})$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA = re.compile(r"^[0-9a-f]{40}$")


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: top level must be an object")
    return value


def validate_entry(entry: dict[str, Any], path: Path) -> list[str]:
    errors: list[str] = []
    entry_id = entry.get("id")
    if entry.get("schemaVersion") != "1.0.0":
        errors.append(f"{path}: unsupported schemaVersion")
    if not isinstance(entry_id, str) or not ENTRY_ID.fullmatch(entry_id):
        errors.append(f"{path}: invalid stable entry id")
        entry_id = ""
    if path.stem != entry_id:
        errors.append(f"{path}: filename must equal the stable entry id")
    if entry.get("workId") != "ibn-hajar-al-isabah":
        errors.append(f"{path}: invalid workId")
    if not isinstance(entry.get("printedEntryNumber"), int) or entry["printedEntryNumber"] < 1:
        errors.append(f"{path}: printedEntryNumber must be positive")

    title = entry.get("title")
    if not isinstance(title, dict) or any(not str(title.get(key, "")).strip() for key in ("ar", "en")):
        errors.append(f"{path}: bilingual title is required")
    segments = entry.get("segments")
    if not isinstance(segments, list) or not segments:
        errors.append(f"{path}: at least one segment is required")
        segments = []
    segment_ids: set[str] = set()
    for index, segment in enumerate(segments):
        location = f"{path}: segment {index}"
        if not isinstance(segment, dict):
            errors.append(f"{location} must be an object")
            continue
        segment_id = segment.get("id")
        match = SEGMENT_ID.fullmatch(str(segment_id or ""))
        if not match or match.group(1) != entry_id:
            errors.append(f"{location} has an invalid stable segment id")
        elif segment_id in segment_ids:
            errors.append(f"{location} duplicates segment id {segment_id}")
        segment_ids.add(str(segment_id))
        for language in ("arabic", "english"):
            if not isinstance(segment.get(language), str) or not segment[language].strip():
                errors.append(f"{location} requires {language} text")
        spans = segment.get("sourceSpans")
        if not isinstance(spans, list) or not spans:
            errors.append(f"{location} requires source spans")
            continue
        for span in spans:
            if not isinstance(span, dict) or not SHA256.fullmatch(str(span.get("textSha256", ""))):
                errors.append(f"{location} has a source span without a SHA-256")

    review = entry.get("review")
    if not isinstance(review, dict) or review.get("compliance") != "approved":
        errors.append(f"{path}: canonical content requires compliance approval")
    elif review.get("arabic") not in {"reviewed", "verified", "disputed"} or review.get("translation") not in {"reviewed", "verified", "disputed"}:
        errors.append(f"{path}: canonical content requires explicit scholarly review")
    provenance = entry.get("provenance")
    if not isinstance(provenance, dict) or not GIT_SHA.fullmatch(str(provenance.get("sourceCommit", ""))) or not str(provenance.get("promotionManifest", "")).strip():
        errors.append(f"{path}: reviewed promotion provenance is required")
    return errors


def validate_ledger(ledger: dict[str, Any], entries: dict[str, Path]) -> list[str]:
    errors: list[str] = []
    if ledger.get("schemaVersion") != "1.0.0" or ledger.get("workId") != "ibn-hajar-al-isabah":
        errors.append("identifier ledger: invalid identity or schema")
    records = ledger.get("entries")
    if not isinstance(records, list):
        return errors + ["identifier ledger: entries must be a list"]
    seen: set[str] = set()
    active: set[str] = set()
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            errors.append(f"identifier ledger entry {index}: must be an object")
            continue
        entry_id = record.get("id")
        if not isinstance(entry_id, str) or not ENTRY_ID.fullmatch(entry_id):
            errors.append(f"identifier ledger entry {index}: invalid id")
            continue
        if entry_id in seen:
            errors.append(f"identifier ledger: duplicate id {entry_id}")
        seen.add(entry_id)
        status = record.get("status")
        if status not in {"active", "retired"}:
            errors.append(f"identifier ledger: {entry_id} has invalid status")
        if status == "active":
            active.add(entry_id)
            if record.get("record") != f"content/entries/{entry_id}.json":
                errors.append(f"identifier ledger: {entry_id} has an invalid record path")
        if status == "retired" and record.get("record") not in {None, ""}:
            errors.append(f"identifier ledger: retired {entry_id} must not have an active record")
    missing_records = sorted(active - set(entries))
    unallocated_records = sorted(set(entries) - active)
    if missing_records:
        errors.append("identifier ledger: active ids without records: " + ", ".join(missing_records))
    if unallocated_records:
        errors.append("identifier ledger: records without active ids: " + ", ".join(unallocated_records))
    return errors


def validate(content: Path = CONTENT) -> list[str]:
    entry_dir = content / "entries"
    entries = {path.stem: path for path in sorted(entry_dir.glob("*.json"))} if entry_dir.exists() else {}
    errors: list[str] = []
    for path in entries.values():
        try:
            errors.extend(validate_entry(load(path), path))
        except (OSError, ValueError, json.JSONDecodeError) as error:
            errors.append(str(error))
    ledger_path = content / "identifiers.json"
    if entries and not ledger_path.is_file():
        errors.append("identifier ledger is required when canonical entries exist")
    if ledger_path.is_file():
        try:
            errors.extend(validate_ledger(load(ledger_path), entries))
        except (OSError, ValueError, json.JSONDecodeError) as error:
            errors.append(str(error))
    return errors


def main() -> int:
    errors = validate()
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("Canonical content and stable identifiers are internally consistent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

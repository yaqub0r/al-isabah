#!/usr/bin/env python3
"""Import adjudicated cohort entries without disturbing reviewed canonical data."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path


ENTRY_SCHEMA = "al-isabah.entry.v1"
IMPORTER_VERSION = "al-isabah.cohort-entry-importer.v1"
HEADING_RE = re.compile(r"^\s*[0-9٠-٩۰-۹]+\s*(?:[-–—.:]|\))\s*(.*)$")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def stable_entry_id(number: int) -> str:
    return f"isabah-entry-{number:08d}"


def title_line(text: str) -> str:
    first = text.strip().splitlines()[0] if text.strip() else ""
    match = HEADING_RE.match(first)
    return (match.group(1) if match else first).strip()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_entries(spec: dict, manifest: dict, adjudicated: dict, cache_root: Path) -> tuple[dict[int, dict], dict]:
    targets = {int(item["entry_number"]): item for item in spec["entry_targets"]}
    sources = {int(item["entry_number"]): item for item in manifest["entries"]}
    final = {int(item["entry_number"]): item for item in adjudicated["entries"]}
    if set(targets) != set(sources) or set(targets) != set(final):
        raise RuntimeError("Spec, source manifest, and adjudication entry sets differ")
    manifest_identity = {key: value for key, value in manifest.items() if key != "generated_at"}
    manifest_sha = sha256_bytes((json.dumps(manifest_identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))).encode("utf-8"))
    entries = {}
    for number in sorted(targets):
        source_record = sources[number]
        cached = load_json(cache_root / source_record["cache_key"])
        arabic = cached["arabic_text"]
        if sha256_text(arabic) != source_record["arabic_text_sha256"]:
            raise RuntimeError(f"Canonical source hash mismatch for entry {number}")
        decision = final[number]
        if decision["source_sha256"] != source_record["arabic_text_sha256"]:
            raise RuntimeError(f"Adjudication is stale for entry {number}")
        english = decision["english_text"].strip()
        unresolved = []
        source_unit_id = f"isabah-usul-4CPCkl83K7:entry:{number}:{source_record['arabic_text_sha256'][:16]}"
        for item in decision["unresolved"]:
            unresolved.append({**item, "source_unit_id": source_unit_id})
        entry_id = stable_entry_id(number)
        segment = {
            "id": f"{entry_id}-segment-0001",
            "volume": int(spec["entry_volume_map"][str(number)]),
            "reader_page": source_record["reader_pages"][0],
            "reader_url": source_record["reader_urls"][0],
            "reader_pages": source_record["reader_pages"],
            "reader_urls": source_record["reader_urls"],
            "source_unit_id": source_unit_id,
            "arabic": arabic,
            "english": english,
            "arabic_sha256": sha256_text(arabic),
            "english_sha256": sha256_text(english),
            "machine_state": "machine_adjudicated_needs_attention" if unresolved else "machine_validated_unreviewed",
        }
        entries[number] = {
            "schema": ENTRY_SCHEMA,
            "id": entry_id,
            "work_id": "ibn-hajar-al-isabah",
            "edition_id": "dar-al-kutub-al-ilmiyyah-1995",
            "printed_entry_number": number,
            "title": {"english": title_line(english), "arabic_observed": title_line(arabic)},
            "segments": [segment],
            "names": decision["names"],
            "unresolved": unresolved,
            "translation": {
                "state": "translated",
                "machine_assessment": "needs_attention" if unresolved else "passed",
                "human_review": "unreviewed",
            },
            "provenance": {
                "importer": IMPORTER_VERSION,
                "cohort_id": spec["cohort_id"],
                "source_manifest_sha256": manifest_sha,
                "source_sha256": source_record["arabic_text_sha256"],
                "adjudication_prompt_sha256": decision["prompt_sha256"],
                "source_repairs": source_record.get("source_repairs", []),
            },
        }
    report = {
        "schema": "al-isabah.cohort-import-report.v1",
        "cohort_id": spec["cohort_id"],
        "entries": len(entries),
        "segments": len(entries),
        "unresolved_items": sum(len(entry["unresolved"]) for entry in entries.values()),
        "needs_attention_entries": sum(entry["translation"]["machine_assessment"] == "needs_attention" for entry in entries.values()),
        "source_manifest_sha256": manifest_sha,
        "pass": True,
    }
    return entries, report


def atomic_json(path: Path, value: object, *, refresh_generated: bool = False) -> None:
    encoded = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() == encoded:
            return
        existing = load_json(path)
        safe = (
            refresh_generated
            and existing.get("schema") == ENTRY_SCHEMA
            and (existing.get("provenance") or {}).get("importer") == IMPORTER_VERSION
            and (existing.get("translation") or {}).get("human_review") == "unreviewed"
            and existing.get("printed_entry_number") == value.get("printed_entry_number")
        )
        if existing.get("schema") == "al-isabah.identifier-ledger.v1" and value.get("schema") == existing.get("schema"):
            replacement_by_id = {item["id"]: item for item in value.get("entries", [])}
            safe = all(replacement_by_id.get(item["id"]) == item for item in existing.get("entries", []))
        if (
            refresh_generated
            and existing.get("schema") == "al-isabah.cohort-import-report.v1"
            and value.get("schema") == existing.get("schema")
            and existing.get("cohort_id") == value.get("cohort_id")
        ):
            safe = True
        if not safe:
            raise RuntimeError(f"Refusing to overwrite divergent canonical record: {path}")
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", suffix=".partial", delete=False) as temporary:
        temporary.write(encoded)
        temporary_path = Path(temporary.name)
    try:
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def write_import(entries: dict[int, dict], report: dict, output_root: Path, refresh_generated: bool) -> None:
    for number, entry in entries.items():
        atomic_json(output_root / "content" / "entries" / f"{stable_entry_id(number)}.json", entry, refresh_generated=refresh_generated)
    ledger_path = output_root / "content" / "identifiers.json"
    ledger = load_json(ledger_path)
    by_id = {item["id"]: item for item in ledger["entries"]}
    for number in sorted(entries):
        record = {
            "id": stable_entry_id(number),
            "allocation_source": "printed-entry-number:dar-al-kutub-al-ilmiyyah-1995",
            "printed_entry_number": number,
            "state": "active",
        }
        if record["id"] in by_id and by_id[record["id"]] != record:
            raise RuntimeError(f"Identifier allocation conflicts for entry {number}")
        by_id[record["id"]] = record
    atomic_json(ledger_path, {"schema": ledger["schema"], "entries": sorted(by_id.values(), key=lambda item: item["id"])})
    atomic_json(output_root / "derived" / "imports" / "khadijah-immediate.json", report, refresh_generated=refresh_generated)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--source-cache", type=Path, required=True)
    parser.add_argument("--adjudicated", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=Path.cwd())
    parser.add_argument("--refresh-generated", action="store_true")
    args = parser.parse_args()
    entries, report = build_entries(load_json(args.spec), load_json(args.source_manifest), load_json(args.adjudicated), args.source_cache)
    write_import(entries, report, args.output_root, args.refresh_generated)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

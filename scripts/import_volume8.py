#!/usr/bin/env python3
"""Import the validated Volume 8 page JSONL into stable biography records."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path


ENTRY_SCHEMA = "al-isabah.entry.v1"
SOURCE_SCHEMA = "firstlight.reviewable-translation-unit.v1"
IMPORTER_VERSION = "al-isabah.volume8-importer.v1"
DIGIT_MAP = str.maketrans(
    "٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789"
)
ENTRY_RE = re.compile(
    r"(?m)^\s*[\[(]?\s*([0-9٠-٩۰-۹]{5})\s*(?:[-–—.:]|\))\s*"
)
EXPECTED_FIRST = 10759
EXPECTED_LAST = 12308


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def normalized_number(value: str) -> int:
    return int(value.translate(DIGIT_MAP))


def split_page(text: str) -> tuple[str, list[tuple[int, str]]]:
    matches = list(ENTRY_RE.finditer(text))
    prelude = text[: matches[0].start()].strip() if matches else text.strip()
    fragments = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        fragments.append((normalized_number(match.group(1)), text[match.start():end].strip()))
    return prelude, fragments


def heading_title(fragment: str) -> str:
    match = ENTRY_RE.search(fragment)
    if not match:
        return ""
    remainder = fragment[match.end():].strip()
    return remainder.splitlines()[0].strip() if remainder else ""


def stable_entry_id(number: int) -> str:
    return f"isabah-entry-{number:08d}"


def stable_segment_id(number: int, index: int) -> str:
    return f"{stable_entry_id(number)}-segment-{index:04d}"


def unique_names(names: list[dict], arabic: str, english: str) -> list[dict]:
    selected = []
    observed: set[tuple[str, str, str]] = set()
    arabic_folded = arabic.casefold()
    english_folded = english.casefold()
    for name in names or []:
        ar = str(name.get("arabic") or "").strip()
        en = str(name.get("english") or "").strip()
        kind = str(name.get("kind") or "other")
        if not ((ar and ar.casefold() in arabic_folded) or (en and en.casefold() in english_folded)):
            continue
        key = (ar, en, kind)
        if key in observed:
            continue
        observed.add(key)
        selected.append({"arabic": ar, "english": en, "kind": kind})
    return selected


def unresolved_for_fragment(items: list[dict], arabic: str, english: str) -> tuple[list[dict], list[dict]]:
    selected, remaining = [], []
    for item in items:
        spans = [
            str(item.get("arabic_span") or ""),
            str(item.get("english_span") or ""),
        ]
        if any(span and (span in arabic or span in english) for span in spans):
            selected.append(item)
        else:
            remaining.append(item)
    return selected, remaining


def new_entry(number: int, english_fragment: str, arabic_fragment: str, input_sha: str) -> dict:
    return {
        "schema": ENTRY_SCHEMA,
        "id": stable_entry_id(number),
        "work_id": "ibn-hajar-al-isabah",
        "edition_id": "dar-al-kutub-al-ilmiyyah-1995",
        "printed_entry_number": number,
        "title": {
            "english": heading_title(english_fragment),
            "arabic_observed": heading_title(arabic_fragment),
        },
        "segments": [],
        "names": [],
        "unresolved": [],
        "translation": {
            "state": "translated",
            "machine_assessment": "passed",
            "human_review": "unreviewed",
        },
        "provenance": {
            "importer": IMPORTER_VERSION,
            "source_artifact_id": (
                "firstlight:firstlight-research/data/translated/ibn_hajar_isabah/"
                "arabic_v1/volume_08.translation-units.jsonl"
            ),
            "source_artifact_sha256": input_sha,
        },
    }


def append_segment(entry: dict, row: dict, arabic: str, english: str, unresolved: list[dict]) -> None:
    source = row["source"]
    segment = {
        "id": stable_segment_id(entry["printed_entry_number"], len(entry["segments"]) + 1),
        "volume": int(source["volume"]),
        "scan_page": int(source["scan_page"]),
        "printed_page": source.get("printed_page"),
        "reader_page": source.get("reader_page"),
        "reader_url": source.get("reader_url"),
        "source_unit_id": row["unit_id"],
        "arabic": arabic,
        "english": english,
        "arabic_sha256": sha256_text(arabic),
        "english_sha256": sha256_text(english),
        "machine_state": row["target"].get("state", "machine_validated_unreviewed"),
    }
    entry["segments"].append(segment)
    for name in unique_names(row["target"].get("names") or [], arabic, english):
        if name not in entry["names"]:
            entry["names"].append(name)
    attach_unresolved(entry, row, unresolved)


def attach_unresolved(entry: dict, row: dict, unresolved: list[dict]) -> None:
    for item in unresolved:
        record = dict(item)
        record["source_unit_id"] = row["unit_id"]
        if record not in entry["unresolved"]:
            entry["unresolved"].append(record)
    if entry["unresolved"]:
        entry["translation"]["machine_assessment"] = "needs_attention"


def import_rows(
    rows: list[dict], input_sha: str, *,
    expected_first: int = EXPECTED_FIRST, expected_last: int = EXPECTED_LAST,
    scan_first: int = 4, scan_last: int = 494,
) -> tuple[dict[int, dict], dict]:
    entries: dict[int, dict] = {}
    active: int | None = None
    volume_preludes = []
    orphan_unresolved = []
    page_numbers = []
    for row in rows:
        if row.get("schema") != SOURCE_SCHEMA:
            raise RuntimeError(f"Unsupported source record schema: {row.get('schema')}")
        source = row.get("source") or {}
        if int(source.get("volume", -1)) != 8:
            raise RuntimeError("Volume 8 importer received another volume")
        page_numbers.append(int(source["scan_page"]))
        arabic_prelude, arabic_fragments = split_page(str(source.get("text") or ""))
        english_prelude, english_fragments = split_page(str((row.get("target") or {}).get("text") or ""))
        arabic_numbers = [number for number, _ in arabic_fragments]
        english_numbers = [number for number, _ in english_fragments]
        if arabic_numbers != english_numbers:
            raise RuntimeError(
                f"Entry headings differ on scan {source['scan_page']}: "
                f"Arabic {arabic_numbers}, English {english_numbers}"
            )
        unresolved = list((row.get("target") or {}).get("unresolved") or [])
        if arabic_prelude or english_prelude:
            if active is None:
                volume_preludes.append({
                    "scan_page": source["scan_page"],
                    "arabic": arabic_prelude,
                    "english": english_prelude,
                })
            else:
                matched, unresolved = unresolved_for_fragment(
                    unresolved, arabic_prelude, english_prelude
                )
                append_segment(entries[active], row, arabic_prelude, english_prelude, matched)
        for index, number in enumerate(arabic_numbers):
            if number in entries:
                raise RuntimeError(f"Entry {number} begins more than once")
            arabic_fragment = arabic_fragments[index][1]
            english_fragment = english_fragments[index][1]
            entry = new_entry(number, english_fragment, arabic_fragment, input_sha)
            entries[number] = entry
            active = number
            matched, unresolved = unresolved_for_fragment(
                unresolved, arabic_fragment, english_fragment
            )
            append_segment(entry, row, arabic_fragment, english_fragment, matched)
        if unresolved:
            if active is None:
                orphan_unresolved.extend(unresolved)
            else:
                attach_unresolved(entries[active], row, unresolved)
    expected = list(range(expected_first, expected_last + 1))
    observed = sorted(entries)
    if observed != expected:
        missing = sorted(set(expected) - set(observed))
        extra = sorted(set(observed) - set(expected))
        raise RuntimeError(f"Entry sequence is incomplete: missing={missing[:20]} extra={extra[:20]}")
    if page_numbers != list(range(scan_first, scan_last + 1)):
        raise RuntimeError(
            f"Scan-page coverage must be exactly {scan_first}-{scan_last}"
        )
    if orphan_unresolved:
        raise RuntimeError("Unresolved items were orphaned from all entries")
    all_segments = [segment for entry in entries.values() for segment in entry["segments"]]
    report = {
        "schema": "al-isabah.volume-import-report.v1",
        "volume": 8,
        "input_sha256": input_sha,
        "source_pages": len(rows),
        "entry_first": expected_first,
        "entry_last": expected_last,
        "entries": len(entries),
        "segments": len(all_segments),
        "unresolved_items": sum(len(entry["unresolved"]) for entry in entries.values()),
        "needs_attention_entries": sum(
            entry["translation"]["machine_assessment"] == "needs_attention"
            for entry in entries.values()
        ),
        "volume_preludes": volume_preludes,
        "pass": True,
    }
    return entries, report


def load_rows(path: Path) -> tuple[list[dict], str]:
    raw = path.read_bytes()
    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    return rows, sha256_bytes(raw)


def refresh_is_safe(existing: object, replacement: object) -> bool:
    if not isinstance(existing, dict) or not isinstance(replacement, dict):
        return False
    schema = existing.get("schema")
    if schema != replacement.get("schema"):
        return False
    if schema == ENTRY_SCHEMA:
        old_provenance = existing.get("provenance") or {}
        new_provenance = replacement.get("provenance") or {}
        return (
            old_provenance.get("importer") == IMPORTER_VERSION
            and old_provenance.get("source_artifact_sha256")
                == new_provenance.get("source_artifact_sha256")
            and (existing.get("translation") or {}).get("human_review") == "unreviewed"
        )
    if schema == "al-isabah.volume-import-report.v1":
        return (
            existing.get("volume") == replacement.get("volume")
            and existing.get("input_sha256") == replacement.get("input_sha256")
        )
    if schema == "al-isabah.identifier-ledger.v1":
        return existing.get("entries") == replacement.get("entries")
    return False


def atomic_json(path: Path, value: object, *, refresh_generated: bool = False) -> None:
    encoded = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() == encoded:
            return
        existing = json.loads(path.read_text(encoding="utf-8"))
        if not refresh_generated or not refresh_is_safe(existing, value):
            raise RuntimeError(f"Refusing to overwrite divergent canonical record: {path}")
    with tempfile.NamedTemporaryFile(
        dir=path.parent, prefix=f".{path.name}.", suffix=".partial", delete=False
    ) as temporary:
        temporary.write(encoded)
        temporary_path = Path(temporary.name)
    try:
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def write_import(
    entries: dict[int, dict], report: dict, output_root: Path, *,
    refresh_generated: bool = False,
) -> None:
    for number, entry in entries.items():
        atomic_json(
            output_root / "content" / "entries" / f"{stable_entry_id(number)}.json",
            entry, refresh_generated=refresh_generated,
        )
    identifiers = {
        "schema": "al-isabah.identifier-ledger.v1",
        "entries": [{
            "id": stable_entry_id(number),
            "allocation_source": "printed-entry-number:dar-al-kutub-al-ilmiyyah-1995",
            "printed_entry_number": number,
            "state": "active",
        } for number in sorted(entries)],
    }
    atomic_json(
        output_root / "content" / "identifiers.json", identifiers,
        refresh_generated=refresh_generated,
    )
    atomic_json(
        output_root / "derived" / "imports" / "volume-08.json", report,
        refresh_generated=refresh_generated,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-root", default=Path.cwd(), type=Path)
    parser.add_argument(
        "--refresh-generated", action="store_true",
        help="Replace only unreviewed records produced from the identical source artifact",
    )
    args = parser.parse_args()
    rows, input_sha = load_rows(args.input)
    entries, report = import_rows(rows, input_sha)
    write_import(
        entries, report, args.output_root,
        refresh_generated=args.refresh_generated,
    )
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"volume8-import: {error}", file=sys.stderr)
        raise SystemExit(1)

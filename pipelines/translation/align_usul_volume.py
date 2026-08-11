#!/usr/bin/env python3
"""Build a page-aligned canonical Arabic corpus from Usul reader captures."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from isabah_entry_sequence import (
    VOLUME8_FIRST_ENTRY,
    VOLUME8_LAST_ENTRY,
    audit_entry_sequence,
    probable_entry_numbers,
)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def heading_index(details_path: Path | None) -> dict[int, list[dict]]:
    if details_path is None:
        return {}
    payload = json.loads(details_path.read_text(encoding="utf-8"))
    indexed: dict[int, list[dict]] = defaultdict(list)
    for heading in payload.get("headings", []):
        page_index = heading.get("pageIndex")
        if isinstance(page_index, int):
            indexed[page_index].append(heading)
    return dict(indexed)


def repair_index(repair_path: Path | None) -> dict[int, dict]:
    if repair_path is None:
        return {}
    payload = json.loads(repair_path.read_text(encoding="utf-8"))
    return {int(row["scan_page"]): row for row in payload.get("repairs", [])}


def apply_text_replacements(text: str, replacements: list[dict], scan_page: int) -> str:
    for replacement in replacements:
        old = str(replacement.get("old") or "")
        new = str(replacement.get("new", ""))
        expected_count = int(replacement.get("expected_count", 1))
        if not old:
            raise ValueError(f"scan {scan_page} has an empty facsimile correction target")
        observed_count = text.count(old)
        if observed_count != expected_count:
            raise ValueError(
                f"scan {scan_page} facsimile correction expected {expected_count} occurrence(s) "
                f"of {old!r}, found {observed_count}"
            )
        text = text.replace(old, new)
    return text


def align_volume(
    *,
    units_path: Path,
    text_root: Path,
    output_path: Path,
    report_path: Path,
    scan_start: int,
    scan_end: int,
    reader_start: int,
    details_path: Path | None = None,
    repair_path: Path | None = None,
    max_fallback_pages: int = 0,
    expected_entry_first: int | None = None,
    expected_entry_last: int | None = None,
) -> dict:
    units = {
        int(row["source"]["scan_page"]): row
        for row in read_jsonl(units_path)
        if scan_start <= int(row["source"]["scan_page"]) <= scan_end
    }
    expected_pages = set(range(scan_start, scan_end + 1))
    missing_units = sorted(expected_pages - set(units))
    if missing_units:
        raise ValueError(f"translation units missing scan pages: {missing_units}")

    headings = heading_index(details_path)
    repairs = repair_index(repair_path)
    records = []
    fallback_pages = []
    facsimile_transcription_pages = []
    facsimile_correction_pages = []
    heading_checks = 0
    heading_mismatches = []
    for scan_page in range(scan_start, scan_end + 1):
        unit = units[scan_page]
        reader_page = reader_start + (scan_page - scan_start)
        printed_page = (unit.get("target") or {}).get("printed_page")
        captured_path = text_root / str(reader_page) / "clean.txt"
        captured_text = captured_path.read_text(encoding="utf-8").strip() if captured_path.exists() else ""
        repair = repairs.get(scan_page)
        if captured_text:
            text = captured_text
            source_state = "canonical_usul_reader"
            fallback_reason = None
        elif repair and str(repair.get("arabic_text") or "").strip():
            text = str(repair["arabic_text"]).strip()
            source_state = "canonical_facsimile_transcription"
            fallback_reason = None
            facsimile_transcription_pages.append(scan_page)
        else:
            text = str((unit.get("source") or {}).get("text") or "").strip()
            source_state = "fallback_archive_ocr"
            fallback_reason = "usul_reader_chunk_unavailable"
            fallback_pages.append(scan_page)
        corrections = list((repair or {}).get("text_replacements") or [])
        heading_override = (repair or {}).get("heading_titles")
        if corrections:
            text = apply_text_replacements(text, corrections, scan_page)
        if corrections or heading_override is not None:
            facsimile_correction_pages.append(scan_page)
            if source_state == "canonical_usul_reader":
                source_state = "canonical_usul_reader_facsimile_corrected"
        if not text:
            raise ValueError(f"no Arabic source text for scan page {scan_page}")

        page_headings = headings.get(reader_page - 1, [])
        heading_titles = [
            str(item.get("title") or item.get("heading") or item.get("text") or "").strip()
            for item in page_headings
            if str(item.get("title") or item.get("heading") or item.get("text") or "").strip()
        ]
        if heading_override is not None:
            if not isinstance(heading_override, list) or not all(str(item).strip() for item in heading_override):
                raise ValueError(f"scan {scan_page} facsimile heading override is invalid")
            heading_titles = [str(item).strip() for item in heading_override]
        if page_headings:
            heading_checks += 1
            observed = {
                (str((item.get("page") or {}).get("vol")), str((item.get("page") or {}).get("page")))
                for item in page_headings
            }
            expected = (str((unit.get("source") or {}).get("volume")), str(printed_page))
            if expected not in observed:
                heading_mismatches.append({
                    "scan_page": scan_page,
                    "reader_page": reader_page,
                    "expected": expected,
                    "observed": sorted(observed),
                })

        records.append({
            "schema": "firstlight.aligned-source-unit.v1",
            "unit_id": unit["unit_id"],
            "work_id": unit["work_id"],
            "volume": int(unit["source"]["volume"]),
            "scan_page": scan_page,
            "printed_page": printed_page,
            "reader_page": reader_page,
            "reader_page_index": reader_page - 1,
            "reader_url": f"https://usul.ai/t/isaba-fi-tamyiz/{reader_page}",
            "facsimile_pdf": unit["source"].get("pdf"),
            "source_state": source_state,
            "fallback_reason": fallback_reason,
            "source_intervention": (
                repair.get("provenance")
                if repair and (not captured_text or corrections or heading_override is not None)
                else None
            ),
            "arabic_text": text,
            "arabic_text_sha256": sha256_text(text),
            "prior_archive_ocr_sha256": unit["source"].get("text_sha256"),
            "heading_titles": heading_titles,
            "alignment": {
                "method": "verified_affine_page_map",
                "formula": f"reader_page = scan_page + {reader_start - scan_start}",
            },
        })

    if len(fallback_pages) > max_fallback_pages:
        raise ValueError(
            f"fallback page count {len(fallback_pages)} exceeds allowed maximum {max_fallback_pages}: {fallback_pages}"
        )
    if heading_mismatches:
        raise ValueError(f"Usul heading metadata disagrees with page mapping: {heading_mismatches[:5]}")
    if (expected_entry_first is None) != (expected_entry_last is None):
        raise ValueError("expected entry range requires both first and last values")
    is_complete_isabah_v8 = bool(
        records
        and records[0]["work_id"] == "ibn_hajar_isabah_v1"
        and records[0]["volume"] == 8
        and scan_start == 4
        and scan_end == 494
    )
    if is_complete_isabah_v8 and expected_entry_first is None:
        expected_entry_first = VOLUME8_FIRST_ENTRY
        expected_entry_last = VOLUME8_LAST_ENTRY
    entry_sequence_audit = None
    if expected_entry_first is not None and expected_entry_last is not None:
        entry_numbers = [
            number
            for record in records
            for number in probable_entry_numbers(record["arabic_text"])
        ]
        entry_sequence_audit = audit_entry_sequence(
            entry_numbers,
            expected_first=expected_entry_first,
            expected_last=expected_entry_last,
        )
        if not entry_sequence_audit["pass"]:
            raise ValueError(
                "canonical entry sequence mismatch: "
                f"expected {expected_entry_first}-{expected_entry_last}; "
                f"observed_count={entry_sequence_audit['observed_count']}, "
                f"gaps={entry_sequence_audit['gaps'][:20]}, "
                f"duplicates={entry_sequence_audit['duplicates'][:20]}, "
                f"reversals={entry_sequence_audit['reversals'][:20]}, "
                f"out_of_range={entry_sequence_audit['out_of_range'][:20]}"
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    pending = output_path.with_suffix(output_path.suffix + ".tmp")
    with pending.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    pending.replace(output_path)
    output_sha256 = hashlib.sha256(output_path.read_bytes()).hexdigest()

    report = {
        "schema": "firstlight.source-alignment-report.v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "work_id": records[0]["work_id"] if records else None,
        "volume": records[0]["volume"] if records else None,
        "scan_page_range": [scan_start, scan_end],
        "reader_page_range": [reader_start, reader_start + scan_end - scan_start],
        "page_count": len(records),
        "canonical_usul_pages": len(records) - len(fallback_pages) - len(facsimile_transcription_pages),
        "canonical_facsimile_transcription_pages": facsimile_transcription_pages,
        "canonical_facsimile_correction_pages": facsimile_correction_pages,
        "fallback_pages": fallback_pages,
        "heading_pages_checked": heading_checks,
        "heading_mismatches": heading_mismatches,
        "entry_sequence_audit": entry_sequence_audit,
        "mapping": f"reader_page = scan_page + {reader_start - scan_start}",
        "output": str(output_path).replace("\\", "/"),
        "output_sha256": output_sha256,
        "pass": not heading_mismatches and len(fallback_pages) <= max_fallback_pages,
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--units", required=True)
    parser.add_argument("--usul-text-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--details-json")
    parser.add_argument("--repair-json")
    parser.add_argument("--scan-start", type=int, required=True)
    parser.add_argument("--scan-end", type=int, required=True)
    parser.add_argument("--reader-start", type=int, required=True)
    parser.add_argument("--max-fallback-pages", type=int, default=0)
    parser.add_argument("--expected-entry-first", type=int)
    parser.add_argument("--expected-entry-last", type=int)
    args = parser.parse_args()
    report = align_volume(
        units_path=Path(args.units),
        text_root=Path(args.usul_text_root),
        output_path=Path(args.output),
        report_path=Path(args.report),
        scan_start=args.scan_start,
        scan_end=args.scan_end,
        reader_start=args.reader_start,
        details_path=Path(args.details_json) if args.details_json else None,
        repair_path=Path(args.repair_json) if args.repair_json else None,
        max_fallback_pages=args.max_fallback_pages,
        expected_entry_first=args.expected_entry_first,
        expected_entry_last=args.expected_entry_last,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

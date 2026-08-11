#!/usr/bin/env python3
"""Build page-addressable translation units from Archive hOCR search text.

Archive hOCR search-text derivatives contain one concatenated UTF-8 text stream.
The companion page-index JSON stores character offsets in the first two fields
of each page record. This builder keeps those observations immutable while
allowing translations and reviews to survive a rebuild.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any


def read_gzip_text(path: Path) -> str:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return handle.read()


def read_page_index(path: Path) -> list[list[int]]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, list):
        raise ValueError("page index must be a JSON array")
    for page_number, row in enumerate(value, 1):
        if not isinstance(row, list) or len(row) < 2:
            raise ValueError(f"page index row {page_number} lacks text offsets")
        if not all(isinstance(offset, int) for offset in row[:2]):
            raise ValueError(f"page index row {page_number} has non-integer offsets")
    return value


def stable_unit_id(work_id: str, volume: int, scan_page: int, text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return f"{work_id}:arabic:v{volume:02d}:p{scan_page:04d}:{digest}"


def load_existing(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    records: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                record = json.loads(line)
                records[record["unit_id"]] = record
    return records


def build_units(
    searchtext_path: Path,
    pageindex_path: Path,
    output_path: Path,
    *,
    work_id: str,
    volume: int,
    pdf_path: str,
    first_page: int,
    last_page: int,
    expected_pages: int | None = None,
) -> dict[str, Any]:
    raw_text = read_gzip_text(searchtext_path)
    page_index = read_page_index(pageindex_path)
    if expected_pages is not None and len(page_index) != expected_pages:
        raise ValueError(
            f"page index has {len(page_index)} pages; expected {expected_pages}"
        )
    if first_page < 1 or last_page < first_page or last_page > len(page_index):
        raise ValueError(
            f"invalid page range {first_page}-{last_page} for {len(page_index)} pages"
        )

    existing = load_existing(output_path)
    records: list[dict[str, Any]] = []
    preserved = 0
    total_chars = 0
    total_words = 0
    for scan_page in range(first_page, last_page + 1):
        start, end = page_index[scan_page - 1][:2]
        if start < 0 or end < start or end > len(raw_text):
            raise ValueError(f"invalid text offsets for scan page {scan_page}: {start}-{end}")
        text = raw_text[start:end].strip()
        text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        word_count = len(text.split())
        total_chars += len(text)
        total_words += word_count
        record: dict[str, Any] = {
            "schema": "firstlight.reviewable-translation-unit.v1",
            "unit_id": stable_unit_id(work_id, volume, scan_page, text),
            "work_id": work_id,
            "witness_id": f"{work_id}_arabic_v1",
            "source": {
                "language": "ar",
                "volume": volume,
                "scan_page": scan_page,
                "pdf": pdf_path,
                "page_ocr": str(searchtext_path).replace("\\", "/"),
                "page_index": str(pageindex_path).replace("\\", "/"),
                "text_sha256": text_hash,
                "text": text,
                "state": "ready" if len(text) >= 80 else "image_review_required",
                "quality": {
                    "word_count": word_count,
                    "character_count": len(text),
                    "confidence_state": "not_available_in_searchtext_derivative",
                },
            },
            "target": {"language": "en", "text": None, "state": "pending"},
            "translation": {
                "method": None,
                "model": None,
                "prompt_version": "isabah-ar-en-faithful-v1",
                "generated_at_utc": None,
            },
            "review": {"state": "unreviewed", "reviewer": None, "notes": None},
            "urdu_cross_check": {
                "state": "pending",
                "witness_id": "ibn_hajar_isabah_urdu_v1",
                "citation": None,
                "notes": None,
            },
        }
        previous = existing.get(record["unit_id"])
        if previous and previous.get("source", {}).get("text_sha256") == text_hash:
            for field in ("target", "translation", "review", "urdu_cross_check"):
                if field in previous:
                    record[field] = previous[field]
            preserved += 1
        records.append(record)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    pending_path = output_path.with_suffix(output_path.suffix + ".tmp")
    with pending_path.open("w", encoding="utf-8", newline="\n") as output:
        for record in records:
            output.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    pending_path.replace(output_path)
    return {
        "pages": len(records),
        "first_scan_page": first_page,
        "last_scan_page": last_page,
        "source_characters": total_chars,
        "source_words": total_words,
        "preserved_units": preserved,
        "page_index_pages": len(page_index),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--searchtext", required=True)
    parser.add_argument("--page-index", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--work-id", default="ibn_hajar_isabah_v1")
    parser.add_argument("--volume", type=int, required=True)
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--first-page", type=int, required=True)
    parser.add_argument("--last-page", type=int, required=True)
    parser.add_argument("--expected-pages", type=int)
    args = parser.parse_args()
    report = build_units(
        Path(args.searchtext),
        Path(args.page_index),
        Path(args.output),
        work_id=args.work_id,
        volume=args.volume,
        pdf_path=args.pdf,
        first_page=args.first_page,
        last_page=args.last_page,
        expected_pages=args.expected_pages,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Extract complete numbered entries from page-addressable Usul reader text."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


SCHEMA = "al-isabah.cohort-source-manifest.v1"
CACHE_SCHEMA = "al-isabah.canonical-entry-source.v1"
USER_AGENT = "Al-Isabah/1.0 canonical-entry-extraction"
BLOCK_RE = re.compile(r'<div class="block">([\s\S]*?)</div>')
HEADING_RE = re.compile(r"(?m)^\s*[\[(]?\s*([0-9٠-٩۰-۹]{4,5})\s*[\])]?\s*(?:ز\s*)?[-–—.:،]")
FOOTNOTE_MARKER_RE = re.compile(r"[«(]\s*([0-9٠-٩۰-۹]{1,2})\s*[»)‏]??")
FOOTNOTE_START_RE = re.compile(r"(?m)^\s*\(([0-9٠-٩۰-۹]{1,2})\)\s*")
ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + ".tmp")
    pending.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pending.replace(path)


def clean_block(value: str) -> str:
    value = html.unescape(re.sub(r"<[^>]+>", " ", value))
    return re.sub(r"[ \t\r\f\v]+", " ", value).strip()


def extract_page_text(page_html: str) -> str:
    blocks = [clean_block(value) for value in BLOCK_RE.findall(page_html)]
    return "\n".join(value for value in blocks if value).strip()


def fetch_reader_page(url: str, timeout_seconds: int = 60, retries: int = 3) -> str:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                text = extract_page_text(response.read().decode("utf-8", "ignore"))
            if not text:
                raise RuntimeError(f"Reader page exposed no canonical blocks: {url}")
            return text
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, RuntimeError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(float(attempt))
    raise RuntimeError(f"Reader page failed after {retries} attempts: {url}: {last_error}")


def headings(text: str) -> list[tuple[int, int]]:
    return [(match.start(), int(match.group(1).translate(ARABIC_DIGITS))) for match in HEADING_RE.finditer(text)]


def referenced_footnotes(page_text: str, fragment: str) -> str:
    """Append page-bottom notes cited by a sliced entry body.

    Usul places notes after all biography blocks on the page. Stopping at the
    next heading therefore must not discard notes cited before that heading.
    """
    labels = {match.group(1).translate(ARABIC_DIGITS) for match in FOOTNOTE_MARKER_RE.finditer(fragment)}
    starts = list(FOOTNOTE_START_RE.finditer(page_text))
    selected = []
    for index, match in enumerate(starts):
        label = match.group(1).translate(ARABIC_DIGITS)
        if label not in labels:
            continue
        end = starts[index + 1].start() if index + 1 < len(starts) else len(page_text)
        note = page_text[match.start():end].strip()
        if note and note not in fragment:
            selected.append(note)
    return "\n".join(selected)


def extract_entry(
    entry_number: int,
    first_reader_page: int,
    *,
    reader_base: str,
    page_fetcher: Callable[[str], str] = fetch_reader_page,
    max_pages: int = 20,
) -> tuple[str, list[dict]]:
    parts: list[str] = []
    page_records = []
    started = False
    for reader_page in range(first_reader_page, first_reader_page + max_pages):
        url = f"{reader_base.rstrip('/')}/{reader_page}"
        page_text = page_fetcher(url)
        page_headings = headings(page_text)
        start = 0
        if not started:
            matches = [position for position, number in page_headings if number == entry_number]
            if not matches:
                continue
            start = matches[0]
            started = True
        later = [(position, number) for position, number in page_headings if position > start and number != entry_number]
        end = later[0][0] if later else len(page_text)
        selected = page_text[start:end].strip()
        notes = referenced_footnotes(page_text, selected)
        if notes:
            selected = f"{selected}\n{notes}"
        if selected:
            parts.append(selected)
            page_records.append({
                "reader_page": reader_page,
                "reader_url": url,
                "page_text_sha256": hashlib.sha256(page_text.encode("utf-8")).hexdigest(),
            })
        if later:
            break
        started = True
    if not started:
        raise RuntimeError(f"Entry {entry_number} was not found at or after reader page {first_reader_page}")
    if not page_records or not later:
        raise RuntimeError(f"Entry {entry_number} did not reach the next numbered heading within {max_pages} pages")
    text = "\n".join(parts).strip()
    observed = headings(text)
    if not observed or observed[0][1] != entry_number:
        raise RuntimeError(f"Entry {entry_number} extraction began at the wrong heading: {observed[:3]}")
    return text, page_records


def cache_entry(cache_root: Path, payload: dict) -> tuple[str, str]:
    text = payload["arabic_text"]
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    path = cache_root / "sha256" / digest[:2] / f"{digest}.json"
    if not path.exists():
        atomic_json(path, {"schema": CACHE_SCHEMA, "arabic_text_sha256": digest, **payload})
    return digest, path.relative_to(cache_root).as_posix()


def apply_source_repairs(text: str, entry_number: int, repairs: list[dict]) -> tuple[str, list[dict]]:
    applied = []
    for repair in repairs:
        if int(repair["entry_number"]) != entry_number:
            continue
        observed = repair["observed_reader_text"]
        replacement = repair["facsimile_text"]
        count = text.count(observed)
        if count != 1:
            raise RuntimeError(
                f"Repair {repair['repair_id']} expected one occurrence in entry "
                f"{entry_number}, found {count}"
            )
        text = text.replace(observed, replacement, 1)
        applied.append({
            "repair_id": repair["repair_id"],
            "reader_page": repair["reader_page"],
            "facsimile_pdf_page": repair["facsimile_pdf_page"],
            "observed_reader_text": observed,
            "facsimile_text": replacement,
        })
    return text, applied


def build_manifest(
    spec: dict,
    cache_root: Path,
    page_fetcher: Callable[[str], str] = fetch_reader_page,
    repairs: list[dict] | None = None,
) -> dict:
    source = spec["canonical_source"]
    reader_base = "https://usul.ai/t/isaba-fi-tamyiz"
    records = []
    for target in spec["entry_targets"]:
        number = int(target["entry_number"])
        text, pages = extract_entry(
            number,
            int(target["first_reader_page"]),
            reader_base=reader_base,
            page_fetcher=page_fetcher,
        )
        text, applied_repairs = apply_source_repairs(text, number, repairs or [])
        digest, cache_key = cache_entry(cache_root, {
            "work_id": source["work_id"],
            "edition_id": source["edition_id"],
            "entry_number": number,
            "name": target["name"],
            "arabic_text": text,
            "pages": pages,
            "source_repairs": applied_repairs,
        })
        records.append({
            **target,
            "arabic_text_sha256": digest,
            "arabic_character_count": len(text),
            "reader_pages": [item["reader_page"] for item in pages],
            "reader_urls": [item["reader_url"] for item in pages],
            "cache_key": cache_key,
            "source_state": "canonical_usul_reader",
            "source_repairs": applied_repairs,
        })
    return {
        "schema": SCHEMA,
        "cohort_id": spec["cohort_id"],
        "generated_at": now_utc(),
        "canonical_source": source,
        "summary": {
            "entry_count": len(records),
            "reader_page_count": sum(len(item["reader_pages"]) for item in records),
            "arabic_character_count": sum(item["arabic_character_count"] for item in records),
        },
        "entries": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repairs", type=Path)
    args = parser.parse_args()
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    repairs = []
    if args.repairs:
        repairs = json.loads(args.repairs.read_text(encoding="utf-8"))["repairs"]
    manifest = build_manifest(spec, args.cache_root, repairs=repairs)
    atomic_json(args.output, manifest)
    print(json.dumps({"output": str(args.output), **manifest["summary"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

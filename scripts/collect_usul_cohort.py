#!/usr/bin/env python3
"""Collect a complete, reproducible Usul mention inventory for a cohort spec.

Full Usul result text is kept in a content-addressed local cache. The committed
inventory contains source locators, hashes, entry numbers, and short contexts,
which keeps discovery auditable without turning Git into a source-blob store.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


INVENTORY_SCHEMA = "al-isabah.cohort-inventory.v1"
SPEC_SCHEMA = "al-isabah.cohort-spec.v1"
USER_AGENT = "Al-Isabah/1.0 scholarly-cohort-discovery"
ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
ENTRY_RE = re.compile(r"(?m)^\s*[\[(]?\s*([0-9٠-٩۰-۹]{4,5})\s*[\])]?\s*(?:[-–—.:،]|ز\s*-)")
SPACE_RE = re.compile(r"\s+")


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + ".tmp")
    pending.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pending.replace(path)


def object_path(cache_root: Path, digest: str) -> Path:
    return cache_root / "sha256" / digest[:2] / f"{digest}.json"


def cache_result(cache_root: Path, result: dict) -> tuple[str, str]:
    text = str(result.get("text") or "")
    digest = sha256_text(text)
    path = object_path(cache_root, digest)
    if not path.exists():
        atomic_json(path, {"schema": "al-isabah.usul-result-cache.v1", "sha256": digest, "result": result})
    return digest, path.relative_to(cache_root).as_posix()


def fetch_json(url: str, *, timeout_seconds: int = 45, retries: int = 3) -> dict:
    last_error: Exception | None = None
    for attempt in range(1, max(1, retries) + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(float(attempt))
    raise RuntimeError(f"Usul request failed after {retries} attempts: {last_error}")


def search_url(source: dict, query: str, page: int, per_page: int, api_base: str) -> str:
    params = urllib.parse.urlencode({
        "q": query,
        "bookId": source["book_id"],
        "versionId": source["version_id"],
        "type": "keyword",
        "page": page,
        "limit": per_page,
        "locale": "en",
    })
    return f"{api_base.rstrip('/')}/search/content?{params}"


def collect_query(
    source: dict,
    query: str,
    *,
    api_base: str = "https://api.usul.ai",
    per_page: int = 10,
    request_json: Callable[[str], dict] = fetch_json,
) -> tuple[list[dict], dict]:
    results: list[dict] = []
    seen: set[str] = set()
    page = 1
    reported_total = None
    while True:
        payload = request_json(search_url(source, query, page, per_page, api_base))
        if reported_total is None:
            reported_total = int(payload.get("total") or 0)
        current = payload.get("results") or []
        for result in current:
            result_id = str(result.get("id") or "")
            if result_id and result_id not in seen:
                seen.add(result_id)
                results.append(result)
        has_next = bool(payload.get("hasNextPage"))
        total_pages = int(payload.get("totalPages") or 0)
        if not has_next and (not total_pages or page >= total_pages):
            break
        if not current:
            raise RuntimeError(f"Usul pagination stalled on page {page} for {query!r}")
        page += 1
    completeness = {
        "reported_total": reported_total or 0,
        "unique_results": len(results),
        "pages_fetched": page,
        "complete": len(results) == (reported_total or 0),
    }
    if not completeness["complete"]:
        raise RuntimeError(f"Usul result count mismatch for {query!r}: {completeness}")
    return results, completeness


def entry_headings(text: str) -> list[tuple[int, int]]:
    return [(match.start(), int(match.group(1).translate(ARABIC_DIGITS))) for match in ENTRY_RE.finditer(text)]


def short_context(text: str, start: int, end: int, radius: int = 180) -> str:
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    value = SPACE_RE.sub(" ", text[left:right]).strip()
    return ("…" if left else "") + value + ("…" if right < len(text) else "")


def literal_occurrences(text: str, query: str) -> list[dict]:
    headings = entry_headings(text)
    occurrences = []
    start = 0
    while True:
        found = text.find(query, start)
        if found < 0:
            break
        preceding = [number for position, number in headings if position <= found]
        occurrences.append({
            "entry_number": preceding[-1] if preceding else None,
            "context": short_context(text, found, found + len(query)),
        })
        start = found + max(1, len(query))
    return occurrences


def result_record(result: dict, query_id: str, query: str, cache_root: Path) -> dict:
    text = str(result.get("text") or "")
    digest, cache_key = cache_result(cache_root, result)
    metadata = result.get("metadata") or {}
    return {
        "query_id": query_id,
        "query": query,
        "result_id": str(result.get("id") or ""),
        "source_and_version": metadata.get("sourceAndVersion"),
        "pages": metadata.get("pages") or [],
        "text_sha256": digest,
        "cache_key": cache_key,
        "literal_match": query in text,
        "occurrences": literal_occurrences(text, query),
    }


def build_inventory(spec: dict, cache_root: Path, request_json: Callable[[str], dict] = fetch_json) -> dict:
    if spec.get("schema") != SPEC_SCHEMA:
        raise ValueError(f"Unsupported cohort spec schema: {spec.get('schema')}")
    source = spec["canonical_source"]
    searches = []
    all_records = []
    for query_spec in spec["discovery_queries"]:
        results, completeness = collect_query(source, query_spec["arabic"], request_json=request_json)
        records = [result_record(item, query_spec["id"], query_spec["arabic"], cache_root) for item in results]
        searches.append({"query_id": query_spec["id"], "query": query_spec["arabic"], **completeness})
        all_records.extend(records)
    literal_records = [item for item in all_records if item["literal_match"]]
    return {
        "schema": INVENTORY_SCHEMA,
        "cohort_id": spec["cohort_id"],
        "generated_at": now_utc(),
        "canonical_source": source,
        "searches": searches,
        "summary": {
            "search_results": len(all_records),
            "literal_result_records": len(literal_records),
            "literal_occurrences": sum(len(item["occurrences"]) for item in literal_records),
            "distinct_result_ids": len({item["result_id"] for item in all_records}),
        },
        "results": all_records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    inventory = build_inventory(spec, args.cache_root)
    atomic_json(args.output, inventory)
    print(json.dumps({"output": str(args.output), **inventory["summary"], "searches": inventory["searches"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

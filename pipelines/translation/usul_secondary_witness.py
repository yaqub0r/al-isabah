#!/usr/bin/env python3
"""Retrieve exact-entry collateral Arabic witnesses from Usul's public search API."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


SCHEMA = "firstlight.usul-secondary-witness.v1"
DEFAULT_API_BASE = "https://api.usul.ai"
USER_AGENT = "FirstLight/1.0 scholarly-source-verification"

WITNESS_SOURCES = (
    {
        "work_id": "ibn_al_athir_usd_al_ghaba_v1",
        "witness_role": "collateral_work",
        "title": "Usd al-Ghaba fi Ma'rifat al-Sahaba",
        "author": "Ibn al-Athir al-Jazari",
        "edition": "Usul turath:1110",
        "book_id": "e5j6lo7201j98j5cnn750wc6",
        "version_id": "pRzuFotC79",
        "source_and_version": "turath:1110",
        "book_slug": "asad-al-ghaba-fi-marifat-al-sahaba",
        "facsimile_url": "https://assets.usul.ai/pdfs/pRzuFotC79.pdf",
    },
    {
        "work_id": "ibn_abd_al_barr_istiab_v1",
        "witness_role": "collateral_work",
        "title": "al-Isti'ab fi Ma'rifat al-Ashab",
        "author": "Ibn Abd al-Barr",
        "edition": "Usul turath:12288",
        "book_id": "0463IbnCabdBarr.IsticabFiMacrifatAshab",
        "version_id": "zDYIs6bLxz",
        "source_and_version": "turath:12288",
        "book_slug": "isticab-fi-macrifat-ashab",
        "facsimile_url": "https://assets.usul.ai/pdfs/zDYIs6bLxz.pdf",
    },
    {
        "work_id": "ibn_hajar_isabah_dar_hajr_v1",
        "witness_role": "alternative_edition",
        "title": "al-Isabah fi Tamyiz al-Sahaba",
        "author": "Ibn Hajar al-Asqalani",
        "edition": "Dar Hajr / Markaz Hajr critical text; Usul OpenITI ShamAY0034568-ara3",
        "book_id": "0852IbnHajarCasqalani.IsabaFiTamyiz",
        "version_id": "-aZ_8_5c6S",
        "source_and_version": "openiti:0852IbnHajarCasqalani.IsabaFiTamyiz.ShamAY0034568-ara3",
        "book_slug": "isaba-fi-tamyiz",
        "facsimile_url": "https://usul.ai/t/isaba-fi-tamyiz",
    },
    {
        "work_id": "ibn_hajar_isabah_dar_jil_v1",
        "witness_role": "alternative_edition",
        "title": "al-Isabah fi Tamyiz al-Sahaba",
        "author": "Ibn Hajar al-Asqalani",
        "edition": "Ali Muhammad al-Bajawi ed.; Dar al-Jil, first edition, 1412 AH; Usul OpenITI JK000533-ara1",
        "book_id": "0852IbnHajarCasqalani.IsabaFiTamyiz",
        "version_id": "xAOjIqxYuv",
        "source_and_version": "openiti:0852IbnHajarCasqalani.IsabaFiTamyiz.JK000533-ara1",
        "book_slug": "isaba-fi-tamyiz",
        "facsimile_url": "https://usul.ai/t/isaba-fi-tamyiz",
    },
)
SOURCE_HEALTH_QUERIES = {
    "ibn_al_athir_usd_al_ghaba_v1": "آسية بنت الفرج الجرهمية",
    "ibn_abd_al_barr_istiab_v1": "فاطمة بنت أسد",
    "ibn_hajar_isabah_dar_hajr_v1": "عاتكة بنت زيد",
    "ibn_hajar_isabah_dar_jil_v1": "عاتكة بنت زيد",
}

ARABIC_MARKS_RE = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED\u0640]")
ENTRY_PREFIX_RE = re.compile(r"^[\s\[(]*(?:[0-9٠-٩]+)[\s\])\].,:;،؛\-–—]*")
SPACE_RE = re.compile(r"\s+")
GENERIC_PERSON_QUERIES = {"النبي", "رسول الله", "محمد", "محمد رسول الله"}


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_arabic(value: str) -> str:
    text = ARABIC_MARKS_RE.sub("", str(value or ""))
    text = text.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي"}))
    text = re.sub(r"[^\u0600-\u06FF0-9٠-٩ ]+", " ", text)
    return SPACE_RE.sub(" ", text).strip()


def clean_query(value: str, *, max_words: int = 12, max_chars: int = 120) -> str:
    text = ENTRY_PREFIX_RE.sub("", str(value or "").strip())
    # Biography headings sometimes append a pronunciation or identity gloss
    # after a colon. That prose is not part of the name, and both Usul search
    # routes reject colon-bearing queries for these entries.
    text = re.split(r"[:\uff1a]", text, maxsplit=1)[0]
    text = re.sub(r"[\[\](){}<>«»]", " ", text)
    text = SPACE_RE.sub(" ", text).strip(" .,:;،؛-–—")
    words = text.split()
    if len(words) > max_words:
        text = " ".join(words[:max_words])
    return text[:max_chars].strip()


def fallback_queries(value: str) -> list[str]:
    """Return progressively broader, explicitly traceable person-name queries."""
    words = clean_query(value).split()
    candidates = []
    if len(words) >= 3:
        candidates.append(" ".join(words[:2]))
        if words[1] in {"بن", "بنت", "ابن"}:
            candidates.append(" ".join(words[1:3]))
    if len(words) >= 2:
        candidates.append(words[0])

    selected = []
    seen = {normalize_arabic(value)}
    for candidate in candidates:
        key = normalize_arabic(candidate)
        if key and key not in seen:
            seen.add(key)
            selected.append(candidate)
    return selected


def _heading_positions(source: dict) -> list[tuple[int, str]]:
    arabic = str(source.get("arabic_text") or "")
    out = []
    cursor = 0
    for heading in source.get("heading_titles") or []:
        query = clean_query(str(heading or ""))
        if not query:
            continue
        position = arabic.find(str(heading), cursor)
        if position < 0:
            position = arabic.find(query, cursor)
        if position < 0:
            position = cursor
        out.append((position, query))
        cursor = max(cursor, position)
    return out


def select_queries(
    source: dict,
    translation: dict,
    concerns: list[dict],
    max_queries: int = 4,
    previous_source: dict | None = None,
) -> list[str]:
    """Choose concern-local names/headings; never spray every isnad name at the API."""
    if max_queries <= 0:
        return []
    arabic = str(source.get("arabic_text") or "")
    headings = _heading_positions(source)
    previous_headings = _heading_positions(previous_source or {})
    person_names = [
        clean_query(item.get("arabic") or "")
        for item in (translation.get("names") or [])
        if item.get("kind") == "person"
    ]
    generic_names = {normalize_arabic(value) for value in GENERIC_PERSON_QUERIES}
    person_names = [
        name for name in person_names
        if len(normalize_arabic(name)) >= 4 and normalize_arabic(name) not in generic_names
    ]
    selected: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        query = clean_query(value)
        key = normalize_arabic(query)
        if query and len(key) >= 4 and key not in seen and len(selected) < max_queries:
            seen.add(key)
            selected.append(query)

    for concern in concerns:
        if len(selected) >= max_queries:
            break
        span = str(concern.get("arabic_span") or "").strip()
        normalized_span = normalize_arabic(span)
        matches = [name for name in person_names if normalize_arabic(name) in normalized_span]
        position = arabic.find(span) if span else -1
        prior_headings = [query for heading_position, query in headings if position < 0 or heading_position <= position]
        if prior_headings:
            add(prior_headings[-1])
        elif previous_headings:
            add(previous_headings[-1][1])
        elif matches:
            for name in sorted(matches, key=lambda value: (-len(value), value)):
                add(name)

    if not selected:
        for _, heading in headings:
            add(heading)
            if len(selected) >= max_queries:
                break
    return selected


def _cache_key(source: dict, query: str, hit_limit: int, max_text_chars: int) -> str:
    payload = json.dumps(
        {
            "book_id": source["book_id"],
            "version_id": source["version_id"],
            "query": query,
            "hit_limit": hit_limit,
            "max_text_chars": max_text_chars,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _cache_path(
    cache_root: Path,
    source: dict,
    query: str,
    hit_limit: int,
    max_text_chars: int,
) -> Path:
    return (
        cache_root
        / source["work_id"]
        / f"{_cache_key(source, query, hit_limit, max_text_chars)}.json"
    )


def _fresh_unavailable_cache(record: dict, max_age_hours: float) -> bool:
    if record.get("retrieval_state") != "unavailable":
        return False
    try:
        retrieved_at = datetime.fromisoformat(
            str(record["retrieved_at"]).replace("Z", "+00:00")
        )
    except (KeyError, TypeError, ValueError):
        return False
    if retrieved_at.tzinfo is None:
        return False
    age_seconds = (datetime.now(timezone.utc) - retrieved_at).total_seconds()
    return 0 <= age_seconds <= max(0.0, max_age_hours) * 3600


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + ".tmp")
    pending.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pending.replace(path)


def _result_evidence(payload: dict, source: dict, query: str, endpoint: str, hit_limit: int, max_text_chars: int) -> dict:
    hits = []
    seen = set()
    for result in payload.get("results") or []:
        result_id = str(result.get("id") or "")
        text = str(result.get("text") or "").strip()
        if not result_id or not text or result_id in seen:
            continue
        seen.add(result_id)
        clipped = text[:max_text_chars]
        hits.append(
            {
                "result_id": result_id,
                "text": clipped,
                "text_truncated": len(text) > len(clipped),
                "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "metadata": result.get("metadata") or {},
            }
        )
        if len(hits) >= hit_limit:
            break
    return {
        "schema": SCHEMA,
        "work_id": source["work_id"],
        "witness_role": source.get("witness_role", "collateral_work"),
        "title": source["title"],
        "author": source["author"],
        "edition": source.get("edition"),
        "book_id": source["book_id"],
        "version_id": source["version_id"],
        "source_and_version": source["source_and_version"],
        "facsimile_url": source["facsimile_url"],
        "query": query,
        "endpoint": endpoint,
        "retrieval_state": "hit" if hits else "no_match",
        "reported_total": int(payload.get("total") or 0),
        "hits": hits,
    }


def resolve_authenticated_api_key(repository_root: Path) -> tuple[str | None, str]:
    """Resolve FirstLight's backend-only Usul key without exposing its value."""
    helper = repository_root.resolve() / "tools/source-acquisition/usul_credentials.py"
    if not helper.is_file():
        return None, "credential-helper-missing"
    spec = importlib.util.spec_from_file_location("firstlight_usul_credentials", helper)
    if spec is None or spec.loader is None:
        return None, "credential-helper-unloadable"
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        return module.resolve_api_key()
    except Exception:
        return None, "credential-helper-error"


def _normalize_v1_payload(payload: dict) -> dict:
    """Flatten authenticated v1 nodes into the stable public-search shape."""
    results = []
    for item in payload.get("results") or []:
        node = item.get("node") or {}
        highlights = [
            re.sub(r"</?em>", "", str(value or ""), flags=re.IGNORECASE).strip()
            for value in node.get("highlights") or []
        ]
        text = "\n\n".join(value for value in highlights if value)
        if not text:
            continue
        metadata = dict(node.get("metadata") or {})
        metadata["versionId"] = item.get("versionId")
        metadata["score"] = item.get("score")
        results.append({"id": node.get("id"), "text": text, "metadata": metadata})
    return {"total": int(payload.get("total") or 0), "results": results}


def _search_authenticated_v1(
    *,
    source: dict,
    query: str,
    api_base: str,
    api_key: str,
    hit_limit: int,
    max_text_chars: int,
    timeout_seconds: int,
    retries: int,
) -> dict:
    params = urllib.parse.urlencode({
        "q": query,
        "type": "text",
        "books": f"{source['book_id']}:{source['version_id']}",
        "include_chapters": "true",
        "include_details": "false",
        "page": 1,
        "limit": max(1, min(50, hit_limit)),
    })
    endpoint = f"{api_base.rstrip('/')}/v1/content-search?{params}"
    last_error = ""
    last_status = None
    for attempt in range(1, max(1, retries) + 1):
        try:
            request = urllib.request.Request(
                endpoint,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "User-Agent": USER_AGENT,
                    "Accept": "application/json",
                },
            )
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
            evidence = _result_evidence(
                _normalize_v1_payload(payload),
                source,
                query,
                endpoint,
                hit_limit,
                max_text_chars,
            )
            evidence["retrieval_route"] = "authenticated_v1_content_search"
            return evidence
        except urllib.error.HTTPError as exc:
            last_status = exc.code
            last_error = f"HTTP {exc.code}"
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        if attempt < max(1, retries):
            time.sleep(float(attempt))
    return {
        "schema": SCHEMA,
        "work_id": source["work_id"],
        "witness_role": source.get("witness_role", "collateral_work"),
        "title": source["title"],
        "author": source["author"],
        "edition": source.get("edition"),
        "book_id": source["book_id"],
        "version_id": source["version_id"],
        "source_and_version": source["source_and_version"],
        "facsimile_url": source["facsimile_url"],
        "query": query,
        "endpoint": endpoint,
        "retrieval_route": "authenticated_v1_content_search",
        "retrieval_state": "error",
        "http_status": last_status,
        "error": last_error or "unknown authenticated retrieval error",
        "reported_total": 0,
        "hits": [],
    }


def search_source(
    *,
    source: dict,
    query: str,
    cache_root: Path,
    api_base: str = DEFAULT_API_BASE,
    hit_limit: int = 2,
    max_text_chars: int = 3500,
    timeout_seconds: int = 45,
    retries: int = 2,
    use_cache: bool = True,
    cache_only: bool = False,
    unavailable_max_age_hours: float = 24.0,
    authenticated_api_key: str | None = None,
) -> dict:
    cache_path = _cache_path(
        cache_root, source, query, hit_limit, max_text_chars
    )
    if use_cache and cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        if cached.get("schema") == SCHEMA and cached.get("retrieval_state") in {"hit", "no_match"}:
            return cached
        if cached.get("schema") == SCHEMA and _fresh_unavailable_cache(
            cached, unavailable_max_age_hours
        ) and not authenticated_api_key:
            return cached

    if cache_only:
        return {
            "schema": SCHEMA,
            "work_id": source["work_id"],
            "witness_role": source.get("witness_role", "collateral_work"),
            "title": source["title"],
            "author": source["author"],
            "edition": source.get("edition"),
            "book_id": source["book_id"],
            "version_id": source["version_id"],
            "source_and_version": source["source_and_version"],
            "facsimile_url": source["facsimile_url"],
            "query": query,
            "endpoint": None,
            "retrieval_state": "error",
            "http_status": None,
            "error": "cache_miss",
            "reported_total": 0,
            "hits": [],
        }

    params = urllib.parse.urlencode(
        {
            "q": query,
            "bookId": source["book_id"],
            "versionId": source["version_id"],
            "type": "keyword",
            "page": 1,
            "limit": max(1, min(10, hit_limit)),
            "locale": "en",
        }
    )
    endpoint = f"{api_base.rstrip('/')}/search/content?{params}"
    last_error = ""
    last_status = None
    for attempt in range(1, max(1, retries) + 1):
        try:
            request = urllib.request.Request(
                endpoint,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
            evidence = _result_evidence(payload, source, query, endpoint, hit_limit, max_text_chars)
            evidence["retrieved_at"] = now_utc()
            _atomic_json(cache_path, evidence)
            return evidence
        except urllib.error.HTTPError as exc:
            last_status = exc.code
            last_error = f"HTTP {exc.code}"
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        if attempt < max(1, retries):
            time.sleep(float(attempt))

    authenticated_error = None
    if authenticated_api_key:
        authenticated = _search_authenticated_v1(
            source=source,
            query=query,
            api_base=api_base,
            api_key=authenticated_api_key,
            hit_limit=hit_limit,
            max_text_chars=max_text_chars,
            timeout_seconds=timeout_seconds,
            retries=retries,
        )
        if authenticated.get("retrieval_state") != "error":
            authenticated["legacy_endpoint"] = endpoint
            authenticated["legacy_http_status"] = last_status
            authenticated["legacy_error"] = last_error or "unknown retrieval error"
            authenticated["retrieved_at"] = now_utc()
            _atomic_json(cache_path, authenticated)
            return authenticated
        authenticated_error = {
            "endpoint": authenticated.get("endpoint"),
            "http_status": authenticated.get("http_status"),
            "error": authenticated.get("error"),
        }

    return {
        "schema": SCHEMA,
        "work_id": source["work_id"],
        "witness_role": source.get("witness_role", "collateral_work"),
        "title": source["title"],
        "author": source["author"],
        "edition": source.get("edition"),
        "book_id": source["book_id"],
        "version_id": source["version_id"],
        "source_and_version": source["source_and_version"],
        "facsimile_url": source["facsimile_url"],
        "query": query,
        "endpoint": endpoint,
        "retrieval_state": "error",
        "http_status": last_status,
        "error": last_error or "unknown retrieval error",
        "authenticated_fallback": authenticated_error,
        "reported_total": 0,
        "hits": [],
    }


def retrieve_secondary_witnesses(
    *,
    source: dict,
    previous_source: dict | None = None,
    translation: dict,
    concerns: list[dict],
    cache_root: Path,
    api_base: str = DEFAULT_API_BASE,
    query_limit: int = 4,
    hit_limit: int = 2,
    max_text_chars: int = 3500,
    timeout_seconds: int = 45,
    retries: int = 2,
    cache_only: bool = False,
    cache_unavailable_errors: bool = False,
    unavailable_max_age_hours: float = 24.0,
    authenticated_api_key: str | None = None,
) -> list[dict]:
    queries = select_queries(
        source,
        translation,
        concerns,
        query_limit,
        previous_source=previous_source,
    )
    evidence = []
    for query in queries:
        for witness_source in WITNESS_SOURCES:
            result = search_source(
                source=witness_source,
                query=query,
                cache_root=cache_root,
                api_base=api_base,
                hit_limit=hit_limit,
                max_text_chars=max_text_chars,
                timeout_seconds=timeout_seconds,
                retries=retries,
                cache_only=cache_only,
                unavailable_max_age_hours=unavailable_max_age_hours,
                authenticated_api_key=authenticated_api_key,
            )
            fallback_attempts = []
            if result.get("retrieval_state") == "error":
                original_error = result.get("error")
                for fallback in fallback_queries(query):
                    fallback_result = search_source(
                        source=witness_source,
                        query=fallback,
                        cache_root=cache_root,
                        api_base=api_base,
                        hit_limit=hit_limit,
                        max_text_chars=max_text_chars,
                        timeout_seconds=timeout_seconds,
                        retries=retries,
                        cache_only=cache_only,
                        unavailable_max_age_hours=unavailable_max_age_hours,
                        authenticated_api_key=authenticated_api_key,
                    )
                    fallback_attempts.append({
                        "query": fallback,
                        "retrieval_state": fallback_result.get("retrieval_state"),
                        "http_status": fallback_result.get("http_status"),
                        "error": fallback_result.get("error"),
                    })
                    if fallback_result.get("retrieval_state") != "error":
                        fallback_result["requested_query"] = query
                        fallback_result["query_fallback_used"] = True
                        fallback_result["query_fallback_reason"] = original_error
                        result = fallback_result
                        break
            if (
                result.get("retrieval_state") == "error"
                and cache_unavailable_errors
                and not cache_only
            ):
                result = {
                    **result,
                    "retrieval_state": "unavailable",
                    "unavailable_reason": "query_failed_after_bounded_retries",
                    "retrieved_at": now_utc(),
                    "fallback_attempts": fallback_attempts,
                }
                _atomic_json(
                    _cache_path(
                        cache_root,
                        witness_source,
                        query,
                        hit_limit,
                        max_text_chars,
                    ),
                    result,
                )
            evidence.append(result)
    return evidence


def verify_source_health(
    *,
    cache_root: Path,
    api_base: str = DEFAULT_API_BASE,
    timeout_seconds: int = 45,
    retries: int = 3,
) -> dict:
    checks = []
    for source in WITNESS_SOURCES:
        query = SOURCE_HEALTH_QUERIES[source["work_id"]]
        result = search_source(
            source=source,
            query=query,
            cache_root=cache_root / "health",
            api_base=api_base,
            hit_limit=1,
            max_text_chars=1200,
            timeout_seconds=timeout_seconds,
            retries=retries,
            use_cache=False,
        )
        checks.append({
            "work_id": source["work_id"],
            "query": query,
            "retrieval_state": result.get("retrieval_state"),
            "reported_total": result.get("reported_total", 0),
            "error": result.get("error"),
        })
    return {
        "schema": "firstlight.usul-secondary-source-health.v1",
        "api_base": api_base,
        "checked_at": now_utc(),
        "live_queries": True,
        "checks": checks,
        "pass": all(item["retrieval_state"] == "hit" for item in checks),
    }


def evidence_sha256(evidence: list[dict]) -> str:
    stable = []
    for item in evidence:
        stable.append({key: value for key, value in item.items() if key != "retrieved_at"})
    payload = json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

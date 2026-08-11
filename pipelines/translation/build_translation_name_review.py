#!/usr/bin/env python3
"""Build durable operator-review name JSON from validated translation units."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCHEMA = "firstlight.name-review.v1"
AUTHORITY = "operator-reviewed JSON; ELIXR is a rebuildable projection"
METHOD = "adjudicated-translation-name-mappings+exact-body-scan"
METHOD_VERSION = "1.0.0"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalized_form(value: str) -> str:
    value = value.replace("’", "'").replace("‘", "'").replace("`", "'")
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip().casefold()


def stable_id(prefix: str, *parts: object, length: int) -> str:
    payload = "\x1f".join(str(part) for part in parts).encode("utf-8")
    return f"{prefix}-{hashlib.sha256(payload).hexdigest()[:length]}"


def read_jsonl(path: Path) -> list[dict]:
    records = []
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if line.strip():
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc
    return records


def load_existing(path: Path, work_id: str) -> dict:
    if not path.exists():
        return {}
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema") != SCHEMA or document.get("work_id") != work_id:
        raise ValueError(f"Refusing to merge incompatible name review: {path}")
    return document


def classification_hint(kinds: set[str]) -> str:
    return "person" if kinds == {"person"} else "unknown"


def passage(text: str, start: int, end: int) -> str:
    return re.sub(r"\s+", " ", text[max(0, start - 180):min(len(text), end + 180)]).strip()


def build_document(
    *, work_id: str, source_path: Path, output_path: Path, issue: int, generated_at: str
) -> dict:
    units = read_jsonl(source_path)
    if not units:
        raise ValueError("Validated translation JSONL is empty")
    if any(unit.get("work_id") != work_id for unit in units):
        raise ValueError("Translation JSONL contains a different work_id")
    if any(unit.get("target", {}).get("language") != "en" for unit in units):
        raise ValueError("Name review source must be validated English translation units")

    existing = load_existing(output_path, work_id)
    old_candidates = {item["candidate_id"]: item for item in existing.get("candidates", [])}
    old_mentions = {item["mention_id"]: item for item in existing.get("mentions", [])}
    detected: dict[str, dict] = {}
    mentions: list[dict] = []
    preserved_candidate_reviews = 0
    preserved_mention_reviews = 0

    for unit in units:
        scan = int(unit["source"]["scan_page"])
        volume = int(unit["source"]["volume"])
        printed_page = unit["source"].get("printed_page")
        text = str(unit["target"].get("text") or "")
        for mapping in unit["target"].get("names") or []:
            english = re.sub(r"\s+", " ", str(mapping.get("english") or "")).strip()
            arabic = re.sub(r"\s+", " ", str(mapping.get("arabic") or "")).strip()
            if not english:
                continue
            norm = normalized_form(english)
            candidate_id = stable_id("candidate", work_id, norm, length=16)
            item = detected.setdefault(norm, {
                "candidate_id": candidate_id,
                "observed_form": english,
                "normalized_form": norm,
                "kinds": set(),
                "arabic_forms": set(),
                "mention_ids": [],
            })
            if mapping.get("kind"):
                item["kinds"].add(str(mapping["kind"]))
            if arabic:
                item["arabic_forms"].add(arabic)

            matches = list(re.finditer(re.escape(english), text, re.IGNORECASE))
            if not matches:
                matches = [None]
            for occurrence, match in enumerate(matches):
                start = match.start() if match else -1
                end = match.end() if match else -1
                observed = match.group(0) if match else english
                mention_id = stable_id(
                    "mention", work_id, volume, scan, candidate_id, occurrence, length=20
                )
                if mention_id in item["mention_ids"]:
                    continue
                item["mention_ids"].append(mention_id)
                old_review = old_mentions.get(mention_id, {}).get("review")
                if old_review is not None:
                    preserved_mention_reviews += 1
                mentions.append({
                    "mention_id": mention_id,
                    "candidate_id": candidate_id,
                    "observed_form": observed,
                    "source_location": {
                        "volume": volume,
                        "scan_page": scan,
                        "printed_page": printed_page,
                        "start_char": start,
                        "end_char": end,
                    },
                    "passage": passage(text, start, end) if match else text[:360].strip(),
                    "machine": {
                        "method": METHOD,
                        "version": METHOD_VERSION,
                        "confidence": 0.95 if match else 0.75,
                        "exact_text_match": bool(match),
                    },
                    "review": old_review,
                })

    candidates = []
    for item in detected.values():
        old_review = old_candidates.get(item["candidate_id"], {}).get("review")
        if old_review is not None:
            preserved_candidate_reviews += 1
        candidates.append({
            "candidate_id": item["candidate_id"],
            "observed_form": item["observed_form"],
            "normalized_form": item["normalized_form"],
            "classification_hint": classification_hint(item["kinds"]),
            "mention_ids": item["mention_ids"],
            "machine": {
                "method": METHOD,
                "version": METHOD_VERSION,
                "status": "translation-attested",
                "confidence": 0.95,
                "arabic_forms": sorted(item["arabic_forms"]),
                "source_kinds": sorted(item["kinds"]),
            },
            "review": old_review,
        })

    detected_ids = {item["candidate_id"] for item in candidates}
    retained_mentions = {item["mention_id"] for item in mentions}
    for old in existing.get("candidates", []):
        if old["candidate_id"] in detected_ids or old.get("review") is None:
            continue
        candidates.append(old)
        preserved_candidate_reviews += 1
        for mention_id in old.get("mention_ids", []):
            old_mention = old_mentions.get(mention_id)
            if old_mention and mention_id not in retained_mentions:
                mentions.append(old_mention)
                retained_mentions.add(mention_id)
                if old_mention.get("review") is not None:
                    preserved_mention_reviews += 1

    candidates.sort(key=lambda item: (-len(item["mention_ids"]), item["normalized_form"]))
    mentions.sort(key=lambda item: (
        item["source_location"].get("volume", 0),
        item["source_location"].get("scan_page", 0),
        item["source_location"].get("start_char", -1),
        item["mention_id"],
    ))
    try:
        source_label = source_path.relative_to(ROOT).as_posix()
    except ValueError:
        source_label = source_path.as_posix()
    return {
        "schema": SCHEMA,
        "authority": AUTHORITY,
        "issue": issue,
        "work_id": work_id,
        "source": {"ocr_text": source_label, "sha256": sha256_file(source_path), "language": "en"},
        "extraction": {
            "method": METHOD,
            "version": METHOD_VERSION,
            "generated_at_utc": generated_at,
            "candidate_count": len(candidates),
            "mention_count": len(mentions),
            "preserved_candidate_reviews": preserved_candidate_reviews,
            "preserved_mention_reviews": preserved_mention_reviews,
        },
        "candidates": candidates,
        "mentions": mentions,
        "review_policy": {
            "machine_output_is_authoritative": False,
            "human_review_is_preserved_on_rerun": True,
            "identity_registry": "docs/narrative/names/name-identities-v1.json",
            "elixr_role": "rebuildable projection",
        },
    }


def update_index(index_path: Path, output_path: Path, document: dict) -> dict:
    index = json.loads(index_path.read_text(encoding="utf-8"))
    if index.get("schema") != "firstlight.name-review-index.v1":
        raise ValueError(f"Incompatible name review index: {index_path}")
    try:
        output_label = "/" + output_path.relative_to(ROOT).as_posix()
    except ValueError:
        raise ValueError("Name review output must be inside the repository")
    index.setdefault("works", {})[document["work_id"]] = output_label

    documents = []
    for work_id, path_label in index["works"].items():
        if work_id == document["work_id"]:
            documents.append(document)
            continue
        path = ROOT / str(path_label).lstrip("/")
        if path.exists():
            documents.append(json.loads(path.read_text(encoding="utf-8")))
    index["summary"] = {
        "reviewable_works": len(documents),
        "candidate_count": sum(len(item.get("candidates") or []) for item in documents),
        "mention_count": sum(len(item.get("mentions") or []) for item in documents),
        "reviewed_candidate_count": sum(
            1 for item in documents for candidate in item.get("candidates") or [] if candidate.get("review") is not None
        ),
    }
    return index


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + ".tmp")
    pending.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pending.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--index", required=True, type=Path)
    parser.add_argument("--work-id", default="ibn_hajar_isabah_v1")
    parser.add_argument("--issue", type=int, default=971)
    parser.add_argument("--generated-at")
    args = parser.parse_args()
    source_path = args.input.resolve()
    output_path = args.output.resolve()
    index_path = args.index.resolve()
    generated_at = args.generated_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    document = build_document(
        work_id=args.work_id,
        source_path=source_path,
        output_path=output_path,
        issue=args.issue,
        generated_at=generated_at,
    )
    index = update_index(index_path, output_path, document)
    atomic_json(output_path, document)
    atomic_json(index_path, index)
    print(json.dumps(document["extraction"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

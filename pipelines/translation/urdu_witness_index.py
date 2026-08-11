#!/usr/bin/env python3
"""Rank page-level Urdu witness candidates for an Arabic al-Isabah page."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path


DIGIT_MAP = str.maketrans(
    "٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹",
    "01234567890123456789",
)
CHAR_MAP = str.maketrans({
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
    "ى": "ي", "ی": "ي", "ے": "ي", "ئ": "ي",
    "ك": "ک", "ة": "ه", "ۀ": "ه", "ہ": "ه", "ھ": "ه",
    "ؤ": "و", "ء": "", "ـ": "",
})
DIACRITICS = re.compile(r"[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed]")
TOKEN_RE = re.compile(r"[\u0621-\u06ff]{2,}|\d{3,}")
STOPWORDS = {
    "الله", "رسول", "عليه", "وسلم", "رضي", "عنها", "عنه", "قال", "قلت",
    "ذكر", "هذا", "هذه", "كان", "كانت", "الى", "على", "من", "في", "عن",
    "اور", "ہے", "ہیں", "نے", "کا", "کی", "کے", "سے", "کو", "میں", "کہ",
    "انہوں", "ان", "ایک", "کیا", "فرمایا", "ہوا", "ہوئے", "تھا", "تھی",
}
URDU_VOLUME8_FIRST_BODY_SCAN = 41
URDU_VOLUME8_LAST_BODY_SCAN = 547
URDU_VOLUME8_EXPECTED_SCANS = frozenset(range(1, 548))


def expected_urdu_scan_page(arabic_scan_page: int) -> int:
    """Estimate the witness page from observed body endpoints (Arabic 4-494, Urdu 41-547)."""
    return round(41 + (arabic_scan_page - 4) * (506 / 490))


def normalize_script(value: str) -> str:
    value = value.translate(DIGIT_MAP).translate(CHAR_MAP)
    value = DIACRITICS.sub("", value)
    return " ".join(TOKEN_RE.findall(value))


def tokens(value: str) -> set[str]:
    return {token for token in normalize_script(value).split() if token not in STOPWORDS}


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def validate_volume8_witness_units(units: list[dict]) -> None:
    scans = [int(unit["source"]["scan_page"]) for unit in units]
    if len(scans) != len(set(scans)):
        raise RuntimeError("Urdu witness contains duplicate scan pages")
    observed = set(scans)
    if observed != URDU_VOLUME8_EXPECTED_SCANS:
        missing = sorted(URDU_VOLUME8_EXPECTED_SCANS - observed)
        extra = sorted(observed - URDU_VOLUME8_EXPECTED_SCANS)
        raise RuntimeError(
            f"Urdu witness does not cover scan pages 1-547 exactly; "
            f"missing={missing[:20]} ({len(missing)} total), extra={extra[:20]} ({len(extra)} total)"
        )
    bad_hashes = []
    for unit in units:
        source = unit["source"]
        observed_hash = hashlib.sha256(str(source.get("text") or "").encode("utf-8")).hexdigest()
        if source.get("text_sha256") != observed_hash:
            bad_hashes.append(int(source["scan_page"]))
    if bad_hashes:
        raise RuntimeError(f"Urdu witness text hashes are stale on pages: {bad_hashes[:20]}")


class UrduWitnessIndex:
    def __init__(self, units: list[dict]):
        scans = [int(unit["source"]["scan_page"]) for unit in units]
        if len(scans) != len(set(scans)):
            raise RuntimeError("Urdu witness contains duplicate scan pages")
        self.units = {int(unit["source"]["scan_page"]): unit for unit in units}
        self.page_tokens: dict[int, set[str]] = {}
        self.normalized_text: dict[int, str] = {}
        self.postings: dict[str, set[int]] = defaultdict(set)
        for page, unit in self.units.items():
            normalized_text = normalize_script(str(unit["source"].get("text") or ""))
            self.normalized_text[page] = normalized_text
            page_tokens = {token for token in normalized_text.split() if token not in STOPWORDS}
            self.page_tokens[page] = page_tokens
            for token in page_tokens:
                self.postings[token].add(page)
        page_count = max(1, len(self.units))
        self.idf = {
            token: math.log((page_count + 1) / (len(pages) + 1)) + 1.0
            for token, pages in self.postings.items()
        }

    def rank(
        self,
        *,
        arabic_text: str,
        arabic_names: list[str],
        heading_names: list[str] | None = None,
        entry_numbers: list[int],
        top_k: int = 3,
        expected_scan_page: int | None = None,
        scan_window: int = 20,
        first_body_scan: int = URDU_VOLUME8_FIRST_BODY_SCAN,
        last_body_scan: int = URDU_VOLUME8_LAST_BODY_SCAN,
    ) -> list[dict]:
        query_tokens = tokens(arabic_text)
        name_forms = [
            (name, normalized)
            for name in arabic_names
            if (normalized := normalize_script(name))
        ]
        heading_forms = [
            (name, normalized)
            for name in (heading_names or [])
            if (normalized := normalize_script(name))
        ]
        number_forms = {str(number) for number in entry_numbers}
        scores: Counter[int] = Counter()
        token_hits: dict[int, set[str]] = defaultdict(set)
        name_hits: dict[int, list[str]] = defaultdict(list)
        heading_hits: dict[int, list[str]] = defaultdict(list)
        number_hits: dict[int, list[int]] = defaultdict(list)

        candidate_pages = {
            page for page in self.units
            if first_body_scan <= page <= last_body_scan
        }
        if expected_scan_page is not None:
            candidate_pages = {
                page for page in candidate_pages
                if abs(page - expected_scan_page) <= scan_window
            }
            for page in candidate_pages:
                distance = abs(page - expected_scan_page)
                scores[page] += 12.0 * (1.0 - distance / max(1, scan_window))

        for token in query_tokens:
            weight = self.idf.get(token, 0.0)
            if not weight:
                continue
            for page in self.postings[token] & candidate_pages:
                scores[page] += weight
                token_hits[page].add(token)

        for page in candidate_pages:
            unit = self.units[page]
            normalized_text = self.normalized_text[page]
            for original, normalized_heading in heading_forms:
                if normalized_heading and normalized_heading in normalized_text:
                    scores[page] += 42.0
                    heading_hits[page].append(original)
            for original, normalized_name in name_forms:
                if normalized_name and normalized_name in normalized_text:
                    scores[page] += 18.0
                    name_hits[page].append(original)
            page_numbers = {token for token in normalized_text.split() if token.isdigit()}
            for number in sorted(number_forms & page_numbers):
                scores[page] += 28.0
                number_hits[page].append(int(number))

        ranked = []
        for page, score in scores.most_common(max(top_k, 1)):
            unit = self.units[page]
            selection_signals = []
            if heading_hits.get(page):
                selection_signals.append("exact_biography_heading")
            if number_hits.get(page):
                selection_signals.append("exact_entry_number")
            if name_hits.get(page):
                selection_signals.append("exact_person_name")
            if token_hits.get(page):
                selection_signals.append("arabic_token_overlap")
            if expected_scan_page is not None:
                selection_signals.append("expected_page_proximity")
            ranked.append({
                "scan_page": page,
                "score": round(float(score), 4),
                "expected_scan_page": expected_scan_page,
                "distance_from_expected": (
                    abs(page - expected_scan_page) if expected_scan_page is not None else None
                ),
                "selection_signals": selection_signals,
                "matched_names": name_hits.get(page, []),
                "matched_headings": heading_hits.get(page, []),
                "matched_entry_numbers": number_hits.get(page, []),
                "matched_tokens": sorted(token_hits.get(page, set()), key=lambda token: (-self.idf.get(token, 0), token))[:16],
                "text_sha256": unit["source"]["text_sha256"],
                "quality": unit["source"].get("quality", {}),
                "text": unit["source"].get("text", ""),
                "pdf": unit["source"].get("pdf"),
            })
        return ranked


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--urdu-units", required=True, type=Path)
    parser.add_argument("--arabic-page", required=True, type=Path, help="JSON object with arabic_text")
    parser.add_argument("--translation-page", type=Path, help="Optional Codex page JSON with names and entry_numbers")
    parser.add_argument("--top", type=int, default=3)
    args = parser.parse_args()
    source = json.loads(args.arabic_page.read_text(encoding="utf-8"))
    translation = json.loads(args.translation_page.read_text(encoding="utf-8")) if args.translation_page else {}
    index = UrduWitnessIndex(read_jsonl(args.urdu_units))
    result = index.rank(
        arabic_text=source["arabic_text"],
        arabic_names=[item["arabic"] for item in translation.get("names", [])],
        entry_numbers=[int(item) for item in translation.get("entry_numbers", [])],
        top_k=args.top,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Build page-addressable, reviewable translation units from Archive DjVu XML."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path


def page_text_and_quality(page: ET.Element) -> tuple[str, dict]:
    paragraphs: list[str] = []
    confidences: list[int] = []
    for paragraph in page.findall(".//PARAGRAPH"):
        lines: list[str] = []
        for line in paragraph.findall("./LINE"):
            words = []
            for word in line.findall("./WORD"):
                value = "".join(word.itertext()).strip()
                if value:
                    words.append(value)
                try:
                    confidences.append(int(word.get("x-confidence", "0")))
                except ValueError:
                    confidences.append(0)
            if words:
                lines.append(" ".join(words))
        if lines:
            paragraphs.append("\n".join(lines))
    text = "\n\n".join(paragraphs).strip()
    mean = round(sum(confidences) / len(confidences), 2) if confidences else 0.0
    low = sum(1 for confidence in confidences if confidence < 50)
    return text, {
        "word_count": len(confidences),
        "mean_word_confidence": mean,
        "low_confidence_word_count": low,
        "low_confidence_ratio": round(low / len(confidences), 4) if confidences else 1.0,
    }


def iter_pages(path: Path):
    with gzip.open(path, "rb") as handle:
        for _, element in ET.iterparse(handle, events=("end",)):
            if element.tag != "OBJECT":
                continue
            yield element
            element.clear()


def stable_unit_id(witness_id: str, volume: int, scan_page: int, text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return f"{witness_id}:v{volume:02d}:p{scan_page:04d}:{digest}"


def build_volume(
    xml_path: Path,
    output_path: Path,
    witness_id: str,
    work_id: str,
    volume: int,
    pdf_path: str,
) -> dict:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if output_path.exists():
        with output_path.open("r", encoding="utf-8") as current:
            for line in current:
                if line.strip():
                    record = json.loads(line)
                    existing[record["unit_id"]] = record
    counts = {"pages": 0, "translatable_pages": 0, "ocr_words": 0, "low_confidence_words": 0, "preserved_reviewed_units": 0}
    pending_output = output_path.with_suffix(output_path.suffix + ".tmp")
    with pending_output.open("w", encoding="utf-8", newline="\n") as output:
        for scan_page, page in enumerate(iter_pages(xml_path), 1):
            text, quality = page_text_and_quality(page)
            counts["pages"] += 1
            counts["ocr_words"] += quality["word_count"]
            counts["low_confidence_words"] += quality["low_confidence_word_count"]
            source_state = "ready" if len(text) >= 80 else "image_review_required"
            if source_state == "ready":
                counts["translatable_pages"] += 1
            record = {
                "schema": "firstlight.reviewable-translation-unit.v1",
                "unit_id": stable_unit_id(witness_id, volume, scan_page, text),
                "work_id": work_id,
                "witness_id": witness_id,
                "source": {
                    "language": "ur",
                    "volume": volume,
                    "scan_page": scan_page,
                    "pdf": pdf_path,
                    "page_ocr": str(xml_path).replace("\\", "/"),
                    "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    "text": text,
                    "state": source_state,
                    "quality": quality,
                },
                "target": {"language": "en", "text": None, "state": "pending"},
                "translation": {
                    "method": None,
                    "model": None,
                    "prompt_version": "isabah-urdu-en-faithful-v1",
                    "generated_at_utc": None,
                },
                "review": {"state": "unreviewed", "reviewer": None, "notes": None},
                "arabic_cross_check": {
                    "state": "pending",
                    "canonical_work_id": work_id,
                    "citation": None,
                    "notes": None,
                },
            }
            previous = existing.get(record["unit_id"])
            if previous and previous.get("source", {}).get("text_sha256") == record["source"]["text_sha256"]:
                for field in ("target", "translation", "review", "arabic_cross_check"):
                    if field in previous:
                        record[field] = previous[field]
                if previous.get("review", {}).get("state") not in {None, "unreviewed"}:
                    counts["preserved_reviewed_units"] += 1
            output.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    pending_output.replace(output_path)
    return counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--witness-lock", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()
    lock_path = Path(args.witness_lock)
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    out_dir = Path(args.out_dir)
    report = {
        "schema": "firstlight.translation-corpus-build.v1",
        "issue": lock["issue"],
        "work_id": lock["parent_work_id"],
        "witness_id": lock["witness_id"],
        "source_language": "ur",
        "target_language": "en",
        "volumes": [],
    }
    repository_root = lock_path.parents[6]
    for volume in lock["volumes"]:
        number = int(volume["volume"])
        xml_path = repository_root / volume["page_ocr_xml_gzip"]
        output_path = out_dir / f"volume_{number:02d}.translation-units.jsonl"
        counts = build_volume(
            xml_path,
            output_path,
            lock["witness_id"],
            lock["parent_work_id"],
            number,
            volume["pdf"],
        )
        report["volumes"].append({"volume": number, "units": str(output_path).replace("\\", "/"), **counts})
    report["total_pages"] = sum(volume["pages"] for volume in report["volumes"])
    report["total_translatable_pages"] = sum(volume["translatable_pages"] for volume in report["volumes"])
    report["total_ocr_words"] = sum(volume["ocr_words"] for volume in report["volumes"])
    report["overall_low_confidence_ratio"] = round(
        sum(volume["low_confidence_words"] for volume in report["volumes"])
        / max(1, report["total_ocr_words"]),
        4,
    )
    (out_dir / "corpus-build.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Localize the complete eight-volume Urdu al-Isabah witness from Archive.org.

The Urdu edition is a secondary translation witness. It never replaces the
canonical Arabic edition and its OCR is never promoted to approved English.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import logging
import re
import shutil
import subprocess
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

from localize_selected_editions import ROOT, get_json, sha256
from pypdf import PdfReader

logging.getLogger("pypdf").setLevel(logging.ERROR)

ISSUE = 970
IDENTIFIER = "al-asabah-fi-tamyeeze-al-sahaba-1"
TARGET = (
    ROOT
    / "docs/narrative/sources/T1_primaries/ibn_hajar_isabah_v1"
    / "urdu_witness_v1"
)
VOLUME_RE = re.compile(r"Al-asabah fi-tamyeeze al-sahaba - ([1-8])\.pdf$")


def md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_verified(url: str, destination: Path, item: dict) -> None:
    expected_size = int(item["size"])
    expected_md5 = str(item["md5"])
    if (
        destination.exists()
        and destination.stat().st_size == expected_size
        and md5(destination) == expected_md5
    ):
        return
    partial = destination.with_suffix(destination.suffix + ".direct.part")
    partial.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "curl.exe", "--fail", "--location", "--show-error", "--retry", "8",
            "--retry-all-errors", "--retry-delay", "2", "--continue-at", "-",
            "--output", str(partial), url,
        ],
        check=True,
    )
    if partial.stat().st_size != expected_size:
        raise RuntimeError(
            f"Size mismatch for {destination.name}: {partial.stat().st_size} != {expected_size}"
        )
    observed_md5 = md5(partial)
    if observed_md5 != expected_md5:
        raise RuntimeError(
            f"MD5 mismatch for {destination.name}: {observed_md5} != {expected_md5}"
        )
    partial.replace(destination)


def select_files(metadata: dict, suffix: str) -> dict[int, dict]:
    selected: dict[int, dict] = {}
    for item in metadata.get("files", []):
        name = str(item.get("name", ""))
        match = VOLUME_RE.match(name) if suffix == "pdf" else re.match(
            rf"Al-asabah fi-tamyeeze al-sahaba - ([1-8])_{re.escape(suffix)}$", name
        )
        if match and item.get("size"):
            selected[int(match.group(1))] = item
    return selected


def deterministic_gzip(source: Path, destination: Path) -> None:
    partial = destination.with_suffix(destination.suffix + ".part")
    with source.open("rb") as input_handle, partial.open("wb") as raw_output:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw_output, mtime=0) as output:
            shutil.copyfileobj(input_handle, output, length=1024 * 1024)
    partial.replace(destination)


def xml_page_count(path: Path) -> int:
    with gzip.open(path, "rb") as handle:
        return sum(
            1
            for _, element in ET.iterparse(handle, events=("end",))
            if element.tag == "OBJECT"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata-only", action="store_true")
    args = parser.parse_args()

    metadata = get_json(f"https://archive.org/metadata/{IDENTIFIER}")
    root = f"https://archive.org/download/{IDENTIFIER}"
    pdfs = select_files(metadata, "pdf")
    texts = select_files(metadata, "djvu.txt")
    xmls = select_files(metadata, "djvu.xml")
    for label, selected in (("PDF", pdfs), ("OCR text", texts), ("page XML", xmls)):
        if sorted(selected) != list(range(1, 9)):
            raise RuntimeError(f"Expected volumes 1-8 for {label}; found {sorted(selected)}")

    TARGET.mkdir(parents=True, exist_ok=True)
    records = []
    for volume in range(1, 9):
        pdf_item = pdfs[volume]
        text_item = texts[volume]
        xml_item = xmls[volume]
        pdf_path = TARGET / f"volume_{volume:02d}.pdf"
        text_path = TARGET / f"volume_{volume:02d}.ocr.txt"
        xml_gz_path = TARGET / f"volume_{volume:02d}.ocr.xml.gz"
        xml_temp = TARGET / f"volume_{volume:02d}.ocr.xml.download"

        if not args.metadata_only:
            download_verified(
                f"{root}/{urllib.parse.quote(pdf_item['name'])}",
                pdf_path,
                pdf_item,
            )
            download_verified(
                f"{root}/{urllib.parse.quote(text_item['name'])}",
                text_path,
                text_item,
            )
            if not xml_gz_path.exists():
                download_verified(
                    f"{root}/{urllib.parse.quote(xml_item['name'])}",
                    xml_temp,
                    xml_item,
                )
                deterministic_gzip(xml_temp, xml_gz_path)
                xml_temp.unlink()

        pdf_page_count = len(PdfReader(str(pdf_path)).pages) if pdf_path.exists() else None
        ocr_page_count = xml_page_count(xml_gz_path) if xml_gz_path.exists() else None
        if pdf_page_count is not None and ocr_page_count != pdf_page_count:
            raise RuntimeError(
                f"Volume {volume} page mismatch: PDF={pdf_page_count}, OCR={ocr_page_count}"
            )

        records.append(
            {
                "volume": volume,
                "source_pdf_name": pdf_item["name"],
                "pdf": str(pdf_path.relative_to(ROOT)).replace("\\", "/"),
                "pdf_source_size_bytes": int(pdf_item["size"]),
                "pdf_source_md5": pdf_item.get("md5"),
                "pdf_sha256": sha256(pdf_path) if pdf_path.exists() else None,
                "pdf_page_count": pdf_page_count,
                "source_text_name": text_item["name"],
                "ocr_text": str(text_path.relative_to(ROOT)).replace("\\", "/"),
                "ocr_text_source_size_bytes": int(text_item["size"]),
                "ocr_text_source_md5": text_item.get("md5"),
                "ocr_text_sha256": sha256(text_path) if text_path.exists() else None,
                "source_page_xml_name": xml_item["name"],
                "page_ocr_xml_gzip": str(xml_gz_path.relative_to(ROOT)).replace("\\", "/"),
                "page_xml_source_size_bytes": int(xml_item["size"]),
                "page_xml_source_md5": xml_item.get("md5"),
                "page_ocr_xml_gzip_size_bytes": xml_gz_path.stat().st_size if xml_gz_path.exists() else None,
                "page_ocr_xml_gzip_sha256": sha256(xml_gz_path) if xml_gz_path.exists() else None,
                "ocr_page_count": ocr_page_count,
            }
        )
        print(f"volume {volume}: localized PDF, OCR text, and page-aware OCR", flush=True)

    confidence_keys = ["word_conf_0_10"] + [
        f"word_conf_{start}_{start + 9}" for start in range(11, 91, 10)
    ] + ["word_conf_91_100"]
    confidence = {
        key: sum(int(item.get(key, 0)) for item in metadata.get("files", []))
        for key in confidence_keys
    }
    lock = {
        "schema": "firstlight.localized-source-witness.v1",
        "issue": ISSUE,
        "parent_work_id": "ibn_hajar_isabah_v1",
        "witness_id": "ibn_hajar_isabah_urdu_v1",
        "title": "Al Isabah Fi Tamyeeze Al Sahaba",
        "author": "Ibn Hajar al-Asqalani",
        "edition": "Maktaba Rahmaniya, Lahore, eight-volume Urdu edition",
        "archive_identifier": IDENTIFIER,
        "language": ["ur"],
        "expected_pdf_count": 8,
        "coverage": "complete_work_claim_pending_human_structure_review",
        "role": "secondary_translation_witness",
        "translator": "Maulana Muhammad Amir Shahzad Alvi",
        "publisher": "Maktaba Rahmaniya, Lahore",
        "source_url": f"https://archive.org/details/{IDENTIFIER}",
        "acquired_at_utc": "2026-08-04T00:00:00Z",
        "localized": not args.metadata_only,
        "localized_pdf_page_count": sum(record["pdf_page_count"] or 0 for record in records),
        "ocr": {
            "engine": metadata.get("metadata", {}).get("ocr"),
            "parameters": metadata.get("metadata", {}).get("ocr_parameters"),
            "detected_script": metadata.get("metadata", {}).get("ocr_detected_script"),
            "detected_language": metadata.get("metadata", {}).get("ocr_detected_lang"),
            "archive_word_confidence_buckets": confidence,
            "assessment": "machine_ocr_requires_human_sampling_especial_attention_to_names",
        },
        "translation_policy": {
            "target_language": "en",
            "machine_output_state": "draft_requires_review",
            "arabic_cross_check_required": True,
            "may_replace_canonical_arabic": False,
        },
        "volumes": records,
    }
    (TARGET / "witness-lock.json").write_text(
        json.dumps(lock, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    readme = [
        "# Urdu translation witness", "",
        "- Parent work: al-Isabah fi Tamyiz al-Sahabah",
        "- Translator: Maulana Muhammad Amir Shahzad Alvi",
        "- Publisher: Maktaba Rahmaniya, Lahore",
        "- Language: Urdu",
        f"- Localized: 8 PDFs, 8 OCR text files, 8 page-aware OCR files, {lock['localized_pdf_page_count']:,} scan pages",
        f"- Source: {lock['source_url']}",
        "- Role: secondary translation witness; the complete Arabic edition remains canonical.",
        "- OCR: Archive.org Tesseract Urdu output. Proper names and low-confidence text require image and Arabic cross-check.",
        "- English status: machine drafts are unapproved until human review.",
    ]
    (TARGET / "README.md").write_text("\n".join(readme) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

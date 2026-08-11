from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("align_usul_volume.py")
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("align_usul_volume", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class AlignUsulVolumeTests(unittest.TestCase):
    def test_alignment_uses_usul_and_audited_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            units = root / "units.jsonl"
            text_root = root / "text"
            output = root / "aligned.jsonl"
            report_path = root / "report.json"
            details = root / "details.json"
            rows = []
            for scan in (4, 5):
                rows.append({
                    "unit_id": f"unit-{scan}",
                    "work_id": "work",
                    "source": {"volume": 8, "scan_page": scan, "pdf": "v8.pdf", "text": f"ocr-{scan}", "text_sha256": f"hash-{scan}"},
                    "target": {"printed_page": scan - 1},
                })
            units.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
            (text_root / "101").mkdir(parents=True)
            (text_root / "101" / "clean.txt").write_text("clean Arabic", encoding="utf-8")
            details.write_text(json.dumps({"headings": [
                {"pageIndex": 100, "page": {"vol": "8", "page": "3"}, "title": "Heading"},
                {"pageIndex": 101, "page": {"vol": "8", "page": "4"}, "title": "Next"},
            ]}), encoding="utf-8")

            report = MODULE.align_volume(
                units_path=units,
                text_root=text_root,
                output_path=output,
                report_path=report_path,
                scan_start=4,
                scan_end=5,
                reader_start=101,
                details_path=details,
                max_fallback_pages=1,
            )
            aligned = MODULE.read_jsonl(output)
            self.assertTrue(report["pass"])
            self.assertEqual(report["fallback_pages"], [5])
            self.assertEqual(aligned[0]["source_state"], "canonical_usul_reader")
            self.assertEqual(aligned[0]["arabic_text"], "clean Arabic")
            self.assertEqual(aligned[1]["source_state"], "fallback_archive_ocr")

    def test_fails_when_fallback_budget_is_exceeded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            units = root / "units.jsonl"
            units.write_text(json.dumps({
                "unit_id": "unit-4",
                "work_id": "work",
                "source": {"volume": 8, "scan_page": 4, "pdf": "v8.pdf", "text": "ocr", "text_sha256": "hash"},
                "target": {"printed_page": 3},
            }) + "\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                MODULE.align_volume(
                    units_path=units,
                    text_root=root / "text",
                    output_path=root / "aligned.jsonl",
                    report_path=root / "report.json",
                    scan_start=4,
                    scan_end=4,
                    reader_start=101,
                    max_fallback_pages=0,
                )

    def test_facsimile_repair_prevents_ocr_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            units = root / "units.jsonl"
            repair = root / "repair.json"
            units.write_text(json.dumps({
                "unit_id": "unit-4", "work_id": "work",
                "source": {"volume": 8, "scan_page": 4, "pdf": "v8.pdf", "text": "damaged ocr", "text_sha256": "hash"},
                "target": {"printed_page": 3},
            }) + "\n", encoding="utf-8")
            repair.write_text(json.dumps({"repairs": [{
                "scan_page": 4,
                "arabic_text": "visually transcribed Arabic",
                "provenance": {"method": "facsimile_visual_transcription"},
            }]}), encoding="utf-8")
            report = MODULE.align_volume(
                units_path=units,
                text_root=root / "text",
                output_path=root / "aligned.jsonl",
                report_path=root / "report.json",
                scan_start=4,
                scan_end=4,
                reader_start=101,
                repair_path=repair,
                max_fallback_pages=0,
            )
            aligned = MODULE.read_jsonl(root / "aligned.jsonl")
            self.assertEqual(report["fallback_pages"], [])
            self.assertEqual(report["canonical_facsimile_transcription_pages"], [4])
            self.assertEqual(aligned[0]["source_state"], "canonical_facsimile_transcription")
            self.assertEqual(aligned[0]["arabic_text"], "visually transcribed Arabic")

    def test_facsimile_correction_repairs_captured_text_and_heading_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            units = root / "units.jsonl"
            repairs = root / "repairs.json"
            details = root / "details.json"
            text_root = root / "text"
            units.write_text(json.dumps({
                "unit_id": "unit-4", "work_id": "work",
                "source": {"volume": 8, "scan_page": 4, "pdf": "v8.pdf", "text": "ocr", "text_sha256": "hash"},
                "target": {"printed_page": 3},
            }) + "\n", encoding="utf-8")
            (text_root / "101").mkdir(parents=True)
            (text_root / "101" / "clean.txt").write_text("1077- Abaraha", encoding="utf-8")
            details.write_text(json.dumps({"headings": [{
                "pageIndex": 100, "page": {"vol": "8", "page": "3"}, "title": "1077- Abaraha",
            }]}), encoding="utf-8")
            repairs.write_text(json.dumps({"repairs": [{
                "scan_page": 4,
                "text_replacements": [{"old": "1077- Abaraha", "new": "10777- Abaraha"}],
                "heading_titles": ["10777- Abaraha"],
                "provenance": {"method": "facsimile_visual_collation"},
            }]}), encoding="utf-8")
            report = MODULE.align_volume(
                units_path=units,
                text_root=text_root,
                output_path=root / "aligned.jsonl",
                report_path=root / "report.json",
                scan_start=4,
                scan_end=4,
                reader_start=101,
                details_path=details,
                repair_path=repairs,
            )
            aligned = MODULE.read_jsonl(root / "aligned.jsonl")
            self.assertEqual(aligned[0]["arabic_text"], "10777- Abaraha")
            self.assertEqual(aligned[0]["heading_titles"], ["10777- Abaraha"])
            self.assertEqual(aligned[0]["source_state"], "canonical_usul_reader_facsimile_corrected")
            self.assertEqual(aligned[0]["source_intervention"]["method"], "facsimile_visual_collation")
            self.assertEqual(report["canonical_facsimile_correction_pages"], [4])

    def test_facsimile_correction_fails_closed_when_expected_text_is_absent(self) -> None:
        with self.assertRaisesRegex(ValueError, "expected 1 occurrence"):
            MODULE.apply_text_replacements(
                "10777- Abaraha",
                [{"old": "1077- Abaraha", "new": "10777- Abaraha"}],
                4,
            )

    def test_facsimile_correction_can_remove_duplicated_ocr_text(self) -> None:
        self.assertEqual(
            MODULE.apply_text_replacements(
                "entry\nduplicated block\nnext",
                [{"old": "duplicated block\n", "new": ""}],
                35,
            ),
            "entry\nnext",
        )

    def test_explicit_entry_sequence_is_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            units = root / "units.jsonl"
            text_root = root / "text"
            units.write_text(json.dumps({
                "unit_id": "unit-4",
                "work_id": "work",
                "source": {
                    "volume": 8,
                    "scan_page": 4,
                    "pdf": "v8.pdf",
                    "text": "ocr",
                    "text_sha256": "hash",
                },
                "target": {"printed_page": 3},
            }) + "\n", encoding="utf-8")
            (text_root / "101").mkdir(parents=True)
            (text_root / "101" / "clean.txt").write_text(
                "10759- First\n10760- Second",
                encoding="utf-8",
            )
            report = MODULE.align_volume(
                units_path=units,
                text_root=text_root,
                output_path=root / "aligned.jsonl",
                report_path=root / "report.json",
                scan_start=4,
                scan_end=4,
                reader_start=101,
                expected_entry_first=10759,
                expected_entry_last=10760,
            )
            self.assertTrue(report["entry_sequence_audit"]["pass"])
            self.assertEqual(report["entry_sequence_audit"]["observed_count"], 2)

    def test_entry_sequence_gap_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            units = root / "units.jsonl"
            text_root = root / "text"
            units.write_text(json.dumps({
                "unit_id": "unit-4",
                "work_id": "work",
                "source": {
                    "volume": 8,
                    "scan_page": 4,
                    "pdf": "v8.pdf",
                    "text": "ocr",
                    "text_sha256": "hash",
                },
                "target": {"printed_page": 3},
            }) + "\n", encoding="utf-8")
            (text_root / "101").mkdir(parents=True)
            (text_root / "101" / "clean.txt").write_text(
                "10759- First\n10761- Third",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "canonical entry sequence mismatch"):
                MODULE.align_volume(
                    units_path=units,
                    text_root=text_root,
                    output_path=root / "aligned.jsonl",
                    report_path=root / "report.json",
                    scan_start=4,
                    scan_end=4,
                    reader_start=101,
                    expected_entry_first=10759,
                    expected_entry_last=10761,
                )


if __name__ == "__main__":
    unittest.main()

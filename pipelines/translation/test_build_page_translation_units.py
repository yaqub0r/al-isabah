from __future__ import annotations

import importlib.util
import gzip
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


SCRIPT = Path(__file__).with_name("build_page_translation_units.py")
SPEC = importlib.util.spec_from_file_location("build_page_translation_units", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class PageTranslationUnitTests(unittest.TestCase):
    def test_page_text_preserves_lines_and_quality(self) -> None:
        page = ET.fromstring(
            """<OBJECT><HIDDENTEXT><PAGECOLUMN><REGION><PARAGRAPH>
            <LINE><WORD x-confidence="90">ایک</WORD><WORD x-confidence="40">نام</WORD></LINE>
            <LINE><WORD x-confidence="80">عبارت</WORD></LINE>
            </PARAGRAPH></REGION></PAGECOLUMN></HIDDENTEXT></OBJECT>"""
        )
        text, quality = MODULE.page_text_and_quality(page)
        self.assertEqual(text, "ایک نام\nعبارت")
        self.assertEqual(quality, {
            "word_count": 3,
            "mean_word_confidence": 70.0,
            "low_confidence_word_count": 1,
            "low_confidence_ratio": 0.3333,
        })


    def test_unit_id_changes_with_source_text(self) -> None:
        first = MODULE.stable_unit_id("witness", 1, 5, "alpha")
        second = MODULE.stable_unit_id("witness", 1, 5, "beta")
        self.assertNotEqual(first, second)
        self.assertTrue(first.startswith("witness:v01:p0005:"))

    def test_rebuild_preserves_reviewed_translation(self) -> None:
        source_xml = """<DJVUXML><BODY><OBJECT><HIDDENTEXT><PAGECOLUMN><REGION><PARAGRAPH>
        <LINE><WORD x-confidence="90">یہ</WORD><WORD x-confidence="80">ایک</WORD><WORD x-confidence="70">طویل</WORD><WORD x-confidence="90">آزمائشی</WORD><WORD x-confidence="90">عبارت</WORD><WORD x-confidence="90">ہے</WORD></LINE>
        </PARAGRAPH></REGION></PAGECOLUMN></HIDDENTEXT></OBJECT></BODY></DJVUXML>"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            xml_path = root / "page.xml.gz"
            output_path = root / "units.jsonl"
            with gzip.open(xml_path, "wb") as handle:
                handle.write(source_xml.encode("utf-8"))
            MODULE.build_volume(xml_path, output_path, "witness", "work", 1, "source.pdf")
            record = json.loads(output_path.read_text(encoding="utf-8"))
            record["target"] = {"language": "en", "text": "Reviewed translation", "state": "approved"}
            record["review"] = {"state": "approved", "reviewer": "operator", "notes": None}
            output_path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
            counts = MODULE.build_volume(xml_path, output_path, "witness", "work", 1, "source.pdf")
            rebuilt = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(rebuilt["target"]["text"], "Reviewed translation")
            self.assertEqual(rebuilt["review"]["state"], "approved")
            self.assertEqual(counts["preserved_reviewed_units"], 1)


if __name__ == "__main__":
    unittest.main()

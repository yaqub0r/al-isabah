from __future__ import annotations

import gzip
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("build_hocr_searchtext_units.py")
SPEC = importlib.util.spec_from_file_location("build_hocr_searchtext_units", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class HocrSearchtextUnitTests(unittest.TestCase):
    def write_fixture(self, root: Path) -> tuple[Path, Path]:
        text_path = root / "searchtext.txt.gz"
        index_path = root / "pageindex.json.gz"
        content = "الصفحة الأولى" + "الصفحة الثانية"
        with gzip.open(text_path, "wt", encoding="utf-8") as handle:
            handle.write(content)
        with gzip.open(index_path, "wt", encoding="utf-8") as handle:
            json.dump([[0, 13, 0, 100], [13, len(content), 100, 200]], handle)
        return text_path, index_path

    def test_builds_selected_page_range(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            text_path, index_path = self.write_fixture(root)
            output = root / "units.jsonl"
            report = MODULE.build_units(
                text_path,
                index_path,
                output,
                work_id="work",
                volume=1,
                pdf_path="volume.pdf",
                first_page=2,
                last_page=2,
                expected_pages=2,
            )
            record = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["pages"], 1)
            self.assertEqual(record["source"]["scan_page"], 2)
            self.assertEqual(record["source"]["text"], "الصفحة الثانية")

    def test_rebuild_preserves_target_and_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            text_path, index_path = self.write_fixture(root)
            output = root / "units.jsonl"
            kwargs = dict(
                work_id="work",
                volume=1,
                pdf_path="volume.pdf",
                first_page=1,
                last_page=1,
                expected_pages=2,
            )
            MODULE.build_units(text_path, index_path, output, **kwargs)
            record = json.loads(output.read_text(encoding="utf-8"))
            record["target"] = {"language": "en", "text": "Reviewed", "state": "approved"}
            record["review"] = {"state": "approved", "reviewer": "operator", "notes": None}
            output.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
            report = MODULE.build_units(text_path, index_path, output, **kwargs)
            rebuilt = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["preserved_units"], 1)
            self.assertEqual(rebuilt["target"]["text"], "Reviewed")
            self.assertEqual(rebuilt["review"]["state"], "approved")

    def test_rejects_page_count_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            text_path, index_path = self.write_fixture(root)
            with self.assertRaisesRegex(ValueError, "expected 3"):
                MODULE.build_units(
                    text_path,
                    index_path,
                    root / "units.jsonl",
                    work_id="work",
                    volume=1,
                    pdf_path="volume.pdf",
                    first_page=1,
                    last_page=1,
                    expected_pages=3,
                )


if __name__ == "__main__":
    unittest.main()

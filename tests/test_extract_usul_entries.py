from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "extract_usul_entries.py"
SPEC = importlib.util.spec_from_file_location("extract_usul_entries", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class EntryExtractorTests(unittest.TestCase):
    def test_source_repair_is_exact_and_provenanced(self) -> None:
        repaired, applied = MODULE.apply_source_repairs(
            "before ع حمّاد after",
            8935,
            [{
                "repair_id": "repair-8935",
                "entry_number": 8935,
                "reader_page": 3370,
                "facsimile_pdf_page": 3588,
                "observed_reader_text": "ع حمّاد",
                "facsimile_text": "عن حمّاد",
            }],
        )
        self.assertEqual(repaired, "before عن حمّاد after")
        self.assertEqual(applied[0]["repair_id"], "repair-8935")

    def test_extracts_across_pages_and_stops_before_next_heading(self) -> None:
        pages = {
            "https://reader/10": "9998- Before:\nold\n10000- Target:\nfirst",
            "https://reader/11": "continuation\n10001- Next:\nnot target",
        }
        text, records = MODULE.extract_entry(10000, 10, reader_base="https://reader", page_fetcher=pages.__getitem__)
        self.assertEqual(text, "10000- Target:\nfirst\ncontinuation")
        self.assertEqual([item["reader_page"] for item in records], [10, 11])

    def test_manifest_caches_full_text_outside_git_manifest(self) -> None:
        def fetcher(url: str) -> str:
            return "10000- Target:\ntext\n10001- Next:" if url.endswith("/10") else ""

        spec = {
            "cohort_id": "test",
            "canonical_source": {"work_id": "w", "edition_id": "e"},
            "entry_targets": [{"entry_number": 10000, "name": "Target", "first_reader_page": 10}],
        }
        with tempfile.TemporaryDirectory() as temporary:
            manifest = MODULE.build_manifest(spec, Path(temporary), page_fetcher=fetcher)
            record = manifest["entries"][0]
            self.assertNotIn("arabic_text", record)
            self.assertTrue((Path(temporary) / record["cache_key"]).is_file())

    def test_keeps_page_bottom_footnote_after_next_entry_heading(self) -> None:
        pages = {
            "https://reader/20": "10000- Target «١»:\nbody\n10001- Next:\nnext body\n(١) Target note.",
        }
        text, _ = MODULE.extract_entry(10000, 20, reader_base="https://reader", page_fetcher=pages.__getitem__)
        self.assertEqual(text, "10000- Target «١»:\nbody\n(١) Target note.")


if __name__ == "__main__":
    unittest.main()

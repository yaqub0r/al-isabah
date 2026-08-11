from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "import_volume8.py"
SPEC = importlib.util.spec_from_file_location("import_volume8", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class ImportVolume8Tests(unittest.TestCase):
    def row(self, scan: int, arabic: str, english: str, unresolved=None) -> dict:
        return {
            "schema": MODULE.SOURCE_SCHEMA,
            "unit_id": f"page-{scan}",
            "source": {
                "volume": 8, "scan_page": scan, "printed_page": scan - 1,
                "reader_page": scan + 3912, "reader_url": f"https://example/{scan}",
                "text": arabic,
            },
            "target": {
                "text": english, "state": "machine_validated_unreviewed",
                "names": [{"arabic": "خديجة", "english": "Khadijah", "kind": "person"}],
                "unresolved": unresolved or [],
            },
        }

    def test_splits_multiple_entries_and_carries_cross_page_continuation(self) -> None:
        rows = [
            self.row(4, "١٠٧٥٩- آسية\nنص\n١٠٧٦٠- آمنة\nبداية", "10759—Asiya\nText\n10760—Amina\nStart"),
            self.row(5, "تكملة خديجة\n١٠٧٦١- خديجة\nخبر", "Continuation Khadijah\n10761—Khadijah\nReport"),
        ]
        entries, report = MODULE.import_rows(
            rows, "a" * 64,
            expected_first=10759, expected_last=10761,
            scan_first=4, scan_last=5,
        )
        self.assertEqual(sorted(entries), [10759, 10760, 10761])
        self.assertEqual(len(entries[10760]["segments"]), 2)
        self.assertEqual(entries[10761]["title"]["english"], "Khadijah")
        self.assertEqual(report["entries"], 3)

    def test_selects_names_and_unresolved_by_fragment(self) -> None:
        names = MODULE.unique_names(
            [{"arabic": "خديجة", "english": "Khadijah", "kind": "person"}],
            "ذكر خديجة", "Khadijah is mentioned",
        )
        self.assertEqual(names[0]["english"], "Khadijah")
        selected, remaining = MODULE.unresolved_for_fragment(
            [{"arabic_span": "خديجة"}, {"arabic_span": "ورقة"}],
            "خديجة", "Khadijah",
        )
        self.assertEqual(len(selected), 1)
        self.assertEqual(len(remaining), 1)

    def test_rejects_arabic_english_heading_mismatch(self) -> None:
        row = self.row(4, "١٠٧٥٩- آسية", "10760—Amina")
        with self.assertRaisesRegex(RuntimeError, "Entry headings differ"):
            # The exact coverage check occurs later; mismatch is detected immediately.
            MODULE.import_rows([row], "b" * 64)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("urdu_witness_index.py")
SPEC = importlib.util.spec_from_file_location("urdu_witness_index", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


def unit(page: int, text: str) -> dict:
    return {
        "source": {
            "scan_page": page,
            "text": text,
            "text_sha256": f"hash-{page}",
            "quality": {"mean_word_confidence": 80},
            "pdf": "witness.pdf",
        }
    }


class UrduWitnessIndexTests(unittest.TestCase):
    def test_normalizes_urdu_and_arabic_forms(self) -> None:
        self.assertEqual(MODULE.normalize_script("خديجة بنت خويلد"), MODULE.normalize_script("خدیجہ بنت خویلد"))
        self.assertEqual(MODULE.normalize_script("۱۰۷۵۹"), "10759")
        self.assertEqual(MODULE.expected_urdu_scan_page(4), 41)
        self.assertEqual(MODULE.expected_urdu_scan_page(494), 547)

    def test_ranks_name_and_entry_match_first(self) -> None:
        index = MODULE.UrduWitnessIndex([
            unit(10, "اسماء بنت عميس"),
            unit(144, "۱۰۷۵۹ خدیجہ بنت خویلد"),
            unit(200, "خدیجہ بنت الحصين"),
        ])
        ranked = index.rank(
            arabic_text="10759 خديجة بنت خويلد",
            arabic_names=["خديجة بنت خويلد"],
            heading_names=["خديجة بنت خويلد"],
            entry_numbers=[10759],
            top_k=2,
        )
        self.assertEqual(ranked[0]["scan_page"], 144)
        self.assertEqual(ranked[0]["matched_entry_numbers"], [10759])
        self.assertEqual(ranked[0]["matched_headings"], ["خديجة بنت خويلد"])

    def test_records_alignment_distance_and_selection_signals(self) -> None:
        index = MODULE.UrduWitnessIndex([
            unit(143, "خدیجہ بنت خویلد"),
            unit(144, "۱۰۷۵۹ خدیجہ بنت خویلد"),
        ])
        ranked = index.rank(
            arabic_text="خديجة بنت خويلد",
            arabic_names=["خديجة بنت خويلد"],
            heading_names=["خديجة بنت خويلد"],
            entry_numbers=[10759],
            top_k=1,
            expected_scan_page=142,
        )
        self.assertEqual(ranked[0]["expected_scan_page"], 142)
        self.assertEqual(ranked[0]["distance_from_expected"], 2)
        self.assertEqual(
            ranked[0]["selection_signals"],
            [
                "exact_biography_heading",
                "exact_entry_number",
                "exact_person_name",
                "arabic_token_overlap",
                "expected_page_proximity",
            ],
        )

    def test_rejects_duplicate_or_incomplete_production_witness(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "duplicate scan pages"):
            MODULE.UrduWitnessIndex([unit(41, "one"), unit(41, "two")])
        with self.assertRaisesRegex(RuntimeError, "does not cover scan pages 1-547"):
            MODULE.validate_volume8_witness_units([unit(41, "one")])


if __name__ == "__main__":
    unittest.main()

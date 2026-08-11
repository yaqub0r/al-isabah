from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("build_translation_name_review.py")
SPEC = importlib.util.spec_from_file_location("build_translation_name_review", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def unit() -> dict:
    return {
        "work_id": "ibn_hajar_isabah_v1",
        "source": {"language": "ar", "volume": 8, "scan_page": 4, "printed_page": 3},
        "target": {
            "language": "en",
            "text": "Asiya bint al-Faraj met Asiya bint al-Faraj at Mecca.",
            "names": [
                {"arabic": "آسية بنت الفرج", "english": "Asiya bint al-Faraj", "kind": "person"},
                {"arabic": "مكة", "english": "Mecca", "kind": "place"},
            ],
        },
    }


class BuildTranslationNameReviewTests(unittest.TestCase):
    def test_builds_stable_candidates_and_exact_mentions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "units.jsonl"
            output = root / "review.json"
            source.write_text(json.dumps(unit(), ensure_ascii=False) + "\n", encoding="utf-8")
            document = MODULE.build_document(
                work_id="ibn_hajar_isabah_v1", source_path=source, output_path=output,
                issue=971, generated_at="2026-08-06T00:00:00Z",
            )
            by_name = {item["observed_form"]: item for item in document["candidates"]}
            self.assertEqual(by_name["Asiya bint al-Faraj"]["classification_hint"], "person")
            self.assertEqual(len(by_name["Asiya bint al-Faraj"]["mention_ids"]), 2)
            self.assertEqual(by_name["Mecca"]["classification_hint"], "unknown")
            self.assertTrue(all(item["machine"]["exact_text_match"] for item in document["mentions"]))

    def test_rerun_preserves_operator_reviews(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "units.jsonl"
            output = root / "review.json"
            source.write_text(json.dumps(unit(), ensure_ascii=False) + "\n", encoding="utf-8")
            first = MODULE.build_document(
                work_id="ibn_hajar_isabah_v1", source_path=source, output_path=output,
                issue=971, generated_at="2026-08-06T00:00:00Z",
            )
            first["candidates"][0]["review"] = {"disposition": "confirmed-name"}
            first["mentions"][0]["review"] = {"disposition": "confirmed-name"}
            output.write_text(json.dumps(first, ensure_ascii=False), encoding="utf-8")
            second = MODULE.build_document(
                work_id="ibn_hajar_isabah_v1", source_path=source, output_path=output,
                issue=971, generated_at="2026-08-06T01:00:00Z",
            )
            self.assertEqual(second["extraction"]["preserved_candidate_reviews"], 1)
            self.assertEqual(second["extraction"]["preserved_mention_reviews"], 1)


if __name__ == "__main__":
    unittest.main()

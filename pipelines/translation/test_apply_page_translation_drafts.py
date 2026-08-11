from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("apply_page_translation_drafts.py")
SPEC = importlib.util.spec_from_file_location("apply_page_translation_drafts", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class ApplyPageTranslationDraftTests(unittest.TestCase):
    def test_applies_page_draft_and_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            units = root / "units.jsonl"
            drafts = root / "drafts.json"
            units.write_text(
                json.dumps({
                    "source": {"scan_page": 4},
                    "target": {"language": "en", "text": None, "state": "pending"},
                    "translation": {},
                }) + "\n",
                encoding="utf-8",
            )
            drafts.write_text(json.dumps({
                "prompt_version": "prompt-v1",
                "authority": "unapproved",
                "pages": [{
                    "scan_page": 4,
                    "printed_page": 3,
                    "english": "Translation",
                    "state": "draft",
                    "flags": ["review"],
                }],
            }), encoding="utf-8")
            report = MODULE.apply_drafts(
                units,
                drafts,
                model="model",
                generated_at_utc="2026-08-04T00:00:00Z",
            )
            record = json.loads(units.read_text(encoding="utf-8"))
            self.assertEqual(report["applied"], 1)
            self.assertEqual(record["target"]["text"], "Translation")
            self.assertEqual(record["target"]["flags"], ["review"])
            self.assertEqual(record["translation"]["prompt_version"], "prompt-v1")

    def test_rejects_draft_without_unit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            units = root / "units.jsonl"
            drafts = root / "drafts.json"
            units.write_text(json.dumps({"source": {"scan_page": 1}}) + "\n", encoding="utf-8")
            drafts.write_text(json.dumps({
                "prompt_version": "v1",
                "authority": "draft",
                "pages": [{"scan_page": 2, "english": "Missing"}],
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "no translation units"):
                MODULE.apply_drafts(
                    units,
                    drafts,
                    model="model",
                    generated_at_utc="2026-08-04T00:00:00Z",
                )


if __name__ == "__main__":
    unittest.main()

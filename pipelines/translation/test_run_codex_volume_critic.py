from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("run_codex_volume_critic.py")
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("run_codex_volume_critic", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class CodexVolumeCriticTests(unittest.TestCase):
    def test_translation_provenance_rejects_stale_source(self) -> None:
        source = {
            "work_id": "work",
            "volume": 8,
            "scan_page": 4,
            "arabic_text_sha256": "current-source",
        }
        translation = {
            "work_id": "work",
            "volume": 8,
            "scan_page": 4,
            "source_sha256": "old-source",
        }
        current, reason = MODULE.validate_translation_provenance(source, translation)
        self.assertFalse(current)
        self.assertIn("source_sha256 mismatch", reason)

    def test_critique_provenance_rejects_stale_translation(self) -> None:
        source = {
            "work_id": "work",
            "volume": 8,
            "scan_page": 4,
            "arabic_text_sha256": "source",
        }
        translation = {
            "work_id": "work",
            "volume": 8,
            "scan_page": 4,
            "source_sha256": "source",
            "english_text": "current",
        }
        critique = {
            "work_id": "work",
            "volume": 8,
            "scan_page": 4,
            "source_sha256": "source",
            "translation_sha256": "old-translation",
        }
        current, reason = MODULE.validate_critique_provenance(
            source, translation, critique
        )
        self.assertFalse(current)
        self.assertIn("translation_sha256 mismatch", reason)

    def test_prompt_enforces_search_friendly_name_policy(self) -> None:
        source = {"scan_page": 4, "arabic_text": "آمنة"}
        translation = {"english_text": "Amna"}
        prompt = MODULE.build_prompt(source, translation, None, None)
        self.assertIn("Amina (not Amna)", prompt)
        self.assertIn("Usd al-Ghaba", prompt)

    def test_prompt_is_independent_fidelity_audit(self) -> None:
        source = {"scan_page": 4, "arabic_text": "ARABIC"}
        translation = {"english_text": "ENGLISH"}
        prompt = MODULE.build_prompt(source, translation, None, None)
        self.assertIn("independent fidelity critic", prompt)
        self.assertIn("CURRENT ARABIC:\nARABIC", prompt)
        self.assertIn("CURRENT ENGLISH TO AUDIT:\nENGLISH", prompt)
        self.assertIn("Do not reward fluent English", prompt)

    def test_record_hash_is_key_order_independent(self) -> None:
        self.assertEqual(MODULE.record_sha256({"a": 1, "b": 2}), MODULE.record_sha256({"b": 2, "a": 1}))

    def test_pass_cannot_contain_issues(self) -> None:
        expected = {"scan_page": 4, "prompt_sha256": "prompt"}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "0004.json"
            path.write_text(json.dumps({
                **expected,
                "verdict": "pass",
                "issues": [{"category": "omission"}],
            }), encoding="utf-8")
            valid, reason = MODULE.validate_existing_page(path, expected)
            self.assertFalse(valid)
            self.assertEqual(reason, "pass verdict contains issues")

    def test_revision_requires_issue(self) -> None:
        expected = {"scan_page": 4, "prompt_sha256": "prompt"}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "0004.json"
            path.write_text(json.dumps({**expected, "verdict": "revise", "issues": []}), encoding="utf-8")
            valid, reason = MODULE.validate_existing_page(path, expected)
            self.assertFalse(valid)
            self.assertEqual(reason, "revise verdict contains no issues")

    def test_witness_required_needs_actionable_witness_concern(self) -> None:
        expected = {"scan_page": 4, "prompt_sha256": "prompt"}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "0004.json"
            path.write_text(json.dumps({
                **expected,
                "verdict": "witness_required",
                "issues": [{"witness_check_recommended": False}],
            }), encoding="utf-8")
            valid, reason = MODULE.validate_existing_page(path, expected)
            self.assertFalse(valid)
            self.assertEqual(reason, "witness_required verdict contains no actionable witness concern")

    def test_pass_requires_all_checks(self) -> None:
        expected = {"scan_page": 4, "prompt_sha256": "prompt"}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "0004.json"
            path.write_text(json.dumps({
                **expected, "verdict": "pass", "issues": [],
                "checks": {"all_arabic_accounted_for": False},
            }), encoding="utf-8")
            valid, reason = MODULE.validate_existing_page(path, expected)
            self.assertFalse(valid)
            self.assertEqual(reason, "pass verdict contains a failed check")


if __name__ == "__main__":
    unittest.main()

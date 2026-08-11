from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("run_codex_volume_adjudication.py")
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("run_codex_volume_adjudication", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class CodexVolumeAdjudicationTests(unittest.TestCase):
    def test_prompt_requires_final_names_to_follow_shared_policy(self) -> None:
        source = {"scan_page": 4, "arabic_text": "آمنة"}
        translation = {"english_text": "Amna"}
        critique = {"verdict": "revise", "issues": []}
        prompt = MODULE.build_prompt(source, translation, critique, None, None, None)
        self.assertIn("Amina (not Amna)", prompt)
        self.assertIn("names array that follows the policy", prompt)
        self.assertIn("stable searchable identity label", prompt)
        self.assertIn("do not include commas, parentheses", prompt)

    def test_name_policy_selects_descriptive_or_non_ascii_labels(self) -> None:
        violations = MODULE.name_mapping_policy_violations([
            {"english": "Amina bint Harmala (also called Atika)"},
            {"english": "Ḥakim"},
            {"english": "Amina bint al-Hakam al-Ghifariyya"},
            {"english": "Qutla or Qutayla", "kind": "person"},
        ])
        self.assertEqual(len(violations), 3)

    def test_name_policy_allows_colon_only_in_stable_work_titles(self) -> None:
        violations = MODULE.name_mapping_policy_violations([
            {"english": "al-Tajrid: Asma al-Sahaba", "kind": "work"},
            {"english": "Amina: also called Atika", "kind": "person"},
        ])
        self.assertEqual(
            [item["english"] for item in violations],
            ["Amina: also called Atika"],
        )

    def test_name_apostrophe_marks_are_normalized_without_adjudication(self) -> None:
        names, changes = MODULE.normalize_name_mappings([
            {"arabic": "name", "english": "Saʿd ibn Riʾab", "kind": "person"},
        ])
        self.assertEqual(names[0]["english"], "Sa'd ibn Ri'ab")
        self.assertEqual(len(changes), 1)

    def test_transliteration_policy_selects_scholarly_marks(self) -> None:
        self.assertEqual(
            MODULE.transliteration_policy_violations("Sa\u02bfd ibn \u1e24akim"),
            ["\u02bf", "\u1e24"],
        )
        clean = {
            "fidelity": {"all_source_content_translated": True},
            "uncertainties": [],
            "names": [],
            "english_text": "Sa\u02bfd ibn Hakim",
        }
        self.assertTrue(
            MODULE.requires_adjudication(
                clean, {"verdict": "pass", "issues": []}
            )
        )

    def test_deterministic_precheck_surfaces_structural_omissions(self) -> None:
        issues = MODULE.deterministic_translation_issues(
            {"arabic_text": "10759- Name\n(1) report 99"},
            {"english_text": "Name", "entry_numbers": [], "names": []},
        )
        self.assertEqual(
            {item["code"] for item in issues},
            {
                "entry_number_mismatch",
                "missing_footnote_labels",
                "missing_material_numeric_tokens",
            },
        )

    def test_selects_disputed_or_uncertain_pages(self) -> None:
        clean = {
            "fidelity": {"all_source_content_translated": True},
            "uncertainties": [],
            "names": [],
        }
        self.assertFalse(MODULE.requires_adjudication(clean, {"verdict": "pass", "issues": []}))
        self.assertTrue(MODULE.requires_adjudication(clean, {"verdict": "revise", "issues": [{}]}))
        self.assertTrue(MODULE.requires_adjudication({**clean, "uncertainties": [{}]}, {"verdict": "pass", "issues": []}))
        self.assertTrue(MODULE.requires_adjudication({"fidelity": {"all_source_content_translated": False}, "names": []}, {"verdict": "pass", "issues": []}))
        self.assertTrue(
            MODULE.should_adjudicate_page(
                clean,
                {"verdict": "pass", "issues": []},
                all_pages=True,
            )
        )

    def test_revised_decision_requires_changes(self) -> None:
        expected = {"scan_page": 4, "prompt_sha256": "prompt"}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "0004.json"
            path.write_text(json.dumps({
                **expected, "decision": "revised", "changes": [],
                "unresolved": [], "final_english_text": "text",
            }), encoding="utf-8")
            valid, reason = MODULE.validate_existing_page(path, expected)
            self.assertFalse(valid)
            self.assertEqual(reason, "revised decision contains no changes")

    def test_decision_normalization_preserves_explicit_uncertainty(self) -> None:
        record = {
            "decision": "revised",
            "changes": [{"category": "name"}],
            "unresolved": [{"category": "name_vocalization"}],
        }
        self.assertEqual(MODULE.normalize_decision_state(record), "revised")
        self.assertEqual(record["decision"], "unresolved")
        self.assertEqual(record["decision_normalized_from"], "revised")
        self.assertEqual(record["unresolved"], [{"category": "name_vocalization"}])

    def test_prompt_requires_complete_final_page(self) -> None:
        prompt = MODULE.build_prompt(
            {"scan_page": 4, "arabic_text": "ARABIC"},
            {"english_text": "ENGLISH"},
            {"verdict": "revise"}, None, None, None,
        )
        self.assertIn("Return a complete final_english_text", prompt)
        self.assertIn("Arabic is authoritative", prompt)

    def test_prompt_explains_how_to_weigh_supplemental_evidence(self) -> None:
        witness = {
            "supplemental_witness_evidence": [{
                "evidence_id": "parallel-1",
                "kind": "parallel_transmission",
            }],
        }
        prompt = MODULE.build_prompt(
            {"scan_page": 12, "arabic_text": "ARABIC"},
            {"english_text": "ENGLISH"},
            {"verdict": "witness_required"}, witness, None, None,
        )
        self.assertIn("SUPPLEMENTAL EVIDENCE RULE", prompt)
        self.assertIn("never silently substitute", prompt)
        expected = MODULE.expected_provenance(
            prompt=prompt,
            source={
                "scan_page": 12, "work_id": "work", "volume": 8,
                "arabic_text_sha256": "source",
            },
            translation={}, critique={}, witness=witness,
            model="model", reasoning_effort="xhigh", schema_sha256="schema",
        )
        self.assertEqual(expected["prompt_version"], MODULE.SUPPLEMENTAL_PROMPT_VERSION)

    def test_non_unresolved_decision_requires_all_fidelity_checks(self) -> None:
        expected = {"scan_page": 4, "prompt_sha256": "prompt"}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "0004.json"
            path.write_text(json.dumps({
                **expected, "decision": "accept", "changes": [],
                "unresolved": [], "final_english_text": "text",
                "fidelity": {"all_source_content_translated": False},
            }), encoding="utf-8")
            valid, reason = MODULE.validate_existing_page(path, expected)
            self.assertFalse(valid)
            self.assertEqual(reason, "accept decision contains a failed fidelity check")

    def test_existing_page_must_match_checkpointed_result_hash(self) -> None:
        expected = {"scan_page": 4, "prompt_sha256": "prompt"}
        valid_record = {
            **expected,
            "decision": "accept",
            "changes": [],
            "unresolved": [],
            "final_english_text": "original",
            "fidelity": {"all_source_content_translated": True},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "0004.json"
            path.write_text(json.dumps(valid_record), encoding="utf-8")
            checkpoint_sha = MODULE.sha256_file(path)
            self.assertEqual(
                MODULE.validate_existing_page(path, expected, checkpoint_sha),
                (True, "current"),
            )

            path.write_text(
                json.dumps({**valid_record, "final_english_text": "edited"}),
                encoding="utf-8",
            )
            valid, reason = MODULE.validate_existing_page(
                path, expected, checkpoint_sha
            )
            self.assertFalse(valid)
            self.assertEqual(
                reason, "result_sha256 mismatch with checkpoint state"
            )


if __name__ == "__main__":
    unittest.main()

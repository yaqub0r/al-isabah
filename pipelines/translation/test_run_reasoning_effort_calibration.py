from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("run_reasoning_effort_calibration.py")
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("run_reasoning_effort_calibration", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


def candidate(scan: int, effort: str) -> dict:
    record = {
        "scan_page": scan,
        "reasoning_effort": effort,
        "overall_status": "resolved",
        "summary": effort,
        "findings": [{"concern_id": "c1"}],
        "remaining_unresolved": [],
    }
    for field in MODULE.PAIR_FIELDS:
        if field == "model":
            record[field] = "model"
        elif field == "concern_ids":
            record[field] = ["c1"]
        elif field in {"urdu_witness_candidates", "secondary_witness_evidence", "supplemental_witness_evidence"}:
            record[field] = []
        else:
            record[field] = field
    return record


def judgment(scan: int, high_label: str, winner: str, *, material: bool = False) -> dict:
    score = {
        "canonical_fidelity": 5,
        "concern_coverage": 5,
        "evidence_use": 5,
        "uncertainty_calibration": 5,
        "editorial_usefulness": 5,
        "material_errors": [],
    }
    return {
        "scan_page": scan,
        "high_candidate_label": high_label,
        "preferred_candidate": winner,
        "material_quality_difference": material,
        "confidence": "high",
        "candidate_a": dict(score),
        "candidate_b": dict(score),
    }


class ReasoningEffortCalibrationTests(unittest.TestCase):
    def test_pair_rejects_non_effort_input_difference(self) -> None:
        high = candidate(11, "high")
        xhigh = candidate(11, "xhigh")
        xhigh["prompt_sha256"] = "different"
        valid, reason = MODULE.validate_pair(high, xhigh)
        self.assertFalse(valid)
        self.assertEqual(reason, "prompt_sha256 mismatch")

    def test_balanced_labels_are_deterministic(self) -> None:
        scans = [11, 12, 75, 102, 110, 115, 119, 124, 263, 313, 336, 337]
        first = MODULE.balanced_high_labels(scans)
        second = MODULE.balanced_high_labels(list(reversed(scans)))
        self.assertEqual(first, second)
        self.assertEqual(list(first.values()).count("A"), 6)
        self.assertEqual(list(first.values()).count("B"), 6)

    def test_public_candidate_hides_effort(self) -> None:
        public = MODULE.public_candidate(candidate(11, "high"))
        self.assertNotIn("reasoning_effort", public)
        self.assertNotIn("model", public)
        self.assertEqual(public["overall_status"], "resolved")

    def test_prompt_does_not_reveal_candidate_effort(self) -> None:
        prompt = MODULE.build_prompt(
            source={"scan_page": 11, "arabic_text": "ARABIC"},
            translation={"english_text": "ENGLISH"},
            critique={"verdict": "revise", "summary": "audit", "issues": []},
            evidence_record={"concern_ids": ["c1"]},
            candidate_a=MODULE.public_candidate(candidate(11, "high")),
            candidate_b=MODULE.public_candidate(candidate(11, "xhigh")),
        )
        self.assertNotIn('"reasoning_effort"', prompt)
        self.assertIn("settings are intentionally hidden", prompt)

    def test_summary_recommends_xhigh_for_material_xhigh_win(self) -> None:
        record = judgment(11, "A", "B", material=True)
        summary = MODULE.build_summary([record])
        self.assertEqual(summary["material_wins"]["xhigh"], 1)
        self.assertEqual(summary["recommendation"], "xhigh")

    def test_existing_result_requires_all_concerns(self) -> None:
        expected = {"scan_page": 11, "prompt_sha256": "prompt"}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "0011.json"
            path.write_text(json.dumps({
                **expected,
                "concern_assessments": [{"concern_id": "c1"}],
            }), encoding="utf-8")
            valid, reason = MODULE.validate_existing_page(path, expected, ["c1", "c2"])
            self.assertFalse(valid)
            self.assertEqual(reason, "concern assessment coverage mismatch")


if __name__ == "__main__":
    unittest.main()

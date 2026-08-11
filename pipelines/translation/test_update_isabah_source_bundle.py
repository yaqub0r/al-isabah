from __future__ import annotations

import importlib.util
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).with_name("update_isabah_source_bundle.py")
SPEC = importlib.util.spec_from_file_location("update_isabah_source_bundle", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class UpdateIsabahSourceBundleTests(unittest.TestCase):
    def test_finds_artifact_by_stable_id(self) -> None:
        bundle = {"artifacts": [{"artifact_id": "one"}, {"artifact_id": "two", "state": "draft"}]}
        self.assertEqual(MODULE.artifact(bundle, "two")["state"], "draft")

    def test_main_publishes_complete_schema_valid_artifact_states(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle_path = root / "bundle.json"
            alignment_path = root / "alignment.json"
            aligned_path = root / "aligned.jsonl"
            readiness_path = root / "readiness.json"
            units_path = root / "units.jsonl"
            presentation_path = root / "review.html"
            names_path = root / "names.json"
            supplemental_path = root / "supplemental.jsonl"
            bundle_path.write_text(json.dumps({
                "work_id": "ibn_hajar_isabah_v1",
                "artifacts": [
                    {"artifact_id": "isabah-volume-08-structured-english", "state": "draft"},
                    {"artifact_id": "isabah-volume-08-english-review-presentation", "state": "draft"},
                ],
                "workflow": {},
                "quality": {"source_text": {}},
                "next_actions": [],
            }), encoding="utf-8")
            aligned_path.write_text(
                "".join(json.dumps({"scan_page": scan}) + "\n" for scan in range(4, 495)),
                encoding="utf-8",
            )
            aligned_sha = MODULE.sha256(aligned_path)
            entry_audit = {
                "pass": True,
                "expected_first": 10759,
                "expected_last": 12308,
                "observed_count": 1550,
            }
            alignment_path.write_text(json.dumps({
                "pass": True, "page_count": 491, "canonical_usul_pages": 490,
                "canonical_facsimile_transcription_pages": [4],
                "canonical_facsimile_correction_pages": [6],
                "heading_mismatches": [],
                "entry_sequence_audit": entry_audit,
                "output_sha256": aligned_sha,
            }), encoding="utf-8")
            unit = {"target": {"text": "English text", "names": [], "unresolved": []}, "quality": {"critic_issue_count": 0}}
            units_path.write_text((json.dumps(unit) + "\n") * 491, encoding="utf-8")
            readiness_path.write_text(json.dumps({
                "ready_for_human_review": True,
                "output_sha256": MODULE.sha256(units_path),
                "adjudication_required_pages": [], "witness_required_pages": [],
                "entry_sequence_audit": entry_audit,
                "inputs": {"aligned_source_sha256": aligned_sha},
            }), encoding="utf-8")
            presentation_path.write_text(
                MODULE.presentation_source_marker(MODULE.sha256(units_path)) + "\nreview",
                encoding="utf-8",
            )
            names_path.write_text(json.dumps({
                "schema": "firstlight.name-review.v1", "work_id": "ibn_hajar_isabah_v1",
                "source": {"sha256": MODULE.sha256(units_path)}, "candidates": [], "mentions": [],
            }), encoding="utf-8")
            excerpt = "parallel Arabic evidence"
            supplemental_path.write_text(json.dumps({
                "schema": "firstlight.supplemental-witness-evidence.v1",
                "scan_page": 12,
                "evidence_id": "parallel-1",
                "kind": "parallel_transmission",
                "concern_ids": ["translation-1"],
                "excerpt": excerpt,
                "excerpt_sha256": hashlib.sha256(excerpt.encode("utf-8")).hexdigest(),
            }) + "\n", encoding="utf-8")
            argv = [
                "update_isabah_source_bundle.py",
                "--bundle", str(bundle_path), "--alignment-report", str(alignment_path),
                "--aligned-source", str(aligned_path), "--readiness", str(readiness_path),
                "--readiness-label", "published/readiness.json",
                "--structured-english", str(units_path), "--presentation", str(presentation_path),
                "--name-review", str(names_path),
                "--supplemental-witness-evidence", str(supplemental_path),
            ]
            with mock.patch.object(sys, "argv", argv):
                self.assertEqual(MODULE.main(), 0)
            published = json.loads(bundle_path.read_text(encoding="utf-8"))
            by_id = {item["artifact_id"]: item for item in published["artifacts"]}
            self.assertEqual(by_id["isabah-volume-08-structured-english"]["state"], "verified_local")
            self.assertEqual(by_id["isabah-volume-08-english-review-presentation"]["state"], "verified_local")
            self.assertEqual(by_id["isabah-volume-08-name-review"]["role"], "quality_evidence")
            self.assertEqual(by_id["isabah-usul-usd-al-ghaba-collateral"]["edition_relationship"], "different_work")
            self.assertEqual(by_id["isabah-usul-istiab-collateral"]["role"], "textual_witness")
            self.assertEqual(
                by_id["isabah-usul-dar-hajr-alternative-edition"]["edition_relationship"],
                "different_edition",
            )
            self.assertEqual(
                by_id["isabah-usul-dar-jil-alternative-edition"]["provider_ids"]["version_id"],
                "xAOjIqxYuv",
            )
            self.assertEqual(
                by_id["isabah-volume-08-supplemental-witness-evidence"]["verification"]["evidence_count"],
                1,
            )
            self.assertEqual(
                by_id["isabah-volume-08-supplemental-witness-evidence"]["language"],
                "mul",
            )
            self.assertEqual(
                by_id["isabah-volume-08-supplemental-witness-evidence"]["verification"]["scan_pages"],
                [12],
            )
            self.assertIn(
                "isabah-usul-usd-al-ghaba-collateral",
                by_id["isabah-volume-08-structured-english"]["derived_from"],
            )
            self.assertIn(
                "isabah-usul-dar-hajr-alternative-edition",
                by_id["isabah-volume-08-structured-english"]["derived_from"],
            )
            self.assertEqual(published["workflow"]["english_draft"]["state"], "complete")
            self.assertEqual(published["workflow"]["english_presentation"]["state"], "complete")
            self.assertIn(
                "full xhigh adjudication",
                by_id["isabah-volume-08-structured-english"]["notes"],
            )
            self.assertEqual(
                by_id["isabah-volume-08-structured-english"]["verification"]["machine_readiness_report"],
                "published/readiness.json",
            )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("publish_isabah_readiness.py")
SPEC = importlib.util.spec_from_file_location("publish_isabah_readiness", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class PublishReadinessTests(unittest.TestCase):
    @staticmethod
    def validated_units() -> list[dict]:
        return [
            {
                "schema": "firstlight.reviewable-translation-unit.v1",
                "source": {"scan_page": scan},
                "unit_id": f"unit-{scan}",
                "target": {
                    "names": [],
                    "unresolved": [],
                    "state": "machine_validated_unreviewed",
                },
                "review": {"state": "unreviewed"},
                "translation": {
                    "method": "codex_blind_translation_with_independent_critique_multilingual_witness_and_full_adjudication",
                    "blind_model": "gpt-5.6-sol",
                    "blind_reasoning_effort": "high",
                    "critic_model": "gpt-5.6-sol",
                    "critic_reasoning_effort": "high",
                    "adjudication_model": "gpt-5.6-sol",
                    "adjudication_reasoning_effort": "xhigh",
                },
            }
            for scan in range(4, 495)
        ]

    def test_validates_every_published_artifact_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            units = root / "units.jsonl"
            units.write_text(
                "".join(json.dumps(unit) + "\n" for unit in self.validated_units()),
                encoding="utf-8",
            )
            units_sha = MODULE.sha256(units)
            aligned = root / "aligned.jsonl"
            aligned.write_text("{}\n", encoding="utf-8")
            aligned_sha = MODULE.sha256(aligned)
            entry_audit = {
                "pass": True,
                "expected_first": 10759,
                "expected_last": 12308,
                "observed_count": 1550,
            }
            candidate = root / "candidate.json"
            candidate.write_text(json.dumps({
                "schema": "firstlight.translation-machine-readiness.v1",
                "work_id": "work", "ready_for_human_review": True,
                "errors": [], "expected_pages": 491, "output_sha256": units_sha,
                "adjudication_required_pages": list(range(4, 495)),
                "unresolved_item_count": 0,
                "unresolved_passages": [],
                "entry_sequence_audit": entry_audit,
                "inputs": {"aligned_source_sha256": aligned_sha},
                "witness_required_pages": [4],
                "witness_evidence": {
                    "retrieval_incomplete": 0,
                    "supplemental_records": 0,
                    "supplemental_scans": [],
                    "works": [
                        "ibn_al_athir_usd_al_ghaba_v1", "ibn_abd_al_barr_istiab_v1",
                        "ibn_hajar_isabah_dar_hajr_v1", "ibn_hajar_isabah_dar_jil_v1",
                    ],
                },
            }), encoding="utf-8")
            presentation = root / "review.html"
            presentation.write_text(
                MODULE.presentation_source_marker(units_sha) + '<article class="page">' * 491,
                encoding="utf-8",
            )
            names = root / "names.json"
            names.write_text(json.dumps({
                "schema": "firstlight.name-review.v1", "work_id": "work",
                "source": {"sha256": units_sha},
                "extraction": {"candidate_count": 0, "mention_count": 0},
                "candidates": [], "mentions": [],
            }), encoding="utf-8")
            index = root / "index.json"
            index.write_text(json.dumps({"works": {"work": "/names.json"}}), encoding="utf-8")
            bundle = root / "bundle.json"
            bundle.write_text(json.dumps({"artifacts": [
                {"artifact_id": "isabah-volume-08-structured-english", "sha256": units_sha},
                {"artifact_id": "isabah-volume-08-english-review-presentation", "sha256": MODULE.sha256(presentation)},
                {"artifact_id": "isabah-volume-08-name-review", "sha256": MODULE.sha256(names)},
                {
                    "artifact_id": "isabah-volume-08-aligned-arabic",
                    "sha256": aligned_sha,
                    "verification": {"entry_sequence_audit": entry_audit},
                },
                {
                    "artifact_id": "isabah-usul-usd-al-ghaba-collateral",
                    "role": "textual_witness", "edition_relationship": "different_work",
                    "state": "verified_remote",
                },
                {
                    "artifact_id": "isabah-usul-istiab-collateral",
                    "role": "textual_witness", "edition_relationship": "different_work",
                    "state": "verified_remote",
                },
                {
                    "artifact_id": "isabah-usul-dar-hajr-alternative-edition",
                    "role": "textual_witness", "edition_relationship": "different_edition",
                    "state": "verified_remote",
                },
                {
                    "artifact_id": "isabah-usul-dar-jil-alternative-edition",
                    "role": "textual_witness", "edition_relationship": "different_edition",
                    "state": "verified_remote",
                },
                {
                    "artifact_id": "isabah-volume-08-supplemental-witness-evidence",
                    "role": "quality_evidence", "language": "mul",
                    "state": "verified_local",
                    "verification": {"evidence_count": 0, "scan_pages": []},
                },
            ]}), encoding="utf-8")
            published = MODULE.validate(
                candidate_path=candidate, units_path=units, presentation_path=presentation,
                name_review_path=names, name_index_path=index, bundle_path=bundle,
                aligned_source_path=aligned,
            )
            self.assertTrue(published["ready_for_human_review"])
            self.assertTrue(published["pipeline_complete"])
            self.assertEqual(published["pipeline_artifacts"]["structured_english_sha256"], units_sha)
            self.assertEqual(published["pipeline_artifacts"]["collateral_witnesses"], 2)
            self.assertEqual(published["pipeline_artifacts"]["alternative_editions"], 2)
            self.assertEqual(published["pipeline_artifacts"]["textual_witnesses"], 4)
            self.assertEqual(published["pipeline_artifacts"]["supplemental_witness_records"], 0)

            bundle_payload = json.loads(bundle.read_text(encoding="utf-8"))
            next(
                item for item in bundle_payload["artifacts"]
                if item["artifact_id"] == "isabah-volume-08-supplemental-witness-evidence"
            )["verification"]["evidence_count"] = 1
            bundle.write_text(json.dumps(bundle_payload), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "supplemental witness evidence"):
                MODULE.validate(
                    candidate_path=candidate, units_path=units, presentation_path=presentation,
                    name_review_path=names, name_index_path=index, bundle_path=bundle,
                    aligned_source_path=aligned,
                )
            next(
                item for item in bundle_payload["artifacts"]
                if item["artifact_id"] == "isabah-volume-08-supplemental-witness-evidence"
            )["verification"]["evidence_count"] = 0
            bundle.write_text(json.dumps(bundle_payload), encoding="utf-8")

            valid_units = self.validated_units()
            valid_units[0]["translation"]["adjudication_reasoning_effort"] = "high"
            units.write_text(
                "".join(json.dumps(unit) + "\n" for unit in valid_units),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "invalid Codex model lineage"):
                MODULE.validate(
                    candidate_path=candidate, units_path=units, presentation_path=presentation,
                    name_review_path=names, name_index_path=index, bundle_path=bundle,
                    aligned_source_path=aligned,
                )
            units.write_text(
                "".join(json.dumps(unit) + "\n" for unit in self.validated_units()),
                encoding="utf-8",
            )

            candidate_payload = json.loads(candidate.read_text(encoding="utf-8"))
            candidate_payload["witness_evidence"]["retrieval_incomplete"] = 1
            candidate.write_text(json.dumps(candidate_payload), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "incomplete collateral"):
                MODULE.validate(
                    candidate_path=candidate, units_path=units, presentation_path=presentation,
                    name_review_path=names, name_index_path=index, bundle_path=bundle,
                    aligned_source_path=aligned,
                )
            candidate_payload["witness_evidence"]["retrieval_incomplete"] = 0
            candidate.write_text(json.dumps(candidate_payload), encoding="utf-8")

            presentation.write_text('<article class="page">' * 491, encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "stale relative to validated English"):
                MODULE.validate(
                    candidate_path=candidate, units_path=units, presentation_path=presentation,
                    name_review_path=names, name_index_path=index, bundle_path=bundle,
                    aligned_source_path=aligned,
                )

            presentation.write_text(
                MODULE.presentation_source_marker(units_sha) + '<article class="page">' * 491,
                encoding="utf-8",
            )
            names.write_text(json.dumps({
                "schema": "firstlight.name-review.v1", "work_id": "work",
                "source": {"sha256": units_sha},
                "extraction": {"candidate_count": 1, "mention_count": 0},
                "candidates": [{
                    "candidate_id": "candidate-1", "normalized_form": "asiyah",
                    "mention_ids": ["missing-mention"],
                }],
                "mentions": [],
            }), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "dangling mention"):
                MODULE.validate(
                    candidate_path=candidate, units_path=units, presentation_path=presentation,
                    name_review_path=names, name_index_path=index, bundle_path=bundle,
                    aligned_source_path=aligned,
                )

    def test_rejects_incomplete_presentation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            units = root / "units.jsonl"
            units.write_text(
                "".join(json.dumps(unit) + "\n" for unit in self.validated_units()),
                encoding="utf-8",
            )
            candidate = root / "candidate.json"
            candidate.write_text(json.dumps({
                "schema": "firstlight.translation-machine-readiness.v1",
                "work_id": "work", "ready_for_human_review": True,
                "errors": [], "expected_pages": 491, "output_sha256": MODULE.sha256(units),
                "adjudication_required_pages": list(range(4, 495)),
                "witness_evidence": {"retrieval_incomplete": 0},
                "unresolved_item_count": 0,
                "unresolved_passages": [],
                "entry_sequence_audit": {
                    "pass": True,
                    "expected_first": 10759,
                    "expected_last": 12308,
                    "observed_count": 1550,
                },
            }), encoding="utf-8")
            presentation = root / "review.html"
            presentation.write_text('<article class="page">', encoding="utf-8")
            names = root / "names.json"
            names.write_text(json.dumps({
                "schema": "firstlight.name-review.v1", "work_id": "work",
                "source": {"sha256": MODULE.sha256(units)},
                "extraction": {"candidate_count": 0, "mention_count": 0},
                "candidates": [], "mentions": [],
            }), encoding="utf-8")
            index = root / "index.json"
            index.write_text(json.dumps({"works": {"work": "/names.json"}}), encoding="utf-8")
            bundle = root / "bundle.json"
            bundle.write_text(json.dumps({"artifacts": []}), encoding="utf-8")
            aligned = root / "aligned.jsonl"
            aligned.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "491 page articles"):
                MODULE.validate(
                    candidate_path=candidate, units_path=units, presentation_path=presentation,
                    name_review_path=names, name_index_path=index, bundle_path=bundle,
                    aligned_source_path=aligned,
                )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).with_name("run_codex_witness_resolution.py")
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("run_codex_witness_resolution", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class CodexWitnessResolutionTests(unittest.TestCase):
    def test_page_proof_scopes_global_supplemental_evidence(self) -> None:
        evidence = {12: [{"evidence_id": "scan-12"}], 105: [{"evidence_id": "scan-105"}]}
        self.assertEqual(
            MODULE.scope_supplemental_evidence(evidence, [105]),
            {105: [{"evidence_id": "scan-105"}]},
        )
        self.assertIs(MODULE.scope_supplemental_evidence(evidence, []), evidence)

    def test_resolves_broken_runtime_override_to_bundled_poppler(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            dependencies = Path(directory) / "dependencies"
            configured = dependencies / "bin" / "override" / "pdftoppm.cmd"
            executable = (
                dependencies / "native" / "poppler" / "Library" / "bin" / "pdftoppm.exe"
            )
            configured.parent.mkdir(parents=True)
            executable.parent.mkdir(parents=True)
            configured.write_text("broken shim", encoding="utf-8")
            executable.write_bytes(b"executable")

            self.assertEqual(
                MODULE.resolve_pdftoppm_executable(configured),
                executable.resolve(),
            )

    def test_preserves_unknown_pdftoppm_wrapper(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            configured = Path(directory) / "custom" / "pdftoppm.cmd"
            configured.parent.mkdir(parents=True)
            configured.write_text("custom shim", encoding="utf-8")

            self.assertEqual(
                MODULE.resolve_pdftoppm_executable(configured),
                configured.resolve(),
            )

    def test_final_evidence_rejects_unavailable_and_error_states(self) -> None:
        evidence = [
            {"retrieval_state": "hit"},
            {"retrieval_state": "no_match"},
            {"retrieval_state": "unavailable", "error": "HTTP 500"},
            {"retrieval_state": "error", "error": "cache_miss"},
        ]
        self.assertEqual(
            MODULE.incomplete_secondary_evidence(evidence),
            evidence[2:],
        )

    def test_prompt_distinguishes_unavailable_query_from_no_match(self) -> None:
        blocks = MODULE.secondary_evidence_blocks([{
            "title": "al-Isti'ab",
            "author": "Ibn Abd al-Barr",
            "query": "Kharqa",
            "retrieval_state": "unavailable",
            "source_and_version": "turath:test",
            "error": "HTTP 500",
        }])
        self.assertIn("Query unavailable after bounded retries", blocks)
        self.assertIn("not evidence that the work lacks a matching passage", blocks)

    def test_cached_health_requires_recent_complete_live_checks(self) -> None:
        now = datetime(2026, 8, 6, 7, 0, tzinfo=timezone.utc)
        health = {
            "schema": "firstlight.usul-secondary-source-health.v1",
            "pass": True,
            "live_queries": True,
            "checked_at": (now - timedelta(hours=2)).isoformat().replace("+00:00", "Z"),
            "checks": [
                {"work_id": item["work_id"], "retrieval_state": "hit"}
                for item in MODULE.WITNESS_SOURCES
            ],
        }
        self.assertEqual(
            MODULE.validate_cached_secondary_health(
                health, max_age_hours=24, current_time=now
            ),
            (True, "current"),
        )
        health["checked_at"] = (now - timedelta(hours=25)).isoformat().replace("+00:00", "Z")
        self.assertEqual(
            MODULE.validate_cached_secondary_health(
                health, max_age_hours=24, current_time=now
            ),
            (False, "live health check is stale"),
        )

    def test_witness_entry_numbers_come_from_canonical_arabic(self) -> None:
        self.assertEqual(
            MODULE.canonical_entry_numbers({
                "arabic_text": "10759- Asiya\n1077: report citation",
            }),
            [10759],
        )

    def test_witness_provenance_rejects_stale_critique(self) -> None:
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
            "english_text": "English",
            "uncertainties": [],
        }
        critique = {
            "work_id": "work",
            "volume": 8,
            "scan_page": 4,
            "source_sha256": "source",
            "translation_sha256": MODULE.record_sha256(translation),
            "issues": [],
        }
        witness = {
            "work_id": "work",
            "volume": 8,
            "scan_page": 4,
            "source_sha256": "source",
            "translation_sha256": MODULE.record_sha256(translation),
            "critique_sha256": "old-critique",
            "candidate_evidence_sha256": MODULE.candidate_evidence_sha256([]),
            "secondary_evidence_sha256": MODULE.evidence_sha256([]),
            "concern_ids": [],
            "findings": [],
            "remaining_unresolved": [],
            "overall_status": "resolved",
            "urdu_witness_candidates": [],
            "secondary_witness_evidence": [],
        }
        current, reason = MODULE.validate_witness_provenance(
            source, translation, critique, witness
        )
        self.assertFalse(current)
        self.assertIn("critique_sha256 mismatch", reason)

    def test_witness_provenance_rejects_tampered_supplemental_evidence(self) -> None:
        source = {
            "work_id": "work", "volume": 8, "scan_page": 4,
            "arabic_text_sha256": "source",
        }
        translation = {
            "work_id": "work", "volume": 8, "scan_page": 4,
            "source_sha256": "source", "english_text": "English",
            "uncertainties": [{"witness_check_recommended": True}],
        }
        critique = {
            "work_id": "work", "volume": 8, "scan_page": 4,
            "source_sha256": "source",
            "translation_sha256": MODULE.record_sha256(translation),
            "issues": [],
        }
        original = [{"evidence_id": "parallel-1", "excerpt": "original"}]
        witness = {
            "work_id": "work", "volume": 8, "scan_page": 4,
            "source_sha256": "source",
            "translation_sha256": MODULE.record_sha256(translation),
            "critique_sha256": MODULE.record_sha256(critique),
            "candidate_evidence_sha256": MODULE.candidate_evidence_sha256([]),
            "secondary_evidence_sha256": MODULE.evidence_sha256([]),
            "supplemental_evidence_sha256": MODULE.evidence_sha256(original),
            "concern_ids": ["translation-1"],
            "findings": [{"concern_id": "translation-1", "conclusion": "supports_current"}],
            "remaining_unresolved": [],
            "overall_status": "resolved",
            "urdu_witness_candidates": [],
            "secondary_witness_evidence": [],
            "supplemental_witness_evidence": [
                {"evidence_id": "parallel-1", "excerpt": "edited"}
            ],
        }
        current, reason = MODULE.validate_witness_provenance(
            source, translation, critique, witness
        )
        self.assertFalse(current)
        self.assertEqual(reason, "supplemental_witness_evidence content hash mismatch")

    def test_extracts_only_numbered_biography_headings(self) -> None:
        self.assertEqual(MODULE.biography_heading_names({"heading_titles": [
            "القسم الأول", "١٠٧٥٩- آسية بنت الفرج،", "Continuation",
        ]}), ["آسية بنت الفرج"])

    def test_continuation_inherits_nearest_numbered_heading_across_pages(self) -> None:
        sources = {
            30: {"heading_titles": ["١٠٨٠٠- أسماء بنت أبي بكر"]},
            31: {"heading_titles": []},
            32: {"heading_titles": ["Unnumbered continuation label"]},
            33: {"heading_titles": []},
        }
        self.assertIs(
            MODULE.nearest_previous_heading_source(sources, 33),
            sources[30],
        )

    def test_selects_only_explicit_witness_concerns(self) -> None:
        translation = {"uncertainties": [
            {"category": "name", "witness_check_recommended": True},
            {"category": "grammar", "witness_check_recommended": False},
        ]}
        critique = {"issues": [
            {"category": "source_uncertainty", "witness_check_recommended": True},
            {"category": "style", "witness_check_recommended": False},
        ]}
        concerns = MODULE.witness_concerns(translation, critique)
        self.assertEqual([item["concern_id"] for item in concerns], ["translation-1", "critic-1"])

    def test_prompt_keeps_arabic_authoritative(self) -> None:
        prompt = MODULE.build_prompt(
            {"scan_page": 4, "arabic_text": "ARABIC"},
            {"english_text": "ENGLISH"},
            None,
            [{"concern_id": "translation-1"}],
            [{"scan_page": 41, "quality": {}, "text": "URDU"}],
        )
        self.assertIn("Canonical al-Isabah Arabic remains authoritative", prompt)
        self.assertIn("attached image 1", prompt)
        self.assertIn("URDU", prompt)
        self.assertIn("Usd al-Ghaba and al-Isti'ab are independent collateral Arabic works", prompt)
        self.assertIn("role=alternative_edition", prompt)
        self.assertIn("transparent, cited emendation", prompt)

    def test_prompt_includes_hash_bound_supplemental_evidence(self) -> None:
        evidence = [{
            "title": "Parallel source",
            "kind": "parallel_transmission",
            "language": "Arabic",
            "edition": "Test edition",
            "concern_ids": ["translation-1"],
            "citation": "vol. 1, p. 2",
            "source_url": "https://example.test/source",
            "evidence_id": "parallel-1",
            "excerpt": "Arabic excerpt",
            "excerpt_sha256": MODULE.sha256_text("Arabic excerpt"),
            "acquisition_note": "Parallel only.",
        }]
        prompt = MODULE.build_prompt(
            {"scan_page": 4, "arabic_text": "ARABIC"},
            {"english_text": "ENGLISH"},
            None,
            [{"concern_id": "translation-1"}],
            [],
            [],
            evidence,
        )
        self.assertIn("SUPPLEMENTAL HASH-BOUND EVIDENCE", prompt)
        self.assertIn("parallel-1", prompt)
        self.assertIn("cannot silently replace the canonical al-Isabah wording", prompt)

    def test_supplemental_refresh_prompt_carries_prior_findings_without_images(self) -> None:
        prior = {
            "overall_status": "partially_resolved",
            "summary": "Prior Urdu analysis",
            "findings": [{
                "concern_id": "translation-1",
                "conclusion": "inconclusive",
            }],
            "remaining_unresolved": ["Needs another edition"],
            "urdu_witness_candidates": [{"scan_page": 50, "text_sha256": "abc"}],
            "witness_image_sha256": ["def"],
        }
        evidence = [{
            "title": "Alternative edition",
            "kind": "alternative_edition",
            "language": "Arabic",
            "edition": "Test edition",
            "concern_ids": ["translation-1"],
            "citation": "page 1",
            "source_url": "https://example.test/source",
            "evidence_id": "edition-1",
            "excerpt": "A clearer reading",
            "excerpt_sha256": MODULE.sha256_text("A clearer reading"),
            "acquisition_note": "Confirms the correction.",
        }]
        prompt = MODULE.build_supplemental_refresh_prompt(
            {"scan_page": 4, "arabic_text": "ARABIC"},
            {"english_text": "ENGLISH"},
            None,
            [{"concern_id": "translation-1"}],
            prior,
            [],
            evidence,
        )
        self.assertIn("PRIOR HASH-BOUND WITNESS RESOLUTION", prompt)
        self.assertIn("Prior Urdu analysis", prompt)
        self.assertIn("edition-1", prompt)
        self.assertIn("Do not pretend to re-read absent images", prompt)
        self.assertNotIn("attached image 1", prompt)

    def test_refresh_provenance_hash_invalidates_changed_prior_record(self) -> None:
        prior = {"scan_page": 4, "summary": "original"}
        expected = {
            "scan_page": 4,
            "concern_ids": ["translation-1"],
            "secondary_evidence_sha256": MODULE.evidence_sha256([]),
            "prior_witness_resolution_sha256": MODULE.record_sha256(prior),
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "0004.json"
            path.write_text(json.dumps({
                **expected,
                "prior_witness_resolution_sha256": MODULE.record_sha256({
                    **prior, "summary": "edited",
                }),
                "overall_status": "resolved",
                "remaining_unresolved": [],
                "findings": [{
                    "concern_id": "translation-1",
                    "conclusion": "supports_current",
                }],
                "secondary_witness_evidence": [],
            }), encoding="utf-8")
            valid, reason = MODULE.validate_existing_page(path, expected)
            self.assertFalse(valid)
            self.assertIn("prior_witness_resolution_sha256 mismatch", reason)

    def test_supplemental_evidence_loader_rejects_edited_excerpt(self) -> None:
        record = {
            "schema": MODULE.SUPPLEMENTAL_EVIDENCE_SCHEMA,
            "scan_page": 12,
            "evidence_id": "edition-1",
            "kind": "alternative_edition",
            "title": "Edition",
            "language": "Arabic",
            "source_url": "https://example.test/edition",
            "citation": "page 1",
            "concern_ids": ["translation-1"],
            "excerpt": "original",
            "excerpt_sha256": MODULE.sha256_text("original"),
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.jsonl"
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            self.assertEqual(
                MODULE.load_supplemental_evidence(path)[12][0]["evidence_id"],
                "edition-1",
            )
            record["excerpt"] = "edited"
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "excerpt_sha256 mismatch"):
                MODULE.load_supplemental_evidence(path)

    def test_candidate_evidence_preserves_alignment_trace(self) -> None:
        evidence = MODULE.candidate_evidence([{
            "scan_page": 44,
            "score": 52.5,
            "expected_scan_page": 41,
            "distance_from_expected": 3,
            "selection_signals": ["exact_biography_heading", "expected_page_proximity"],
            "matched_names": [],
            "matched_headings": ["Heading"],
            "matched_entry_numbers": [],
            "matched_tokens": ["Token"],
            "text_sha256": "abc",
            "quality": {"ocr": "witness"},
        }])
        self.assertEqual(evidence[0]["expected_scan_page"], 41)
        self.assertEqual(evidence[0]["distance_from_expected"], 3)
        self.assertEqual(
            evidence[0]["selection_signals"],
            ["exact_biography_heading", "expected_page_proximity"],
        )

    def test_resolution_must_cover_every_concern(self) -> None:
        expected = {
            "scan_page": 4,
            "concern_ids": ["translation-1", "critic-1"],
            "secondary_evidence_sha256": MODULE.evidence_sha256([]),
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "0004.json"
            path.write_text(json.dumps({
                **expected,
                "overall_status": "resolved",
                "remaining_unresolved": [],
                "findings": [{"concern_id": "translation-1", "conclusion": "supports_current"}],
            }), encoding="utf-8")
            valid, reason = MODULE.validate_existing_page(path, expected)
            self.assertFalse(valid)
            self.assertEqual(reason, "witness findings do not cover the concerns in order")

    def test_secondary_evidence_tampering_invalidates_saved_page(self) -> None:
        evidence = [{
            "schema": "firstlight.usul-secondary-witness.v1",
            "work_id": "usd",
            "retrieval_state": "hit",
            "hits": [{"text": "original"}],
        }]
        expected = {
            "scan_page": 4,
            "concern_ids": ["translation-1"],
            "secondary_evidence_sha256": MODULE.evidence_sha256(evidence),
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "0004.json"
            path.write_text(json.dumps({
                **expected,
                "overall_status": "resolved",
                "remaining_unresolved": [],
                "findings": [{"concern_id": "translation-1", "conclusion": "supports_current"}],
                "secondary_witness_evidence": [{**evidence[0], "hits": [{"text": "edited"}]}],
            }), encoding="utf-8")
            valid, reason = MODULE.validate_existing_page(path, expected)
            self.assertFalse(valid)
            self.assertEqual(reason, "secondary_witness_evidence content hash mismatch")

    def test_supplemental_evidence_tampering_invalidates_saved_page(self) -> None:
        evidence = [{"evidence_id": "parallel-1", "excerpt": "original"}]
        expected = {
            "scan_page": 4,
            "concern_ids": ["translation-1"],
            "secondary_evidence_sha256": MODULE.evidence_sha256([]),
            "supplemental_evidence_sha256": MODULE.evidence_sha256(evidence),
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "0004.json"
            path.write_text(json.dumps({
                **expected,
                "overall_status": "resolved",
                "remaining_unresolved": [],
                "findings": [{"concern_id": "translation-1", "conclusion": "supports_current"}],
                "secondary_witness_evidence": [],
                "supplemental_witness_evidence": [
                    {"evidence_id": "parallel-1", "excerpt": "edited"}
                ],
            }), encoding="utf-8")
            valid, reason = MODULE.validate_existing_page(path, expected)
            self.assertFalse(valid)
            self.assertEqual(reason, "supplemental_witness_evidence content hash mismatch")

    def test_urdu_candidate_tampering_invalidates_saved_page(self) -> None:
        candidates = [{"scan_page": 41, "distance_from_expected": 0}]
        expected = {
            "scan_page": 4,
            "concern_ids": ["translation-1"],
            "candidate_evidence_sha256": MODULE.candidate_evidence_sha256(candidates),
            "secondary_evidence_sha256": MODULE.evidence_sha256([]),
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "0004.json"
            path.write_text(json.dumps({
                **expected,
                "overall_status": "resolved",
                "remaining_unresolved": [],
                "findings": [{"concern_id": "translation-1", "conclusion": "supports_current"}],
                "urdu_witness_candidates": [{"scan_page": 44, "distance_from_expected": 3}],
                "secondary_witness_evidence": [],
            }), encoding="utf-8")
            valid, reason = MODULE.validate_existing_page(path, expected)
            self.assertFalse(valid)
            self.assertEqual(reason, "urdu_witness_candidates content hash mismatch")

    @mock.patch.object(MODULE.subprocess, "run")
    def test_render_pdf_page_uses_exact_scan(self, run: mock.Mock) -> None:
        run.return_value.returncode = 0
        run.return_value.stderr = ""
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "witness.pdf"
            source.write_bytes(b"source")
            output = Path(directory) / "page.png"
            def render(command: list[str], **_: object) -> mock.Mock:
                Path(f"{command[-1]}.png").write_bytes(b"image")
                return run.return_value
            run.side_effect = render
            MODULE.render_pdf_page(Path("pdftoppm"), source, 144, output)
        command = run.call_args.args[0]
        self.assertEqual(command[command.index("-f") + 1], "144")
        self.assertEqual(command[command.index("-l") + 1], "144")

    @mock.patch.object(MODULE.subprocess, "run")
    def test_render_pdf_page_reuses_only_hash_bound_image(self, run: mock.Mock) -> None:
        run.return_value.returncode = 0
        run.return_value.stderr = ""
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "witness.pdf"
            source.write_bytes(b"source")
            output = Path(directory) / "page.png"

            def render(command: list[str], **_: object) -> mock.Mock:
                Path(f"{command[-1]}.png").write_bytes(b"image")
                return run.return_value

            run.side_effect = render
            MODULE.render_pdf_page(Path("pdftoppm"), source, 144, output)
            MODULE.render_pdf_page(Path("pdftoppm"), source, 144, output)
            self.assertEqual(run.call_count, 1)

            output.write_bytes(b"tampered")
            MODULE.render_pdf_page(Path("pdftoppm"), source, 144, output)
            self.assertEqual(run.call_count, 2)


if __name__ == "__main__":
    unittest.main()

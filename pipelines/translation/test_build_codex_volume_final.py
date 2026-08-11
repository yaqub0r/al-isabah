from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("build_codex_volume_final.py")
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("build_codex_volume_final", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class BuildCodexVolumeFinalTests(unittest.TestCase):
    def test_complete_volume_requires_adjudication_even_after_clean_critic_pass(self) -> None:
        translation = {"fidelity": {}, "uncertainties": [], "names": [], "english_text": "text"}
        critique = {"verdict": "pass", "issues": []}
        source = {"arabic_text": "text"}
        self.assertFalse(
            MODULE.requires_final_adjudication(
                translation, critique, source, complete_volume=False
            )
        )
        self.assertTrue(
            MODULE.requires_final_adjudication(
                translation, critique, source, complete_volume=True
            )
        )

    def test_scan_index_rejects_duplicate_pages(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "duplicate scan pages"):
            MODULE.records_in_scan_range([{"scan_page": 4}, {"scan_page": 4}], {4})

    def test_probable_entry_numbers_accepts_english_heading_punctuation(self) -> None:
        self.assertEqual(MODULE.probable_entry_numbers("10953. Buthayna\n10954: Bujayda\n10955—Badila"), [10953, 10954, 10955])

    def test_probable_entry_numbers_rejects_four_digit_line_start_citations(self) -> None:
        self.assertEqual(
            MODULE.probable_entry_numbers("10759 - Asiyah\n1077: a cited report number"),
            [10759],
        )

    def test_probable_entry_numbers_accepts_editorially_bracketed_heading(self) -> None:
        self.assertEqual(MODULE.probable_entry_numbers("[11769- Malika bint Abd Allah"), [11769])

    def test_entry_sequence_audit_rejects_gap_duplicate_and_reversal(self) -> None:
        audit = MODULE.audit_entry_sequence(
            [10759, 10760, 10760, 10762, 10761],
            expected_first=10759,
            expected_last=10762,
        )
        self.assertFalse(audit["pass"])
        self.assertEqual(audit["duplicate_count"], 1)
        self.assertEqual(audit["reversal_count"], 1)

    def test_boundary_overlap_detects_translated_context_repetition(self) -> None:
        repeated = "this is a deliberately repeated translated boundary with enough words to identify context leakage"
        count, preview = MODULE.boundary_word_overlap(f"Unique opening. {repeated}", f"{repeated} Different close.")
        self.assertEqual(count, 14)
        self.assertEqual(preview, repeated)

    def test_unresolved_passage_report_preserves_review_citations(self) -> None:
        item = {"category": "name_vocalization", "explanation": "Two readings remain"}
        records = [{
            "unit_id": "unit-4",
            "source": {"scan_page": 4, "printed_page": 3, "reader_url": "https://reader/4"},
            "target": {"unresolved": [item]},
        }]
        self.assertEqual(MODULE.unresolved_passage_report(records), [{
            "scan_page": 4,
            "printed_page": 3,
            "reader_url": "https://reader/4",
            "unit_id": "unit-4",
            "items": [item],
        }])

    def test_numeric_tokens_normalize_arabic_and_superscript_digits(self) -> None:
        self.assertEqual(MODULE.numeric_tokens("١٠٨٤٩ and ² / ٥٥١"), {2, 551, 10849})

    def test_documented_numeric_correction_accepts_flattened_rtl_citation(self) -> None:
        adjudication = {"changes": [{
            "category": "bibliographic citation",
            "original": "al-Tabaqat, 5/218",
            "replacement": "al-Tabaqat, 8/52",
            "rationale": "The RTL citation lost its separator.",
            "evidence": "The cited entry is in volume 8, page 52.",
        }]}
        self.assertIn(
            5218,
            MODULE.documented_numeric_corrections(
                adjudication, "See al-Tabaqat, 8/52."
            ),
        )

    def test_documented_numeric_correction_requires_final_replacement_and_evidence(self) -> None:
        base = {
            "category": "citation correction",
            "original": "entry 7162",
            "replacement": "entry 7164",
            "rationale": "The printed cross-reference is wrong.",
            "evidence": "",
        }
        self.assertEqual(
            MODULE.documented_numeric_corrections(
                {"changes": [base]}, "See entry 7164."
            ),
            set(),
        )
        with_evidence = {**base, "evidence": "The parallel entry is 7164."}
        self.assertEqual(
            MODULE.documented_numeric_corrections(
                {"changes": [with_evidence]}, "Replacement absent here."
            ),
            set(),
        )

    def test_documented_numeric_correction_rejects_unrelated_change_category(self) -> None:
        adjudication = {"changes": [{
            "category": "style",
            "original": "entry 7162",
            "replacement": "entry 7164",
            "rationale": "Prefer this form.",
            "evidence": "A witness uses it.",
        }]}
        self.assertEqual(
            MODULE.documented_numeric_corrections(
                adjudication, "See entry 7164."
            ),
            set(),
        )

    def test_final_page_accepts_only_documented_numeric_correction(self) -> None:
        source = {
            "work_id": "work", "volume": 8, "scan_page": 4, "printed_page": 3,
            "reader_page": 3916, "reader_url": "url", "facsimile_pdf": "source.pdf",
            "arabic_text_sha256": "a" * 64, "source_state": "canonical",
            "arabic_text": "Reference ٥٢١٨",
        }
        translation = {
            "english_text": "Reference 5/218", "entry_numbers": [], "names": [],
            "model": "model", "reasoning_effort": "high", "prompt_version": "v1",
            "generated_at": "now",
        }
        critique = {
            "verdict": "revise", "issues": [], "model": "model",
            "reasoning_effort": "high", "prompt_version": "v1",
        }
        adjudication = {
            "decision": "revised", "final_english_text": "Reference 8/52",
            "entry_numbers": [], "names": [], "unresolved": [],
            "changes": [{
                "category": "bibliographic citation",
                "original": "Reference 5/218",
                "replacement": "Reference 8/52",
                "rationale": "The RTL citation lost its separator.",
                "evidence": "The cited entry is in volume 8, page 52.",
            }],
            "model": "model", "reasoning_effort": "xhigh", "prompt_version": "v5",
        }
        _, errors, warnings = MODULE.final_page_record(
            source, translation, critique, None, adjudication
        )
        self.assertNotIn("missing_numeric_tokens", {item["code"] for item in errors})
        self.assertIn("documented_numeric_corrections", {item["code"] for item in warnings})

    def test_provenance_chain_rejects_stale_critique(self) -> None:
        source = {
            "scan_page": 4, "work_id": "work", "volume": 8,
            "arabic_text_sha256": "a" * 64,
        }
        translation = {
            "scan_page": 4, "work_id": "work", "volume": 8,
            "source_sha256": "a" * 64, "schema": "firstlight.codex-page-translation.v1",
            "pass": "blind_translation", "english_text": "current",
        }
        critique = {
            "scan_page": 4, "work_id": "work", "volume": 8,
            "source_sha256": "a" * 64, "schema": "firstlight.codex-page-critique.v1",
            "pass": "fidelity_critic", "translation_sha256": "stale",
        }
        errors = MODULE.provenance_chain_errors(source, translation, critique, None, None)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["stage"], "critique")
        self.assertEqual(errors[0]["field"], "translation_sha256")

    def test_provenance_chain_rejects_tampered_secondary_witness_text(self) -> None:
        source = {
            "scan_page": 4, "work_id": "work", "volume": 8,
            "arabic_text_sha256": "a" * 64,
        }
        translation = {
            "scan_page": 4, "work_id": "work", "volume": 8,
            "source_sha256": "a" * 64, "schema": "firstlight.codex-page-translation.v1",
            "pass": "blind_translation", "english_text": "current",
        }
        critique = {
            "scan_page": 4, "work_id": "work", "volume": 8,
            "source_sha256": "a" * 64, "schema": "firstlight.codex-page-critique.v1",
            "pass": "fidelity_critic", "translation_sha256": MODULE.record_sha256(translation),
        }
        original = [{"work_id": "usd", "query": "name", "retrieval_state": "hit", "hits": [{"text": "original"}]}]
        witness = {
            "scan_page": 4, "work_id": "work", "volume": 8,
            "source_sha256": "a" * 64, "schema": "firstlight.codex-witness-resolution.v1",
            "pass": "multilingual_witness_resolution",
            "translation_sha256": MODULE.record_sha256(translation),
            "critique_sha256": MODULE.record_sha256(critique),
            "candidate_evidence_sha256": MODULE.candidate_evidence_sha256([]),
            "urdu_witness_candidates": [],
            "secondary_evidence_sha256": MODULE.evidence_sha256(original),
            "secondary_witness_evidence": [{**original[0], "hits": [{"text": "edited"}]}],
        }
        errors = MODULE.provenance_chain_errors(source, translation, critique, witness, None)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["stage"], "witness")
        self.assertEqual(errors[0]["field"], "secondary_witness_evidence")

    def test_provenance_chain_rejects_tampered_supplemental_witness_text(self) -> None:
        source = {
            "scan_page": 4, "work_id": "work", "volume": 8,
            "arabic_text_sha256": "a" * 64,
        }
        translation = {
            "scan_page": 4, "work_id": "work", "volume": 8,
            "source_sha256": "a" * 64,
            "schema": "firstlight.codex-page-translation.v1",
            "pass": "blind_translation", "english_text": "current",
        }
        critique = {
            "scan_page": 4, "work_id": "work", "volume": 8,
            "source_sha256": "a" * 64,
            "schema": "firstlight.codex-page-critique.v1",
            "pass": "fidelity_critic",
            "translation_sha256": MODULE.record_sha256(translation),
        }
        original = [{"evidence_id": "parallel-1", "excerpt": "original"}]
        witness = {
            "scan_page": 4, "work_id": "work", "volume": 8,
            "source_sha256": "a" * 64,
            "schema": "firstlight.codex-witness-resolution.v1",
            "pass": "multilingual_witness_resolution",
            "translation_sha256": MODULE.record_sha256(translation),
            "critique_sha256": MODULE.record_sha256(critique),
            "candidate_evidence_sha256": MODULE.candidate_evidence_sha256([]),
            "urdu_witness_candidates": [],
            "secondary_evidence_sha256": MODULE.evidence_sha256([]),
            "secondary_witness_evidence": [],
            "supplemental_evidence_sha256": MODULE.evidence_sha256(original),
            "supplemental_witness_evidence": [
                {"evidence_id": "parallel-1", "excerpt": "edited"}
            ],
        }
        errors = MODULE.provenance_chain_errors(source, translation, critique, witness, None)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["field"], "supplemental_witness_evidence")

    def test_provenance_chain_rejects_tampered_urdu_candidates(self) -> None:
        source = {
            "scan_page": 4, "work_id": "work", "volume": 8,
            "arabic_text_sha256": "a" * 64,
        }
        translation = {
            "scan_page": 4, "work_id": "work", "volume": 8,
            "source_sha256": "a" * 64, "schema": "firstlight.codex-page-translation.v1",
            "pass": "blind_translation",
        }
        critique = {
            "scan_page": 4, "work_id": "work", "volume": 8,
            "source_sha256": "a" * 64, "schema": "firstlight.codex-page-critique.v1",
            "pass": "fidelity_critic", "translation_sha256": MODULE.record_sha256(translation),
        }
        original = [{"scan_page": 41, "distance_from_expected": 0}]
        witness = {
            "scan_page": 4, "work_id": "work", "volume": 8,
            "source_sha256": "a" * 64, "schema": "firstlight.codex-witness-resolution.v1",
            "pass": "multilingual_witness_resolution",
            "translation_sha256": MODULE.record_sha256(translation),
            "critique_sha256": MODULE.record_sha256(critique),
            "candidate_evidence_sha256": MODULE.candidate_evidence_sha256(original),
            "urdu_witness_candidates": [{"scan_page": 44, "distance_from_expected": 3}],
            "secondary_evidence_sha256": MODULE.evidence_sha256([]),
            "secondary_witness_evidence": [],
        }
        errors = MODULE.provenance_chain_errors(source, translation, critique, witness, None)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["stage"], "witness")
        self.assertEqual(errors[0]["field"], "urdu_witness_candidates")

    def test_witness_evidence_report_counts_provider_outcomes(self) -> None:
        report = MODULE.witness_evidence_report([
            {"secondary_witness_evidence": [
                {"work_id": "usd", "query": "a", "retrieval_state": "hit"},
                {"work_id": "istiab", "query": "a", "retrieval_state": "error"},
            ]},
            {"secondary_witness_evidence": [
                {"work_id": "usd", "query": "b", "retrieval_state": "no_match"},
            ], "supplemental_witness_evidence": [
                {"scan_page": 12, "kind": "alternative_edition"},
            ]},
        ])
        self.assertEqual(report["resolution_pages"], 2)
        self.assertEqual(report["collateral_records"], 3)
        self.assertEqual(report["query_attempts"], 3)
        self.assertEqual(report["unique_queries"], 2)
        self.assertEqual(report["retrieval_hits"], 1)
        self.assertEqual(report["retrieval_errors"], 1)
        self.assertEqual(report["retrieval_no_matches"], 1)
        self.assertEqual(report["retrieval_unavailable"], 0)
        self.assertEqual(report["retrieval_incomplete"], 1)
        self.assertEqual(report["supplemental_records"], 1)
        self.assertEqual(report["supplemental_kinds"], ["alternative_edition"])
        self.assertEqual(report["supplemental_scans"], [12])

    def test_extracts_arabic_indic_entry_numbers_and_notes(self) -> None:
        text = "١٠٧٥٩- آسية\n\n(١) نص\n١٠٧٦٠- آمنة\n(٢) نص"
        self.assertEqual(MODULE.probable_entry_numbers(text), [10759, 10760])
        self.assertEqual(MODULE.footnote_labels(text), {1, 2})
        self.assertEqual(MODULE.english_footnote_labels("Footnotes\n1. First\n[2] Second\n(3) Third"), {1, 2, 3})
        self.assertEqual(MODULE.english_footnote_labels("Text² and more.\n¹ First note\n² Second note"), {1, 2})

    def test_final_page_detects_missing_entry_and_footnote(self) -> None:
        source = {
            "work_id": "work", "volume": 8, "scan_page": 4, "printed_page": 3,
            "reader_page": 3916, "reader_url": "url", "facsimile_pdf": "source.pdf",
            "arabic_text_sha256": "a" * 64, "source_state": "canonical",
            "arabic_text": "١٠٧٥٩- آسية\n(١) مرجع",
        }
        translation = {
            "english_text": "Asiyah", "entry_numbers": [], "names": [],
            "model": "model", "reasoning_effort": "high", "prompt_version": "v1",
            "generated_at": "now",
        }
        critique = {"verdict": "pass", "issues": [], "model": "model", "reasoning_effort": "high", "prompt_version": "v1"}
        _, errors, _ = MODULE.final_page_record(source, translation, critique, None, None)
        self.assertEqual(
            {item["code"] for item in errors},
            {"entry_number_mismatch", "missing_footnote_labels", "missing_numeric_tokens"},
        )

    def test_final_page_rejects_descriptive_name_mapping(self) -> None:
        source = {
            "work_id": "work", "volume": 8, "scan_page": 4, "printed_page": 3,
            "reader_page": 3916, "reader_url": "url", "facsimile_pdf": "source.pdf",
            "arabic_text_sha256": "a" * 64, "source_state": "canonical",
            "arabic_text": "Arabic prose",
        }
        translation = {
            "english_text": "Asiya appears here.",
            "entry_numbers": [],
            "names": [{"arabic": "name", "english": "Amina (an explanatory note)"}],
            "model": "model", "reasoning_effort": "high", "prompt_version": "v1",
            "generated_at": "now",
        }
        critique = {
            "verdict": "pass", "issues": [], "model": "model",
            "reasoning_effort": "high", "prompt_version": "v1",
        }
        _, errors, _ = MODULE.final_page_record(
            source, translation, critique, None, None
        )
        self.assertIn(
            "name_mapping_policy_violation",
            {item["code"] for item in errors},
        )

    def test_adjudication_unresolved_supersedes_witness_queue(self) -> None:
        source = {
            "work_id": "work", "volume": 8, "scan_page": 4, "printed_page": 3,
            "reader_page": 3916, "reader_url": "url", "facsimile_pdf": "source.pdf",
            "arabic_text_sha256": "a" * 64, "source_state": "canonical",
            "arabic_text": "Arabic prose",
        }
        translation = {
            "english_text": "English prose", "entry_numbers": [], "names": [],
            "model": "model", "reasoning_effort": "high", "prompt_version": "v1",
            "generated_at": "now",
        }
        critique = {
            "verdict": "pass", "issues": [], "model": "model",
            "reasoning_effort": "high", "prompt_version": "v1",
        }
        witness = {
            "overall_status": "partially_resolved",
            "remaining_unresolved": ["same witness concern"],
            "findings": [],
            "supplemental_evidence_sha256": "supplemental-sha",
            "supplemental_witness_evidence": [{"evidence_id": "parallel-1"}],
        }
        adjudication = {
            "decision": "unresolved",
            "final_english_text": "English prose",
            "names": [],
            "entry_numbers": [],
            "unresolved": [{
                "category": "reference",
                "arabic_span": "it",
                "explanation": "same witness concern",
                "human_review_priority": "high",
            }],
            "changes": [],
            "model": "model",
            "reasoning_effort": "xhigh",
            "prompt_version": "v5",
            "generated_at": "now",
        }
        record, _, _ = MODULE.final_page_record(
            source, translation, critique, witness, adjudication
        )
        self.assertEqual(
            record["translation"]["method"],
            "codex_blind_translation_with_independent_critique_multilingual_witness_and_full_adjudication",
        )
        self.assertEqual(len(record["target"]["unresolved"]), 1)
        self.assertEqual(
            record["supplemental_cross_check"]["evidence"][0]["evidence_id"],
            "parallel-1",
        )

    def test_name_report_surfaces_variant_renderings(self) -> None:
        records = [
            {"target": {"names": [{"arabic": "آسية", "english": "Asiyah"}]}},
            {"target": {"names": [{"arabic": "آسية", "english": "Asiya"}]}},
        ]
        report = MODULE.build_name_report(records)
        self.assertEqual(len(report["arabic_forms_with_multiple_english_renderings"]), 1)

    def test_name_report_normalizes_arabic_marks_and_apostrophe_style(self) -> None:
        records = [
            {"target": {"names": [{"arabic": "البلاذريّ", "english": "al-Baladhuri"}]}},
            {"target": {"names": [{"arabic": "البلاذري", "english": "al-Baladhuri"}]}},
            {"target": {"names": [{"arabic": "أبو عمر", "english": "Abu ‘Umar"}]}},
            {"target": {"names": [{"arabic": "أبو عمر", "english": "Abu 'Umar"}]}},
        ]
        report = MODULE.build_name_report(records)
        self.assertEqual(report["english_renderings_with_multiple_arabic_forms"], [])
        self.assertEqual(report["arabic_forms_with_multiple_english_renderings"], [])

    def test_records_in_scan_range_ignores_complete_volume_superset(self) -> None:
        records = [
            {"scan_page": 4, "value": "selected"},
            {"scan_page": 5, "value": "outside proof range"},
        ]
        self.assertEqual(
            MODULE.records_in_scan_range(records, {4}),
            {4: {"scan_page": 4, "value": "selected"}},
        )


if __name__ == "__main__":
    unittest.main()

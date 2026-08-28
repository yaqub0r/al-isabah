import copy
import importlib.util
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "translation_workflow", ROOT / "scripts" / "translation_workflow.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)

FIXTURE_SOURCE = ROOT / "tests" / "fixtures" / "openiti-mini.mARkdown"
FIXTURE_MANIFEST = ROOT / "tests" / "fixtures" / "translation-source.mini.json"
ISSUE_0026_PROPOSAL = (
    ROOT / "content" / "public-proposals" / "issue-0026.public-proposal.json"
)


def assignment_issue(number=25, start=1, end=2):
    marker = {
        "schemaVersion": "1.0.0",
        "workId": "ibn-hajar-al-isabah",
        "sourceId": "openiti-jk000533-5835c183",
        "contractId": "translation-quality-workflow",
        "startUnit": start,
        "endUnit": end,
    }
    return {
        "number": number,
        "url": f"https://github.com/yaqub0r/al-isabah/issues/{number}",
        "state": "OPEN",
        "createdAt": "2026-08-14T00:00:00Z",
        "assignees": [{"login": "translator"}],
        "body": f"Assignment\n\n{MODULE.assignment_marker(marker)}\n",
    }


def complete_autonomous_stages(packet):
    policy_sha256 = packet["policy"]["bindingSha256"]

    def translated(label, source_text):
        targets = [
            occurrence["rule"]["target"]
            for occurrence in MODULE.registered_occurrences(source_text or "", "source")
        ]
        return " ".join([label, *targets]).strip()

    def semantic_audit(source, heading_english, english):
        return {
            "status": "complete",
            "checklistVersion": MODULE.SEMANTIC_AUDIT_VERSION,
            "sourceSha256": MODULE.semantic_source_sha256(source),
            "candidateSha256": MODULE.semantic_candidate_sha256(
                heading_english, english
            ),
            "checks": [
                {
                    "category": category,
                    "outcome": "no_issue",
                    "assessment": f"Fixture review checked {category} against both texts.",
                }
                for category in MODULE.SEMANTIC_AUDIT_CATEGORIES
            ],
        }

    def name_audit(source, heading_english, english, number):
        return {
            "status": "complete",
            "runId": f"names-{number}",
            "method": "independent bilingual name inventory",
            "sourceSha256": MODULE.semantic_source_sha256(source),
            "englishSha256": MODULE.semantic_candidate_sha256(
                heading_english, english
            ),
            "assessment": "Every personal reference in the fixture was reconciled.",
        }

    def independent_context(
        stage, source, upstream, model, reasoning, evidence, receipt
    ):
        input_sha256 = MODULE.stage_input_sha256(
            stage,
            MODULE.semantic_source_sha256(source),
            MODULE.stage_upstream_sha256(upstream),
            policy_sha256,
            MODULE.packet_schema_sha256(),
            model,
            reasoning,
            MODULE.stage_evidence_sha256(evidence),
        )
        return {
            "status": "complete",
            "method": "fresh isolated synthetic test execution",
            "freshContext": True,
            "priorStageContextExcluded": True,
            "inputSha256": input_sha256,
            "receipt": receipt,
        }

    def finish_stage_chain(owner, source, token):
        blind = owner["blindTranslation"]
        blind["provenance"] = MODULE.completed_stage_provenance(
            blind,
            "blind_translation",
            source,
            [],
            policy_sha256,
            blind["model"],
            blind["reasoning"],
            [],
        )

        critique = owner["independentCritique"]
        critique_receipt = {
            "receiptId": f"critique-context-{token}",
            "issuer": "synthetic-test-execution-harness",
            "receiptSha256": MODULE.text_sha256(f"critique receipt {token}"),
        }
        critique_evidence = [
            {
                "evidenceId": critique_receipt["receiptId"],
                "role": "independent_context_receipt",
                "sha256": critique_receipt["receiptSha256"],
            }
        ]
        critique_reasoning = "high"
        critique["independentContext"] = independent_context(
            "independent_critique",
            source,
            [("blind_translation", blind)],
            critique["model"],
            critique_reasoning,
            critique_evidence,
            critique_receipt,
        )
        critique["provenance"] = MODULE.completed_stage_provenance(
            critique,
            "independent_critique",
            source,
            [("blind_translation", blind)],
            policy_sha256,
            critique["model"],
            critique_reasoning,
            critique_evidence,
        )

        witness = owner["witnessResolution"]
        witness_evidence = [
            {
                "evidenceId": f"witness-result-{token}-{index}",
                "role": "witness_result",
                "sha256": result["evidenceSha256"],
            }
            for index, result in enumerate(witness["results"], start=1)
        ]
        witness["provenance"] = MODULE.completed_stage_provenance(
            witness,
            "witness_resolution",
            source,
            [("independent_critique", critique)],
            policy_sha256,
            "deterministic-witness-gate",
            "source-bound",
            witness_evidence,
            run_id=f"witness-{token}",
        )

        adjudication = owner["adjudication"]
        adjudication["provenance"] = MODULE.completed_stage_provenance(
            adjudication,
            "adjudication",
            source,
            [
                ("blind_translation", blind),
                ("independent_critique", critique),
                ("witness_resolution", witness),
            ],
            policy_sha256,
            "codex-adjudication",
            "high",
            [],
            run_id=f"adjudication-{token}",
        )

        names = owner["names"]
        name_receipt = {
            "receiptId": f"name-context-{token}",
            "issuer": "synthetic-test-execution-harness",
            "receiptSha256": MODULE.text_sha256(f"name receipt {token}"),
        }
        name_evidence = [
            {
                "evidenceId": name_receipt["receiptId"],
                "role": "independent_context_receipt",
                "sha256": name_receipt["receiptSha256"],
            }
        ]
        name_model = "codex-independent-name-pass"
        name_reasoning = "high"
        names["independentContext"] = independent_context(
            "name_inventory",
            source,
            [("adjudication", adjudication)],
            name_model,
            name_reasoning,
            name_evidence,
            name_receipt,
        )
        names["provenance"] = MODULE.completed_stage_provenance(
            names,
            "name_inventory",
            source,
            [("adjudication", adjudication)],
            policy_sha256,
            name_model,
            name_reasoning,
            name_evidence,
        )

    for entry in packet["entries"]:
        number = entry["sourceOrdinal"]
        for index, (source, translation) in enumerate(
            zip(
                entry["source"]["precedingSegments"],
                entry["precedingTranslations"],
            ),
            start=1,
        ):
            heading = source.get("headingArabic")
            prose = source.get("arabic")
            translation["blindTranslation"].update(
                {
                    "status": "complete",
                    "runId": f"blind-structure-{number}-{index}",
                    "model": "codex",
                    "reasoning": "high",
                    "headingEnglish": translated("Translated heading", heading)
                    if heading
                    else None,
                    "english": translated("Translated source prose.", prose)
                    if prose
                    else None,
                }
            )
            translation["independentCritique"].update(
                {
                    "status": "complete",
                    "runId": f"critique-structure-{number}-{index}",
                    "model": "codex-independent-pass",
                    "findings": [],
                    "semanticAudit": semantic_audit(
                        source,
                        translation["blindTranslation"]["headingEnglish"],
                        translation["blindTranslation"]["english"],
                    ),
                }
            )
            translation["witnessResolution"] = {
                "status": "not_required",
                "results": [],
                "notRequiredRationale": "The independent critique found no concern requiring a witness.",
            }
            translation["adjudication"] = {
                "status": "complete",
                "headingEnglish": translated("Translated heading", heading)
                if heading
                else None,
                "english": translated("Adjudicated source prose.", prose)
                if prose
                else None,
                "decisions": [],
            }
            translation["names"] = {
                "status": "complete",
                "candidates": [],
                "mentions": [],
                "inventoryAudit": name_audit(
                    source,
                    translation["adjudication"]["headingEnglish"],
                    translation["adjudication"]["english"],
                    f"{number}-{index}",
                ),
            }
            translation["unresolved"] = []
            finish_stage_chain(translation, source, f"structure-{number}-{index}")
        entry["blindTranslation"].update(
            {
                "status": "complete",
                "runId": f"blind-{number}",
                "model": "codex",
                "reasoning": "high",
                "english": translated(
                    f"Blind English for entry {number}.", entry["source"]["arabic"]
                ),
            }
        )
        entry["independentCritique"].update(
            {
                "status": "complete",
                "runId": f"critique-{number}",
                "model": "codex-independent-pass",
                "findings": [],
                "semanticAudit": semantic_audit(
                    entry["source"], None, entry["blindTranslation"]["english"]
                ),
            }
        )
        entry["witnessResolution"] = {
            "status": "not_required",
            "results": [],
            "notRequiredRationale": "The independent critique found no concern requiring a witness.",
        }
        entry["adjudication"] = {
            "status": "complete",
            "english": translated(
                f"Adjudicated English for entry {number}. Duba'a.",
                entry["source"]["arabic"],
            ),
            "decisions": [],
        }
        observed = "ضباعة"
        source_start = entry["source"]["arabic"].index(observed)
        entry["names"] = {
            "status": "complete",
            "candidates": [
                {
                    "candidateId": f"issue-25-name-{number}",
                    "observedArabic": observed,
                    "proposedEnglish": "Duba'a",
                    "aliases": [],
                    "confidenceEvidence": ["entry heading"],
                    "reviewState": "unreviewed",
                }
            ],
            "mentions": [
                {
                    "candidateId": f"issue-25-name-{number}",
                    "recordId": entry["sourceUnitId"],
                    "location": "entry-heading",
                    "mentionId": f"issue-25-name-{number}-mention-001",
                    "originCandidateId": f"issue-25-name-{number}",
                    "sourceSpans": [
                        {
                            "sourceField": "arabic",
                            "start": source_start,
                            "end": source_start + len(observed),
                            "sha256": MODULE.text_sha256(observed),
                        }
                    ],
                }
            ],
            "inventoryAudit": name_audit(
                entry["source"], None, entry["adjudication"]["english"], number
            ),
        }
        entry["unresolved"] = []
        finish_stage_chain(entry, entry["source"], f"entry-{number}")


class TranslationWorkflowTests(unittest.TestCase):
    def test_private_data_scan_accepts_escaped_newline_after_prose_colon(self):
        value = {
            "decision": "Verses by Haritha:\\n\\nThe first translated line."
        }

        self.assertEqual(MODULE.private_data_errors(value), [])

    def test_private_data_scan_rejects_windows_absolute_path(self):
        value = {"decision": r"Evidence cached at C:\Users\editor\scan.pdf"}

        errors = MODULE.private_data_errors(value)

        self.assertTrue(any("local absolute path" in error for error in errors))

    def packet(self):
        issue = assignment_issue()
        claims = MODULE.parse_claims([issue])
        return MODULE.build_packet(
            issue,
            claims,
            FIXTURE_SOURCE,
            FIXTURE_MANIFEST,
            MODULE.DEFAULT_POLICY,
        )

    def test_fixture_integrity_is_valid(self):
        manifest = MODULE.load_json(FIXTURE_MANIFEST)
        self.assertEqual(MODULE.verify_source(FIXTURE_SOURCE, manifest), [])
        entries = MODULE.parse_openiti_entries(FIXTURE_SOURCE)
        self.assertEqual(MODULE.validate_source_inventory(entries, manifest), [])

    def test_claim_dry_run_links_parent_and_separates_human_review(self):
        with tempfile.TemporaryDirectory() as directory:
            issues_path = Path(directory) / "issues.json"
            issues_path.write_text("[]", encoding="utf-8")
            args = SimpleNamespace(
                manifest=FIXTURE_MANIFEST,
                source=FIXTURE_SOURCE,
                issues_json=issues_path,
                start_unit=1,
                end_unit=1,
                parent_issue=53,
                assignee="@me",
                dry_run=True,
            )
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(MODULE.command_claim(args), 0)
            body = output.getvalue()
            self.assertIn("Parent implementation: #53.", body)
            self.assertIn("agent-complete", body)
            self.assertIn("independent, ongoing management state", body)

    def test_hydrate_from_file_is_atomic_and_hash_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "source.mARkdown"
            result = MODULE.hydrate_source(
                FIXTURE_MANIFEST, destination=target, from_file=FIXTURE_SOURCE
            )
            self.assertEqual(result, target)
            self.assertEqual(result.read_bytes(), FIXTURE_SOURCE.read_bytes())

    def test_hydrate_rejects_wrong_hash(self):
        manifest = MODULE.load_json(FIXTURE_MANIFEST)
        manifest["download"]["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = Path(directory) / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(MODULE.WorkflowError, "SHA-256"):
                MODULE.hydrate_source(
                    manifest_path,
                    destination=Path(directory) / "source.mARkdown",
                    from_file=FIXTURE_SOURCE,
                )

    def test_parser_preserves_entry_boundaries_and_context(self):
        entries = MODULE.parse_openiti_entries(FIXTURE_SOURCE)
        self.assertEqual(
            [entry["sourceEntryNumber"] for entry in entries],
            [11426, 11427, 11428, 11428],
        )
        self.assertNotEqual(entries[2]["sourceUnitId"], entries[3]["sourceUnitId"])
        self.assertIn("ضباعة بنت عامر", entries[0]["arabic"])
        first_context = entries[0]["precedingSegments"]
        self.assertEqual(
            [segment["kind"] for segment in first_context],
            ["front_matter", "structural_heading", "structural_heading"],
        )
        self.assertEqual(first_context[1]["headingArabic"], "( مقدمة الاختبار )")
        self.assertIn("هذا تمهيد أصلي", first_context[1]["arabic"])
        self.assertTrue(
            all("#META#" not in segment["rawOpeniti"] for segment in first_context)
        )
        historical_paratext = entries[1]["precedingSegments"][0]
        self.assertEqual(historical_paratext["kind"], "interstitial_prose")
        self.assertIn("قال مؤلفه فرغت", historical_paratext["arabic"])
        self.assertIn("بسم الله الرحمن الرحيم", historical_paratext["arabic"])
        self.assertNotIn("PARATEXT", historical_paratext["rawOpeniti"])
        self.assertNotIn("باب الطاء", entries[1]["rawOpeniti"])
        self.assertEqual(
            entries[2]["precedingSegments"][0]["headingArabic"],
            "( باب الطاء )",
        )
        self.assertNotIn(
            "مقدمة حديثة للمحقق",
            " ".join(
                segment.get("arabic") or ""
                for entry in entries
                for segment in entry["precedingSegments"]
            ),
        )
        self.assertEqual(entries[2]["locations"][0], {"volume": 8, "page": 5})

    def test_packet_explicitly_excludes_container_metadata(self):
        packet = self.packet()
        exclusions = packet["scope"]["excludedRanges"]
        self.assertEqual(packet["schemaVersion"], "1.5.0")
        self.assertEqual(
            packet["sliceContext"],
            {
                "state": "root",
                "beforeSourceOrdinal": 1,
                "sourceProposalId": None,
                "sourceProposalSha256": None,
                "contexts": [],
            },
        )
        self.assertEqual(exclusions[0]["kind"], "openiti_metadata")
        self.assertEqual(exclusions[0]["lineStart"], 1)
        self.assertEqual(exclusions[0]["lineEnd"], 4)
        self.assertEqual(exclusions[1]["kind"], "openiti_control")
        self.assertEqual(exclusions[1]["lineStart"], 15)
        self.assertEqual(exclusions[1]["lineEnd"], 15)
        self.assertEqual(exclusions[2]["kind"], "modern_paratext")
        self.assertEqual(exclusions[2]["lineStart"], 21)
        self.assertEqual(exclusions[2]["lineEnd"], 22)
        self.assertEqual(
            packet["scope"]["precedingMaterialOwnership"],
            "following_source_unit",
        )

    def test_nonroot_packet_requires_explicit_reviewable_context_source(self):
        issue = assignment_issue(start=2, end=2)
        with self.assertRaisesRegex(
            MODULE.WorkflowError,
            "explicit prior public proposal",
        ):
            MODULE.build_packet(
                issue,
                MODULE.parse_claims([issue]),
                FIXTURE_SOURCE,
                FIXTURE_MANIFEST,
                MODULE.DEFAULT_POLICY,
            )

    def test_volume2_context_is_source_bound_distinct_and_rendered_first(self):
        proposal = MODULE.load_json(ISSUE_0026_PROPOSAL)
        source_authority = proposal["sourceAuthority"]
        authority = {
            "commit": source_authority["commit"],
            "sha256": source_authority["sha256"],
        }
        binding, contexts = MODULE.slice_context(
            1538,
            authority,
            ISSUE_0026_PROPOSAL,
        )
        self.assertEqual(binding["state"], "continued")
        self.assertEqual(binding["sourceProposalId"], "issue-0026-public-proposal-v1")
        self.assertEqual(len(contexts), 4)
        self.assertEqual(
            binding["contexts"][-1],
            {
                "sourceOccurrenceId": (
                    "openiti-5835c183-before-unit-001536-segment-001"
                ),
                "displayContextId": (
                    "continued-before-unit-001538-from-"
                    "openiti-5835c183-before-unit-001536-segment-001"
                ),
            },
        )
        self.assertTrue(
            all(
                item["sourceOccurrenceId"] != item["displayContextId"]
                for item in contexts
            )
        )
        packet_contexts, errors = MODULE.resolved_packet_slice_context(
            {
                "assignment": {"startUnit": 1538},
                "authority": authority,
                "sliceContext": binding,
            }
        )
        self.assertEqual(errors, [])
        self.assertEqual(packet_contexts, contexts)

        review_packet = self.packet()
        complete_autonomous_stages(review_packet)
        review_packet["assignment"]["startUnit"] = 1538
        review_packet["authority"].update(authority)
        review_packet["sliceContext"] = binding
        review_packet["entries"][0]["sourceOrdinal"] = 1538
        review = MODULE.render_review(review_packet)
        context_position = review.index("## Continued source hierarchy")
        first_unit_position = review.index("## Source unit 1538")
        self.assertLess(context_position, first_unit_position)
        self.assertIn("Continued context · First Division", review)
        self.assertIn("القسم الأول", review)
        self.assertIn(binding["contexts"][-1]["sourceOccurrenceId"], review)
        self.assertIn(binding["contexts"][-1]["displayContextId"], review)

    def test_machine_readiness_rejects_missing_or_drifted_slice_context(self):
        packet = self.packet()
        complete_autonomous_stages(packet)
        packet.pop("sliceContext")
        errors = MODULE.validate_packet(packet, machine_ready=True)
        self.assertIn("packet: inherited slice context is missing", errors)

        proposal = MODULE.load_json(ISSUE_0026_PROPOSAL)
        authority = {
            "commit": proposal["sourceAuthority"]["commit"],
            "sha256": proposal["sourceAuthority"]["sha256"],
        }
        binding, _ = MODULE.slice_context(1538, authority, ISSUE_0026_PROPOSAL)
        binding["sourceProposalSha256"] = "0" * 64
        drifted = self.packet()
        drifted["assignment"]["startUnit"] = 1538
        drifted["assignment"]["endUnit"] = 1539
        drifted["authority"].update(authority)
        drifted["sliceContext"] = binding
        for ordinal, entry in enumerate(drifted["entries"], start=1538):
            entry["sourceOrdinal"] = ordinal
        errors = MODULE.validate_packet(drifted, machine_ready=True)
        self.assertIn(
            "packet: inherited slice context binding is stale or incomplete",
            errors,
        )

    def test_assignment_overlap_is_rejected(self):
        claims = MODULE.parse_claims([assignment_issue(number=30, start=1, end=3)])
        overlaps = MODULE.overlapping_claims(claims, 1, 2)
        self.assertEqual([claim["number"] for claim in overlaps], [30])

    def test_live_assignment_recheck_rejects_new_overlap(self):
        packet = self.packet()
        issue = assignment_issue()
        claims = MODULE.parse_claims(
            [issue, assignment_issue(number=31, start=2, end=3)]
        )
        errors = MODULE.validate_live_assignment(packet, issue, claims)
        self.assertTrue(any("overlaps open claim" in error for error in errors))

    def test_packet_covers_claim_and_validates_prepared_state(self):
        packet = self.packet()
        self.assertEqual(
            [entry["sourceEntryNumber"] for entry in packet["entries"]],
            [11426, 11427],
        )
        self.assertEqual(MODULE.validate_packet(packet), [])

    def test_prepared_validation_rejects_stale_completed_blind_policy(self):
        packet = self.packet()
        complete_autonomous_stages(packet)
        stale_policy = "0" * 64
        packet["entries"][0]["blindTranslation"]["policySha256"] = stale_policy
        structural = packet["entries"][0]["precedingTranslations"][0]
        structural["blindTranslation"]["policySha256"] = stale_policy

        errors = MODULE.validate_packet(packet, machine_ready=False)

        self.assertEqual(
            sum("blind translation used a stale policy" in error for error in errors),
            2,
        )
        self.assertTrue(any("preceding segment" in error for error in errors))

    def test_packet_requires_exact_preceding_segment_coverage(self):
        packet = self.packet()
        packet["entries"][0]["precedingTranslations"].pop()
        self.assertTrue(
            any(
                "preceding translations must exactly cover source segments" in error
                for error in MODULE.validate_packet(packet)
            )
        )

    def test_entry_shard_merge_is_atomic_and_source_locked(self):
        completed = self.packet()
        complete_autonomous_stages(completed)
        output_fields = (
            "sourceOrdinal",
            "sourceUnitId",
            "blindTranslation",
            "independentCritique",
            "witnessResolution",
            "adjudication",
            "names",
            "unresolved",
            "humanReview",
        )
        outputs = [
            {field: entry[field] for field in output_fields}
            for entry in completed["entries"]
        ]
        shard = {
            "schemaVersion": "1.0.0",
            "packetId": completed["packetId"],
            "issueNumber": completed["assignment"]["issueNumber"],
            "startUnit": 1,
            "endUnit": 2,
            "entries": outputs,
        }
        with tempfile.TemporaryDirectory() as temporary:
            packet_path = Path(temporary) / "packet.json"
            shard_path = Path(temporary) / "shard.json"
            packet_path.write_bytes(MODULE.json_bytes(self.packet()))
            shard_path.write_bytes(MODULE.json_bytes(shard))
            self.assertEqual(MODULE.merge_entry_shard(packet_path, shard_path), 2)
            merged = MODULE.load_json(packet_path)
            self.assertTrue(
                merged["entries"][0]["adjudication"]["english"].startswith(
                    "Adjudicated English for entry 1."
                )
            )

            original = packet_path.read_bytes()
            shard["entries"][0]["sourceUnitId"] = "wrong-source-unit"
            shard_path.write_bytes(MODULE.json_bytes(shard))
            with self.assertRaisesRegex(MODULE.WorkflowError, "sourceUnitId"):
                MODULE.merge_entry_shard(packet_path, shard_path)
            self.assertEqual(packet_path.read_bytes(), original)

    def test_entry_shard_rejects_unavailable_witness(self):
        completed = self.packet()
        complete_autonomous_stages(completed)
        output = {
            field: completed["entries"][0][field]
            for field in (
                "sourceOrdinal",
                "sourceUnitId",
                "blindTranslation",
                "independentCritique",
                "witnessResolution",
                "adjudication",
                "names",
                "unresolved",
                "humanReview",
            )
        }
        output["independentCritique"]["findings"] = [
            {
                "findingId": "source-reading-1",
                "kind": "source-reading",
                "requiresWitness": True,
            }
        ]
        output["witnessResolution"] = {
            "status": "pending",
            "results": [{"status": "unavailable"}],
        }
        shard = {
            "schemaVersion": "1.0.0",
            "packetId": completed["packetId"],
            "issueNumber": completed["assignment"]["issueNumber"],
            "startUnit": 1,
            "endUnit": 1,
            "entries": [output],
        }
        with tempfile.TemporaryDirectory() as temporary:
            packet_path = Path(temporary) / "packet.json"
            shard_path = Path(temporary) / "shard.json"
            packet_path.write_bytes(MODULE.json_bytes(self.packet()))
            shard_path.write_bytes(MODULE.json_bytes(shard))
            with self.assertRaisesRegex(MODULE.WorkflowError, "not final"):
                MODULE.merge_entry_shard(packet_path, shard_path)

    def test_shard_merges_reject_completed_post_run_repairs(self):
        completed = self.packet()
        complete_autonomous_stages(completed)
        output_fields = (
            "sourceOrdinal",
            "sourceUnitId",
            "blindTranslation",
            "independentCritique",
            "witnessResolution",
            "adjudication",
            "names",
            "unresolved",
            "humanReview",
        )
        entry_shard = {
            "schemaVersion": "1.0.0",
            "packetId": completed["packetId"],
            "issueNumber": completed["assignment"]["issueNumber"],
            "startUnit": 1,
            "endUnit": 2,
            "entries": [
                {field: entry[field] for field in output_fields}
                for entry in completed["entries"]
            ],
        }
        structural_shard = {
            "schemaVersion": "1.1.0",
            "packetId": completed["packetId"],
            "issueNumber": completed["assignment"]["issueNumber"],
            "sourceOrdinal": 1,
            "precedingTranslations": completed["entries"][0][
                "precedingTranslations"
            ],
        }
        packet = self.packet()
        packet["postRunRepairAudits"] = [
            {
                "status": "complete",
                "previousAuditSha256": None,
                "basePacketSha256": "1" * 64,
                "artifactSha256": "2" * 64,
                "runId": "translation-repair-run-1234567890abcdef",
                "operations": [{"repairId": "already-applied"}],
            }
        ]
        with tempfile.TemporaryDirectory() as temporary:
            packet_path = Path(temporary) / "packet.json"
            entry_path = Path(temporary) / "entry-shard.json"
            structural_path = Path(temporary) / "structural-shard.json"
            original = MODULE.json_bytes(packet)
            packet_path.write_bytes(original)
            entry_path.write_bytes(MODULE.json_bytes(entry_shard))
            structural_path.write_bytes(MODULE.json_bytes(structural_shard))
            with self.assertRaisesRegex(MODULE.WorkflowError, "post-run repairs"):
                MODULE.merge_entry_shard(packet_path, entry_path)
            with self.assertRaisesRegex(MODULE.WorkflowError, "post-run repairs"):
                MODULE.merge_preceding_shard(packet_path, structural_path)
            self.assertEqual(packet_path.read_bytes(), original)

    def test_structural_shard_merge_requires_exact_segment_ids(self):
        completed = self.packet()
        complete_autonomous_stages(completed)
        shard = {
            "schemaVersion": "1.1.0",
            "packetId": completed["packetId"],
            "issueNumber": completed["assignment"]["issueNumber"],
            "sourceOrdinal": 1,
            "precedingTranslations": completed["entries"][0][
                "precedingTranslations"
            ],
        }
        with tempfile.TemporaryDirectory() as temporary:
            packet_path = Path(temporary) / "packet.json"
            shard_path = Path(temporary) / "structural-shard.json"
            packet_path.write_bytes(MODULE.json_bytes(self.packet()))
            shard_path.write_bytes(MODULE.json_bytes(shard))
            self.assertEqual(MODULE.merge_preceding_shard(packet_path, shard_path), 3)
            merged = MODULE.load_json(packet_path)
            self.assertEqual(
                merged["entries"][0]["precedingTranslations"][0]["adjudication"]
                ["english"],
                "Adjudicated source prose.",
            )

            original = packet_path.read_bytes()
            shard["precedingTranslations"][0]["segmentId"] = "wrong-segment"
            shard_path.write_bytes(MODULE.json_bytes(shard))
            with self.assertRaisesRegex(MODULE.WorkflowError, "exactly"):
                MODULE.merge_preceding_shard(packet_path, shard_path)
            self.assertEqual(packet_path.read_bytes(), original)

    def test_multi_unit_structural_shard_requires_every_owner_in_range(self):
        completed = self.packet()
        complete_autonomous_stages(completed)
        source_units = [
            {
                "sourceOrdinal": entry["sourceOrdinal"],
                "precedingTranslations": entry["precedingTranslations"],
            }
            for entry in completed["entries"]
            if entry["source"]["precedingSegments"]
        ]
        shard = {
            "schemaVersion": "1.1.0",
            "packetId": completed["packetId"],
            "issueNumber": completed["assignment"]["issueNumber"],
            "startUnit": 1,
            "endUnit": 2,
            "sourceUnits": source_units,
        }
        expected_segments = sum(
            len(item["precedingTranslations"]) for item in source_units
        )
        with tempfile.TemporaryDirectory() as temporary:
            packet_path = Path(temporary) / "packet.json"
            shard_path = Path(temporary) / "structural-shard.json"
            prepared = self.packet()
            original = MODULE.json_bytes(prepared)
            packet_path.write_bytes(original)
            shard_path.write_bytes(MODULE.json_bytes(shard))
            self.assertEqual(
                MODULE.merge_preceding_shard(packet_path, shard_path),
                expected_segments,
            )
            merged = MODULE.load_json(packet_path)
            self.assertEqual(
                merged["entries"][1]["precedingTranslations"][0]["adjudication"]
                ["english"],
                "Adjudicated source prose.",
            )

            packet_path.write_bytes(original)
            shard["sourceUnits"].pop()
            shard_path.write_bytes(MODULE.json_bytes(shard))
            with self.assertRaisesRegex(MODULE.WorkflowError, "exactly cover"):
                MODULE.merge_preceding_shard(packet_path, shard_path)
            self.assertEqual(packet_path.read_bytes(), original)

    def test_packet_rejects_stale_policy(self):
        packet = self.packet()
        packet["policy"]["bindingSha256"] = "0" * 64
        self.assertIn("packet: policy binding is stale", MODULE.validate_packet(packet))

    def test_machine_ready_production_packet_enforces_governed_title_projection(self):
        packet = self.packet()
        complete_autonomous_stages(packet)
        original_load = MODULE.load_json

        def production_manifest(path):
            value = original_load(path)
            if Path(path).resolve() == FIXTURE_MANIFEST.resolve():
                value = copy.deepcopy(value)
                value["status"] = "active"
            return value

        with mock.patch.object(MODULE, "load_json", side_effect=production_manifest):
            errors = MODULE.validate_packet(packet, machine_ready=True)
        self.assertTrue(
            any(
                "public title projection failed" in error
                or "lacks a governed title decision" in error
                for error in errors
            ),
            errors,
        )

    def test_machine_ready_requires_independent_critique(self):
        packet = self.packet()
        complete_autonomous_stages(packet)
        packet["entries"][0]["independentCritique"]["runId"] = packet["entries"][0][
            "blindTranslation"
        ]["runId"]
        packet["reviewPresentation"] = {
            "status": "ready",
            "path": "review.md",
            "sha256": "0" * 64,
        }
        packet["machineReadiness"] = {
            "status": "ready",
            "validatedAt": "2026-08-14T00:00:00Z",
            "validatorVersion": MODULE.TOOL_VERSION,
        }
        self.assertTrue(
            any(
                "critique must use a distinct run" in error
                for error in MODULE.validate_packet(packet, machine_ready=True)
            )
        )

    def test_machine_ready_requires_content_bound_semantic_audit(self):
        packet = self.packet()
        complete_autonomous_stages(packet)
        audit = packet["entries"][0]["independentCritique"]["semanticAudit"]
        audit["sourceSha256"] = "0" * 64
        errors = MODULE.validate_packet(packet, machine_ready=True)
        self.assertTrue(
            any("semantic critique source hash is stale" in error for error in errors)
        )

        complete_autonomous_stages(packet)
        packet["entries"][0]["independentCritique"]["semanticAudit"]["checks"] = []
        errors = MODULE.validate_packet(packet, machine_ready=True)
        self.assertTrue(
            any("explicitly cover every required category" in error for error in errors)
        )

    def test_prepared_packet_carries_pending_stage_provenance(self):
        packet = self.packet()
        owners = [
            owner
            for entry in packet["entries"]
            for owner in [entry, *entry["precedingTranslations"]]
        ]
        for owner in owners:
            for field in (
                "blindTranslation",
                "independentCritique",
                "witnessResolution",
                "adjudication",
                "names",
            ):
                self.assertEqual(owner[field]["provenance"]["status"], "pending")
            self.assertEqual(
                owner["independentCritique"]["independentContext"]["status"],
                "pending",
            )
            self.assertEqual(
                owner["names"]["independentContext"]["status"], "pending"
            )

    def test_schema_1_4_packet_cannot_be_machine_ready(self):
        packet = self.packet()
        complete_autonomous_stages(packet)
        packet["schemaVersion"] = "1.4.0"
        packet["toolVersion"] = "1.4.0"
        errors = MODULE.validate_packet(packet, machine_ready=True)
        self.assertTrue(any("schemaVersion must be 1.5.0" in error for error in errors))
        self.assertTrue(any("toolVersion must be 1.5.0" in error for error in errors))

    def test_status_run_and_content_hashes_do_not_replace_stage_provenance(self):
        packet = self.packet()
        complete_autonomous_stages(packet)
        critique = packet["entries"][0]["independentCritique"]
        critique.pop("provenance")
        errors = MODULE.validate_packet(packet, machine_ready=True)
        self.assertTrue(
            any("content-addressed provenance is incomplete" in error for error in errors)
        )

    def test_machine_ready_requires_internal_context_self_attestation(self):
        packet = self.packet()
        complete_autonomous_stages(packet)
        critique = packet["entries"][0]["independentCritique"]
        critique["independentContext"]["receipt"] = None
        errors = MODULE.validate_packet(packet, machine_ready=True)
        self.assertTrue(
            any(
                "context self-attestation receipt is incomplete" in error
                for error in errors
            )
        )

        complete_autonomous_stages(packet)
        names = packet["entries"][0]["names"]
        names["independentContext"]["receipt"] = None
        errors = MODULE.validate_packet(packet, machine_ready=True)
        self.assertTrue(
            any(
                "context self-attestation receipt is incomplete" in error
                for error in errors
            )
        )

    def test_stage_provenance_detects_upstream_output_drift(self):
        packet = self.packet()
        complete_autonomous_stages(packet)
        packet["entries"][0]["blindTranslation"]["english"] += " Drift."
        errors = MODULE.validate_packet(packet, machine_ready=True)
        self.assertTrue(
            any("blind_translation outputSha256 is stale" in error for error in errors)
        )
        self.assertTrue(
            any("independent_critique upstreamSha256 is stale" in error for error in errors)
        )

    def test_canned_witness_rationale_alone_is_not_stage_evidence(self):
        packet = self.packet()
        complete_autonomous_stages(packet)
        witness = packet["entries"][0]["witnessResolution"]
        witness["provenance"] = MODULE.pending_stage_provenance(
            "witness_resolution"
        )
        errors = MODULE.validate_packet(packet, machine_ready=True)
        self.assertTrue(
            any(
                "witness_resolution content-addressed provenance is incomplete" in error
                for error in errors
            )
        )

    def test_name_candidate_requires_grounded_english_form(self):
        packet = self.packet()
        complete_autonomous_stages(packet)
        entry = packet["entries"][0]
        candidate = entry["names"]["candidates"][0]
        candidate["proposedEnglish"] = "An absent English rendering"
        candidate["aliases"] = []
        errors = MODULE.validate_names(
            entry["names"],
            entry["source"],
            None,
            entry["adjudication"]["english"],
            entry["sourceUnitId"],
            "test",
            require_spans=True,
        )
        self.assertTrue(
            any("no English form in the adjudicated translation" in error for error in errors),
            errors,
        )

    def test_name_candidate_grounding_rejects_stale_close_romanization(self):
        packet = self.packet()
        complete_autonomous_stages(packet)
        entry = packet["entries"][0]
        candidate = entry["names"]["candidates"][0]
        candidate["proposedEnglish"] = "Khudayj ibn Rāfiʿ"
        candidate["aliases"] = []
        entry["adjudication"]["english"] = (
            "Khadīj ibn Rāfiʿ transmitted the report."
        )
        entry["names"]["inventoryAudit"]["englishSha256"] = (
            MODULE.semantic_candidate_sha256(
                None, entry["adjudication"]["english"]
            )
        )

        errors = MODULE.validate_names(
            entry["names"],
            entry["source"],
            None,
            entry["adjudication"]["english"],
            entry["sourceUnitId"],
            "test",
            require_spans=True,
        )
        self.assertTrue(
            any("no English form in the adjudicated translation" in error for error in errors),
            errors,
        )

        candidate["proposedEnglish"] = "Khadīj ibn Rāfiʿ"
        self.assertEqual(
            MODULE.validate_names(
                entry["names"],
                entry["source"],
                None,
                entry["adjudication"]["english"],
                entry["sourceUnitId"],
                "test",
                require_spans=True,
            ),
            [],
        )

    def _formula_internal_name_case(self):
        record_id = "openiti-test-unit-formula-name"
        formula = "اللهم بارك على محمد وعلى آل محمد"
        arabic = f"قال الراوي {formula} ثم سكت"
        observed = "آل محمد"
        start = arabic.index(observed)
        end = start + len(observed)
        adjudicated = f"The narrator preserved the prayer verbatim: {formula}."
        names = {
            "status": "complete",
            "candidates": [
                {
                    "candidateId": "formula-collective-001",
                    "observedArabic": observed,
                    "proposedEnglish": "the family of Muḥammad",
                    "aliases": [],
                    "confidenceEvidence": [
                        "Exact formula-internal collective with accessible English grounding."
                    ],
                    "reviewState": "unreviewed",
                    "entityType": "collective",
                }
            ],
            "mentions": [
                {
                    "mentionId": "formula-collective-001-mention-001",
                    "candidateId": "formula-collective-001",
                    "originCandidateId": "formula-collective-001",
                    "recordId": record_id,
                    "location": "entry-body-quoted-prayer",
                    "sourceSpans": [
                        {
                            "sourceField": "arabic",
                            "start": start,
                            "end": end,
                            "sha256": MODULE.text_sha256(observed),
                        }
                    ],
                }
            ],
            "inventoryAudit": {
                "status": "complete",
                "sourceSha256": MODULE.semantic_source_sha256(
                    {"headingArabic": None, "arabic": arabic}
                ),
                "englishSha256": MODULE.semantic_candidate_sha256(
                    None, adjudicated
                ),
                "runId": "formula-name-test-run",
                "method": "Exact bilingual formula-name test.",
                "assessment": "One collective and one exact mention.",
            },
        }
        occurrence = {
            "recordId": record_id,
            "sourceField": "arabic",
            "sourceStart": arabic.index(formula),
            "sourceEnd": arabic.index(formula) + len(formula),
            "accessibleEnglish": (
                "O God, bless Muḥammad and the family of Muḥammad."
            ),
        }
        return names, arabic, adjudicated, occurrence, record_id

    def test_formula_internal_name_uses_exact_accessible_english_grounding(self):
        names, arabic, adjudicated, occurrence, record_id = (
            self._formula_internal_name_case()
        )
        self.assertEqual(
            MODULE.validate_names(
                names,
                {"headingArabic": None, "arabic": arabic},
                None,
                adjudicated,
                record_id,
                "test",
                require_spans=True,
                formula_occurrences=[occurrence],
            ),
            [],
        )

    def test_formula_accessibility_cannot_bypass_name_grounding_guards(self):
        names, arabic, adjudicated, occurrence, record_id = (
            self._formula_internal_name_case()
        )
        cases = []

        unnested = copy.deepcopy(occurrence)
        unnested["sourceStart"] = names["mentions"][0]["sourceSpans"][0]["end"]
        cases.append((copy.deepcopy(names), [unnested], "unnested span"))

        wrong_record = copy.deepcopy(occurrence)
        wrong_record["recordId"] = "different-record"
        cases.append((copy.deepcopy(names), [wrong_record], "wrong record"))

        inexact = copy.deepcopy(names)
        inexact["candidates"][0]["proposedEnglish"] = (
            "the household of Muḥammad"
        )
        inexact["candidates"][0]["aliases"] = ["the family of Muḥammad"]
        cases.append((inexact, [copy.deepcopy(occurrence)], "alias-only match"))

        for case_names, occurrences, label in cases:
            with self.subTest(label=label):
                errors = MODULE.validate_names(
                    case_names,
                    {"headingArabic": None, "arabic": arabic},
                    None,
                    adjudicated,
                    record_id,
                    "test",
                    require_spans=True,
                    formula_occurrences=occurrences,
                )
                self.assertTrue(
                    any(
                        "no English form in the adjudicated translation" in error
                        for error in errors
                    ),
                    errors,
                )

    def test_name_candidate_allows_pronunciation_note_inside_canonical_form(self):
        packet = self.packet()
        complete_autonomous_stages(packet)
        entry = packet["entries"][0]
        entry["names"]["candidates"][0]["proposedEnglish"] = "Duba'a al-Anṣārī"
        entry["adjudication"]["english"] = (
            "Duba'a—with an open first letter—al-Anṣārī transmitted the report."
        )
        entry["names"]["inventoryAudit"]["englishSha256"] = (
            MODULE.semantic_candidate_sha256(None, entry["adjudication"]["english"])
        )
        self.assertEqual(
            MODULE.validate_names(
                entry["names"],
                entry["source"],
                None,
                entry["adjudication"]["english"],
                entry["sourceUnitId"],
                "test",
                require_spans=True,
            ),
            [],
        )

    def test_machine_ready_requires_review_presentation_path(self):
        packet = self.packet()
        complete_autonomous_stages(packet)
        inventory, formula_errors = MODULE.formula_inventory(packet)
        self.assertEqual(formula_errors, [])
        packet["formulaInventory"] = inventory
        packet["reviewPresentation"] = {
            "status": "ready",
            "path": None,
            "sha256": "0" * 64,
        }
        packet["machineReadiness"] = {
            "status": "ready",
            "validatedAt": "2026-08-14T00:00:00Z",
            "validatorVersion": MODULE.TOOL_VERSION,
        }
        errors = MODULE.validate_packet(packet, machine_ready=True)
        self.assertIn("packet: review presentation is not ready", errors)

    def test_material_uncertainty_requires_resolved_witness(self):
        packet = self.packet()
        complete_autonomous_stages(packet)
        packet["entries"][0]["independentCritique"]["findings"] = [
            {
                "findingId": "ambiguous-name-1",
                "kind": "ambiguous-name",
                "requiresWitness": True,
            }
        ]
        errors = MODULE.validate_packet(packet, machine_ready=True)
        self.assertTrue(any("requires witness resolution" in error for error in errors))

        packet["entries"][0]["independentCritique"]["findings"] = []
        packet["entries"][0]["unresolved"] = [
            {
                "kind": "damaged-reading",
                "description": "The source reading remains materially uncertain.",
                "severity": "material",
                "location": "entry body",
                "disposition": "Resolve against a classified witness.",
            }
        ]
        errors = MODULE.validate_packet(packet, machine_ready=True)
        self.assertTrue(
            any("material unresolved finding requires" in error for error in errors)
        )

    def test_active_editorial_supply_rejects_contradictory_unresolved_state(self):
        unresolved = [
            {
                "kind": "damaged-subject-heading",
                "description": "The subject head still lacks an editorial-supply model.",
                "severity": "material",
                "location": "entry title",
                "disposition": "needs_attention",
            }
        ]
        supplies = {
            2784: {
                "sourceEntryNumber": 2784,
                "editorialSupply": {"kind": "witness-bound-subject-head"},
            }
        }
        self.assertEqual(
            MODULE.validate_unresolved_editorial_supply_state(
                unresolved, 2784, supplies, "test"
            ),
            [
                "test, unresolved item 1: damaged-subject-heading state "
                "contradicts the active witness-bound editorial supply"
            ],
        )
        self.assertEqual(
            MODULE.validate_unresolved_editorial_supply_state(
                [], 2784, supplies, "test"
            ),
            [],
        )
        self.assertEqual(
            MODULE.validate_unresolved_editorial_supply_state(
                unresolved, 2880, supplies, "test"
            ),
            [],
        )

    def test_machine_ready_witness_requires_canonical_hashed_provenance(self):
        passage = "Exact short witness reading."
        result = {
            "status": "hit",
            "findingIds": ["ambiguous-name-1"],
            "query": "Which reading is attested?",
            "witnessRole": "alternative_edition",
            "witnessIdentity": "Public test facsimile",
            "passage": passage,
            "passageSha256": MODULE.text_sha256(passage),
            "location": "volume 1, page 1",
            "evidenceKind": "passage",
            "evidenceSha256": MODULE.text_sha256(passage),
            "decision": "The reading is confirmed.",
            "retrievedAt": "2026-08-14",
        }
        self.assertEqual(
            MODULE.validate_witness(
                {"status": "complete", "results": [result]},
                [{"findingId": "ambiguous-name-1", "requiresWitness": True}],
                "test",
                strict=True,
            ),
            [],
        )
        self.assertTrue(
            any(
                "requires evidence" in error
                for error in MODULE.validate_witness(
                    {"status": "complete", "results": []},
                    [],
                    "test",
                    strict=True,
                )
            )
        )
        legacy = {"status": "hit", "detail": "Unpinned result"}
        self.assertTrue(
            any(
                "not canonical" in error
                for error in MODULE.validate_witness(
                    {"status": "complete", "results": [legacy]},
                    [
                        {
                            "findingId": "ambiguous-name-1",
                            "requiresWitness": True,
                        }
                    ],
                    "test",
                    strict=True,
                )
            )
        )

    def test_witness_result_hash_must_be_attached_to_witness_provenance(self):
        packet = self.packet()
        complete_autonomous_stages(packet)
        entry = packet["entries"][0]
        passage = "Exact short witness reading."
        evidence_sha256 = MODULE.text_sha256(passage)
        result = {
            "status": "hit",
            "findingIds": ["ambiguous-name-1"],
            "query": "Which reading is attested?",
            "witnessRole": "alternative_edition",
            "witnessIdentity": "Public test facsimile",
            "passage": passage,
            "passageSha256": evidence_sha256,
            "location": "volume 1, page 1",
            "evidenceKind": "passage",
            "evidenceSha256": evidence_sha256,
            "decision": "The reading is confirmed.",
            "retrievedAt": "2026-08-14",
        }
        witness = entry["witnessResolution"]
        witness.update(
            {
                "status": "complete",
                "results": [result],
                "notRequiredRationale": None,
            }
        )
        evidence = [
            {
                "evidenceId": "witness-result-regression-1",
                "role": "witness_result",
                "sha256": evidence_sha256,
            }
        ]
        witness["provenance"] = MODULE.completed_stage_provenance(
            witness,
            "witness_resolution",
            entry["source"],
            [("independent_critique", entry["independentCritique"])],
            packet["policy"]["bindingSha256"],
            "deterministic-witness-gate",
            "source-bound",
            evidence,
            run_id="witness-result-regression",
        )
        linked_errors = MODULE.validate_stage_provenance(
            witness,
            "witness_resolution",
            entry["source"],
            [("independent_critique", entry["independentCritique"])],
            packet["policy"]["bindingSha256"],
            "test",
        )
        self.assertFalse(
            any("witness result evidence is not attached" in error for error in linked_errors),
            linked_errors,
        )

        witness["provenance"] = MODULE.completed_stage_provenance(
            witness,
            "witness_resolution",
            entry["source"],
            [("independent_critique", entry["independentCritique"])],
            packet["policy"]["bindingSha256"],
            "deterministic-witness-gate",
            "source-bound",
            [],
            run_id="witness-result-regression",
        )
        unlinked_errors = MODULE.validate_stage_provenance(
            witness,
            "witness_resolution",
            entry["source"],
            [("independent_critique", entry["independentCritique"])],
            packet["policy"]["bindingSha256"],
            "test",
        )
        self.assertIn(
            "test: witness result evidence is not attached",
            unlinked_errors,
        )

    def test_machine_ready_names_require_exact_source_spans(self):
        packet = self.packet()
        complete_autonomous_stages(packet)
        entry = packet["entries"][0]
        self.assertEqual(
            MODULE.validate_names(
                entry["names"],
                entry["source"],
                None,
                entry["adjudication"]["english"],
                entry["sourceUnitId"],
                "test",
                require_spans=True,
            ),
            [],
        )
        entry["names"]["mentions"][0]["sourceSpans"][0]["start"] += 1
        self.assertTrue(
            any(
                "does not match observed Arabic" in error
                for error in MODULE.validate_names(
                    entry["names"],
                    entry["source"],
                    None,
                    entry["adjudication"]["english"],
                    entry["sourceUnitId"],
                    "test",
                    require_spans=True,
                )
            )
        )

    def test_unresolved_items_require_canonical_classification(self):
        canonical = {
            "kind": "source-variant",
            "description": "Two readings remain attested.",
            "severity": "source_reported",
            "location": "entry body",
            "disposition": "Preserve both readings for human review.",
        }
        self.assertEqual(MODULE.validate_unresolved([canonical], "test", True), [])
        self.assertTrue(
            MODULE.validate_unresolved([{"detail": "Unclassified"}], "test", True)
        )

    def test_openiti_poetry_marker_is_rendered_as_a_line_boundary(self):
        rendered = MODULE.present_openiti_arabic("prose % first % second")
        self.assertNotIn("%", rendered)
        self.assertEqual(rendered.count("<br />"), 2)

    def test_machine_ready_requires_every_preceding_segment_translation(self):
        packet = self.packet()
        complete_autonomous_stages(packet)
        first = packet["entries"][0]["precedingTranslations"][0]
        first["adjudication"]["english"] = None
        errors = MODULE.validate_packet(packet, machine_ready=True)
        self.assertTrue(
            any(
                "adjudicated substantive prose is untranslated" in error
                for error in errors
            )
        )

    def test_render_finalizes_machine_ready_packet_without_human_approval(self):
        packet = self.packet()
        complete_autonomous_stages(packet)
        with tempfile.TemporaryDirectory() as directory:
            packet_path = Path(directory) / "issue-0025.json"
            MODULE.atomic_write(packet_path, MODULE.json_bytes(packet))
            review_path = MODULE.finalize_packet(packet_path)
            final = MODULE.load_json(packet_path)
            self.assertTrue(review_path.is_file())
            review = review_path.read_text(encoding="utf-8")
            self.assertIn("Adjudicated source prose.", review)
            self.assertIn("هذا تمهيد أصلي", review)
            self.assertIn("قال مؤلفه فرغت", review)
            self.assertNotIn("### |PARATEXT|", review)
            self.assertNotIn("مقدمة حديثة للمحقق", review)
            self.assertNotIn("#META# 020.BookTITLE", review)
            self.assertEqual(final["machineReadiness"]["status"], "ready")
            self.assertEqual(final["formulaInventory"]["status"], "complete")
            self.assertGreater(len(final["formulaInventory"]["occurrences"]), 0)
            self.assertTrue(
                all(
                    occurrence["accessibleEnglish"]
                    for occurrence in final["formulaInventory"]["occurrences"]
                )
            )
            self.assertIn("## Formula key", review)
            self.assertTrue(
                all(
                    entry["humanReview"]["status"] == "unreviewed"
                    for entry in final["entries"]
                )
            )
            self.assertEqual(MODULE.validate_packet(final, machine_ready=True), [])

    def test_formula_registry_covers_contextual_and_source_damaged_prayers(self):
        contextual = (
            "صلى الله عليه وعليهم صلاة خالدة ، وسلاما مؤبدا [ وسلم تسليما ]"
        )
        contextual_target = (
            "May God bless him and them with an everlasting blessing and grant "
            "them perpetual peace [and fullest peace]."
        )
        damaged = "صلى الله علسه وسلم"
        self.assertEqual(
            MODULE.registered_occurrences(contextual, "source")[0]["rule"][
                "semanticClass"
            ],
            "contextual_prayer_and_peace_invocation",
        )
        self.assertEqual(
            MODULE.registered_occurrences(contextual_target, "target")[0]["value"],
            contextual_target,
        )
        self.assertEqual(
            MODULE.registered_occurrences(damaged, "source")[0]["rule"]["target"],
            "ﷺ",
        )
        transposed_family = "صلى الله عليه وسلم وآله وسلم"
        family_occurrences = MODULE.registered_occurrences(
            transposed_family,
            "source",
        )
        self.assertEqual(len(family_occurrences), 1)
        self.assertEqual(family_occurrences[0]["rule"]["target"], "﵌")
        self.assertEqual(
            family_occurrences[0]["rule"]["semanticClass"],
            "prophetic_blessing_with_family",
        )
        page_split_family = "صلى 204 الله عليه وآله وسلم"
        page_split_occurrences = MODULE.registered_occurrences(
            page_split_family,
            "source",
        )
        self.assertEqual(len(page_split_occurrences), 1)
        self.assertEqual(page_split_occurrences[0]["rule"]["target"], "﵌")
        mid_formula_page_split = "صلى الله 207 عليه وآله وسلم"
        mid_formula_occurrences = MODULE.registered_occurrences(
            mid_formula_page_split,
            "source",
        )
        self.assertEqual(len(mid_formula_occurrences), 1)
        self.assertEqual(mid_formula_occurrences[0]["rule"]["target"], "﵌")
        self.assertEqual(
            MODULE.registered_occurrences("والله اعلم", "source")[0]["rule"][
                "target"
            ],
            "والله أعلم",
        )
        self.assertTrue(
            all(rule["accessibleEnglish"] for rule in MODULE.FORMULA_RULES)
        )

    def test_machine_readable_formula_registry_matches_the_workflow(self):
        registry = MODULE.load_json(MODULE.FORMULA_REGISTRY_PATH)
        self.assertEqual(
            registry["schema"],
            "al-isabah.honorific-formula-registry.v1",
        )
        self.assertEqual(
            registry["registryVersion"],
            MODULE.FORMULA_REGISTRY_VERSION,
        )
        self.assertEqual(registry["contractId"], "translation-quality-workflow")
        self.assertEqual(registry["profileId"], "al-isabah-translation-profile")
        self.assertEqual(registry["entries"], list(MODULE.FORMULA_RULES))

    def test_formula_inventory_rejects_lost_exaltation_semantics(self):
        packet = self.packet()
        complete_autonomous_stages(packet)
        packet["entries"][0]["source"]["arabic"] = "إن شاء الله تعالى"
        packet["entries"][0]["blindTranslation"]["english"] = "إن شاء الله"
        packet["entries"][0]["adjudication"]["english"] = "إن شاء الله"
        _, errors = MODULE.formula_inventory(packet)
        self.assertTrue(
            any("blind devotional formulas do not match" in error for error in errors)
        )
        self.assertTrue(
            any(
                "adjudicated devotional formulas do not match" in error
                for error in errors
            )
        )

    def test_public_english_rejects_internal_source_lock_language(self):
        for phrase in ("pinned OpenITI", "pinned wording", "pinned text", "pinned unit"):
            self.assertTrue(MODULE.validate_public_english(phrase, "candidate"))
        self.assertEqual(
            MODULE.registered_occurrences("صلى آله عليه وسلم", "source")[0][
                "rule"
            ]["target"],
            "ﷺ",
        )

    def test_submit_is_immutable_and_copies_only_validated_artifacts(self):
        packet = self.packet()
        complete_autonomous_stages(packet)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            packet_path = root / "runtime" / "issue-0025.json"
            MODULE.atomic_write(packet_path, MODULE.json_bytes(packet))
            MODULE.finalize_packet(packet_path)
            output_root = root / "proposals"
            proposal, review = MODULE.submit_packet(
                packet_path, output_root, allow_test_fixture=True
            )
            self.assertTrue(proposal.is_file())
            self.assertTrue(review.is_file())
            with self.assertRaisesRegex(MODULE.WorkflowError, "never overwrite"):
                MODULE.submit_packet(
                    packet_path, output_root, allow_test_fixture=True
                )

    def test_submit_rejects_review_drift_after_packet_mutation(self):
        packet = self.packet()
        complete_autonomous_stages(packet)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            packet_path = root / "issue-0025.json"
            MODULE.atomic_write(packet_path, MODULE.json_bytes(packet))
            MODULE.finalize_packet(packet_path)
            mutated = MODULE.load_json(packet_path)
            mutated["entries"][0]["adjudication"]["english"] += " Changed later."
            mutated["entries"][0]["names"]["inventoryAudit"]["englishSha256"] = (
                MODULE.semantic_candidate_sha256(
                    None, mutated["entries"][0]["adjudication"]["english"]
                )
            )
            entry = mutated["entries"][0]
            adjudication = entry["adjudication"]
            adjudication_provenance = adjudication["provenance"]
            adjudication["provenance"] = MODULE.completed_stage_provenance(
                adjudication,
                "adjudication",
                entry["source"],
                [
                    ("blind_translation", entry["blindTranslation"]),
                    ("independent_critique", entry["independentCritique"]),
                    ("witness_resolution", entry["witnessResolution"]),
                ],
                mutated["policy"]["bindingSha256"],
                adjudication_provenance["model"],
                adjudication_provenance["reasoning"],
                adjudication_provenance["evidence"],
                run_id=adjudication_provenance["runId"],
            )
            names = entry["names"]
            name_provenance = names["provenance"]
            names["independentContext"]["inputSha256"] = MODULE.stage_input_sha256(
                "name_inventory",
                MODULE.semantic_source_sha256(entry["source"]),
                MODULE.stage_upstream_sha256(
                    [("adjudication", adjudication)]
                ),
                mutated["policy"]["bindingSha256"],
                MODULE.packet_schema_sha256(),
                name_provenance["model"],
                name_provenance["reasoning"],
                MODULE.stage_evidence_sha256(name_provenance["evidence"]),
            )
            names["provenance"] = MODULE.completed_stage_provenance(
                names,
                "name_inventory",
                entry["source"],
                [("adjudication", adjudication)],
                mutated["policy"]["bindingSha256"],
                name_provenance["model"],
                name_provenance["reasoning"],
                name_provenance["evidence"],
            )
            MODULE.atomic_write(packet_path, MODULE.json_bytes(mutated))
            with self.assertRaisesRegex(
                MODULE.WorkflowError,
                "review presentation does not match governed titles",
            ):
                MODULE.submit_packet(
                    packet_path, root / "proposals", allow_test_fixture=True
                )

    def test_submit_rejects_any_public_repository_destination(self):
        with self.assertRaisesRegex(
            MODULE.WorkflowError, "cannot be written inside the public repository"
        ):
            MODULE.submit_packet(
                ROOT / "synthetic-does-not-need-to-exist.json",
                ROOT / "content" / "translation-proposals",
                allow_test_fixture=True,
            )

    def test_machine_validation_enforces_schema_and_packet_scoped_name_ids(self):
        packet = self.packet()
        complete_autonomous_stages(packet)
        duplicate = json.loads(json.dumps(packet["entries"][0]))
        duplicate["sourceOrdinal"] = 2
        duplicate["sourceEntryNumber"] = 2
        duplicate["sourceUnitId"] = "openiti-test-unit-000002"
        duplicate["canonicalEntryId"] = "isabah-entry-00000002"
        duplicate["source"]["sourceOrdinal"] = 2
        duplicate["source"]["sourceEntryNumber"] = 2
        duplicate["source"]["sourceUnitId"] = duplicate["sourceUnitId"]
        duplicate["source"]["precedingSegments"] = []
        duplicate["precedingTranslations"] = []
        packet["entries"].append(duplicate)
        packet["assignment"]["endUnit"] = 2
        packet["assignment"]["printedEntryEnd"] = 2
        packet["entries"][0]["names"]["candidates"][0]["unexpected"] = True
        packet["formulaInventory"], _ = MODULE.formula_inventory(packet)
        errors = MODULE.validate_packet(packet, machine_ready=True)
        self.assertTrue(any("unexpected property 'unexpected'" in e for e in errors))
        self.assertIn("packet: name candidate IDs must be globally unique", errors)

    def test_post_run_repair_audit_detects_output_drift(self):
        packet = self.packet()
        path = "$.entries[0].blindTranslation.english"
        original = packet["entries"][0]["blindTranslation"]["english"] or ""
        packet["entries"][0]["blindTranslation"]["english"] = "Repaired blind text."
        packet["postRunRepairAudits"] = [
            {
                "status": "complete",
                "previousAuditSha256": None,
                "basePacketSha256": "1" * 64,
                "artifactSha256": "2" * 64,
                "runId": "translation-repair-run-1234567890abcdef",
                "operations": [
                {
                    "repairId": "repair-1",
                    "sourceUnitId": packet["entries"][0]["sourceUnitId"],
                    "segmentId": None,
                    "recordKind": "entry",
                    "targetStage": "blind_translation",
                    "fieldPath": path,
                    "valueKind": "text",
                    "oldTextSha256": MODULE.text_sha256(original),
                    "newTextSha256": MODULE.text_sha256("Repaired blind text."),
                    "reasons": [
                        {"code": "test", "explanation": "Test repair provenance."}
                    ],
                }
                ],
            }
        ]
        self.assertEqual(MODULE.validate_post_run_repair_audits(packet), [])
        packet["entries"][0]["blindTranslation"]["english"] = "Drifted."
        self.assertTrue(
            any(
                "target drifted" in error
                for error in MODULE.validate_post_run_repair_audits(packet)
            )
        )

    def test_cumulative_repairs_chain_and_rebind_historical_stage_evidence(self):
        packet = self.packet()
        complete_autonomous_stages(packet)
        entry = packet["entries"][0]
        source = entry["source"]
        policy_sha256 = packet["policy"]["bindingSha256"]
        path = "$.entries[0].blindTranslation.english"
        original = entry["blindTranslation"]["english"]

        def operation(repair_id, old_text, new_text):
            return {
                "repairId": repair_id,
                "sourceUnitId": entry["sourceUnitId"],
                "segmentId": None,
                "recordKind": "entry",
                "targetStage": "blind_translation",
                "fieldPath": path,
                "valueKind": "text",
                "oldTextSha256": MODULE.text_sha256(old_text),
                "newTextSha256": MODULE.text_sha256(new_text),
                "reasons": [
                    {"code": "test", "explanation": "Audited fixture text repair."}
                ],
            }

        def rebind_stage(stage_field, stage_name, upstream, repair_run_ids):
            stage = entry[stage_field]
            previous = copy.deepcopy(stage["provenance"])
            evidence = copy.deepcopy(previous["evidence"])
            if stage_name == "independent_critique":
                stage["independentContext"]["inputSha256"] = (
                    MODULE.stage_input_sha256(
                        stage_name,
                        MODULE.semantic_source_sha256(source),
                        MODULE.stage_upstream_sha256(upstream),
                        policy_sha256,
                        MODULE.packet_schema_sha256(),
                        previous["model"],
                        previous["reasoning"],
                        MODULE.stage_evidence_sha256(evidence),
                    )
                )
            rebinding = {
                "reason": "post_run_repair",
                "previousOrigin": previous["origin"],
                "previousSourceSha256": previous["sourceSha256"],
                "previousUpstreamSha256": previous["upstreamSha256"],
                "previousPromptOrPolicySha256": previous[
                    "promptOrPolicySha256"
                ],
                "previousSchemaSha256": previous["schemaSha256"],
                "previousInputSha256": previous["inputSha256"],
                "previousOutputSha256": previous["outputSha256"],
                "previousFingerprint": previous["fingerprint"],
                "previousModel": previous["model"],
                "previousReasoning": previous["reasoning"],
                "evidenceSha256": previous["evidenceSha256"],
                "runId": previous["runId"],
                "repairRunIds": list(repair_run_ids),
            }
            stage["provenance"] = MODULE.completed_stage_provenance(
                stage,
                stage_name,
                source,
                upstream,
                policy_sha256,
                previous["model"],
                previous["reasoning"],
                evidence,
                run_id=previous["runId"],
                origin="deterministic_rebinding",
                rebinding=rebinding,
            )

        def rebind_downstream(repair_run_ids):
            blind = entry["blindTranslation"]
            critique = entry["independentCritique"]
            witness = entry["witnessResolution"]
            rebind_stage("blindTranslation", "blind_translation", [], repair_run_ids)
            rebind_stage(
                "independentCritique",
                "independent_critique",
                [("blind_translation", blind)],
                repair_run_ids,
            )
            rebind_stage(
                "witnessResolution",
                "witness_resolution",
                [("independent_critique", critique)],
                repair_run_ids,
            )
            rebind_stage(
                "adjudication",
                "adjudication",
                [
                    ("blind_translation", blind),
                    ("independent_critique", critique),
                    ("witness_resolution", witness),
                ],
                repair_run_ids,
            )

        first_text = f"{original} First audited repair."
        entry["blindTranslation"]["english"] = first_text
        first = {
            "status": "complete",
            "previousAuditSha256": None,
            "basePacketSha256": "1" * 64,
            "artifactSha256": "2" * 64,
            "runId": "translation-repair-run-1111111111111111",
            "operations": [operation("repair-1", original, first_text)],
        }
        packet["postRunRepairAudits"] = [first]
        rebind_downstream((first["runId"],))

        second_text = f"{first_text} Second audited repair."
        entry["blindTranslation"]["english"] = second_text
        second = {
            "status": "complete",
            "previousAuditSha256": MODULE.content_sha256(first),
            "basePacketSha256": "3" * 64,
            "artifactSha256": "4" * 64,
            "runId": "translation-repair-run-2222222222222222",
            "operations": [operation("repair-2", first_text, second_text)],
        }
        packet["postRunRepairAudits"].append(second)
        run_ids = (first["runId"], second["runId"])
        rebind_downstream(run_ids)

        self.assertEqual(MODULE.validate_post_run_repair_audits(packet), [])
        self.assertEqual(
            MODULE.validate_semantic_audit(
                entry["independentCritique"],
                source,
                None,
                second_text,
                "test",
                allow_historical_candidate=True,
            ),
            [],
        )
        self.assertEqual(
            MODULE.validate_stage_chain(
                entry,
                source,
                policy_sha256,
                "test",
                MODULE.repair_rebinding_permissions(packet)[
                    (entry["sourceUnitId"], None)
                ],
            ),
            [],
        )

        deleted_first = copy.deepcopy(packet)
        deleted_first["postRunRepairAudits"] = [
            deleted_first["postRunRepairAudits"][1]
        ]
        self.assertTrue(
            any(
                "previous-audit hash chain" in error
                for error in MODULE.validate_post_run_repair_audits(deleted_first)
            )
        )
        broken_continuity = copy.deepcopy(packet)
        broken_continuity["postRunRepairAudits"][1]["operations"][0][
            "oldTextSha256"
        ] = "f" * 64
        self.assertTrue(
            any(
                "value-hash chain" in error
                for error in MODULE.validate_post_run_repair_audits(
                    broken_continuity
                )
            )
        )

    def test_canonical_json_repairs_are_exact_stage_bound_and_terminal(self):
        packet = self.packet()
        entry = packet["entries"][0]
        paths = (
            (
                "$.entries[0].independentCritique.findings",
                "independent_critique",
            ),
            (
                "$.entries[0].independentCritique.semanticAudit",
                "independent_critique",
            ),
            ("$.entries[0].witnessResolution", "witness_resolution"),
            ("$.entries[0].unresolved", "witness_resolution"),
            ("$.entries[0].names.candidates", "name_inventory"),
            ("$.entries[0].names.mentions", "name_inventory"),
            ("$.entries[0].names.inventoryAudit", "name_inventory"),
            ("$.entries[0].adjudication", "adjudication"),
        )
        operations = []
        for index, (path, stage) in enumerate(paths, start=1):
            operation = {
                "repairId": f"canonical-repair-{index}",
                "sourceUnitId": entry["sourceUnitId"],
                "segmentId": None,
                "recordKind": "entry",
                "targetStage": stage,
                "fieldPath": path,
                "valueKind": "canonical_json",
                "oldValueSha256": f"{index:x}" * 64,
                "newValueSha256": MODULE.content_sha256(
                    MODULE.json_path_value(packet, path)
                ),
                "reasons": [
                    {
                        "code": "test-object-repair",
                        "explanation": "Exact canonical object or array repair.",
                    }
                ],
            }
            if stage == "adjudication":
                semantic_hash = MODULE.content_sha256(
                    MODULE.stage_output_payload(
                        entry["adjudication"], "adjudication"
                    )
                )
                operation["oldSemanticValueSha256"] = semantic_hash
                operation["newSemanticValueSha256"] = semantic_hash
            operations.append(operation)
        packet["postRunRepairAudits"] = [
            {
                "status": "complete",
                "previousAuditSha256": None,
                "basePacketSha256": "a" * 64,
                "artifactSha256": "b" * 64,
                "runId": "translation-repair-run-3333333333333333",
                "operations": operations,
            }
        ]
        self.assertEqual(MODULE.validate_post_run_repair_audits(packet), [])
        self.assertEqual(
            MODULE.validate_schema_instance(
                packet, MODULE.load_json(MODULE.DEFAULT_PACKET_SCHEMA)
            ),
            [],
        )
        permissions = MODULE.repair_rebinding_permissions(packet)[
            (entry["sourceUnitId"], None)
        ]
        self.assertEqual(
            set(permissions),
            {
                "independent_critique",
                "witness_resolution",
                "adjudication",
                "name_inventory",
            },
        )

        drifted = copy.deepcopy(packet)
        drifted["entries"][0]["unresolved"].append({"unexpected": True})
        self.assertTrue(
            any(
                "terminal target drifted" in error
                for error in MODULE.validate_post_run_repair_audits(drifted)
            )
        )
        changed_adjudication = copy.deepcopy(packet)
        adjudication_operation = changed_adjudication["postRunRepairAudits"][0][
            "operations"
        ][-1]
        adjudication_operation["newSemanticValueSha256"] = "f" * 64
        self.assertTrue(
            any(
                "changed semantic content" in error
                for error in MODULE.validate_post_run_repair_audits(
                    changed_adjudication
                )
            )
        )
        forbidden = copy.deepcopy(packet)
        forbidden["postRunRepairAudits"][0]["operations"][0][
            "fieldPath"
        ] = "$.entries[0].independentCritique.independentContext"
        self.assertTrue(
            any(
                "not an allowlisted" in error
                for error in MODULE.validate_post_run_repair_audits(forbidden)
            )
        )

    def test_policy_sha256_repairs_are_exact_stage_bound_and_terminal(self):
        packet = self.packet()
        entry = packet["entries"][0]
        structural = entry["precedingTranslations"][0]
        old_policy = packet["policy"]["bindingSha256"]
        new_policy = "f" * 64
        entry["blindTranslation"]["policySha256"] = new_policy
        structural["blindTranslation"]["policySha256"] = new_policy
        operations = [
            {
                "repairId": "entry-policy-repair",
                "sourceUnitId": entry["sourceUnitId"],
                "segmentId": None,
                "recordKind": "entry",
                "targetStage": "blind_translation",
                "fieldPath": "$.entries[0].blindTranslation.policySha256",
                "valueKind": "text",
                "oldTextSha256": MODULE.text_sha256(old_policy),
                "newTextSha256": MODULE.text_sha256(new_policy),
                "reasons": [
                    {
                        "code": "stale-policy-field",
                        "explanation": "Refresh the exact stage policy binding.",
                    }
                ],
            },
            {
                "repairId": "structural-policy-repair",
                "sourceUnitId": entry["sourceUnitId"],
                "segmentId": structural["segmentId"],
                "recordKind": "structural",
                "targetStage": "blind_translation",
                "fieldPath": (
                    "$.entries[0].precedingTranslations[0]."
                    "blindTranslation.policySha256"
                ),
                "valueKind": "text",
                "oldTextSha256": MODULE.text_sha256(old_policy),
                "newTextSha256": MODULE.text_sha256(new_policy),
                "reasons": [
                    {
                        "code": "stale-policy-field",
                        "explanation": "Refresh the exact stage policy binding.",
                    }
                ],
            },
        ]
        packet["postRunRepairAudits"] = [
            {
                "status": "complete",
                "previousAuditSha256": None,
                "basePacketSha256": "a" * 64,
                "artifactSha256": "b" * 64,
                "runId": "translation-repair-run-4444444444444444",
                "operations": operations,
            }
        ]

        self.assertEqual(MODULE.validate_post_run_repair_audits(packet), [])
        self.assertEqual(
            MODULE.validate_schema_instance(
                packet, MODULE.load_json(MODULE.DEFAULT_PACKET_SCHEMA)
            ),
            [],
        )

        permissions = MODULE.repair_rebinding_permissions(packet)
        self.assertIn(
            "blind_translation",
            permissions[(entry["sourceUnitId"], None)],
        )
        self.assertIn(
            "blind_translation",
            permissions[(entry["sourceUnitId"], structural["segmentId"])],
        )
        self.assertNotIn(
            (entry["sourceUnitId"], None),
            MODULE.repaired_target_stages(packet),
        )

        drifted = copy.deepcopy(packet)
        drifted["entries"][0]["blindTranslation"]["policySha256"] = "e" * 64
        self.assertTrue(
            any(
                "terminal target drifted" in error
                for error in MODULE.validate_post_run_repair_audits(drifted)
            )
        )
        wrong_kind = copy.deepcopy(packet)
        wrong_kind["postRunRepairAudits"][0]["operations"][0][
            "valueKind"
        ] = "canonical_json"
        self.assertTrue(
            any(
                "value kind does not match" in error
                for error in MODULE.validate_post_run_repair_audits(wrong_kind)
            )
        )

    def test_policy_root_repair_is_exact_exhaustive_and_globally_scoped(self):
        packet = self.packet()
        current_policy = copy.deepcopy(packet["policy"])
        old_policy = copy.deepcopy(current_policy)
        old_policy["bindingSha256"] = "a" * 64
        run_id = "translation-repair-run-5555555555555555"
        operations = [
            {
                "repairId": "packet-policy-root-repair",
                "sourceUnitId": None,
                "segmentId": None,
                "recordKind": "packet",
                "targetStage": "policy_binding",
                "fieldPath": "$.policy",
                "valueKind": "canonical_json",
                "oldValueSha256": MODULE.content_sha256(old_policy),
                "newValueSha256": MODULE.content_sha256(current_policy),
                "oldPolicyBindingSha256": old_policy["bindingSha256"],
                "newPolicyBindingSha256": current_policy["bindingSha256"],
                "reasons": [
                    {
                        "code": "policy-binding-refresh",
                        "explanation": "Bind the packet to the reviewed local policy.",
                    }
                ],
            }
        ]
        for index, (key, path, stage) in enumerate(
            MODULE.packet_semantic_owner_stage_paths(packet), start=1
        ):
            current_stage = MODULE.json_path_value(packet, path)
            old_stage = copy.deepcopy(current_stage)
            if stage == "blind_translation":
                old_stage["policySha256"] = old_policy["bindingSha256"]
            else:
                old_stage["provenance"]["fingerprint"] = "d" * 64
            semantic_hash = MODULE.content_sha256(
                MODULE.stage_semantic_repair_payload(current_stage, stage)
            )
            operations.append(
                {
                    "repairId": f"packet-policy-stage-repair-{index}",
                    "sourceUnitId": key[0],
                    "segmentId": key[1],
                    "recordKind": "structural"
                    if key[1] is not None
                    else "entry",
                    "targetStage": stage,
                    "fieldPath": path,
                    "valueKind": "canonical_json",
                    "oldValueSha256": MODULE.content_sha256(old_stage),
                    "newValueSha256": MODULE.content_sha256(current_stage),
                    "oldSemanticValueSha256": semantic_hash,
                    "newSemanticValueSha256": semantic_hash,
                    "reasons": [
                        {
                            "code": "policy-binding-refresh",
                            "explanation": "Refresh this exact policy-bound stage.",
                        }
                    ],
                }
            )
        packet["postRunRepairAudits"] = [
            {
                "status": "complete",
                "previousAuditSha256": None,
                "basePacketSha256": "b" * 64,
                "artifactSha256": "c" * 64,
                "runId": run_id,
                "operations": operations,
            }
        ]

        self.assertEqual(MODULE.validate_post_run_repair_audits(packet), [])
        self.assertEqual(
            MODULE.validate_schema_instance(
                packet, MODULE.load_json(MODULE.DEFAULT_PACKET_SCHEMA)
            ),
            [],
        )
        with_descendant = copy.deepcopy(packet)
        root_audit = with_descendant["postRunRepairAudits"][0]
        blind_stage_operation = root_audit["operations"][1]
        blind_stage_path = blind_stage_operation["fieldPath"]
        descendant_path = f"{blind_stage_path}.policySha256"
        prior_leaf_audit = {
            "status": "complete",
            "previousAuditSha256": None,
            "basePacketSha256": "4" * 64,
            "artifactSha256": "5" * 64,
            "runId": "translation-repair-run-4545454545454545",
            "operations": [
                {
                    "repairId": "prior-policy-leaf-repair",
                    "sourceUnitId": blind_stage_operation["sourceUnitId"],
                    "segmentId": blind_stage_operation["segmentId"],
                    "recordKind": blind_stage_operation["recordKind"],
                    "targetStage": "blind_translation",
                    "fieldPath": descendant_path,
                    "valueKind": "text",
                    "oldTextSha256": MODULE.text_sha256("0" * 64),
                    "newTextSha256": MODULE.text_sha256(
                        old_policy["bindingSha256"]
                    ),
                    "reasons": [
                        {
                            "code": "prior-policy-leaf",
                            "explanation": "Fixture for ordered ancestor supersession.",
                        }
                    ],
                }
            ],
        }
        root_audit["previousAuditSha256"] = MODULE.content_sha256(
            prior_leaf_audit
        )
        with_descendant["postRunRepairAudits"] = [prior_leaf_audit, root_audit]
        self.assertEqual(
            MODULE.validate_post_run_repair_audits(with_descendant), []
        )
        tampered_ancestor = copy.deepcopy(with_descendant)
        MODULE.json_path_value(tampered_ancestor, blind_stage_path)["provenance"][
            "fingerprint"
        ] = "6" * 64
        self.assertTrue(
            any(
                blind_stage_path in error and "terminal target drifted" in error
                for error in MODULE.validate_post_run_repair_audits(
                    tampered_ancestor
                )
            )
        )
        permissions = MODULE.repair_rebinding_permissions(packet)
        for key, _, _ in MODULE.packet_semantic_owner_stage_paths(packet):
            self.assertEqual(
                set(permissions[key]), set(MODULE.SEMANTIC_STAGE_NAMES)
            )

        incomplete = copy.deepcopy(packet)
        incomplete["postRunRepairAudits"][0]["operations"].pop()
        self.assertTrue(
            any(
                "cover all five whole stages for every semantic owner" in error
                for error in MODULE.validate_post_run_repair_audits(incomplete)
            )
        )
        drifted = copy.deepcopy(packet)
        drifted["policy"]["contracts"] = list(
            reversed(drifted["policy"]["contracts"])
        )
        drifted["postRunRepairAudits"][0]["operations"][0][
            "newValueSha256"
        ] = MODULE.content_sha256(drifted["policy"])
        self.assertTrue(
            any(
                "does not exactly match the active local binding" in error
                for error in MODULE.validate_post_run_repair_audits(drifted)
            )
        )
        arbitrary_root = copy.deepcopy(packet)
        arbitrary_root["postRunRepairAudits"][0]["operations"][0][
            "fieldPath"
        ] = "$.authority"
        self.assertTrue(
            any(
                "exact repairable stage-output path" in error
                or "unexpected depth" in error
                for error in MODULE.validate_post_run_repair_audits(arbitrary_root)
            )
        )

    def test_policy_root_rebinding_preserves_semantic_stage_output(self):
        packet = self.packet()
        current_policy = copy.deepcopy(packet["policy"])
        old_policy = copy.deepcopy(current_policy)
        old_policy["bindingSha256"] = "d" * 64
        packet["policy"] = old_policy
        for entry in packet["entries"]:
            entry["blindTranslation"]["policySha256"] = old_policy[
                "bindingSha256"
            ]
            for translation in entry["precedingTranslations"]:
                translation["blindTranslation"]["policySha256"] = old_policy[
                    "bindingSha256"
                ]
        complete_autonomous_stages(packet)

        old_stage_values = {
            path: copy.deepcopy(MODULE.json_path_value(packet, path))
            for _, path, _ in MODULE.packet_semantic_owner_stage_paths(packet)
        }
        packet["policy"] = current_policy
        run_id = "translation-repair-run-6666666666666666"
        operations = [
            {
                "repairId": "packet-policy-root-rebind",
                "sourceUnitId": None,
                "segmentId": None,
                "recordKind": "packet",
                "targetStage": "policy_binding",
                "fieldPath": "$.policy",
                "valueKind": "canonical_json",
                "oldValueSha256": MODULE.content_sha256(old_policy),
                "newValueSha256": MODULE.content_sha256(current_policy),
                "oldPolicyBindingSha256": old_policy["bindingSha256"],
                "newPolicyBindingSha256": current_policy["bindingSha256"],
                "reasons": [
                    {
                        "code": "policy-binding-refresh",
                        "explanation": "Refresh policy-bound hashes only.",
                    }
                ],
            }
        ]

        semantic_owners = []
        for entry_index, entry in enumerate(packet["entries"]):
            for translation_index, (source, translation) in enumerate(
                zip(
                    entry["source"]["precedingSegments"],
                    entry["precedingTranslations"],
                )
            ):
                semantic_owners.append((translation, source))
                translation["blindTranslation"]["policySha256"] = current_policy[
                    "bindingSha256"
                ]
            semantic_owners.append((entry, entry["source"]))
            entry["blindTranslation"]["policySha256"] = current_policy[
                "bindingSha256"
            ]

        def rebind_stage(owner, field, stage, source, upstream):
            stage_owner = owner[field]
            previous = copy.deepcopy(stage_owner["provenance"])
            evidence = copy.deepcopy(previous["evidence"])
            if stage in {"independent_critique", "name_inventory"}:
                stage_owner["independentContext"]["inputSha256"] = (
                    MODULE.stage_input_sha256(
                        stage,
                        MODULE.semantic_source_sha256(source),
                        MODULE.stage_upstream_sha256(upstream),
                        current_policy["bindingSha256"],
                        MODULE.packet_schema_sha256(),
                        previous["model"],
                        previous["reasoning"],
                        MODULE.stage_evidence_sha256(evidence),
                    )
                )
            rebinding = {
                "reason": "post_run_repair",
                "previousOrigin": previous["origin"],
                "previousSourceSha256": previous["sourceSha256"],
                "previousUpstreamSha256": previous["upstreamSha256"],
                "previousPromptOrPolicySha256": previous[
                    "promptOrPolicySha256"
                ],
                "previousSchemaSha256": previous["schemaSha256"],
                "previousInputSha256": previous["inputSha256"],
                "previousOutputSha256": previous["outputSha256"],
                "previousFingerprint": previous["fingerprint"],
                "previousModel": previous["model"],
                "previousReasoning": previous["reasoning"],
                "evidenceSha256": previous["evidenceSha256"],
                "runId": previous["runId"],
                "repairRunIds": [run_id],
            }
            stage_owner["provenance"] = MODULE.completed_stage_provenance(
                stage_owner,
                stage,
                source,
                upstream,
                current_policy["bindingSha256"],
                previous["model"],
                previous["reasoning"],
                evidence,
                run_id=previous["runId"],
                origin="deterministic_rebinding",
                rebinding=rebinding,
            )

        for owner, source in semantic_owners:
            blind = owner["blindTranslation"]
            critique = owner["independentCritique"]
            witness = owner["witnessResolution"]
            adjudication = owner["adjudication"]
            rebind_stage(owner, "blindTranslation", "blind_translation", source, [])
            rebind_stage(
                owner,
                "independentCritique",
                "independent_critique",
                source,
                [("blind_translation", blind)],
            )
            rebind_stage(
                owner,
                "witnessResolution",
                "witness_resolution",
                source,
                [("independent_critique", critique)],
            )
            rebind_stage(
                owner,
                "adjudication",
                "adjudication",
                source,
                [
                    ("blind_translation", blind),
                    ("independent_critique", critique),
                    ("witness_resolution", witness),
                ],
            )
            rebind_stage(
                owner,
                "names",
                "name_inventory",
                source,
                [("adjudication", adjudication)],
            )

        for index, (key, path, stage) in enumerate(
            MODULE.packet_semantic_owner_stage_paths(packet), start=1
        ):
            old_stage = old_stage_values[path]
            current_stage = MODULE.json_path_value(packet, path)
            old_semantic_hash = MODULE.content_sha256(
                MODULE.stage_semantic_repair_payload(old_stage, stage)
            )
            new_semantic_hash = MODULE.content_sha256(
                MODULE.stage_semantic_repair_payload(current_stage, stage)
            )
            self.assertEqual(old_semantic_hash, new_semantic_hash)
            operations.append(
                {
                    "repairId": f"policy-whole-stage-{index}",
                    "sourceUnitId": key[0],
                    "segmentId": key[1],
                    "recordKind": "structural" if key[1] is not None else "entry",
                    "targetStage": stage,
                    "fieldPath": path,
                    "valueKind": "canonical_json",
                    "oldValueSha256": MODULE.content_sha256(old_stage),
                    "newValueSha256": MODULE.content_sha256(current_stage),
                    "oldSemanticValueSha256": old_semantic_hash,
                    "newSemanticValueSha256": new_semantic_hash,
                    "reasons": [
                        {
                            "code": "policy-binding-refresh",
                            "explanation": "Refresh this exact policy-bound stage.",
                        }
                    ],
                }
            )
        packet["postRunRepairAudits"] = [
            {
                "status": "complete",
                "previousAuditSha256": None,
                "basePacketSha256": "e" * 64,
                "artifactSha256": "f" * 64,
                "runId": run_id,
                "operations": operations,
            }
        ]

        permissions = MODULE.repair_rebinding_permissions(packet)
        policy_bindings = MODULE.policy_repair_bindings(packet)
        for owner, source in semantic_owners:
            segment_id = owner.get("segmentId")
            entry = next(
                entry
                for entry in packet["entries"]
                if owner is entry or owner in entry["precedingTranslations"]
            )
            key = (entry["sourceUnitId"], segment_id)
            self.assertEqual(
                MODULE.validate_stage_chain(
                    owner,
                    source,
                    current_policy["bindingSha256"],
                    "policy fixture",
                    permissions[key],
                    policy_bindings,
                ),
                [],
            )

        victim = packet["entries"][0]["blindTranslation"]
        victim["english"] += " Unaudited drift."
        victim["provenance"]["outputSha256"] = MODULE.content_sha256(
            MODULE.stage_output_payload(victim, "blind_translation")
        )
        victim["provenance"]["fingerprint"] = MODULE.stage_fingerprint(
            victim["provenance"]
        )
        errors = MODULE.validate_stage_provenance(
            victim,
            "blind_translation",
            packet["entries"][0]["source"],
            [],
            current_policy["bindingSha256"],
            "policy fixture",
            permitted_repair_run_ids=permissions[
                (packet["entries"][0]["sourceUnitId"], None)
            ]["blind_translation"],
            permitted_policy_repair_bindings=policy_bindings,
        )
        self.assertTrue(
            any("changed unaudited semantic stage output" in error for error in errors)
        )

    def test_policy_rebinding_cannot_supersede_unenumerated_whole_stage_terminal(self):
        packet = self.packet()
        current_policy = copy.deepcopy(packet["policy"])
        old_policy = copy.deepcopy(current_policy)
        old_policy["bindingSha256"] = "7" * 64
        packet["policy"] = old_policy
        for entry in packet["entries"]:
            entry["blindTranslation"]["policySha256"] = old_policy[
                "bindingSha256"
            ]
            for translation in entry["precedingTranslations"]:
                translation["blindTranslation"]["policySha256"] = old_policy[
                    "bindingSha256"
                ]
        complete_autonomous_stages(packet)

        entry = packet["entries"][0]
        witness = entry["witnessResolution"]
        first_run_id = "translation-repair-run-7777777777777777"
        witness_path = "$.entries[0].witnessResolution"
        first_audit = {
            "status": "complete",
            "previousAuditSha256": None,
            "basePacketSha256": "8" * 64,
            "artifactSha256": "9" * 64,
            "runId": first_run_id,
            "operations": [
                {
                    "repairId": "prior-whole-witness-repair",
                    "sourceUnitId": entry["sourceUnitId"],
                    "segmentId": None,
                    "recordKind": "entry",
                    "targetStage": "witness_resolution",
                    "fieldPath": witness_path,
                    "valueKind": "canonical_json",
                    "oldValueSha256": "1" * 64,
                    "newValueSha256": MODULE.content_sha256(witness),
                    "reasons": [
                        {
                            "code": "prior-witness-link",
                            "explanation": "Fixture for a prior whole-witness repair.",
                        }
                    ],
                }
            ],
        }

        packet["policy"] = current_policy
        root_run_id = "translation-repair-run-8888888888888888"
        root_operations = [
            {
                "repairId": "packet-policy-root-after-witness",
                "sourceUnitId": None,
                "segmentId": None,
                "recordKind": "packet",
                "targetStage": "policy_binding",
                "fieldPath": "$.policy",
                "valueKind": "canonical_json",
                "oldValueSha256": MODULE.content_sha256(old_policy),
                "newValueSha256": MODULE.content_sha256(current_policy),
                "oldPolicyBindingSha256": old_policy["bindingSha256"],
                "newPolicyBindingSha256": current_policy["bindingSha256"],
                "reasons": [
                    {
                        "code": "policy-binding-refresh",
                        "explanation": "Refresh policy-bound metadata only.",
                    }
                ],
            }
        ]
        for index, (key, path) in enumerate(
            MODULE.packet_semantic_owner_policy_paths(packet), start=1
        ):
            root_operations.append(
                {
                    "repairId": f"policy-after-witness-owner-{index}",
                    "sourceUnitId": key[0],
                    "segmentId": key[1],
                    "recordKind": "structural" if key[1] is not None else "entry",
                    "targetStage": "blind_translation",
                    "fieldPath": path,
                    "valueKind": "text",
                    "oldTextSha256": MODULE.text_sha256(
                        old_policy["bindingSha256"]
                    ),
                    "newTextSha256": MODULE.text_sha256(
                        current_policy["bindingSha256"]
                    ),
                    "reasons": [
                        {
                            "code": "policy-binding-refresh",
                            "explanation": "Refresh the exact owner policy field.",
                        }
                    ],
                }
            )
        root_audit = {
            "status": "complete",
            "previousAuditSha256": MODULE.content_sha256(first_audit),
            "basePacketSha256": "2" * 64,
            "artifactSha256": "3" * 64,
            "runId": root_run_id,
            "operations": root_operations,
        }
        packet["postRunRepairAudits"] = [first_audit, root_audit]
        for owner_key, path in MODULE.packet_semantic_owner_policy_paths(packet):
            MODULE.json_path_value(
                packet, path.rsplit(".policySha256", 1)[0]
            )["policySha256"] = current_policy["bindingSha256"]

        previous = copy.deepcopy(witness["provenance"])
        rebinding = {
            "reason": "post_run_repair",
            "previousOrigin": previous["origin"],
            "previousSourceSha256": previous["sourceSha256"],
            "previousUpstreamSha256": previous["upstreamSha256"],
            "previousPromptOrPolicySha256": previous[
                "promptOrPolicySha256"
            ],
            "previousSchemaSha256": previous["schemaSha256"],
            "previousInputSha256": previous["inputSha256"],
            "previousOutputSha256": previous["outputSha256"],
            "previousFingerprint": previous["fingerprint"],
            "previousModel": previous["model"],
            "previousReasoning": previous["reasoning"],
            "evidenceSha256": previous["evidenceSha256"],
            "runId": previous["runId"],
            "repairRunIds": [first_run_id, root_run_id],
        }
        witness["provenance"] = MODULE.completed_stage_provenance(
            witness,
            "witness_resolution",
            entry["source"],
            [("independent_critique", entry["independentCritique"])],
            current_policy["bindingSha256"],
            previous["model"],
            previous["reasoning"],
            copy.deepcopy(previous["evidence"]),
            run_id=previous["runId"],
            origin="deterministic_rebinding",
            rebinding=rebinding,
        )

        errors = MODULE.validate_post_run_repair_audits(packet)
        self.assertTrue(
            any(
                "cover all five whole stages for every semantic owner" in error
                for error in errors
            )
        )
        self.assertTrue(
            any(
                witness_path in error and "terminal target drifted" in error
                for error in errors
            )
        )
        witness["notRequiredRationale"] += " Unaudited semantic drift."
        self.assertTrue(
            any(
                witness_path in error and "terminal target drifted" in error
                for error in MODULE.validate_post_run_repair_audits(packet)
            )
        )

    def test_later_leaf_repair_supersedes_prior_whole_stage_terminal(self):
        packet = self.packet()
        complete_autonomous_stages(packet)
        entry = packet["entries"][0]
        stage_path = "$.entries[0].adjudication"
        leaf_path = f"{stage_path}.english"
        old_stage = copy.deepcopy(entry["adjudication"])
        old_english = old_stage["english"]
        new_english = f"{old_english} Audited correction."
        semantic_sha256 = MODULE.content_sha256(
            MODULE.stage_semantic_repair_payload(old_stage, "adjudication")
        )
        first_audit = {
            "status": "complete",
            "previousAuditSha256": None,
            "basePacketSha256": "1" * 64,
            "artifactSha256": "2" * 64,
            "runId": "translation-repair-run-aaaaaaaaaaaaaaaa",
            "operations": [
                {
                    "repairId": "whole-adjudication-snapshot",
                    "sourceUnitId": entry["sourceUnitId"],
                    "segmentId": None,
                    "recordKind": "entry",
                    "targetStage": "adjudication",
                    "fieldPath": stage_path,
                    "valueKind": "canonical_json",
                    "oldValueSha256": "3" * 64,
                    "newValueSha256": MODULE.content_sha256(old_stage),
                    "oldSemanticValueSha256": semantic_sha256,
                    "newSemanticValueSha256": semantic_sha256,
                    "reasons": [
                        {
                            "code": "test-stage-snapshot",
                            "explanation": "Record the exact pre-repair stage object.",
                        }
                    ],
                }
            ],
        }
        entry["adjudication"]["english"] = new_english
        second_audit = {
            "status": "complete",
            "previousAuditSha256": MODULE.content_sha256(first_audit),
            "basePacketSha256": "4" * 64,
            "artifactSha256": "5" * 64,
            "runId": "translation-repair-run-bbbbbbbbbbbbbbbb",
            "operations": [
                {
                    "repairId": "later-adjudication-leaf-repair",
                    "sourceUnitId": entry["sourceUnitId"],
                    "segmentId": None,
                    "recordKind": "entry",
                    "targetStage": "adjudication",
                    "fieldPath": leaf_path,
                    "valueKind": "text",
                    "oldTextSha256": MODULE.text_sha256(old_english),
                    "newTextSha256": MODULE.text_sha256(new_english),
                    "reasons": [
                        {
                            "code": "test-leaf-repair",
                            "explanation": "Apply one later exact append-only repair.",
                        }
                    ],
                }
            ],
        }
        packet["postRunRepairAudits"] = [first_audit, second_audit]

        self.assertEqual(MODULE.validate_post_run_repair_audits(packet), [])

    def test_production_repair_record_kind_normalizes_biography_to_entry(self):
        self.assertEqual(MODULE.normalized_repair_record_kind("biography"), "entry")
        self.assertEqual(
            MODULE.normalized_repair_record_kind("structural"), "structural"
        )
        with self.assertRaisesRegex(MODULE.WorkflowError, "unsupported"):
            MODULE.normalized_repair_record_kind("unknown")

    def test_post_run_repair_metadata_must_match_field_path(self):
        packet = self.packet()
        path = "$.entries[0].blindTranslation.english"
        packet["entries"][0]["blindTranslation"]["english"] = "Repaired."
        packet["postRunRepairAudits"] = [
            {
                "status": "complete",
                "previousAuditSha256": None,
                "basePacketSha256": "1" * 64,
                "artifactSha256": "2" * 64,
                "runId": "translation-repair-run-1234567890abcdef",
                "operations": [
                {
                    "repairId": "repair-1",
                    "sourceUnitId": "wrong-unit",
                    "segmentId": "wrong-segment",
                    "recordKind": "structural",
                    "targetStage": "adjudication",
                    "fieldPath": path,
                    "valueKind": "text",
                    "oldTextSha256": MODULE.text_sha256(""),
                    "newTextSha256": MODULE.text_sha256("Repaired."),
                    "reasons": [
                        {"code": "test", "explanation": "Test repair provenance."}
                    ],
                }
                ],
            }
        ]
        errors = MODULE.validate_post_run_repair_audits(packet)
        self.assertTrue(any("source unit metadata" in error for error in errors))
        self.assertTrue(any("record kind" in error for error in errors))
        self.assertTrue(any("segment metadata" in error for error in errors))
        self.assertTrue(any("target stage" in error for error in errors))

    def test_schema_format_validation_rejects_date_only_and_colon_uri(self):
        self.assertTrue(
            MODULE.validate_schema_instance(
                "2026-08-14", {"type": "string", "format": "date-time"}
            )
        )
        self.assertTrue(
            MODULE.validate_schema_instance(
                ":", {"type": "string", "format": "uri"}
            )
        )


if __name__ == "__main__":
    unittest.main()

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "translation_workflow", ROOT / "scripts" / "translation_workflow.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)

FIXTURE_SOURCE = ROOT / "tests" / "fixtures" / "openiti-mini.mARkdown"
FIXTURE_MANIFEST = ROOT / "tests" / "fixtures" / "translation-source.mini.json"


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
    def translated(label, source_text):
        targets = [
            occurrence["rule"]["target"]
            for occurrence in MODULE.registered_occurrences(source_text or "", "source")
        ]
        return " ".join([label, *targets]).strip()

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
                }
            )
            translation["witnessResolution"] = {
                "status": "not_required",
                "results": [],
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
            }
            translation["unresolved"] = []
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
            }
        )
        entry["witnessResolution"] = {"status": "not_required", "results": []}
        entry["adjudication"] = {
            "status": "complete",
            "english": translated(
                f"Adjudicated English for entry {number}.",
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
        }
        entry["unresolved"] = []


class TranslationWorkflowTests(unittest.TestCase):
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
        self.assertEqual(packet["schemaVersion"], "1.2.0")
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
            {"kind": "source-reading", "requiresWitness": True}
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
        packet["postRunRepairAudit"] = {
            "status": "complete",
            "basePacketSha256": "1" * 64,
            "artifactSha256": "2" * 64,
            "runId": "translation-repair-run-1234567890abcdef",
            "operations": [{"repairId": "already-applied"}],
        }
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
            {"kind": "ambiguous-name", "requiresWitness": True}
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

    def test_machine_ready_witness_requires_canonical_hashed_provenance(self):
        passage = "Exact short witness reading."
        result = {
            "status": "hit",
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
                [{"requiresWitness": True}],
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
                    [{"requiresWitness": True}],
                    "test",
                    strict=True,
                )
            )
        )

    def test_machine_ready_names_require_exact_source_spans(self):
        packet = self.packet()
        complete_autonomous_stages(packet)
        entry = packet["entries"][0]
        self.assertEqual(
            MODULE.validate_names(
                entry["names"],
                entry["source"],
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
        self.assertTrue(
            all(rule["accessibleEnglish"] for rule in MODULE.FORMULA_RULES)
        )

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
            MODULE.atomic_write(packet_path, MODULE.json_bytes(mutated))
            with self.assertRaisesRegex(
                MODULE.WorkflowError, "review presentation does not match packet"
            ):
                MODULE.submit_packet(
                    packet_path, root / "proposals", allow_test_fixture=True
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
        packet["postRunRepairAudit"] = {
            "status": "complete",
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
                    "oldTextSha256": MODULE.text_sha256(original),
                    "newTextSha256": MODULE.text_sha256("Repaired blind text."),
                    "reasons": [
                        {"code": "test", "explanation": "Test repair provenance."}
                    ],
                }
            ],
        }
        self.assertEqual(MODULE.validate_post_run_repair_audit(packet), [])
        packet["entries"][0]["blindTranslation"]["english"] = "Drifted."
        self.assertTrue(
            any(
                "target drifted" in error
                for error in MODULE.validate_post_run_repair_audit(packet)
            )
        )

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
        packet["postRunRepairAudit"] = {
            "status": "complete",
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
                    "oldTextSha256": MODULE.text_sha256(""),
                    "newTextSha256": MODULE.text_sha256("Repaired."),
                    "reasons": [
                        {"code": "test", "explanation": "Test repair provenance."}
                    ],
                }
            ],
        }
        errors = MODULE.validate_post_run_repair_audit(packet)
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

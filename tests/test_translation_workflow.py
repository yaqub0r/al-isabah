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
    for entry in packet["entries"]:
        number = entry["sourceOrdinal"]
        entry["blindTranslation"].update(
            {
                "status": "complete",
                "runId": f"blind-{number}",
                "model": "codex",
                "reasoning": "high",
                "english": f"Blind English for entry {number}.",
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
            "english": f"Adjudicated English for entry {number}.",
            "decisions": [],
        }
        entry["names"] = {
            "status": "complete",
            "candidates": [
                {
                    "candidateId": f"issue-25-name-{number}",
                    "observedArabic": "ضباعة",
                    "proposedEnglish": "Duba'a",
                    "aliases": [],
                    "confidenceEvidence": ["entry heading"],
                    "reviewState": "unreviewed",
                }
            ],
            "mentions": [
                {
                    "candidateId": f"issue-25-name-{number}",
                    "sourceUnitId": entry["sourceUnitId"],
                    "location": "entry-heading",
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
        self.assertNotIn("باب الطاء", entries[1]["rawOpeniti"])
        self.assertIn("باب الطاء", entries[2]["structuralEvents"][0])
        self.assertEqual(entries[2]["locations"][0], {"volume": 8, "page": 5})

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

    def test_material_uncertainty_requires_resolved_witness(self):
        packet = self.packet()
        complete_autonomous_stages(packet)
        packet["entries"][0]["independentCritique"]["findings"] = [
            {"kind": "ambiguous-name", "requiresWitness": True}
        ]
        errors = MODULE.validate_packet(packet, machine_ready=True)
        self.assertTrue(any("requires witness resolution" in error for error in errors))

    def test_render_finalizes_machine_ready_packet_without_human_approval(self):
        packet = self.packet()
        complete_autonomous_stages(packet)
        with tempfile.TemporaryDirectory() as directory:
            packet_path = Path(directory) / "issue-0025.json"
            MODULE.atomic_write(packet_path, MODULE.json_bytes(packet))
            review_path = MODULE.finalize_packet(packet_path)
            final = MODULE.load_json(packet_path)
            self.assertTrue(review_path.is_file())
            self.assertEqual(final["machineReadiness"]["status"], "ready")
            self.assertTrue(
                all(
                    entry["humanReview"]["status"] == "unreviewed"
                    for entry in final["entries"]
                )
            )
            self.assertEqual(MODULE.validate_packet(final, machine_ready=True), [])

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


if __name__ == "__main__":
    unittest.main()

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "integrate_issue_0026", ROOT / "scripts" / "integrate_issue_0026.py"
)
INTEGRATOR = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(INTEGRATOR)


class TranslationRepairIntegrationTests(unittest.TestCase):
    def artifact(self, packet_path, **values):
        return {
            "sourcePacket": {"sha256": INTEGRATOR.file_sha256(packet_path)},
            "coverage": {"exactBlockersAfter": 0},
            **values,
        }

    def test_blocker_count_covers_production_report_shapes(self):
        self.assertEqual(
            INTEGRATOR.blocker_count({"coverage": {"exactBlockersAfter": 2}}),
            2,
        )
        self.assertEqual(
            INTEGRATOR.blocker_count({"report": {"blockers": [{}, {}]}}),
            2,
        )
        self.assertEqual(
            INTEGRATOR.blocker_count({"coverage": {"remainingBlockers": 1}}),
            1,
        )

    def test_middle_range_mutation_keys_replay_with_owner_replacement(self):
        old_result = {"status": "hit", "decision": "old"}
        new_result = {"status": "hit", "decision": "renewed"}
        old_unresolved = {"description": "old", "severity": "material"}
        new_unresolved = {"description": "old", "severity": "major"}
        old_witness = {"status": "complete", "results": [old_result]}
        new_witness = {"status": "complete", "results": [new_result]}
        target = {
            "ownerType": "entry",
            "sourceOrdinal": 513,
            "sourceUnitId": "unit-513",
            "segmentId": None,
        }
        packet = {
            "entries": [
                {
                    "sourceOrdinal": 513,
                    "sourceUnitId": "unit-513",
                    "precedingTranslations": [],
                    "witnessResolution": copy.deepcopy(old_witness),
                    "unresolved": [copy.deepcopy(old_unresolved)],
                }
            ]
        }
        with tempfile.TemporaryDirectory() as temporary:
            packet_path = Path(temporary) / "packet.json"
            packet_path.write_text("{}", encoding="utf-8")
            artifact = self.artifact(
                packet_path,
                witnessResultMutations=[
                    {
                        "target": {**target, "resultIndex": 0},
                        "oldObjectSnapshot": old_result,
                        "oldObjectSha256": INTEGRATOR.js_object_sha256(old_result),
                        "normalized": new_result,
                    }
                ],
                unresolvedItemMutations=[
                    {
                        "target": {**target, "unresolvedIndex": 0},
                        "oldObjectSnapshot": old_unresolved,
                        "oldObjectSha256": INTEGRATOR.js_object_sha256(old_unresolved),
                        "normalized": new_unresolved,
                    }
                ],
                witnessResolutionMutations=[
                    {
                        "target": target,
                        "oldObjectSnapshot": old_witness,
                        "oldObjectSha256": INTEGRATOR.js_object_sha256(old_witness),
                        "replacement": new_witness,
                        "replacementObjectSha256": INTEGRATOR.js_object_sha256(
                            new_witness
                        ),
                    }
                ],
            )
            with mock.patch.object(INTEGRATOR, "PACKET", packet_path):
                counts = INTEGRATOR.apply_provenance(packet, [artifact])

        self.assertEqual(
            counts, {"witness": 1, "unresolved": 1, "alignments": 1, "structural": 0}
        )
        self.assertEqual(packet["entries"][0]["witnessResolution"], new_witness)
        self.assertEqual(packet["entries"][0]["unresolved"], [new_unresolved])

    def test_structural_addition_is_verified_then_applied_once(self):
        old_witness = {"status": "not_required", "results": []}
        added_result = {"status": "hit", "decision": "page break verified"}
        new_witness = {"status": "complete", "results": [added_result]}
        old_finding = {"kind": "source-reading", "requiresWitness": False}
        new_finding = {"kind": "source-reading", "requiresWitness": True}
        old_decision = {"issue": "separator", "resolution": "pending"}
        new_decision = {"issue": "separator", "resolution": "[Page break]"}
        segment = {
            "segmentId": "before-unit-641-segment-001",
            "witnessResolution": copy.deepcopy(old_witness),
            "independentCritique": {"findings": [copy.deepcopy(old_finding)]},
            "adjudication": {
                "english": "٫",
                "decisions": [copy.deepcopy(old_decision)],
            },
            "unresolved": [],
        }
        packet = {
            "entries": [
                {
                    "sourceOrdinal": 641,
                    "sourceUnitId": "unit-641",
                    "precedingTranslations": [segment],
                    "witnessResolution": {"status": "not_required", "results": []},
                    "unresolved": [],
                }
            ]
        }
        target = {
            "ownerType": "preceding_segment",
            "sourceOrdinal": 641,
            "sourceUnitId": "unit-641",
            "segmentId": segment["segmentId"],
        }
        structural_mutation = {
            "target": target,
            "oldWitnessResolutionSnapshot": old_witness,
            "oldWitnessResolutionSha256": INTEGRATOR.js_object_sha256(old_witness),
            "witnessResolutionReplacement": new_witness,
            "critiqueFindingReplacement": {
                "findingIndex": 0,
                "oldObjectSnapshot": old_finding,
                "oldObjectSha256": INTEGRATOR.js_object_sha256(old_finding),
                "replacement": new_finding,
            },
            "adjudicationDecisionReplacement": {
                "decisionIndex": 0,
                "oldObjectSnapshot": old_decision,
                "oldObjectSha256": INTEGRATOR.js_object_sha256(old_decision),
                "replacement": new_decision,
            },
            "adjudicationEnglishReplacement": {
                "oldValue": "٫",
                "oldValueSha256": INTEGRATOR.workflow.text_sha256("٫"),
                "replacement": "[Page break]",
            },
        }
        with tempfile.TemporaryDirectory() as temporary:
            packet_path = Path(temporary) / "packet.json"
            packet_path.write_text(json.dumps(packet), encoding="utf-8")
            artifact = self.artifact(
                packet_path,
                witnessNormalizations=[
                    {
                        "operation": "add",
                        "target": {**target, "resultIndex": 0},
                        "normalized": added_result,
                    }
                ],
                structuralOwnerMutation=structural_mutation,
            )
            with mock.patch.object(INTEGRATOR, "PACKET", packet_path):
                counts = INTEGRATOR.apply_provenance(packet, [artifact])

        self.assertEqual(
            counts, {"witness": 1, "unresolved": 0, "alignments": 0, "structural": 1}
        )
        self.assertEqual(segment["witnessResolution"], new_witness)
        self.assertEqual(segment["independentCritique"]["findings"], [new_finding])
        self.assertEqual(segment["adjudication"]["decisions"], [new_decision])
        self.assertEqual(segment["adjudication"]["english"], "[Page break]")


if __name__ == "__main__":
    unittest.main()

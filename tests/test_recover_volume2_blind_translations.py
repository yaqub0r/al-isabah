from __future__ import annotations

import copy
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "recover_volume2_blind_translations",
    ROOT / "scripts" / "recover_volume2_blind_translations.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)
WORKFLOW = MODULE.workflow

FIXTURE_SOURCE = ROOT / "tests" / "fixtures" / "openiti-mini.mARkdown"
FIXTURE_MANIFEST = ROOT / "tests" / "fixtures" / "translation-source.mini.json"
TEST_RANGES = {54: (1, 1), 55: (2, 2)}


def assignment_issue(number: int = 70, start: int = 1, end: int = 2) -> dict:
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
        "createdAt": "2026-08-26T00:00:00Z",
        "assignees": [{"login": "translator"}],
        "body": f"Assignment\n\n{WORKFLOW.assignment_marker(marker)}\n",
    }


def fresh_target() -> dict:
    issue = assignment_issue()
    return WORKFLOW.build_packet(
        issue,
        WORKFLOW.parse_claims([issue]),
        FIXTURE_SOURCE,
        FIXTURE_MANIFEST,
        WORKFLOW.DEFAULT_POLICY,
    )


def legacy_packets(target: dict) -> dict[int, dict]:
    packets = {}
    for issue, (start, end) in TEST_RANGES.items():
        packet = copy.deepcopy(target)
        packet["schemaVersion"] = MODULE.LEGACY_SCHEMA_VERSION
        packet["toolVersion"] = MODULE.LEGACY_SCHEMA_VERSION
        packet["packetId"] = f"isabah-translation-issue-{issue}"
        packet["assignment"].update(
            {
                "issueNumber": issue,
                "issueUrl": f"https://github.com/yaqub0r/al-isabah/issues/{issue}",
                "startUnit": start,
                "endUnit": end,
            }
        )
        packet["entries"] = [
            entry
            for entry in packet["entries"]
            if start <= entry["sourceOrdinal"] <= end
        ]
        for entry in packet["entries"]:
            owners = [entry, *entry["precedingTranslations"]]
            sources = [entry["source"], *entry["source"]["precedingSegments"]]
            for index, (owner, source) in enumerate(zip(owners, sources), start=1):
                blind = owner["blindTranslation"]
                blind.pop("provenance")
                blind.update(
                    {
                        "status": "complete",
                        "runId": f"legacy-{issue}-{entry['sourceOrdinal']}-{index}",
                        "model": "gpt-test",
                        "reasoning": "high",
                    }
                )
                if owner is entry:
                    blind["english"] = (
                        f"Original blind English for source unit {entry['sourceOrdinal']}."
                    )
                else:
                    blind["headingEnglish"] = (
                        f"Original structural heading {index}."
                        if source.get("headingArabic")
                        else None
                    )
                    blind["english"] = (
                        f"Original structural prose {index}."
                        if source.get("arabic")
                        else None
                    )
                owner["independentCritique"] = {
                    "status": "complete",
                    "mechanicallyGenerated": True,
                }
                owner["witnessResolution"] = {
                    "status": "not_required",
                    "mechanicallyGenerated": True,
                }
                owner["adjudication"] = {
                    "status": "complete",
                    "mechanicallyGenerated": True,
                }
                owner["names"] = {
                    "status": "complete",
                    "mechanicallyGenerated": True,
                }
                owner["unresolved"] = [{"mechanicallyGenerated": True}]
        packet["formulaInventory"]["status"] = "complete"
        packet["reviewPresentation"] = {
            "status": "ready",
            "path": f"issue-{issue:04d}.review.md",
            "sha256": "a" * 64,
        }
        packet["machineReadiness"] = {
            "status": "ready",
            "validatedAt": "2026-08-26T00:00:00Z",
            "validatorVersion": MODULE.LEGACY_SCHEMA_VERSION,
        }
        packets[issue] = packet
    return packets


class Volume2BlindRecoveryTests(unittest.TestCase):
    def recover(self, target: dict, packets: dict[int, dict]):
        return MODULE.recover_blind_translations(
            target,
            packets,
            expected_target_issue=70,
            expected_target_range=(1, 2),
            expected_legacy_ranges=TEST_RANGES,
            legacy_packet_blob_sha256s={
                issue: WORKFLOW.bytes_sha256(WORKFLOW.json_bytes(packet))
                for issue, packet in packets.items()
            },
        )

    def test_recovers_only_exact_blind_records_and_resets_later_stages(self) -> None:
        target = fresh_target()
        packets = legacy_packets(target)
        original_target = copy.deepcopy(target)
        legacy_blind = copy.deepcopy(packets[54]["entries"][0]["blindTranslation"])

        recovered, summary = self.recover(target, packets)

        self.assertEqual(target, original_target)
        self.assertEqual(summary["entries"], 2)
        self.assertGreater(summary["structuralSegments"], 0)
        recovered_blind = recovered["entries"][0]["blindTranslation"]
        for field, value in legacy_blind.items():
            self.assertEqual(recovered_blind[field], value)
        self.assertEqual(
            WORKFLOW.validate_stage_provenance(
                recovered_blind,
                "blind_translation",
                recovered["entries"][0]["source"],
                [],
                recovered["policy"]["bindingSha256"],
                "test entry",
            ),
            [],
        )
        for entry in recovered["entries"]:
            for owner in [entry, *entry["precedingTranslations"]]:
                self.assertEqual(owner["independentCritique"]["status"], "pending")
                self.assertEqual(owner["witnessResolution"]["status"], "pending")
                self.assertEqual(owner["adjudication"]["status"], "pending")
                self.assertEqual(owner["names"]["status"], "pending")
                self.assertEqual(owner["unresolved"], [])
                self.assertEqual(owner["humanReview"], {"status": "unreviewed"})
                self.assertNotIn("mechanicallyGenerated", str(owner))
        self.assertEqual(recovered["formulaInventory"]["status"], "pending")
        self.assertEqual(recovered["postRunRepairAudit"]["status"], "not_required")
        self.assertEqual(recovered["reviewPresentation"]["status"], "pending")
        self.assertEqual(recovered["machineReadiness"]["status"], "pending")
        self.assertEqual(WORKFLOW.validate_packet(recovered, machine_ready=False), [])

    def test_rejects_source_drift_without_mutating_target(self) -> None:
        target = fresh_target()
        packets = legacy_packets(target)
        original_target = copy.deepcopy(target)
        packets[54]["entries"][0]["source"]["arabic"] += " drift"

        with self.assertRaisesRegex(MODULE.RecoveryError, "does not exactly match"):
            self.recover(target, packets)

        self.assertEqual(target, original_target)

    def test_requires_exact_authorized_legacy_packet_set(self) -> None:
        target = fresh_target()
        packets = legacy_packets(target)
        packets.pop(55)

        with self.assertRaisesRegex(MODULE.RecoveryError, "exactly match"):
            self.recover(target, packets)

    def test_hash_binds_documented_blind_repair_but_clears_completion_claim(self) -> None:
        target = fresh_target()
        packets = legacy_packets(target)
        packet = packets[54]
        entry = packet["entries"][0]
        blind_text = entry["blindTranslation"]["english"]
        operation = {
            "repairId": "synthetic-blind-repair",
            "sourceUnitId": entry["sourceUnitId"],
            "segmentId": None,
            "recordKind": "entry",
            "targetStage": "blind_translation",
            "fieldPath": "$.entries[0].blindTranslation.english",
            "oldTextSha256": WORKFLOW.text_sha256("earlier blind text"),
            "newTextSha256": WORKFLOW.text_sha256(blind_text),
            "reasons": [
                {"code": "test-repair", "explanation": "Synthetic fixture repair."}
            ],
        }
        packet["postRunRepairAudit"] = {
            "status": "complete",
            "basePacketSha256": "b" * 64,
            "artifactSha256": "c" * 64,
            "runId": "translation-repair-run-0123456789abcdef",
            "operations": [operation],
        }

        recovered, summary = self.recover(target, packets)

        recovered_blind = recovered["entries"][0]["blindTranslation"]
        self.assertEqual(recovered_blind["english"], blind_text)
        repair_evidence = [
            item
            for item in recovered_blind["provenance"]["evidence"]
            if item["role"] == "legacy_post_run_repair_operation"
        ]
        self.assertEqual(len(repair_evidence), 1)
        self.assertEqual(repair_evidence[0]["sha256"], WORKFLOW.content_sha256(operation))
        lineage_roles = {
            item["role"] for item in recovered_blind["provenance"]["evidence"]
        }
        self.assertTrue(
            {
                "legacy_packet_blob",
                "legacy_packet_schema",
                "legacy_blind_translation_record",
            }.issubset(lineage_roles)
        )
        self.assertEqual(recovered_blind["provenance"]["origin"], "legacy_migration")
        self.assertEqual(summary["documentedBlindRepairs"], 1)
        self.assertEqual(
            recovered["postRunRepairAudit"],
            {
                "status": "not_required",
                "basePacketSha256": None,
                "artifactSha256": None,
                "runId": None,
                "operations": [],
            },
        )


if __name__ == "__main__":
    unittest.main()

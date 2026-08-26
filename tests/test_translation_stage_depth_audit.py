import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "audit_translation_stage_depth",
    ROOT / "scripts" / "audit_translation_stage_depth.py",
)
AUDIT = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(AUDIT)


class TranslationStageDepthAuditTests(unittest.TestCase):
    def test_packet_audit_counts_positive_stage_evidence(self):
        owner = {
            "independentCritique": {
                "status": "complete",
                "findings": [{"kind": "source-reading"}],
                "semanticAudit": {"status": "complete"},
            },
            "witnessResolution": {"status": "complete", "results": [{}, {}]},
            "adjudication": {
                "status": "complete",
                "english": "English",
                "decisions": [{"kind": "source-reading"}],
            },
            "names": {
                "status": "complete",
                "inventoryAudit": {"status": "complete"},
                "candidates": [{}, {}],
                "mentions": [{}, {}],
            },
            "unresolved": [{}],
        }
        packet = {
            "assignment": {"issueNumber": 70},
            "entries": [
                {
                    **owner,
                    "source": {
                        "arabic": "نص",
                        "precedingSegments": [],
                    },
                    "precedingTranslations": [],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "packet.json"
            path.write_text(json.dumps(packet), encoding="utf-8")
            report = AUDIT.audit_packets([path])
        metrics = report["metrics"]
        self.assertEqual(metrics["biographies"], 1)
        self.assertEqual(metrics["findings"], 1)
        self.assertEqual(metrics["witnessResults"], 2)
        self.assertEqual(metrics["nameCandidates"], 2)
        self.assertEqual(metrics["biographiesWithMultipleNames"], 1)
        self.assertEqual(metrics["semanticAuditComplete"], 1)
        self.assertEqual(metrics["nameInventoryAuditComplete"], 1)

    def test_empty_findings_remain_visible_in_aggregate(self):
        packet = {
            "assignment": {"issueNumber": 70},
            "entries": [
                {
                    "source": {"arabic": "نص", "precedingSegments": []},
                    "precedingTranslations": [],
                    "independentCritique": {"status": "complete", "findings": []},
                    "witnessResolution": {"status": "not_required", "results": []},
                    "adjudication": {"status": "complete", "english": "Text", "decisions": []},
                    "names": {"status": "complete", "candidates": [{}], "mentions": [{}]},
                    "unresolved": [],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "packet.json"
            path.write_text(json.dumps(packet), encoding="utf-8")
            report = AUDIT.audit_packets([path])
        self.assertEqual(report["metrics"]["recordsWithoutFindings"], 1)
        self.assertEqual(report["metrics"].get("semanticAuditComplete", 0), 0)


if __name__ == "__main__":
    unittest.main()

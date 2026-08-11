from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
ENTRIES = ROOT / "content" / "entries"
REPORT = ROOT / "derived" / "imports" / "volume-08.json"
MANIFEST = ROOT / "evidence" / "manifests" / "firstlight-artifacts.v1.json"


class CanonicalContentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.paths = sorted(ENTRIES.glob("isabah-entry-*.json"))
        cls.entries = [json.loads(path.read_text(encoding="utf-8")) for path in cls.paths]
        cls.report = json.loads(REPORT.read_text(encoding="utf-8"))
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_volume_8_entry_sequence_is_complete_and_unique(self) -> None:
        self.assertEqual(len(self.entries), 1550)
        numbers = [entry["printed_entry_number"] for entry in self.entries]
        self.assertEqual(numbers, list(range(10759, 12309)))
        self.assertEqual(len({entry["id"] for entry in self.entries}), 1550)
        self.assertEqual(self.report["entries"], 1550)
        self.assertTrue(self.report["pass"])

    def test_segments_and_translation_state_are_internally_valid(self) -> None:
        segment_ids = set()
        unresolved = 0
        for entry in self.entries:
            self.assertEqual(entry["schema"], "al-isabah.entry.v1")
            self.assertTrue(entry["segments"])
            self.assertEqual(entry["translation"]["human_review"], "unreviewed")
            for segment in entry["segments"]:
                self.assertTrue(segment["arabic"] or segment["english"])
                self.assertNotIn(segment["id"], segment_ids)
                segment_ids.add(segment["id"])
                self.assertEqual(
                    segment["arabic_sha256"],
                    hashlib.sha256(segment["arabic"].encode("utf-8")).hexdigest(),
                )
                self.assertEqual(
                    segment["english_sha256"],
                    hashlib.sha256(segment["english"].encode("utf-8")).hexdigest(),
                )
            unresolved += len(entry["unresolved"])
            expected_assessment = "needs_attention" if entry["unresolved"] else "passed"
            self.assertEqual(entry["translation"]["machine_assessment"], expected_assessment)
        self.assertEqual(len(segment_ids), self.report["segments"])
        self.assertEqual(unresolved, 281)

    def test_import_is_bound_to_the_manifested_page_evidence(self) -> None:
        source_id = (
            "firstlight:firstlight-research/data/translated/ibn_hajar_isabah/"
            "arabic_v1/volume_08.translation-units.jsonl"
        )
        source = next(
            artifact for artifact in self.manifest["artifacts"]
            if artifact["artifact_id"] == source_id
        )
        self.assertEqual(source["sha256"], self.report["input_sha256"])
        self.assertTrue(all(
            entry["provenance"]["source_artifact_sha256"] == source["sha256"]
            for entry in self.entries
        ))


if __name__ == "__main__":
    unittest.main()


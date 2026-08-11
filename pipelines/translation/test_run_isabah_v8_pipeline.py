from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("run_isabah_v8_pipeline.py")
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("run_isabah_v8_pipeline", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class RunIsabahV8PipelineTests(unittest.TestCase):
    def test_counts_state_and_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "state.json"
            state.write_text(json.dumps({"completed": {"4": {}, "5": {}}, "failed": {"6": {}}}), encoding="utf-8")
            records = root / "records.jsonl"
            records.write_text('{"scan_page":4}\n\n{"scan_page":5}\n', encoding="utf-8")
            self.assertEqual(MODULE.state_counts(state), (2, 1))
            self.assertEqual(MODULE.jsonl_count(records), 2)

    def test_invalidating_readiness_closes_human_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "readiness.json"
            path.write_text(json.dumps({"ready_for_human_review": True, "pipeline_complete": True}), encoding="utf-8")
            MODULE.invalidate_published_readiness(path)
            state = json.loads(path.read_text(encoding="utf-8"))
            self.assertFalse(state["ready_for_human_review"])
            self.assertFalse(state["pipeline_complete"])
            self.assertEqual(state["gate_state"], "autonomous_pipeline_in_progress")


if __name__ == "__main__":
    unittest.main()

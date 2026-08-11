from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_codex_contexts.py"
SPEC = importlib.util.spec_from_file_location("run_codex_contexts", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class ContextPassTests(unittest.TestCase):
    def test_selects_only_context_and_hashes_source(self) -> None:
        classification = {
            "source_results": [{"result_id": "a", "pages": [{"index": 1}]}],
            "items": [
                {"result_id": "a", "decision": "include_context", "relationship": "trade", "rationale": "adds fact", "relevant_arabic": "نص"},
                {"result_id": "b", "decision": "exclude_other_person", "relationship": "", "rationale": "other", "relevant_arabic": ""},
            ],
        }
        items = MODULE.context_items(classification)
        self.assertEqual([item["result_id"] for item in items], ["a"])
        self.assertEqual(items[0]["arabic_sha256"], MODULE.sha256_text("نص"))


if __name__ == "__main__":
    unittest.main()

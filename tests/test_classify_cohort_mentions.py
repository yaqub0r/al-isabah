from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "classify_cohort_mentions.py"
SPEC = importlib.util.spec_from_file_location("classify_cohort_mentions", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class MentionClassifierTests(unittest.TestCase):
    def test_extractive_excerpt_may_retain_non_contiguous_footnotes(self) -> None:
        source = "first relevant\nunrelated\n_________\n(1) exact note"
        excerpt = "first relevant\n_________\n(1) exact note"
        self.assertTrue(MODULE.is_extractive_excerpt(source, excerpt))
        self.assertFalse(MODULE.is_extractive_excerpt(source, "first altered"))

    def test_detects_passage_already_covered_by_selected_entry(self) -> None:
        sources = [(2897, "first line\nother\nfootnote")]
        self.assertEqual(MODULE.covered_selected_entry("first line\nfootnote", sources), 2897)

    def test_deduplicates_literal_results_and_verifies_cache_hash(self) -> None:
        text = "ذكر خديجة"
        digest = MODULE.sha256_text(text)
        discovery = {"results": [{
            "result_id": "r1", "literal_match": True, "text_sha256": digest,
            "cache_key": f"sha256/{digest[:2]}/{digest}.json",
        }, {
            "result_id": "r1", "literal_match": True, "text_sha256": digest,
            "cache_key": f"sha256/{digest[:2]}/{digest}.json",
        }]}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / discovery["results"][0]["cache_key"]
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({
                "sha256": digest,
                "result": {"text": text, "metadata": {"pages": [{"index": 2, "page": 3, "volume": "1"}]}},
            }), encoding="utf-8")
            items = MODULE.unique_literal_results(discovery, root)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["text"], text)


if __name__ == "__main__":
    unittest.main()

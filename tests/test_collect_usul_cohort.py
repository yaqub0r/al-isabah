from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
import urllib.parse
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "collect_usul_cohort.py"
SPEC = importlib.util.spec_from_file_location("collect_usul_cohort", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class CohortCollectorTests(unittest.TestCase):
    def test_paginates_and_preserves_literal_context(self) -> None:
        calls = []

        def fake_request(url: str) -> dict:
            calls.append(url)
            page = int(urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["page"][0])
            if page == 1:
                return {
                    "total": 2,
                    "totalPages": 2,
                    "hasNextPage": True,
                    "results": [{"id": "a", "text": "١١٠٩٢- خديجة بنت خويلد\nنص", "metadata": {"pages": [{"volume": "8", "page": 99}]}}],
                }
            return {
                "total": 2,
                "totalPages": 2,
                "hasNextPage": False,
                "results": [{"id": "b", "text": "٤٣٢٠- طيابة\nلا تطابق", "metadata": {"pages": [{"volume": "3", "page": 445}]}}],
            }

        spec = {
            "schema": MODULE.SPEC_SCHEMA,
            "cohort_id": "test",
            "canonical_source": {"book_id": "book", "version_id": "version"},
            "discovery_queries": [{"id": "name", "arabic": "خديجة"}],
        }
        with tempfile.TemporaryDirectory() as temporary:
            inventory = MODULE.build_inventory(spec, Path(temporary), request_json=fake_request)
            self.assertEqual(len(calls), 2)
            self.assertTrue(inventory["searches"][0]["complete"])
            self.assertEqual(inventory["summary"]["literal_occurrences"], 1)
            self.assertEqual(inventory["results"][0]["occurrences"][0]["entry_number"], 11092)
            cached = list(Path(temporary).rglob("*.json"))
            self.assertEqual(len(cached), 2)
            self.assertEqual(json.loads(cached[0].read_text(encoding="utf-8"))["schema"], "al-isabah.usul-result-cache.v1")

    def test_rejects_incomplete_pagination(self) -> None:
        def fake_request(_url: str) -> dict:
            return {"total": 2, "totalPages": 1, "hasNextPage": False, "results": [{"id": "a", "text": "x"}]}

        with self.assertRaisesRegex(RuntimeError, "result count mismatch"):
            MODULE.collect_query({"book_id": "b", "version_id": "v"}, "q", request_json=fake_request)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).with_name("usul_secondary_witness.py")
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("usul_secondary_witness", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class _Response:
    def __init__(self, payload: dict):
        self.payload = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return self.payload


class UsulSecondaryWitnessTests(unittest.TestCase):
    def test_clean_query_removes_heading_gloss_after_colon(self) -> None:
        self.assertEqual(
            MODULE.clean_query(
                "\u0645\u0639\u0627\u0630\u0629: \u062c\u0627\u0631\u064a\u0629 \u0639\u0628\u062f \u0627\u0644\u0644\u0647 \u0628\u0646 \u0623\u0628\u064a \u0627\u0628\u0646 \u0633\u0644\u0648\u0644"
            ),
            "\u0645\u0639\u0627\u0630\u0629",
        )
        self.assertEqual(
            MODULE.clean_query(
                "\u0642\u0631\u064a\u0628\u0629: \u0628\u0641\u062a\u062d \u0623\u0648\u0644\u0647\u060c \u0648\u064a\u0642\u0627\u0644 \u0628\u0627\u0644\u062a\u0635\u063a\u064a\u0631"
            ),
            "\u0642\u0631\u064a\u0628\u0629",
        )

    def test_fallback_queries_preserve_person_name_structure(self) -> None:
        self.assertEqual(
            MODULE.fallback_queries("آسية بنت الفرج الجرهمية"),
            ["آسية بنت", "بنت الفرج", "آسية"],
        )

    def test_select_queries_prefers_concern_local_person_name(self) -> None:
        source = {
            "arabic_text": "١٠٧٦٠- آسية بنت الفرج الجرهمية. جاءت آسية بنت الفرج إلى النبي.",
            "heading_titles": ["١٠٧٦٠- آسية بنت الفرج الجرهمية"],
        }
        translation = {"names": [
            {"arabic": "آسية بنت الفرج", "english": "Asiyah bint al-Faraj", "kind": "person"},
            {"arabic": "النبي", "english": "the Prophet", "kind": "person"},
        ]}
        concerns = [{"arabic_span": "جاءت آسية بنت الفرج إلى النبي", "category": "name"}]
        self.assertEqual(MODULE.select_queries(source, translation, concerns), ["آسية بنت الفرج الجرهمية"])

    def test_select_queries_falls_back_to_nearest_entry_heading(self) -> None:
        source = {
            "arabic_text": "١- آمنة بنت الأرقم\nنص أول\n٢- آمنة بنت خلف\nعبارة غامضة هنا",
            "heading_titles": ["١- آمنة بنت الأرقم", "٢- آمنة بنت خلف"],
        }
        concerns = [{"arabic_span": "عبارة غامضة", "category": "source_text"}]
        self.assertEqual(
            MODULE.select_queries(source, {"names": []}, concerns),
            ["آمنة بنت خلف"],
        )

    def test_select_queries_uses_previous_heading_for_page_continuation(self) -> None:
        previous_source = {
            "arabic_text": "١٠٧٩١- أروى بنت عبد المطلب\nبداية الخبر",
            "heading_titles": ["١٠٧٩١- أروى بنت عبد المطلب"],
        }
        source = {
            "arabic_text": "واساه في ذي دمه وماله\n١٠٧٩٢- أروى بنت عميس",
            "heading_titles": ["١٠٧٩٢- أروى بنت عميس"],
        }
        concerns = [{"arabic_span": "واساه في ذي دمه وماله", "category": "continuation"}]
        self.assertEqual(
            MODULE.select_queries(
                source,
                {"names": [{"arabic": "محمد", "kind": "person"}]},
                concerns,
                previous_source=previous_source,
            ),
            ["أروى بنت عبد المطلب"],
        )

    def test_select_queries_does_not_search_broadly_for_cited_compiler(self) -> None:
        source = {
            "arabic_text": "١٠٧٦٠- آسية بنت الفرج الجرهمية\nذكرها ابن منده، ولم يخرجه ابن منده.",
            "heading_titles": ["١٠٧٦٠- آسية بنت الفرج الجرهمية"],
        }
        translation = {"names": [
            {"arabic": "آسية بنت الفرج", "english": "Asiyah bint al-Faraj", "kind": "person"},
            {"arabic": "ابن منده", "english": "Ibn Mandah", "kind": "person"},
        ]}
        concerns = [
            {"arabic_span": "آسية بنت الفرج", "category": "name"},
            {"arabic_span": "لم يخرجه ابن منده", "category": "reference"},
        ]
        self.assertEqual(MODULE.select_queries(source, translation, concerns), ["آسية بنت الفرج الجرهمية"])

    @mock.patch.object(MODULE.urllib.request, "urlopen")
    def test_search_source_caches_exact_text_and_page_metadata(self, urlopen: mock.Mock) -> None:
        urlopen.return_value = _Response({
            "total": 1,
            "results": [{
                "id": "result-1",
                "text": "كتاب النساء\n٦٦٨٩ - آسية بنت الفرج الجرهمية",
                "metadata": {"pages": [{"index": 3276, "page": 3, "volume": "7"}]},
            }],
        })
        with tempfile.TemporaryDirectory() as directory:
            first = MODULE.search_source(
                source=MODULE.WITNESS_SOURCES[0],
                query="آسية بنت الفرج",
                cache_root=Path(directory),
            )
            second = MODULE.search_source(
                source=MODULE.WITNESS_SOURCES[0],
                query="آسية بنت الفرج",
                cache_root=Path(directory),
            )
        self.assertEqual(first["retrieval_state"], "hit")
        self.assertEqual(first["hits"][0]["metadata"]["pages"][0]["volume"], "7")
        self.assertEqual(first, second)
        self.assertEqual(urlopen.call_count, 1)

    @mock.patch.object(MODULE.urllib.request, "urlopen")
    def test_cache_only_source_search_never_contacts_network(self, urlopen: mock.Mock) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = MODULE.search_source(
                source=MODULE.WITNESS_SOURCES[0],
                query="missing cached query",
                cache_root=Path(directory),
                cache_only=True,
            )
        self.assertEqual(result["retrieval_state"], "error")
        self.assertEqual(result["error"], "cache_miss")
        urlopen.assert_not_called()

    @mock.patch.object(MODULE.urllib.request, "urlopen")
    def test_query_local_provider_error_is_cached_as_unavailable(
        self, urlopen: mock.Mock
    ) -> None:
        urlopen.side_effect = urllib.error.HTTPError(
            "https://api.usul.ai/search/content", 500, "Internal Server Error", {}, None
        )
        query = "\u062e\u0631\u0642\u0627\u0621"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = MODULE.retrieve_secondary_witnesses(
                source={"arabic_text": query, "heading_titles": [query]},
                translation={"names": []},
                concerns=[],
                cache_root=root,
                query_limit=1,
                retries=1,
                cache_unavailable_errors=True,
            )
            replay = MODULE.search_source(
                source=MODULE.WITNESS_SOURCES[0],
                query=query,
                cache_root=root,
                cache_only=True,
            )

        self.assertEqual(
            [item["retrieval_state"] for item in evidence],
            ["unavailable"] * len(MODULE.WITNESS_SOURCES),
        )
        self.assertEqual(replay["retrieval_state"], "unavailable")
        self.assertEqual(replay["error"], "HTTP 500")
        self.assertEqual(urlopen.call_count, len(MODULE.WITNESS_SOURCES))

    @mock.patch.object(MODULE.urllib.request, "urlopen")
    def test_authenticated_v1_fallback_normalizes_highlights(
        self, urlopen: mock.Mock
    ) -> None:
        legacy_error = urllib.error.HTTPError(
            "https://api.usul.ai/search/content", 500, "Internal Server Error", {}, None
        )
        urlopen.side_effect = [legacy_error, _Response({
            "total": 1,
            "results": [{
                "score": 12.5,
                "versionId": "version",
                "node": {
                    "id": "v1-result",
                    "highlights": ["<em>Ø®Ø±Ù†ÙŠÙ‚</em> Ø¨Ù†Øª Ø­ØµÙ†"],
                    "metadata": {"pages": [{"page": 123, "volume": "4"}]},
                },
            }],
        })]
        with tempfile.TemporaryDirectory() as directory:
            result = MODULE.search_source(
                source=MODULE.WITNESS_SOURCES[0],
                query="Ø®Ø±Ù†ÙŠÙ‚",
                cache_root=Path(directory),
                retries=1,
                authenticated_api_key="secret-not-recorded",
            )
        self.assertEqual(result["retrieval_state"], "hit")
        self.assertEqual(result["retrieval_route"], "authenticated_v1_content_search")
        self.assertEqual(result["legacy_http_status"], 500)
        self.assertNotIn("<em>", result["hits"][0]["text"])
        self.assertEqual(result["hits"][0]["metadata"]["pages"][0]["page"], 123)
        self.assertNotIn("secret-not-recorded", json.dumps(result))

    @mock.patch.object(MODULE, "search_source")
    def test_source_health_fails_closed_when_one_corpus_is_unavailable(self, search: mock.Mock) -> None:
        search.side_effect = [
            {"retrieval_state": "hit", "reported_total": 1},
            {"retrieval_state": "error", "reported_total": 0, "error": "network"},
            *(
                {"retrieval_state": "hit", "reported_total": 1}
                for _ in MODULE.WITNESS_SOURCES[2:]
            ),
        ]
        with tempfile.TemporaryDirectory() as directory:
            health = MODULE.verify_source_health(cache_root=Path(directory))
        self.assertFalse(health["pass"])
        self.assertTrue(health["live_queries"])
        self.assertTrue(all(call.kwargs["use_cache"] is False for call in search.call_args_list))
        self.assertEqual(
            [item["work_id"] for item in health["checks"]],
            [item["work_id"] for item in MODULE.WITNESS_SOURCES],
        )

    @mock.patch.object(MODULE, "search_source")
    def test_retrieval_records_successful_query_fallback(self, search: mock.Mock) -> None:
        search.side_effect = [
            {"retrieval_state": "error", "error": "HTTP 500"},
            {"retrieval_state": "hit", "query": "آسية بنت", "hits": []},
            *(
                {"retrieval_state": "hit", "query": "آسية بنت الفرج الجرهمية", "hits": []}
                for _ in MODULE.WITNESS_SOURCES[1:]
            ),
        ]
        with tempfile.TemporaryDirectory() as directory:
            evidence = MODULE.retrieve_secondary_witnesses(
                source={"arabic_text": "", "heading_titles": []},
                translation={"names": []},
                concerns=[],
                cache_root=Path(directory),
                query_limit=0,
            )
        self.assertEqual(evidence, [])

        # Exercise the per-source fallback using one selected heading query.
        search.reset_mock()
        search.side_effect = [
            {"retrieval_state": "error", "error": "HTTP 500"},
            {"retrieval_state": "hit", "query": "آسية بنت", "hits": []},
            *(
                {"retrieval_state": "hit", "query": "آسية بنت الفرج الجرهمية", "hits": []}
                for _ in MODULE.WITNESS_SOURCES[1:]
            ),
        ]
        with tempfile.TemporaryDirectory() as directory:
            evidence = MODULE.retrieve_secondary_witnesses(
                source={
                    "arabic_text": "آسية بنت الفرج الجرهمية",
                    "heading_titles": ["آسية بنت الفرج الجرهمية"],
                },
                translation={"names": []},
                concerns=[],
                cache_root=Path(directory),
                query_limit=1,
            )
        self.assertEqual(len(evidence), len(MODULE.WITNESS_SOURCES))
        self.assertTrue(evidence[0]["query_fallback_used"])
        self.assertEqual(evidence[0]["requested_query"], "آسية بنت الفرج الجرهمية")
        self.assertEqual(evidence[0]["query_fallback_reason"], "HTTP 500")


if __name__ == "__main__":
    unittest.main()

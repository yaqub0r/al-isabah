import json
import hashlib
import tempfile
import unittest
from pathlib import Path

from render_english_review import read_units, render_document


class RenderEnglishReviewTests(unittest.TestCase):
    def test_skips_pending_units_and_escapes_operator_visible_text(self):
        translated = {
            "unit_id": "work:v08:p0004",
            "source": {"scan_page": 4, "text": "آسية بنت الحارث"},
            "target": {
                "text": "Entry 1 - A <name> & witness",
                "printed_page": 3,
                "flags": ["name_<review>"],
                "names": [{"arabic": "آسية", "english": "Asiyah", "kind": "person"}],
                "unresolved": [{
                    "category": "source_text",
                    "explanation": "A damaged preposition remains.",
                    "human_review_priority": "high",
                }],
            },
            "review": {"state": "unreviewed"},
            "urdu_cross_check": {
                "state": "resolved", "citation": [41], "notes": "The witnesses support this reading.",
                "candidates": [{
                    "scan_page": 44,
                    "score": 52.5,
                    "expected_scan_page": 41,
                    "distance_from_expected": 3,
                    "selection_signals": ["exact_biography_heading", "expected_page_proximity"],
                }],
            },
            "collateral_cross_check": {
                "state": "resolved",
                "evidence": [{
                    "title": "Usd <al-Ghaba>", "query": "آسية", "retrieval_state": "hit",
                    "facsimile_url": "https://assets.example/witness.pdf",
                    "hits": [{
                        "text": "نص <الشاهد>", "text_truncated": False,
                        "metadata": {"pages": [{"volume": "7", "page": 3, "index": 3276}]},
                    }],
                }],
            },
            "supplemental_cross_check": {
                "state": "partially_resolved",
                "evidence": [{
                    "evidence_id": "parallel-1",
                    "kind": "parallel_transmission",
                    "title": "Sunan source <edition>",
                    "language": "Arabic",
                    "citation": "vol. 1, p. 72",
                    "source_url": "https://example.test/source",
                    "excerpt": "parallel <Arabic> chain",
                    "excerpt_sha256": "abc123",
                    "acquisition_note": "Parallel only; canonical text remains authoritative.",
                }],
            },
        }
        pending = {
            "unit_id": "work:v08:p0005",
            "source": {"scan_page": 5},
            "target": {"text": None},
            "review": {"state": "unreviewed"},
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "units.jsonl"
            path.write_text(
                "\n".join(json.dumps(unit) for unit in (translated, pending)),
                encoding="utf-8",
            )
            units = read_units(path)
            document = render_document(units, path)
            source_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()

        self.assertEqual(len(units), 1)
        self.assertIn("Entry 1 - A &lt;name&gt; &amp; witness", document)
        self.assertIn("name_&lt;review&gt;", document)
        self.assertNotIn("work:v08:p0005", document)
        self.assertIn("Open aligned Arabic scan", document)
        self.assertIn("Unapproved research translation", document)
        self.assertIn("Canonical Arabic", document)
        self.assertIn("آسية بنت الحارث", document)
        self.assertIn("Asiyah", document)
        self.assertIn("Explicitly unresolved", document)
        self.assertIn("A damaged preposition remains.", document)
        self.assertIn("Witness evidence and decision", document)
        self.assertIn("Urdu scan 41", document)
        self.assertIn("Urdu retrieval candidates", document)
        self.assertIn("Urdu scan 44", document)
        self.assertIn("expected 41, distance 3", document)
        self.assertIn("exact biography heading", document)
        self.assertIn("Usd &lt;al-Ghaba&gt;", document)
        self.assertIn("نص &lt;الشاهد&gt;", document)
        self.assertIn("vol. 7, p. 3 (index 3276)", document)
        self.assertIn("Sunan source &lt;edition&gt;", document)
        self.assertIn("parallel transmission", document)
        self.assertIn("parallel &lt;Arabic&gt; chain", document)
        self.assertIn('lang="ar" dir="rtl"', document)
        self.assertIn("Excerpt SHA-256: abc123", document)
        self.assertIn("Open cited source", document)
        self.assertIn("Parallel only; canonical text remains authoritative.", document)
        self.assertIn(f'<meta name="firstlight-source-sha256" content="{source_sha256}">', document)


if __name__ == "__main__":
    unittest.main()

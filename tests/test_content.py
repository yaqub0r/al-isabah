import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("validate_content", ROOT / "scripts" / "validate_content.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def entry(entry_id: str = "isabah-entry-00000001") -> dict:
    return {
        "schemaVersion": "2.0.0",
        "id": entry_id,
        "workId": "ibn-hajar-al-isabah",
        "printedEntryNumber": 1,
        "title": {"ar": "اسم", "en": "Name"},
        "segments": [
            {
                "id": f"{entry_id}-segment-0001",
                "arabic": "نص",
                "english": "Text",
                "sourceSpans": [
                    {"editionId": "edition", "volume": 1, "page": 1, "textSha256": "a" * 64}
                ],
            }
        ],
        "names": ["Name"],
        "review": {
            "managementState": "ongoing",
            "arabic": "unreviewed",
            "translation": "unreviewed",
        },
        "compliance": "approved",
        "eligibility": {
            "sourceBinding": "passed",
            "provenanceBinding": "passed",
            "rightsEligibility": "passed",
            "publicOutputBoundary": "passed",
            "deterministicValidation": "passed",
            "substantiveEligibility": "passed",
            "unresolvedStateDisclosure": "passed",
        },
        "unresolved": [],
        "provenance": {"promotionManifest": "compliance/promotions/release.v1.json", "sourceCommit": "b" * 40},
    }


def ledger(entry_id: str = "isabah-entry-00000001") -> dict:
    return {
        "schemaVersion": "1.0.0",
        "workId": "ibn-hajar-al-isabah",
        "entries": [
            {
                "id": entry_id,
                "status": "active",
                "allocationSource": "promotion-test",
                "record": f"content/entries/{entry_id}.json",
                "aliases": [],
            }
        ],
    }


class ContentValidationTests(unittest.TestCase):
    def test_accepts_zero_review_promoted_entry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            content = Path(directory) / "content"
            write_json(content / "entries" / "isabah-entry-00000001.json", entry())
            write_json(content / "identifiers.json", ledger())
            self.assertEqual(MODULE.validate(content), [])

    def test_rejects_unapproved_candidate_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            content = Path(directory) / "content"
            value = entry()
            value["compliance"] = "blocked"
            write_json(content / "entries" / "isabah-entry-00000001.json", value)
            write_json(content / "identifiers.json", ledger())
            errors = MODULE.validate(content)
            self.assertTrue(any("compliance approval" in error for error in errors), errors)

    def test_rejects_missing_human_review_disclosure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            content = Path(directory) / "content"
            value = entry()
            del value["review"]
            write_json(content / "entries" / "isabah-entry-00000001.json", value)
            write_json(content / "identifiers.json", ledger())
            errors = MODULE.validate(content)
            self.assertTrue(any("state disclosure" in error for error in errors), errors)

    def test_rejects_substantive_eligibility_defect(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            content = Path(directory) / "content"
            value = entry()
            value["eligibility"]["substantiveEligibility"] = "blocked"
            write_json(content / "entries" / "isabah-entry-00000001.json", value)
            write_json(content / "identifiers.json", ledger())
            errors = MODULE.validate(content)
            self.assertTrue(any("substantiveEligibility must pass" in error for error in errors), errors)

    def test_rejects_unallocated_record(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            content = Path(directory) / "content"
            write_json(content / "entries" / "isabah-entry-00000001.json", entry())
            write_json(content / "identifiers.json", {"schemaVersion": "1.0.0", "workId": "ibn-hajar-al-isabah", "entries": []})
            errors = MODULE.validate(content)
            self.assertTrue(any("records without active ids" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()

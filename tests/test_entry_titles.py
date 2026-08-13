import copy
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_entry_titles", ROOT / "scripts" / "validate_entry_titles.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class EntryTitleContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = MODULE.load()

    def test_active_profile_is_valid(self) -> None:
        self.assertEqual(MODULE.validate(self.profile), [])

    def test_covers_reported_entries(self) -> None:
        numbers = {item["sourceEntryNumber"] for item in self.profile["decisions"]}
        self.assertEqual(numbers, {11426, 11427, 11430, 11439, 11441})

    def test_rejects_duplicate_entry_decision(self) -> None:
        profile = copy.deepcopy(self.profile)
        profile["decisions"].append(copy.deepcopy(profile["decisions"][0]))
        errors = MODULE.validate(profile)
        self.assertTrue(any("duplicate sourceEntryNumber" in error for error in errors), errors)

    def test_rejects_relationship_prose_in_title(self) -> None:
        profile = copy.deepcopy(self.profile)
        profile["decisions"][0]["title"]["en"] = "Name, the wife of Person"
        errors = MODULE.validate(profile)
        self.assertTrue(any("belongs in the body" in error for error in errors), errors)

    def test_rejects_missing_bilingual_body_opening(self) -> None:
        profile = copy.deepcopy(self.profile)
        profile["decisions"][0]["bodyOpening"]["ar"] = ""
        errors = MODULE.validate(profile)
        self.assertTrue(any("bodyOpening.ar" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()

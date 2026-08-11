from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "import_cohort_entries.py"
SPEC = importlib.util.spec_from_file_location("import_cohort_entries", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class ImportCohortEntriesTests(unittest.TestCase):
    def test_title_removes_arabic_or_latin_entry_number(self) -> None:
        self.assertEqual(MODULE.title_line("٢٢٦٣- خزيمة بن حكيم\ntext"), "خزيمة بن حكيم")
        self.assertEqual(MODULE.title_line("2263—Khuzayma ibn Hakim\nText"), "Khuzayma ibn Hakim")

    def test_stable_entry_identifier_supports_incremental_fill(self) -> None:
        self.assertEqual(MODULE.stable_entry_id(2263), "isabah-entry-00002263")


if __name__ == "__main__":
    unittest.main()

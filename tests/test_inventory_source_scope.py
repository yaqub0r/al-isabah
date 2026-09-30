"""Synthetic-only coverage and public-boundary tests for source inventories."""
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import inventory_source_scope as inventory


class SourceScopeInventoryTests(unittest.TestCase):
    def setUp(self):
        self.source = ROOT / "tests/fixtures/openiti-mini.mARkdown"
        self.manifest = json.loads((ROOT / "tests/fixtures/translation-source.mini.json").read_text())

    def test_complete_inventory_has_duplicates_and_structure_but_no_expression(self):
        value = inventory.build_inventory(self.source, self.manifest, 1, 4)
        self.assertEqual(value["counts"]["entries"], 4)
        self.assertEqual(value["duplicatePrintedNumbers"], [11428])
        self.assertGreater(value["counts"]["structuralSegments"], 3)
        self.assertIn("modern_paratext", [x["kind"] for x in value["exclusions"]])
        encoded = inventory.canonical_bytes(value)
        self.assertNotIn(b"headingArabic", encoded)
        self.assertNotIn(b"rawOpeniti", encoded)
        self.assertNotIn(b"english", encoded)
        pin = value.pop("inventorySha256")
        self.assertEqual(pin, inventory.digest(value))

    def test_subrange_preserves_structure_ownership(self):
        full = inventory.build_inventory(self.source, self.manifest, 1, 4)
        part = inventory.build_inventory(self.source, self.manifest, 2, 3)
        ids = {e["id"] for e in part["entries"]}
        self.assertEqual(part["structuralSegments"], [s for s in full["structuralSegments"] if s["ownerUnitId"] in ids])
        self.assertTrue(part["inheritedContextDependencies"])
        self.assertTrue({s["id"] for s in part["inheritedContextDependencies"]}.isdisjoint({s["id"] for s in part["structuralSegments"]}))

    def test_hash_drift_and_invalid_ranges_fail(self):
        changed = copy.deepcopy(self.manifest)
        changed["download"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "source-binding-invalid"):
            inventory.build_inventory(self.source, changed, 1, 4)
        for a, b in [(0, 4), (1, 5), (3, 2)]:
            with self.assertRaisesRegex(ValueError, "scope-range-invalid"):
                inventory.build_inventory(self.source, self.manifest, a, b)

    def test_unattached_trailing_heading_cannot_disappear(self):
        raw = self.source.read_bytes() + b"\n### | Synthetic trailing heading\n# Substantive tail\n"
        manifest = copy.deepcopy(self.manifest)
        manifest["download"]["bytes"] = len(raw)
        manifest["download"]["sha256"] = hashlib.sha256(raw).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.mARkdown"
            path.write_bytes(raw)
            with self.assertRaisesRegex(ValueError, "unrepresented-source-material"):
                inventory.build_inventory(path, manifest, 1, 4)


if __name__ == "__main__":
    unittest.main()

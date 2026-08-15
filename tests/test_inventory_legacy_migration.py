from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "inventory_legacy_migration.py"
SPEC = importlib.util.spec_from_file_location("inventory_legacy_migration", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class LegacyMigrationInventoryTests(unittest.TestCase):
    def test_inventory_is_deterministic_and_role_summarized(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "source").mkdir()
            (root / "source" / "a.txt").write_text("Arabic", encoding="utf-8")
            (root / "review.json").write_text("{}\n", encoding="utf-8")
            scope = root / "scope.json"
            scope.write_text(json.dumps({
                "schema": MODULE.SCOPE_SCHEMA,
                "includes": [
                    {"path": "source", "kind": "tree", "role": "evidence"},
                    {"path": "review.json", "kind": "file", "role": "review"},
                ],
            }), encoding="utf-8")

            first = MODULE.build_inventory(
                source_root=root,
                scope_path=scope,
                source_repository="owner/repo",
                source_revision="abc123",
                source_state="dirty",
            )
            second = MODULE.build_inventory(
                source_root=root,
                scope_path=scope,
                source_repository="owner/repo",
                source_revision="abc123",
                source_state="dirty",
            )

            self.assertEqual(first, second)
            self.assertEqual(first["summary"]["file_count"], 2)
            self.assertEqual(first["summary"]["by_role"]["evidence"]["file_count"], 1)
            self.assertEqual(
                first["inventory_sha256"], MODULE.canonical_sha256(first["files"])
            )

    def test_rejects_path_traversal(self) -> None:
        for value in ("../secret", "/absolute", "a/../b", "a\\b"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                MODULE.validate_relative_path(value)

    def test_rejects_duplicate_inclusion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "record.json").write_text("{}", encoding="utf-8")
            scope = root / "scope.json"
            scope.write_text(json.dumps({
                "schema": MODULE.SCOPE_SCHEMA,
                "includes": [
                    {"path": "record.json", "kind": "file", "role": "one"},
                    {"path": "record.json", "kind": "file", "role": "two"},
                ],
            }), encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "included twice"):
                MODULE.build_inventory(
                    source_root=root,
                    scope_path=scope,
                    source_repository="owner/repo",
                    source_revision="abc123",
                    source_state="clean",
                )


if __name__ == "__main__":
    unittest.main()

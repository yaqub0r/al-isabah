from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "artifact_store.py"
SPEC = importlib.util.spec_from_file_location("artifact_store", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class ArtifactStoreTests(unittest.TestCase):
    def inventory(self, path: str, value: bytes) -> dict:
        return {
            "schema": MODULE.INVENTORY_SCHEMA,
            "source_repository": "owner/firstlight",
            "source_revision": "abc123",
            "inventory_sha256": digest(b"inventory"),
            "files": [{
                "path": path,
                "role": "translation_and_qa_evidence",
                "byte_size": len(value),
                "sha256": digest(value),
            }],
        }

    def test_manifest_is_content_addressed_and_volume_selectable(self) -> None:
        value = b"review evidence"
        manifest = MODULE.build_manifest(
            self.inventory(
                "firstlight-research/data/translated/ibn_hajar_isabah/arabic_v1/volume_08.review.html",
                value,
            ),
            work_id="ibn-hajar-al-isabah",
        )
        MODULE.validate_manifest(manifest)
        item = manifest["artifacts"][0]
        self.assertEqual(item["volume"], 8)
        self.assertEqual(item["object_key"], f"sha256/{item['sha256'][:2]}/{item['sha256']}")
        self.assertEqual(MODULE.select_artifacts(manifest, volume=8), [item])
        with self.assertRaisesRegex(RuntimeError, "selection is empty"):
            MODULE.select_artifacts(manifest, volume=7)

    def test_stage_reuses_verified_cache_and_detects_corruption(self) -> None:
        value = b"canonical bytes"
        relative = "source/volume_08.pdf"
        manifest = MODULE.build_manifest(self.inventory(relative, value), work_id="work")
        item = manifest["artifacts"][0]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source-root" / relative
            source.parent.mkdir(parents=True)
            source.write_bytes(value)
            cache = root / "cache"
            first = MODULE.stage(root / "source-root", cache, [item])
            second = MODULE.stage(root / "source-root", cache, [item])
            self.assertEqual(first, {"selected": 1, "staged": 1, "reused": 0})
            self.assertEqual(second, {"selected": 1, "staged": 0, "reused": 1})
            MODULE.cached_path(cache, item).write_bytes(b"corrupt")
            with self.assertRaisesRegex(RuntimeError, "Size mismatch"):
                MODULE.verify(cache, [item])

    def test_rejects_traversal_and_conflicting_identity(self) -> None:
        with self.assertRaises(ValueError):
            MODULE.safe_repository_path("../secret")
        value = b"one"
        manifest = MODULE.build_manifest(self.inventory("one.txt", value), work_id="work")
        manifest["artifacts"][0]["object_key"] = "sha256/00/" + "0" * 64
        with self.assertRaisesRegex(RuntimeError, "Invalid content identity"):
            MODULE.validate_manifest(manifest)


if __name__ == "__main__":
    unittest.main()


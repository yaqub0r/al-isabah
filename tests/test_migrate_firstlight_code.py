from __future__ import annotations

import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "migrate_firstlight_code.py"
SPEC = importlib.util.spec_from_file_location("migrate_firstlight_code", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class MigrateFirstLightCodeTests(unittest.TestCase):
    def test_copies_verified_pipeline_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            destination = root / "destination"
            path = source / "firstlight-research/scripts/translation/runner.py"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"print('ok')\n")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            inventory = {"files": [{
                "path": "firstlight-research/scripts/translation/runner.py",
                "role": "candidate_translation_pipeline",
                "byte_size": path.stat().st_size,
                "sha256": digest,
            }]}
            first = MODULE.migrate(source, destination, inventory)
            second = MODULE.migrate(source, destination, inventory)
            self.assertEqual(first, {
                "selected": 1, "copied": 1, "reused": 0, "preserved_adapted": 0,
            })
            self.assertEqual(second, {
                "selected": 1, "copied": 0, "reused": 1, "preserved_adapted": 0,
            })
            self.assertEqual(
                (destination / "pipelines/translation/runner.py").read_bytes(),
                path.read_bytes(),
            )

    def test_refuses_divergent_destination(self) -> None:
        record = {
            "path": "tools/source-acquisition/acquire.py",
            "role": "candidate_acquisition_pipeline",
            "byte_size": 4,
            "sha256": hashlib.sha256(b"good").hexdigest(),
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source/tools/source-acquisition/acquire.py"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"good")
            destination = root / "destination/pipelines/acquisition/acquire.py"
            destination.parent.mkdir(parents=True)
            destination.write_bytes(b"bad")
            with self.assertRaisesRegex(RuntimeError, "Refusing to overwrite"):
                MODULE.migrate(root / "source", root / "destination", {"files": [record]})
            result = MODULE.migrate(
                root / "source", root / "destination", {"files": [record]},
                preserve_adapted=True,
            )
            self.assertEqual(result["preserved_adapted"], 1)
            self.assertEqual(destination.read_bytes(), b"bad")


if __name__ == "__main__":
    unittest.main()

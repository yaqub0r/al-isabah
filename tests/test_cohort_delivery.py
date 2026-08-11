from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


def module(name: str, script: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / script)
    loaded = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(loaded)
    return loaded


ARTIFACTS = module("build_cohort_artifact_manifest", "build_cohort_artifact_manifest.py")
REVIEW = module("render_cohort_review", "render_cohort_review.py")


class CohortDeliveryTests(unittest.TestCase):
    def test_artifact_subset_keeps_facsimile_and_witness_volumes(self) -> None:
        def artifact(path: str) -> dict:
            return {"artifact_id": path, "origin": {"repository_path": path}}
        global_manifest = {
            "schema": "al-isabah.artifact-manifest.v1", "work_id": "w", "generated_from": {},
            "artifacts": [
                artifact("x/ibn_hajar_isabah_v1/usul_canonical_facsimile_v1.pdf"),
                artifact("x/urdu_witness_v1/volume_05.translation-units.jsonl"),
                artifact("x/urdu_witness_v1/volume_06.translation-units.jsonl"),
                artifact("x/urdu_witness_v1/volume_08.translation-units.jsonl"),
            ],
        }
        selected = ARTIFACTS.select(global_manifest, {"cohort_id": "c", "items": [{"volume": 5}, {"volume": 6}]})
        self.assertEqual(len(selected["artifacts"]), 3)

    def test_review_marks_unresolved_material(self) -> None:
        lines = REVIEW.unresolved_markdown([{"issue": "damaged reading", "best_rendering": "best"}])
        self.assertIn("damaged reading", "\n".join(lines))


if __name__ == "__main__":
    unittest.main()

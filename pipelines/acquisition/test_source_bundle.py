import json
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPOSITORY_ROOT / "evidence/schemas/source-bundle-v1.schema.json"
BUNDLE_PATH = REPOSITORY_ROOT / "evidence/firstlight/source/source-bundle.v1.json"
ARTIFACT_MANIFEST_PATH = REPOSITORY_ROOT / "evidence/manifests/firstlight-artifacts.v1.json"


class SourceBundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.bundle = json.loads(BUNDLE_PATH.read_text(encoding="utf-8"))
        cls.artifact_manifest = json.loads(ARTIFACT_MANIFEST_PATH.read_text(encoding="utf-8"))

    def test_bundle_has_schema_required_fields_and_unique_artifacts(self):
        for field in self.schema["required"]:
            self.assertIn(field, self.bundle)
        required_artifact_fields = self.schema["$defs"]["artifact"]["required"]
        ids = []
        for artifact in self.bundle["artifacts"]:
            for field in required_artifact_fields:
                self.assertIn(field, artifact, f"{artifact.get('artifact_id')} lacks {field}")
            ids.append(artifact["artifact_id"])
        self.assertEqual(len(ids), len(set(ids)))

    def test_bundle_implements_required_source_and_english_roles(self):
        roles = {artifact["role"] for artifact in self.bundle["artifacts"]}
        self.assertTrue(
            {"canonical_facsimile", "canonical_source_text", "structured_english", "english_presentation"}.issubset(roles)
        )
        presentation = next(artifact for artifact in self.bundle["artifacts"] if artifact["role"] == "english_presentation")
        structured = next(artifact for artifact in self.bundle["artifacts"] if artifact["role"] == "structured_english")
        self.assertIn(structured["artifact_id"], presentation["derived_from"])
        self.assertIn(presentation["state"], {"draft", "verified_local"})
        self.assertEqual(self.bundle["workflow"]["english_approval"]["state"], "review_required")

    def test_verified_local_hashes_are_preserved_by_artifact_manifest(self):
        artifacts_by_path = {
            artifact["origin"]["repository_path"]: artifact
            for artifact in self.artifact_manifest["artifacts"]
        }
        for artifact in self.bundle["artifacts"]:
            if artifact["state"] != "verified_local":
                continue
            paths = artifact.get("local_path")
            paths = paths if isinstance(paths, list) else [paths]
            for path in paths:
                if path in artifacts_by_path:
                    if not artifact.get("sha256"):
                        continue
                    self.assertEqual(
                        artifacts_by_path[path]["sha256"],
                        artifact["sha256"],
                        artifact["artifact_id"],
                    )
                    continue
                prefix = path.rstrip("/") + "/"
                self.assertTrue(
                    any(candidate.startswith(prefix) for candidate in artifacts_by_path),
                    f"Missing manifest record or descendants for {path}",
                )


if __name__ == "__main__":
    unittest.main()

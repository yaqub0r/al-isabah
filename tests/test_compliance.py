import copy
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_compliance", ROOT / "scripts" / "validate_compliance.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class ComplianceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = MODULE.load_json(MODULE.POLICY_PATH)
        cls.register = MODULE.load_json(MODULE.REGISTER_PATH)
        cls.promotion = MODULE.load_json(MODULE.PROMOTION_PATH)
        cls.retirement = MODULE.load_json(MODULE.RETIREMENT_PATH)

    def validate(self, *, policy=None, register=None, promotion=None):
        return MODULE.validate_all(
            copy.deepcopy(policy or self.policy),
            copy.deepcopy(register or self.register),
            copy.deepcopy(promotion or self.promotion),
            copy.deepcopy(self.retirement),
        )

    def test_current_blocked_manifest_is_valid(self):
        self.assertEqual(self.validate(), [])

    def test_eligible_claim_rejects_non_public_dependency(self):
        promotion = copy.deepcopy(self.promotion)
        promotion["status"] = "eligible"
        promotion["public_release_eligible"] = True
        promotion["blockers"] = []
        promotion["reviews"] = {
            "source_compliance": "approved",
            "human_scholarly": "approved",
            "canonical_repository": "approved",
        }
        errors = self.validate(promotion=promotion)
        self.assertTrue(
            any("depends on non-approved artifacts" in error for error in errors),
            errors,
        )

    def test_eligible_claim_requires_all_reviews(self):
        register = copy.deepcopy(self.register)
        for artifact in register["artifacts"]:
            artifact["classification"] = "approved-for-publication"
        promotion = copy.deepcopy(self.promotion)
        promotion["status"] = "eligible"
        promotion["public_release_eligible"] = True
        promotion["blockers"] = []
        errors = self.validate(register=register, promotion=promotion)
        self.assertIn(
            "promotion: eligible release requires every review to be approved", errors
        )

    def test_eligible_claim_rejects_empty_reviews(self):
        register = copy.deepcopy(self.register)
        for artifact in register["artifacts"]:
            artifact["classification"] = "approved-for-publication"
        promotion = copy.deepcopy(self.promotion)
        promotion["status"] = "eligible"
        promotion["public_release_eligible"] = True
        promotion["blockers"] = []
        promotion["reviews"] = {}
        errors = self.validate(register=register, promotion=promotion)
        self.assertIn(
            "promotion: eligible release requires every review to be approved", errors
        )

    def test_unknown_dependency_fails(self):
        promotion = copy.deepcopy(self.promotion)
        promotion["candidate_revisions"][0]["dependencies"].append("not-registered")
        errors = self.validate(promotion=promotion)
        self.assertTrue(any("unknown dependency not-registered" in e for e in errors))

    def test_private_storage_fields_fail(self):
        register = copy.deepcopy(self.register)
        register["artifacts"][0]["object_key"] = "sha256/private-object"
        errors = self.validate(register=register)
        self.assertTrue(any("private field is not allowed" in error for error in errors))

    def test_local_paths_fail(self):
        register = copy.deepcopy(self.register)
        register["artifacts"][0]["note"] = "C:\\private\\source.pdf"
        errors = self.validate(register=register)
        self.assertTrue(any("local filesystem path" in error for error in errors))

    def test_duplicate_artifact_ids_fail(self):
        register = copy.deepcopy(self.register)
        register["artifacts"].append(copy.deepcopy(register["artifacts"][0]))
        errors = self.validate(register=register)
        self.assertTrue(any("duplicate id" in error for error in errors))

    def test_retirement_record_rejects_public_promotion(self):
        retirement = copy.deepcopy(self.retirement)
        retirement["publication_status"] = "eligible"
        errors = MODULE.validate_retirement(retirement)
        self.assertIn("retirement: legacy candidate content must remain blocked", errors)

    def test_retirement_record_requires_canonical_archive(self):
        retirement = copy.deepcopy(self.retirement)
        retirement["sabiqah_snapshot"]["archive_format"] = "git-archive-tar"
        errors = MODULE.validate_retirement(retirement)
        self.assertIn(
            "retirement: archive format must be canonical-git-tree-tar-v1", errors
        )


if __name__ == "__main__":
    unittest.main()

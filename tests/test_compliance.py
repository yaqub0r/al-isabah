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
            "translation_quality": "approved",
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

    def test_policy_requires_every_local_translation_policy(self):
        policy = copy.deepcopy(self.policy)
        policy["contracts"] = [
            contract
            for contract in policy["contracts"]
            if contract["id"] != "translation-quality-workflow"
        ]
        self.assertIn(
            "policy: all required local translation policies are required",
            self.validate(policy=policy),
        )

    def test_policy_rejects_external_translation_authority(self):
        policy = copy.deepcopy(self.policy)
        policy["authority"]["repository"] = "https://github.com/yaqub0r/sabiqah"
        self.assertIn(
            "policy: authority repository must be Al-Isabah",
            self.validate(policy=policy),
        )

    def test_policy_rejects_stale_local_contract_hash(self):
        policy = copy.deepcopy(self.policy)
        policy["contracts"][0]["sha256"] = "0" * 64
        self.assertTrue(
            any(
                error.endswith("sha256 does not match local file")
                for error in self.validate(policy=policy)
            )
        )

    def test_eligible_claim_requires_translation_quality_controls(self):
        register = copy.deepcopy(self.register)
        for artifact in register["artifacts"]:
            artifact["classification"] = "approved-for-publication"
        promotion = copy.deepcopy(self.promotion)
        promotion["status"] = "eligible"
        promotion["public_release_eligible"] = True
        promotion["blockers"] = []
        promotion["reviews"] = {
            "source_compliance": "approved",
            "translation_quality": "approved",
            "human_scholarly": "approved",
            "canonical_repository": "approved",
        }
        errors = self.validate(register=register, promotion=promotion)
        self.assertIn(
            "promotion: eligible release requires every translation-quality control to pass",
            errors,
        )

    def test_fully_attested_eligible_claim_passes(self):
        register = copy.deepcopy(self.register)
        for artifact in register["artifacts"]:
            artifact["classification"] = "approved-for-publication"
        promotion = copy.deepcopy(self.promotion)
        promotion["status"] = "eligible"
        promotion["public_release_eligible"] = True
        promotion["blockers"] = []
        promotion["reviews"] = {
            "source_compliance": "approved",
            "translation_quality": "approved",
            "human_scholarly": "approved",
            "canonical_repository": "approved",
        }
        promotion["translation_quality"] = {
            control: "passed" for control in MODULE.REQUIRED_TRANSLATION_CONTROLS
        }
        self.assertEqual(self.validate(register=register, promotion=promotion), [])

    def test_public_output_cannot_pass_before_source_authority(self):
        promotion = copy.deepcopy(self.promotion)
        promotion["translation_quality"]["public_output"] = "passed"
        errors = self.validate(promotion=promotion)
        self.assertIn(
            "promotion: public_output cannot pass before source_authority passes",
            errors,
        )

    def test_public_working_display_requires_all_public_gates(self):
        promotion = copy.deepcopy(self.promotion)
        promotion["working_publication"]["gates"]["honorific_preservation"] = (
            "incomplete"
        )
        errors = self.validate(promotion=promotion)
        self.assertIn(
            "promotion: public working gate honorific_preservation must pass", errors
        )

    def test_public_working_counts_must_match_registered_artifact(self):
        promotion = copy.deepcopy(self.promotion)
        promotion["working_publication"]["public_entries"] += 1
        errors = self.validate(promotion=promotion)
        self.assertIn(
            "promotion: working public count differs from its register", errors
        )

    def test_public_working_translation_counts_must_cover_public_entries(self):
        register = copy.deepcopy(self.register)
        artifact = next(
            item
            for item in register["artifacts"]
            if item["id"] == "sabiqah-public-working-corpus-openiti-5835c18-v1"
        )
        artifact["integrity"]["arabic_only_entries"] -= 1
        errors = self.validate(register=register)
        self.assertIn(
            "register: translated and Arabic-only entries must equal public entries",
            errors,
        )

    def test_public_working_quarantine_is_limited_to_contextual_passages(self):
        register = copy.deepcopy(self.register)
        artifact = next(
            item
            for item in register["artifacts"]
            if item["id"] == "sabiqah-public-working-corpus-openiti-5835c18-v1"
        )
        artifact["integrity"]["excluded_contextual_passages"] -= 1
        errors = self.validate(register=register)
        self.assertIn(
            "register: quarantine must contain only excluded contextual passages",
            errors,
        )

    def test_public_working_artifact_must_be_public_approved(self):
        register = copy.deepcopy(self.register)
        artifact = next(
            item
            for item in register["artifacts"]
            if item["id"] == "sabiqah-public-working-corpus-openiti-5835c18-v1"
        )
        artifact["classification"] = "unresolved"
        errors = self.validate(register=register)
        self.assertIn(
            "promotion: working publication artifact is not public-approved", errors
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

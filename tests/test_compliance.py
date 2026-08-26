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
        cls.rights_matrix = MODULE.load_json(MODULE.RIGHTS_MATRIX_PATH)
        cls.governance_reference = MODULE.load_json(
            MODULE.GOVERNANCE_REFERENCE_PATH
        )
        cls.formula_registry = MODULE.load_json(MODULE.FORMULA_REGISTRY_PATH)
        cls.translation_coverage = MODULE.load_json(MODULE.COVERAGE_PATH)

    def validate(
        self,
        *,
        policy=None,
        register=None,
        promotion=None,
        rights_matrix=None,
        governance_reference=None,
        formula_registry=None,
        translation_coverage=None,
    ):
        return MODULE.validate_all(
            copy.deepcopy(self.policy if policy is None else policy),
            copy.deepcopy(self.register if register is None else register),
            copy.deepcopy(self.promotion if promotion is None else promotion),
            copy.deepcopy(self.retirement),
            copy.deepcopy(
                self.rights_matrix if rights_matrix is None else rights_matrix
            ),
            copy.deepcopy(
                self.governance_reference
                if governance_reference is None
                else governance_reference
            ),
            copy.deepcopy(
                self.formula_registry
                if formula_registry is None
                else formula_registry
            ),
            copy.deepcopy(
                self.translation_coverage
                if translation_coverage is None
                else translation_coverage
            ),
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

    def test_governance_reference_rejects_external_authority(self):
        reference = copy.deepcopy(self.governance_reference)
        reference["authority"]["repository"] = "https://github.com/yaqub0r/sabiqah"
        self.assertIn(
            "governance reference: authority or pinning rule is incorrect",
            self.validate(governance_reference=reference),
        )

    def test_governance_reference_rejects_stale_formula_hash(self):
        reference = copy.deepcopy(self.governance_reference)
        artifact = next(
            item
            for item in reference["governanceArtifacts"]
            if item["id"] == "honorific-formula-registry"
        )
        artifact["sha256"] = "0" * 64
        self.assertIn(
            "governance reference: honorific-formula-registry hash is stale",
            self.validate(governance_reference=reference),
        )

    def test_governance_reference_preserves_review_release_semantics(self):
        reference = copy.deepcopy(self.governance_reference)
        reference["releaseSemantics"]["humanReviewChangesReleaseClass"] = True
        self.assertIn(
            "governance reference: release semantics are incorrect",
            self.validate(governance_reference=reference),
        )

    def test_agent_completion_is_independent_of_human_review_coverage(self):
        coverage = copy.deepcopy(self.translation_coverage)
        volume_one = next(
            scope for scope in coverage["scopes"] if scope["scope_id"] == "volume-01"
        )
        volume_one["human_review"]["reviewed_units"] = 1
        volume_one["human_review"]["unreviewed_units"] = 1536
        self.assertEqual(self.validate(translation_coverage=coverage), [])
        self.assertEqual(
            volume_one["agent_completion"]["status"], "agent_complete"
        )

    def test_agent_complete_requires_zero_remaining_agent_units(self):
        coverage = copy.deepcopy(self.translation_coverage)
        volume_one = next(
            scope for scope in coverage["scopes"] if scope["scope_id"] == "volume-01"
        )
        volume_one["agent_completion"]["translated_units"] = 1536
        volume_one["agent_completion"]["remaining_agent_units"] = 1
        errors = self.validate(translation_coverage=coverage)
        self.assertTrue(
            any(
                "agent_complete requires full coverage and zero remaining agent units"
                in error
                for error in errors
            ),
            errors,
        )

    def test_reopened_scope_allows_translated_and_remaining_counts_to_overlap(self):
        coverage = copy.deepcopy(self.translation_coverage)
        volume_two = next(
            scope for scope in coverage["scopes"] if scope["scope_id"] == "volume-02"
        )
        self.assertEqual(volume_two["agent_completion"]["status"], "reopened")
        self.assertEqual(volume_two["agent_completion"]["translated_units"], 1497)
        self.assertEqual(
            volume_two["agent_completion"]["remaining_agent_units"], 1497
        )
        self.assertEqual(self.validate(translation_coverage=coverage), [])

    def test_reopened_scope_requires_machine_actionable_work_remaining(self):
        coverage = copy.deepcopy(self.translation_coverage)
        volume_two = next(
            scope for scope in coverage["scopes"] if scope["scope_id"] == "volume-02"
        )
        volume_two["agent_completion"]["remaining_agent_units"] = 0
        errors = self.validate(translation_coverage=coverage)
        self.assertTrue(
            any(
                "reopened requires machine-actionable work remaining" in error
                for error in errors
            ),
            errors,
        )

    def test_reopened_scope_scopes_prior_evidence_to_historical_claim(self):
        coverage = copy.deepcopy(self.translation_coverage)
        volume_two = next(
            scope for scope in coverage["scopes"] if scope["scope_id"] == "volume-02"
        )

    def test_reopened_historical_counts_match_the_registered_artifact(self):
        coverage = copy.deepcopy(self.translation_coverage)
        volume_two = next(
            scope for scope in coverage["scopes"] if scope["scope_id"] == "volume-02"
        )
        historical = volume_two["agent_completion"]["recovery"][
            "historical_completion"
        ]
        historical["locked_units"] = 1
        historical["translated_units"] = 1
        errors = self.validate(translation_coverage=coverage)
        self.assertTrue(
            any(
                "counts differ from the registered historical artifact" in error
                for error in errors
            ),
            errors,
        )
        recovery = volume_two["agent_completion"]["recovery"]
        recovery["historical_evidence_scope"] = "current-recovery-completion"
        errors = self.validate(translation_coverage=coverage)
        self.assertTrue(
            any(
                "must limit retained evidence to the superseded claim" in error
                for error in errors
            ),
            errors,
        )

    def test_reopened_scope_blocks_current_public_and_canonical_use(self):
        coverage = copy.deepcopy(self.translation_coverage)
        volume_two = next(
            scope for scope in coverage["scopes"] if scope["scope_id"] == "volume-02"
        )
        volume_two["public_working_status"] = "available"
        errors = self.validate(translation_coverage=coverage)
        self.assertTrue(
            any("public-working status must match" in error for error in errors), errors
        )
        self.assertTrue(
            any("volume-02 recovery evidence is incorrect" in error for error in errors),
            errors,
        )

    def test_human_review_cannot_be_made_a_completion_trigger(self):
        coverage = copy.deepcopy(self.translation_coverage)
        coverage["semantics"]["human_review_edits_reopen_completion"] = True
        self.assertIn(
            "translation coverage: completion semantics are incorrect",
            self.validate(translation_coverage=coverage),
        )

    def test_completion_evidence_must_match_the_source_register(self):
        coverage = copy.deepcopy(self.translation_coverage)
        coverage["scopes"][0]["agent_completion"]["evidence"]["sha256"] = "0" * 64
        self.assertTrue(
            any(
                "hash differs from source register" in error
                for error in self.validate(translation_coverage=coverage)
            )
        )

    def test_governance_reference_requires_the_sabiqah_deprecation_inventory(self):
        reference = copy.deepcopy(self.governance_reference)
        reference["deprecatedConsumerAuthorities"].pop()
        self.assertIn(
            "governance reference: exact Sabiqah authority inventory is required",
            self.validate(governance_reference=reference),
        )

    def test_formula_registry_rejects_duplicate_source(self):
        registry = copy.deepcopy(self.formula_registry)
        registry["entries"].append(copy.deepcopy(registry["entries"][0]))
        self.assertTrue(
            any(
                "duplicate formula source" in error
                for error in self.validate(formula_registry=registry)
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
            if item["id"] == MODULE.PUBLIC_CORPUS_ID
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
            if item["id"] == MODULE.PUBLIC_CORPUS_ID
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
            if item["id"] == MODULE.PUBLIC_CORPUS_ID
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

    def test_promotion_must_link_the_book_rights_matrix(self):
        promotion = copy.deepcopy(self.promotion)
        promotion["rights_matrix"] = "compliance/other-rights.json"
        self.assertIn(
            "promotion: rights matrix must use the repository-relative v1 path",
            self.validate(promotion=promotion),
        )

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
        retirement["external_private_snapshot"]["archive_format"] = "git-archive-tar"
        errors = MODULE.validate_retirement(retirement)
        self.assertIn(
            "retirement: archive format must be canonical-git-tree-tar-v1", errors
        )

    def test_rights_matrix_requires_exact_openiti_pin(self):
        matrix = copy.deepcopy(self.rights_matrix)
        source = next(
            item
            for item in matrix["source_editions"]
            if item["source_id"] == "openiti-cleaned-arabic-comparison"
        )
        source["sha256"] = "0" * 64
        self.assertIn(
            "rights matrix: OpenITI artifact hash is not pinned",
            self.validate(rights_matrix=matrix),
        )

    def test_rights_matrix_keeps_private_witnesses_private(self):
        matrix = copy.deepcopy(self.rights_matrix)
        source = next(
            item
            for item in matrix["source_editions"]
            if item["source_id"] == "urdu-modern-translation-witness"
        )
        source["publication_role"] = "arabic-publication-base"
        self.assertIn(
            "rights matrix: urdu-modern-translation-witness must remain private-reference-only",
            self.validate(rights_matrix=matrix),
        )

    def test_rights_matrix_does_not_grant_software_terms(self):
        matrix = copy.deepcopy(self.rights_matrix)
        matrix["public_content_license"]["software_license_granted"] = True
        self.assertIn(
            "rights matrix: software must remain outside the content grant",
            self.validate(rights_matrix=matrix),
        )


if __name__ == "__main__":
    unittest.main()

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
        promotion["eligibility_controls"] = {
            control: "passed" for control in MODULE.REQUIRED_ELIGIBILITY_CONTROLS
        }
        errors = self.validate(promotion=promotion)
        self.assertTrue(
            any("depends on non-approved artifacts" in error for error in errors),
            errors,
        )

    def test_eligible_claim_allows_zero_human_reviews(self):
        register = copy.deepcopy(self.register)
        for artifact in register["artifacts"]:
            artifact["classification"] = "approved-for-publication"
        promotion = copy.deepcopy(self.promotion)
        promotion["status"] = "eligible"
        promotion["public_release_eligible"] = True
        promotion["blockers"] = []
        promotion["eligibility_controls"] = {
            control: "passed" for control in MODULE.REQUIRED_ELIGIBILITY_CONTROLS
        }
        self.assertTrue(
            all(
                scope["human_review"]["reviewed_units"] == 0
                for scope in self.translation_coverage["scopes"]
            )
        )
        self.assertEqual(self.validate(register=register, promotion=promotion), [])

    def test_missing_human_review_disclosure_fails(self):
        promotion = copy.deepcopy(self.promotion)
        del promotion["human_review"]
        self.assertIn(
            "promotion: complete non-gating human-review disclosure is required",
            self.validate(promotion=promotion),
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

    def test_policy_binds_active_title_and_formula_authorities(self):
        contracts = {item["id"]: item for item in self.policy["contracts"]}
        self.assertEqual(
            contracts["entry-title-decisions"],
            {
                "id": "entry-title-decisions",
                "path": "profiles/entry-title-decisions.v8.json",
                "sha256": MODULE.canonical_text_sha256(
                    ROOT / "profiles" / "entry-title-decisions.v8.json"
                ),
            },
        )
        self.assertEqual(
            contracts["entry-title-decision-schema"],
            {
                "id": "entry-title-decision-schema",
                "path": "schemas/entry-title-decisions.v3.schema.json",
                "sha256": MODULE.canonical_text_sha256(
                    ROOT / "schemas" / "entry-title-decisions.v3.schema.json"
                ),
            },
        )
        self.assertEqual(
            contracts["honorific-formula-registry"],
            {
                "id": "honorific-formula-registry",
                "path": "profiles/honorific-formulas.v1.json",
                "sha256": MODULE.canonical_text_sha256(
                    ROOT / "profiles" / "honorific-formulas.v1.json"
                ),
            },
        )

    def test_registry_contains_exact_quoted_prayer_record(self):
        self.assertEqual(self.formula_registry["registryVersion"], "1.6.0")
        prayer = "اللهم بارك على محمد وعلى آل محمد"
        records = [
            item for item in self.formula_registry["entries"]
            if item["source"] == prayer
        ]
        self.assertEqual(
            records,
            [
                {
                    "source": prayer,
                    "target": prayer,
                    "semanticClass": "quoted_prophetic_blessing_with_family",
                    "referentScope": "Muḥammad and the family of Muḥammad",
                    "grammaticalAgreement": (
                        "second-person masculine singular imperative addressed to God; "
                        "masculine singular prophetic referent with family inclusion"
                    ),
                    "expandedArabic": prayer,
                    "accessibleEnglish": (
                        "O God, bless Muḥammad and the family of Muḥammad."
                    ),
                }
            ],
        )

    def test_registry_contains_exact_damaged_prophetic_blessing_variants(self):
        family_expansions = {
            "صلى الله عليه وسلم وعلى آله وسلم": "صلى الله عليه وعلى آله وسلم",
            "صلى الله عليه وسلم وآله": "صلى الله عليه وآله وسلم",
            "صلى الله عيه وآله وسلم": "صلى الله عليه وآله وسلم",
            "صلى الله عليه وسلم وآوله وسلم": "صلى الله عليه وآله وسلم",
            "صلى الله علي وآله وسلم": "صلى الله عليه وآله وسلم",
            "صلى الله عليه وسلم وآله سلم": "صلى الله عليه وآله وسلم",
            "صلى الله عيله وآله وسلم": "صلى الله عليه وآله وسلم",
            "صلى الله عله وآله وسلم": "صلى الله عليه وآله وسلم",
            "صلى الله عليه وسلم وآله ولم": "صلى الله عليه وآله وسلم",
        }
        records = {
            item["source"]: item for item in self.formula_registry["entries"]
        }
        for source, expanded_arabic in family_expansions.items():
            self.assertEqual(
                records[source],
                {
                    "source": source,
                    "target": "﵌",
                    "semanticClass": "prophetic_blessing_with_family",
                    "referentScope": "the Prophet and his family",
                    "grammaticalAgreement": (
                        "masculine singular with family inclusion"
                    ),
                    "expandedArabic": expanded_arabic,
                    "accessibleEnglish": (
                        "May God bless him and his family and grant them peace."
                    ),
                },
            )

        damaged_plain = "صلى الله عيله وسلم"
        self.assertEqual(
            records[damaged_plain],
            {
                "source": damaged_plain,
                "target": "ﷺ",
                "semanticClass": "prophetic_blessing",
                "referentScope": "the Prophet",
                "grammaticalAgreement": "masculine singular",
                "expandedArabic": "صلى الله عليه وسلم",
                "accessibleEnglish": "May God bless him and grant him peace.",
            },
        )

    def test_registry_contains_volume_five_formula_successor_rules(self):
        records = {
            item["source"]: item for item in self.formula_registry["entries"]
        }
        expected = {
            "والله الموفق": (
                "والله الموفق",
                "divine_success_qualification",
            ),
            "ان شاء الله تعالى": (
                "ان شاء الله تعالى",
                "divine_will_qualification",
            ),
            "ان شاء الله": (
                "ان شاء الله",
                "divine_will_qualification",
            ),
            "نسأل الله التوفيق": (
                "نسأل الله التوفيق",
                "divine_success_supplication",
            ),
            "والله عنده حسن المآب": (
                "والله عنده حسن المآب",
                "divine_return_qualification",
            ),
            "والله سبحانه وتعالى اعلم": (
                "والله سبحانه وتعالى اعلم",
                "divine_knowledge_with_exaltation_qualification",
            ),
            "وبالله التوفيق": (
                "وبالله التوفيق",
                "divine_success_qualification",
            ),
            "صلى الله عليه وسلم وأله وسلم": (
                "﵌",
                "prophetic_blessing_with_family",
            ),
            "صلى الله عليه وسلم آله وسلم": (
                "﵌",
                "prophetic_blessing_with_family",
            ),
            "صل الله عليه وآله وسلم": (
                "﵌",
                "prophetic_blessing_with_family",
            ),
            "صلى الله": (
                "صلى الله",
                "truncated_prophetic_blessing",
            ),
            "اللهم صل على النبي والوصي": (
                "اللهم صل على النبي والوصي",
                "quoted_prophetic_blessing_with_legatee",
            ),
            "رحم الله عائشة": ("رحم الله عائشة", "mercy_invocation"),
            "رحم الله هشاما": ("رحم الله هشاما", "mercy_invocation"),
            "رحم الله عبادا": ("رحم الله عبادا", "mercy_invocation"),
            "رحم الله لبيدا": ("رحم الله لبيدا", "mercy_invocation"),
            "رحم الله عروة": ("رحم الله عروة", "mercy_invocation"),
            "رحم الله قسا": ("رحم الله قسا", "mercy_invocation"),
            "يرحمك الله": ("يرحمك الله", "mercy_invocation"),
        }
        for source, (target, semantic_class) in expected.items():
            self.assertEqual(records[source]["target"], target)
            self.assertEqual(records[source]["semanticClass"], semantic_class)

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

    def test_governance_reference_requires_new_execution_interpretation(self):
        for replacement in (True, 0, None):
            reference = copy.deepcopy(self.governance_reference)
            reference["executionSemantics"]["workerSelfReportSufficient"] = replacement
            self.assertIn("governance reference: schema validation failed",
                          self.validate(governance_reference=reference))
        reference = copy.deepcopy(self.governance_reference)
        del reference["executionSemantics"]
        self.assertTrue(self.validate(governance_reference=reference))

    def test_governance_reference_forbids_review_coverage_gating(self):
        reference = copy.deepcopy(self.governance_reference)
        reference["releaseSemantics"]["humanReviewAffectsEligibility"] = True
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

    def test_volume_two_is_agent_complete_after_immutable_submission(self):
        coverage = copy.deepcopy(self.translation_coverage)
        volume_two = next(
            scope for scope in coverage["scopes"] if scope["scope_id"] == "volume-02"
        )
        completion = volume_two["agent_completion"]
        self.assertEqual(completion["status"], "agent_complete")
        self.assertEqual(volume_two["agent_completion"]["translated_units"], 1497)
        self.assertEqual(completion["remaining_agent_units"], 0)
        self.assertEqual(
            completion["evidence"]["source_register_artifact"],
            "issue-0070-public-proposal-v1",
        )
        self.assertEqual(volume_two["workflow_conformance"], "current")
        self.assertEqual(volume_two["public_working_status"], "available")
        self.assertEqual(volume_two["canonical_promotion"], "blocked")
        self.assertEqual(volume_two["human_review"]["reviewed_units"], 0)
        self.assertEqual(volume_two["human_review"]["unreviewed_units"], 1497)
        self.assertEqual(self.validate(translation_coverage=coverage), [])

    def test_volume_two_agent_complete_requires_zero_remaining_units(self):
        coverage = copy.deepcopy(self.translation_coverage)
        volume_two = next(
            scope for scope in coverage["scopes"] if scope["scope_id"] == "volume-02"
        )
        volume_two["agent_completion"]["remaining_agent_units"] = 1
        errors = self.validate(translation_coverage=coverage)
        self.assertTrue(
            any(
                "agent_complete requires full coverage and zero remaining agent units"
                in error
                for error in errors
            ),
            errors,
        )

    def test_volume_four_completion_is_full_and_nonadditive(self):
        coverage = copy.deepcopy(self.translation_coverage)
        scopes = {scope["scope_id"]: scope for scope in coverage["scopes"]}
        cohort = scopes["issue-0086-volume-04"]
        volume = scopes["volume-04"]
        for scope in (cohort, volume):
            completion = scope["agent_completion"]
            self.assertEqual(completion["status"], "agent_complete")
            self.assertEqual(completion["locked_units"], 1633)
            self.assertEqual(completion["translated_units"], 1633)
            self.assertEqual(completion["remaining_agent_units"], 0)
            self.assertEqual(
                completion["evidence"]["source_register_artifact"],
                "issue-0086-public-proposal-v1",
            )
            self.assertEqual(scope["public_working_status"], "blocked")
            self.assertEqual(scope["canonical_promotion"], "blocked")
            self.assertEqual(scope["human_review"]["unreviewed_units"], 1633)
        self.assertIn("not additive", cohort["agent_completion"]["basis"])
        self.assertIn("must not be added", volume["agent_completion"]["basis"])
        self.assertEqual(self.validate(translation_coverage=coverage), [])

    def test_volume_five_completion_is_full_and_nonadditive(self):
        coverage = copy.deepcopy(self.translation_coverage)
        scopes = {scope["scope_id"]: scope for scope in coverage["scopes"]}
        cohort = scopes["issue-0085-volume-05"]
        volume = scopes["volume-05"]
        for scope in (cohort, volume):
            completion = scope["agent_completion"]
            self.assertEqual(completion["status"], "agent_complete")
            self.assertEqual(completion["locked_units"], 1604)
            self.assertEqual(completion["translated_units"], 1604)
            self.assertEqual(completion["remaining_agent_units"], 0)
            self.assertEqual(
                completion["evidence"]["source_register_artifact"],
                "issue-0085-public-proposal-v1",
            )
            self.assertEqual(scope["public_working_status"], "blocked")
            self.assertEqual(scope["canonical_promotion"], "blocked")
            self.assertEqual(scope["human_review"]["unreviewed_units"], 1604)
        self.assertIn("not additive", cohort["agent_completion"]["basis"])
        self.assertIn("must not be added", volume["agent_completion"]["basis"])
        self.assertEqual(self.validate(translation_coverage=coverage), [])

    def test_volume_two_completion_uses_the_corrected_proposal(self):
        coverage = copy.deepcopy(self.translation_coverage)
        volume_two = next(
            scope for scope in coverage["scopes"] if scope["scope_id"] == "volume-02"
        )
        evidence = volume_two["agent_completion"]["evidence"]
        evidence["source_register_artifact"] = "issue-0053-public-proposal-v1"
        evidence["sha256"] = (
            "2d5d43858dfecf55cd82be0ac92fd978087b43daac2c048ac2e718efb9de4a7b"
        )
        errors = self.validate(translation_coverage=coverage)
        self.assertTrue(
            any(
                "volume-02 completion evidence is incorrect" in error
                for error in errors
            ),
            errors,
        )

    def test_volume_two_completion_requires_current_public_working_state(self):
        coverage = copy.deepcopy(self.translation_coverage)
        volume_two = next(
            scope for scope in coverage["scopes"] if scope["scope_id"] == "volume-02"
        )
        volume_two["public_working_status"] = "blocked"
        errors = self.validate(translation_coverage=coverage)
        self.assertTrue(
            any("volume-02 completion evidence is incorrect" in error for error in errors),
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

    def test_eligible_claim_requires_substantive_controls(self):
        register = copy.deepcopy(self.register)
        for artifact in register["artifacts"]:
            artifact["classification"] = "approved-for-publication"
        promotion = copy.deepcopy(self.promotion)
        promotion["status"] = "eligible"
        promotion["public_release_eligible"] = True
        promotion["blockers"] = []
        errors = self.validate(register=register, promotion=promotion)
        self.assertIn(
            "promotion: eligible release requires every substantive control to pass",
            errors,
        )

    def test_source_rights_provenance_and_substantive_blockers_fail_closed(self):
        register = copy.deepcopy(self.register)
        for artifact in register["artifacts"]:
            artifact["classification"] = "approved-for-publication"
        for control in (
            "source_binding",
            "rights_eligibility",
            "provenance_binding",
            "substantive_eligibility",
        ):
            with self.subTest(control=control):
                promotion = copy.deepcopy(self.promotion)
                promotion["status"] = "eligible"
                promotion["public_release_eligible"] = True
                promotion["blockers"] = []
                promotion["eligibility_controls"] = {
                    name: "passed"
                    for name in MODULE.REQUIRED_ELIGIBILITY_CONTROLS
                }
                promotion["eligibility_controls"][control] = "blocked"
                errors = self.validate(register=register, promotion=promotion)
                self.assertIn(
                    "promotion: eligible release requires every substantive control to pass",
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
        promotion["eligibility_controls"] = {
            control: "passed" for control in MODULE.REQUIRED_ELIGIBILITY_CONTROLS
        }
        self.assertEqual(self.validate(register=register, promotion=promotion), [])

    def test_public_output_cannot_pass_before_source_authority(self):
        promotion = copy.deepcopy(self.promotion)
        promotion["eligibility_controls"]["public_output_boundary"] = "passed"
        errors = self.validate(promotion=promotion)
        self.assertIn(
            "promotion: public output cannot pass before source binding",
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

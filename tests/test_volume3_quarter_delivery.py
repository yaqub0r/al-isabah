"""The completed quarter is reviewable without claiming a completed volume or release."""
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import validate_compliance as compliance
import validate_current_release_closure as closure
import validate_public_proposal as proposal_validator
from build_public_review import review
from public_boundary import canonical_json


class VolumeThreeQuarterDeliveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.coverage = compliance.load_json(compliance.COVERAGE_PATH)
        cls.register = compliance.load_json(compliance.REGISTER_PATH)
        cls.artifacts = {a["id"]: a for a in cls.register["artifacts"]}
        cls.proposal = compliance.load_json(compliance.QUARTER_PROPOSAL_PATH)
        cls.second_proposal = compliance.load_json(
            compliance.SECOND_QUARTER_PROPOSAL_PATH
        )

    def scope(self, coverage, scope_id=compliance.QUARTER_SCOPE_ID):
        return next(s for s in coverage["scopes"] if s["scope_id"] == scope_id)

    def test_completed_cohort_and_partial_volume_are_independent_of_review(self):
        self.assertEqual(compliance.validate_translation_coverage(self.coverage, self.artifacts), [])
        quarter = self.scope(self.coverage)
        second_quarter = self.scope(
            self.coverage, compliance.SECOND_QUARTER_SCOPE_ID
        )
        volume = self.scope(self.coverage, "volume-03")
        for cohort in (quarter, second_quarter):
            self.assertEqual(cohort["scope_kind"], "cohort")
            self.assertEqual(cohort["agent_completion"]["status"], "agent_complete")
            self.assertEqual(cohort["agent_completion"]["locked_units"], 373)
            self.assertEqual(cohort["agent_completion"]["remaining_agent_units"], 0)
        self.assertEqual(volume["agent_completion"]["status"], "in_progress")
        self.assertEqual(volume["agent_completion"]["locked_units"], 1491)
        self.assertEqual(volume["agent_completion"]["translated_units"], 746)
        self.assertEqual(volume["agent_completion"]["remaining_agent_units"], 745)
        self.assertNotIn("evidence", volume["agent_completion"])
        for scope, count in (
            (quarter, 373),
            (second_quarter, 373),
            (volume, 1491),
        ):
            self.assertEqual(scope["human_review"], {
                "management_state": "ongoing", "reviewed_units": 0, "unreviewed_units": count})
            self.assertEqual(scope["public_working_status"], "blocked")
            self.assertEqual(scope["canonical_promotion"], "blocked")
        # Coverage semantics retain their historical v2 envelope; Issue 80
        # retains its exact v5 execution binding after v6 becomes active.
        self.assertEqual(self.coverage["policy_binding"], "compliance/policy-binding.v2.json")
        self.assertEqual(self.proposal["policy"]["bindingSha256"],
                         "a89774893a9c623814f51a942c0c43056a0f6ffb8b979a43bc6bdb6e317c3f91")
        self.assertNotEqual(
            self.proposal["policy"]["bindingSha256"],
            compliance.canonical_text_sha256(compliance.POLICY_PATH),
        )
        self.assertEqual(
            self.second_proposal["policy"]["bindingSha256"],
            compliance.canonical_text_sha256(compliance.POLICY_PATH),
        )

    def test_wrong_counts_duplicate_scope_and_full_volume_claim_fail(self):
        for field, value in (("locked_units", 374), ("translated_units", 372), ("remaining_agent_units", 1)):
            with self.subTest(field=field):
                coverage = copy.deepcopy(self.coverage)
                self.scope(coverage)["agent_completion"][field] = value
                self.assertTrue(compliance.validate_translation_coverage(coverage, self.artifacts))
        coverage = copy.deepcopy(self.coverage)
        coverage["scopes"].append(copy.deepcopy(self.scope(coverage)))
        self.assertTrue(compliance.validate_translation_coverage(coverage, self.artifacts))
        coverage = copy.deepcopy(self.coverage)
        completion = self.scope(coverage, "volume-03")["agent_completion"]
        completion.update(status="agent_complete", translated_units=1491, remaining_agent_units=0,
                          evidence=copy.deepcopy(self.scope(coverage)["agent_completion"]["evidence"]))
        self.assertTrue(compliance.validate_translation_coverage(coverage, self.artifacts))

    def test_exact_proposal_range_identity_and_hash_are_bound(self):
        for field, value in (("source_ordinal_start", 3036), ("source_ordinal_end", 3408),
                             ("owned_structural_segments", 12), ("structural_owners", 13)):
            with self.subTest(field=field):
                artifacts = copy.deepcopy(self.artifacts)
                artifacts["issue-0080-public-proposal-v1"]["integrity"][field] = value
                self.assertTrue(compliance.validate_translation_coverage(self.coverage, artifacts))
        for mutation in ("range", "count", "identity", "hash"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                proposal = copy.deepcopy(self.proposal)
                if mutation == "range":
                    proposal["records"][0]["sourceOrdinal"] = 3036
                elif mutation == "count":
                    proposal["records"].pop()
                elif mutation == "identity":
                    proposal["proposalId"] = "issue-0075-public-proposal-v1"
                data = canonical_json(proposal)
                path = Path(directory) / "quarter.json"
                path.write_bytes(data)
                artifacts = copy.deepcopy(self.artifacts)
                coverage = copy.deepcopy(self.coverage)
                digest = "0" * 64 if mutation == "hash" else hashlib.sha256(data).hexdigest()
                artifacts["issue-0080-public-proposal-v1"]["integrity"]["proposal_sha256"] = digest
                self.scope(coverage)["agent_completion"]["evidence"]["sha256"] = digest
                with patch.object(compliance, "QUARTER_PROPOSAL_PATH", path):
                    self.assertTrue(compliance.validate_translation_coverage(coverage, artifacts))

    def test_second_quarter_exact_range_identity_and_hash_are_bound(self):
        config = compliance.QUARTER_COMPLETIONS[
            compliance.SECOND_QUARTER_SCOPE_ID
        ]
        for field, value in (
            ("source_ordinal_start", 3409),
            ("source_ordinal_end", 3781),
            ("owned_structural_segments", 35),
            ("structural_owners", 31),
        ):
            with self.subTest(field=field):
                artifacts = copy.deepcopy(self.artifacts)
                artifacts["issue-0082-public-proposal-v1"]["integrity"][field] = value
                self.assertTrue(
                    compliance.validate_quarter_completion(
                        self.scope(
                            self.coverage, compliance.SECOND_QUARTER_SCOPE_ID
                        ),
                        artifacts,
                        config,
                    )
                )
        for mutation in ("range", "count", "identity", "hash"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                proposal = copy.deepcopy(self.second_proposal)
                if mutation == "range":
                    proposal["records"][0]["sourceOrdinal"] = 3409
                elif mutation == "count":
                    proposal["records"].pop()
                elif mutation == "identity":
                    proposal["proposalId"] = "issue-0075-public-proposal-v1"
                data = canonical_json(proposal)
                path = Path(directory) / "quarter.json"
                path.write_bytes(data)
                artifacts = copy.deepcopy(self.artifacts)
                digest = "0" * 64 if mutation == "hash" else hashlib.sha256(data).hexdigest()
                artifacts["issue-0082-public-proposal-v1"]["integrity"]["proposal_sha256"] = digest
                mutated_config = dict(config, proposalPath=path)
                self.assertTrue(
                    compliance.validate_quarter_completion(
                        self.scope(
                            self.coverage, compliance.SECOND_QUARTER_SCOPE_ID
                        ),
                        artifacts,
                        mutated_config,
                    )
                )

    def test_second_quarter_name_ids_are_source_derived_and_fail_closed(self):
        for record in self.second_proposal["records"]:
            self.assertEqual(
                [name["id"] for name in record["names"]],
                [
                    f"{record['id']}-name-{index:03d}"
                    for index in range(1, len(record["names"]) + 1)
                ],
            )
        proposal = copy.deepcopy(self.second_proposal)
        proposal["records"][0]["names"][0]["id"] = (
            "issue82-rerun2-final-name-a-r001-c001"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "issue-0082.public-proposal.json"
            path.write_bytes(canonical_json(proposal))
            errors = proposal_validator.validate(path)
        self.assertTrue(
            any("category=invalid-stable-name-id" in error for error in errors)
        )

    def test_no_submission_or_distribution_admission_is_claimed(self):
        artifact = self.artifacts["issue-0080-public-proposal-v1"]
        self.assertEqual(artifact["review_status"], compliance.QUARTER_PENDING_STATUS)
        self.assertFalse(any(key.startswith("submitted_") for key in artifact["integrity"]))
        paths, errors = closure.current_proposal_paths()
        self.assertEqual(errors, [])
        self.assertEqual([p.name for p in paths], [
            "issue-0026.public-proposal.json", "issue-0070.public-proposal.json"])
        current = compliance.load_json(closure.CURRENT_CLOSURE)
        self.assertEqual(current["closureId"], "issue-0070-current-public-working-closure-v1")
        self.assertNotIn("issue-0080-public-proposal-v1", [p["proposalId"] for p in current["proposals"]])
        self.assertNotIn("issue-0082-public-proposal-v1", [p["proposalId"] for p in current["proposals"]])
        self.assertFalse(any("volume-03" in item["path"] for item in current["outputInventory"]))
        self.assertFalse((ROOT / "compliance/publication/issue-0080.release-closure.v1.json").exists())
        self.assertFalse((ROOT / "compliance/publication/issue-0082.release-closure.v1.json").exists())
        artifacts = copy.deepcopy(self.artifacts)
        artifacts["issue-0080-public-proposal-v1"]["review_status"] = closure.CURRENT_DISTRIBUTION_REVIEW_STATUS
        self.assertTrue(compliance.validate_translation_coverage(self.coverage, artifacts))

    def test_current_ready_cohort_cannot_be_silently_admitted(self):
        coverage = copy.deepcopy(self.coverage)
        self.scope(coverage)["public_working_status"] = "available"
        register = copy.deepcopy(self.register)
        next(a for a in register["artifacts"] if a["id"] == "issue-0080-public-proposal-v1")["review_status"] = closure.CURRENT_DISTRIBUTION_REVIEW_STATUS
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            coverage_path, register_path = root / "coverage.json", root / "register.json"
            coverage_path.write_bytes(canonical_json(coverage))
            register_path.write_bytes(canonical_json(register))
            paths, errors = closure.current_proposal_paths(coverage_path, register_path)
            self.assertTrue(errors)
            self.assertNotIn(compliance.QUARTER_PROPOSAL_PATH, paths)

    def test_current_closure_metadata_drift_is_rejected(self):
        current = compliance.load_json(closure.CURRENT_CLOSURE)
        self.assertEqual(
            current["sourceRegister"], closure.CURRENT_CLOSURE_SOURCE_REGISTER
        )
        self.assertEqual(
            current["translationCoverage"],
            closure.CURRENT_CLOSURE_TRANSLATION_COVERAGE,
        )
        self.assertNotEqual(
            current["sourceRegister"]["sha256"],
            compliance.canonical_text_sha256(compliance.REGISTER_PATH),
        )
        self.assertNotEqual(
            current["translationCoverage"]["sha256"],
            compliance.canonical_text_sha256(compliance.COVERAGE_PATH),
        )
        current["translationCoverage"]["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "closure.json"
            path.write_bytes(canonical_json(current))
            self.assertTrue(any("current-closure-mismatch" in error for error in closure.validate(path)))

    def test_current_closure_byte_drift_is_rejected(self):
        self.assertEqual(
            hashlib.sha256(closure.CURRENT_CLOSURE.read_bytes()).hexdigest(),
            closure.CURRENT_CLOSURE_SHA256,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "closure.json"
            path.write_bytes(closure.CURRENT_CLOSURE.read_bytes() + b"\n")
            self.assertTrue(
                any(
                    "current-closure-mismatch" in error
                    for error in closure.validate(path)
                )
            )

    def test_review_and_structural_counts_are_separate_from_biographies(self):
        records = self.proposal["records"]
        self.assertEqual([r["sourceOrdinal"] for r in records], list(range(3035, 3408)))
        self.assertTrue(all(r["volume"] == 3 for r in records))
        owned = [[c for c in r["precedingMaterial"] if c["kind"] != "continued_structural_heading"] for r in records]
        self.assertEqual(sum(map(len, owned)), 13)
        self.assertEqual(sum(bool(contexts) for contexts in owned), 12)
        review_path = compliance.QUARTER_PROPOSAL_PATH.with_name("issue-0080.public-review.json")
        self.assertEqual(review_path.read_bytes(), canonical_json(review(compliance.QUARTER_PROPOSAL_PATH)))
        self.assertEqual(hashlib.sha256(review_path.read_bytes()).hexdigest(),
                         self.artifacts["issue-0080-public-proposal-v1"]["integrity"]["public_review_sha256"])

        second_records = self.second_proposal["records"]
        self.assertEqual(
            [record["sourceOrdinal"] for record in second_records],
            list(range(3408, 3781)),
        )
        second_owned = [
            [
                context
                for context in record["precedingMaterial"]
                if context["kind"] != "continued_structural_heading"
            ]
            for record in second_records
        ]
        self.assertEqual(sum(map(len, second_owned)), 36)
        self.assertEqual(sum(bool(contexts) for contexts in second_owned), 32)
        second_review_path = compliance.SECOND_QUARTER_PROPOSAL_PATH.with_name(
            "issue-0082.public-review.json"
        )
        self.assertEqual(
            second_review_path.read_bytes(),
            canonical_json(review(compliance.SECOND_QUARTER_PROPOSAL_PATH)),
        )
        self.assertEqual(
            hashlib.sha256(second_review_path.read_bytes()).hexdigest(),
            self.artifacts["issue-0082-public-proposal-v1"]["integrity"][
                "public_review_sha256"
            ],
        )

    def test_title_uncertainties_survive_public_projection(self):
        records = {r["sourceOrdinal"]: r for r in self.proposal["records"]}
        for ordinal in (3052, 3103, 3123, 3141, 3245, 3296, 3317, 3374):
            with self.subTest(ordinal=ordinal):
                record = records[ordinal]
                self.assertEqual(record["title"]["state"], "needs_attention")
                self.assertTrue(record["unresolved"])
                self.assertIn("Editorial note:", record["english"])
                self.assertEqual(record["humanReview"], "unreviewed")
        second_records = {
            record["sourceOrdinal"]: record
            for record in self.second_proposal["records"]
        }
        second_quarter_unresolved = {
            3475: ("source_route_lacuna", "material"),
            3494: ("legal_term_ambiguity", "source_reported"),
            3507: ("idiom_referent_ambiguity", "source_reported"),
            3609: ("damaged_source_reading", "material"),
            3740: ("name_vocalization", "source_reported"),
        }
        for ordinal, (category, priority) in second_quarter_unresolved.items():
            with self.subTest(ordinal=ordinal):
                record = second_records[ordinal]
                self.assertEqual(record["title"]["state"], "needs_attention")
                self.assertEqual(
                    record["unresolved"],
                    [{"category": category, "priority": priority}],
                )
                self.assertEqual(record["humanReview"], "unreviewed")


if __name__ == "__main__":
    unittest.main()

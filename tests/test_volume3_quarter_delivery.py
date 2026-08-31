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
from build_public_review import review
from public_boundary import canonical_json


class VolumeThreeQuarterDeliveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.coverage = compliance.load_json(compliance.COVERAGE_PATH)
        cls.register = compliance.load_json(compliance.REGISTER_PATH)
        cls.artifacts = {a["id"]: a for a in cls.register["artifacts"]}
        cls.proposal = compliance.load_json(compliance.QUARTER_PROPOSAL_PATH)

    def scope(self, coverage, scope_id=compliance.QUARTER_SCOPE_ID):
        return next(s for s in coverage["scopes"] if s["scope_id"] == scope_id)

    def test_completed_cohort_and_partial_volume_are_independent_of_review(self):
        self.assertEqual(compliance.validate_translation_coverage(self.coverage, self.artifacts), [])
        quarter = self.scope(self.coverage)
        volume = self.scope(self.coverage, "volume-03")
        self.assertEqual(quarter["scope_kind"], "cohort")
        self.assertEqual(quarter["agent_completion"]["status"], "agent_complete")
        self.assertEqual(quarter["agent_completion"]["locked_units"], 373)
        self.assertEqual(quarter["agent_completion"]["remaining_agent_units"], 0)
        self.assertEqual(volume["agent_completion"]["status"], "in_progress")
        self.assertEqual(volume["agent_completion"]["locked_units"], 1491)
        self.assertEqual(volume["agent_completion"]["translated_units"], 373)
        self.assertEqual(volume["agent_completion"]["remaining_agent_units"], 1118)
        self.assertNotIn("evidence", volume["agent_completion"])
        for scope, count in ((quarter, 373), (volume, 1491)):
            self.assertEqual(scope["human_review"], {
                "management_state": "ongoing", "reviewed_units": 0, "unreviewed_units": count})
            self.assertEqual(scope["public_working_status"], "blocked")
            self.assertEqual(scope["canonical_promotion"], "blocked")
        # Coverage semantics retain their historical v2 envelope; this actual
        # translation has its own exact v5 execution binding.
        self.assertEqual(self.coverage["policy_binding"], "compliance/policy-binding.v2.json")
        self.assertEqual(self.proposal["policy"]["bindingSha256"],
                         "a89774893a9c623814f51a942c0c43056a0f6ffb8b979a43bc6bdb6e317c3f91")

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
        self.assertFalse(any("volume-03" in item["path"] for item in current["outputInventory"]))
        self.assertFalse((ROOT / "compliance/publication/issue-0080.release-closure.v1.json").exists())
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
        current["translationCoverage"]["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "closure.json"
            path.write_bytes(canonical_json(current))
            self.assertTrue(any("current-closure-mismatch" in error for error in closure.validate(path)))

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

    def test_title_uncertainties_survive_public_projection(self):
        records = {r["sourceOrdinal"]: r for r in self.proposal["records"]}
        for ordinal in (3052, 3103, 3123, 3141, 3245, 3296, 3317, 3374):
            with self.subTest(ordinal=ordinal):
                record = records[ordinal]
                self.assertEqual(record["title"]["state"], "needs_attention")
                self.assertTrue(record["unresolved"])
                self.assertIn("Editorial note:", record["english"])
                self.assertEqual(record["humanReview"], "unreviewed")


if __name__ == "__main__":
    unittest.main()

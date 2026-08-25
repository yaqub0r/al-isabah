import copy
import importlib.util
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


sys.path.insert(0, str(ROOT / "scripts"))
BOUNDARY = load_module("public_boundary", ROOT / "scripts" / "public_boundary.py")
PROJECT = load_module("project_public_proposal", ROOT / "scripts" / "project_public_proposal.py")
PROPOSAL_VALIDATOR = load_module("validate_public_proposal", ROOT / "scripts" / "validate_public_proposal.py")
REVIEW = load_module("build_public_review", ROOT / "scripts" / "build_public_review.py")
CLOSURE = load_module("validate_release_closure", ROOT / "scripts" / "validate_release_closure.py")
CURRENT_CLOSURE = load_module(
    "validate_current_release_closure",
    ROOT / "scripts" / "validate_current_release_closure.py",
)
BUILD = load_module("build_public_distribution", ROOT / "scripts" / "build_public_distribution.py")
VALIDATE = load_module("validate_public_distribution", ROOT / "scripts" / "validate_public_distribution.py")
TREE = load_module("validate_public_tree", ROOT / "scripts" / "validate_public_tree.py")
COMMIT = "abd81f7eab94158be9e957d4b6f80751f1cc19e8"
GENERATED_AT = "2026-08-14T16:22:30Z"
PROPOSAL_PATH = ROOT / "content" / "public-proposals" / "issue-0026.public-proposal.json"
VOLUME2_PROPOSAL_PATH = ROOT / "content" / "public-proposals" / "issue-0053.public-proposal.json"
VOLUME2_REVIEW_PATH = ROOT / "content" / "public-proposals" / "issue-0053.public-review.json"
EXPECTED_USER_FACING_SHA256 = "702a3af5543f3c8d83aa45559f62a132300cd6dabe7a3b3428940b73d8493047"
VOLUME2_USER_FACING_SHA256 = "872684aaf7ed2ebbc6b78a3500b611321d28475d04d97dc4906ab37a23587423"


class PublicDistributionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proposal = json.loads(PROPOSAL_PATH.read_text(encoding="utf-8"))
        cls.volume2_proposal = json.loads(VOLUME2_PROPOSAL_PATH.read_text(encoding="utf-8"))

    def test_current_tree_and_exact_closure_are_valid(self):
        self.assertEqual(PROPOSAL_VALIDATOR.validate(), [])
        self.assertEqual(CLOSURE.validate(), [])
        self.assertEqual(CURRENT_CLOSURE.validate(), [])
        self.assertEqual(TREE.validate(), [])
        self.assertEqual(REVIEW.canonical_json(REVIEW.review()), (ROOT / "content" / "public-proposals" / "issue-0026.public-review.json").read_bytes())

    def test_exact_1537_record_user_facing_parity_and_stable_order(self):
        records = self.proposal["records"]
        self.assertEqual(len(records), 1537)
        self.assertEqual(self.proposal["baseline"]["userFacingSha256"], EXPECTED_USER_FACING_SHA256)
        self.assertEqual(BOUNDARY.sha256_bytes(PROJECT.parity_projection(records)), EXPECTED_USER_FACING_SHA256)
        self.assertEqual(PROPOSAL_VALIDATOR.order_sha256(records), "69efa02ecc2c277471bd1108ffb4f6f758c3454659814b2ef3f80fce845f667f")
        self.assertTrue(all(record["schemaVersion"] == "2.0.0" for record in records))
        self.assertTrue(all(record["arabic"].strip() and record["english"].strip() for record in records))

    def test_volume2_packet_set_projection_is_strict_and_agent_complete(self):
        proposal = self.volume2_proposal
        records = proposal["records"]
        self.assertEqual(PROPOSAL_VALIDATOR.validate(VOLUME2_PROPOSAL_PATH), [])
        self.assertEqual(
            REVIEW.canonical_json(REVIEW.review(VOLUME2_PROPOSAL_PATH)),
            VOLUME2_REVIEW_PATH.read_bytes(),
        )
        self.assertEqual(proposal["schemaVersion"], "1.1.0")
        self.assertEqual(len(records), 1497)
        self.assertEqual(records[0]["sourceOrdinal"], 1538)
        self.assertEqual(records[-1]["sourceOrdinal"], 3034)
        self.assertEqual(
            [record["sourceOrdinal"] for record in records],
            list(range(1538, 3035)),
        )
        self.assertEqual(proposal["baseline"]["userFacingSha256"], VOLUME2_USER_FACING_SHA256)
        self.assertEqual(
            BOUNDARY.sha256_bytes(PROJECT.parity_projection(records)),
            VOLUME2_USER_FACING_SHA256,
        )
        self.assertEqual(proposal["evidenceBinding"]["packetCount"], 15)
        self.assertEqual(proposal["evidenceBinding"]["reviewCount"], 15)
        self.assertEqual(proposal["review"]["humanReviewed"], 0)
        self.assertEqual(proposal["review"]["humanUnreviewed"], 1497)
        self.assertTrue(all(record["humanReview"] == "unreviewed" for record in records))
        self.assertTrue(all(record["arabic"].strip() and record["english"].strip() for record in records))
        self.assertEqual(BOUNDARY.boundary_errors(proposal), [])

    def test_v2_build_is_deterministic_and_consumer_compatible(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "distribution"
            manifest = BUILD.build(output, COMMIT, GENERATED_AT)
            self.assertEqual(manifest["counts"]["entries"], 3034)
            self.assertEqual(manifest["counts"]["humanReviewed"], 0)
            self.assertEqual(
                [item["entryCount"] for item in manifest["packets"]],
                [1537, 1497],
            )
            self.assertEqual(manifest["schemaVersion"], "2.0.0")
            self.assertEqual(manifest["canonicalPromotion"], "blocked")
            self.assertEqual(VALIDATE.validate(output), [])
            first = root / "first.zip"
            second = root / "second.zip"
            BUILD.package(output, first)
            BUILD.package(output, second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with zipfile.ZipFile(first) as archive:
                self.assertEqual(
                    sorted(archive.namelist()),
                    [
                        "manifest.json",
                        "records/volume-01.jsonl",
                        "records/volume-02.jsonl",
                        "release-closure.json",
                        "reviews/issue-0026.json",
                        "reviews/issue-0053.json",
                    ],
                )

    def test_all_synthetic_negative_fixture_categories_are_covered(self):
        fixture = json.loads((ROOT / "tests" / "fixtures" / "public-boundary-negative.v1.json").read_text(encoding="utf-8"))
        covered = {item["category"] for item in fixture["cases"]}
        required = {
            "blind-translation", "independent-critique", "witness-resolution", "model-reasoning",
            "prompt-response", "raw-findings", "reconstructive-repair", "absolute-path",
            "relative-path", "unsafe-url", "token-shaped-secret", "unknown-key",
            "raw-packet-inclusion", "raw-review-inclusion", "closure-mismatch", "source-mismatch",
            "rights-mismatch", "policy-mismatch", "user-facing-drift",
        }
        self.assertEqual(covered, required)

    def test_recursive_boundary_rejects_prohibited_categories_at_arbitrary_nesting(self):
        prohibited_keys = ["blindTranslation", "independentCritique", "witnessResolution", "modelReasoning", "promptResponse", "rawFindings", "reconstructiveRepairOperation"]
        for key in prohibited_keys:
            errors = BOUNDARY.boundary_errors({"safe": [{"deeper": {key: "synthetic"}}]})
            self.assertTrue(any("category=prohibited-field" in error for error in errors), key)
        unsafe_values = [
            "C:" + "\\" + "synthetic" + "\\" + "file",
            "/" + "synthetic" + "/" + "file",
            ".." + "/" + "synthetic" + "/" + "file",
            "https:" + "//example.invalid/private",
            "ghp_" + "0" * 24,
            "content/translation-" + "proposals/issue-0026.packet.json",
            "issue-0026." + "review.md",
        ]
        for value in unsafe_values:
            self.assertTrue(BOUNDARY.boundary_errors({"safe": [{"deeper": value}]}), value)

    def test_unknown_keys_are_rejected_at_nested_record_levels(self):
        proposal = copy.deepcopy(self.proposal)
        proposal["records"][0]["title"]["unexpected"] = "synthetic"
        errors = PROPOSAL_VALIDATOR.nested_key_errors(proposal)
        self.assertTrue(any("category=unknown-field" in error for error in errors))

    def test_user_facing_drift_and_source_rights_policy_mismatches_fail(self):
        mutations = [
            ("user-facing", lambda value: value["records"][0].__setitem__("english", value["records"][0]["english"] + " synthetic"), "user-facing-drift"),
            ("source", lambda value: value["sourceAuthority"].__setitem__("commit", "0" * 40), "source-register-mismatch"),
            ("rights", lambda value: value["rights"].__setitem__("matrixId", "synthetic"), "rights-mismatch"),
            ("policy", lambda value: value["policy"].__setitem__("bindingSha256", "0" * 64), "policy-mismatch"),
        ]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "proposal.json"
            for _, mutate, category in mutations:
                proposal = copy.deepcopy(self.proposal)
                mutate(proposal)
                path.write_bytes(BOUNDARY.canonical_json(proposal))
                self.assertTrue(any(f"category={category}" in error for error in PROPOSAL_VALIDATOR.validate(path)), category)

    def test_closure_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "closure.json"
            closure = json.loads(CLOSURE.CLOSURE.read_text(encoding="utf-8"))
            closure["projection"]["entryCount"] -= 1
            path.write_bytes(BOUNDARY.canonical_json(closure))
            self.assertTrue(any("category=projection-mismatch" in error for error in CLOSURE.validate(path)))

    def test_current_closure_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "closure.json"
            closure = json.loads(
                CURRENT_CLOSURE.CURRENT_CLOSURE.read_text(encoding="utf-8")
            )
            closure["reviewCounts"]["humanReviewed"] += 1
            path.write_bytes(BOUNDARY.canonical_json(closure))
            self.assertTrue(
                any(
                    "category=current-closure-mismatch" in error
                    for error in CURRENT_CLOSURE.validate(path)
                )
            )

    def test_diagnostics_do_not_echo_rejected_values(self):
        rejected = "ghp_" + "9" * 24
        errors = BOUNDARY.boundary_errors({"outer": [{"inner": rejected}]})
        rendered = "\n".join(errors + [BOUNDARY.summarize(errors)])
        self.assertNotIn(rejected, rendered)
        self.assertIn("sha256=", rendered)


if __name__ == "__main__":
    unittest.main()

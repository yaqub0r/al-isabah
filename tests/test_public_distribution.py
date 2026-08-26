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
PACKET_PROJECT = load_module(
    "project_packet_set_public_proposal",
    ROOT / "scripts" / "project_packet_set_public_proposal.py",
)
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
VOLUME2_USER_FACING_SHA256 = "60137418e7c1dbd3c9a1020bc290dcb1d8ec539d24fb58fbbc2793332b32b782"


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

    def test_historical_volume2_packet_set_projection_remains_strict(self):
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

    def test_current_closure_quarantines_the_reopened_volume2_scope(self):
        paths, errors = CURRENT_CLOSURE.current_proposal_paths()
        self.assertEqual(errors, [])
        self.assertEqual(paths, [PROPOSAL_PATH])
        closure = json.loads(
            CURRENT_CLOSURE.CURRENT_CLOSURE.read_text(encoding="utf-8")
        )
        self.assertEqual(
            [item["proposalId"] for item in closure["proposals"]],
            ["issue-0026-public-proposal-v1"],
        )
        self.assertEqual(
            closure["historicalClosure"]["path"],
            "compliance/publication/issue-0053.release-closure.v1.json",
        )
        self.assertEqual(
            closure["translationCoverage"]["path"],
            "compliance/translation-coverage.v1.json",
        )
        register = json.loads(
            (ROOT / "compliance" / "source-register.v1.json").read_text(
                encoding="utf-8"
            )
        )
        volume_two = next(
            item
            for item in register["artifacts"]
            if item["id"] == "issue-0053-public-proposal-v1"
        )
        self.assertEqual(
            volume_two["review_status"],
            "historical-reopened-scope-current-distribution-quarantined",
        )

    def test_legacy_volume2_proposal_is_not_current_title_ready(self):
        errors = PROPOSAL_VALIDATOR.validate(
            VOLUME2_PROPOSAL_PATH,
            require_current=True,
        )
        self.assertTrue(
            any("category=historical-proposal-not-current" in error for error in errors),
            errors,
        )

    def test_volume2_first_title_requires_an_exact_bilingual_boundary_decision(self):
        record = self.volume2_proposal["records"][0]
        self.assertEqual(record["sourceOrdinal"], 1538)
        self.assertEqual(
            record["title"],
            {
                "arabic": "حازم غير منسوب روى عبدان ومن طريقه أبو موسى من رواية محمد السعدي",
                "english": "Ḥāzim",
                "method": "primary-name-candidate",
                "state": "ready",
            },
        )
        entry = {
            "sourceOrdinal": 1538,
            "source": {
                "headingArabic": record["title"]["arabic"],
                "arabic": record["arabic"],
            },
            "adjudication": {"english": record["english"]},
            "unresolved": [],
        }
        decision = {
            "title": {"ar": "حازم", "en": "Ḥāzim"},
            "bodyOpening": {
                "ar": "غير منسوب",
                "en": "without a lineage attribution",
            },
        }
        title, arabic, english = PACKET_PROJECT.title_and_body(entry, decision)
        self.assertEqual(title["arabic"], "حازم")
        self.assertEqual(title["english"], "Ḥāzim")
        self.assertEqual(title["method"], "profile-decision")
        self.assertTrue(arabic.startswith("غير منسوب"))
        self.assertTrue(english.startswith("without a lineage attribution"))

    def test_current_title_binding_requires_exact_hash_and_unique_coverage(self):
        profile = PACKET_PROJECT.load_title_profile(PACKET_PROJECT.ENTRY_TITLE_PROFILE)
        decision = next(
            item
            for item in profile["decisions"]
            if item["sourceEntryNumber"] == 11426
        )
        proposal = {
            "entryTitleDecisions": {
                "profileId": "entry-title-decisions.v2",
                "profileSha256": BOUNDARY.sha256_file(PACKET_PROJECT.ENTRY_TITLE_PROFILE),
                "coveredRecordCount": 1,
            },
            "records": [
                {
                    "printedEntryNumber": 11426,
                    "title": {
                        "arabic": decision["title"]["ar"],
                        "english": decision["title"]["en"],
                        "method": "profile-decision",
                    },
                    "arabic": decision["bodyOpening"]["ar"] + " synthetic",
                    "english": decision["bodyOpening"]["en"] + " synthetic",
                }
            ],
        }
        self.assertEqual(PROPOSAL_VALIDATOR._title_decision_errors(proposal), [])
        mismatched = copy.deepcopy(proposal)
        mismatched["records"][0]["title"]["arabic"] += " synthetic continuation"
        mismatched["records"][0]["english"] = "synthetic omitted body opening"
        errors = PROPOSAL_VALIDATOR._title_decision_errors(mismatched)
        self.assertTrue(any("category=title-decision-mismatch" in error for error in errors), errors)
        self.assertTrue(any("category=title-body-opening-mismatch" in error for error in errors), errors)
        proposal["entryTitleDecisions"]["profileSha256"] = "0" * 64
        errors = PROPOSAL_VALIDATOR._title_decision_errors(proposal)
        self.assertTrue(any("category=title-profile-mismatch" in error for error in errors), errors)
        proposal["entryTitleDecisions"]["profileSha256"] = BOUNDARY.sha256_file(
            PACKET_PROJECT.ENTRY_TITLE_PROFILE
        )
        proposal["entryTitleDecisions"]["coveredRecordCount"] = 2
        proposal["records"].append(copy.deepcopy(proposal["records"][0]))
        errors = PROPOSAL_VALIDATOR._title_decision_errors(proposal)
        self.assertTrue(
            any("category=ambiguous-title-decision-key" in error for error in errors),
            errors,
        )

    def test_volume2_slice_requires_distinct_continued_heading_context(self):
        first = self.volume2_proposal["records"][0]
        self.assertEqual(first["sourceOrdinal"], 1538)
        self.assertEqual(first["precedingMaterial"], [])
        errors = PROPOSAL_VALIDATOR._slice_context_errors(self.volume2_proposal)
        self.assertTrue(
            any("category=missing-inherited-slice-context" in error for error in errors),
            errors,
        )
        binding, contexts = PACKET_PROJECT.slice_context(
            1538,
            self.volume2_proposal["sourceAuthority"],
            PROPOSAL_PATH,
        )
        self.assertEqual(binding["state"], "continued")
        self.assertEqual(len(binding["contexts"]), 4)
        self.assertEqual(
            binding["contexts"][-1],
            {
                "sourceOccurrenceId": "openiti-5835c183-before-unit-001536-segment-001",
                "displayContextId": (
                    "continued-before-unit-001538-from-"
                    "openiti-5835c183-before-unit-001536-segment-001"
                ),
            },
        )
        self.assertEqual(len(contexts), 4)
        self.assertTrue(
            all(item["kind"] == "continued_structural_heading" for item in contexts)
        )
        self.assertEqual(
            contexts[-1]["heading"],
            {
                "arabic": "ذكر بقية حرف الحاء بعدها الألف",
                "english": "Remaining Names under the Letter Ḥāʾ Followed by Alif",
                "level": 4,
            },
        )
        self.assertTrue(
            all(
                display["id"] != source["sourceOccurrenceId"]
                for display, source in zip(contexts, binding["contexts"], strict=True)
            )
        )

    def test_packet_projection_preserves_collective_entity_type(self):
        projected = PACKET_PROJECT.public_name(
            {
                "candidateId": "synthetic-collective",
                "observedArabic": "بنو تميم",
                "proposedEnglish": "Banū Tamīm",
                "aliases": [],
                "entityType": "collective",
                "reviewState": "unreviewed",
            }
        )
        self.assertEqual(projected["kind"], "collective")

    def test_v2_build_is_deterministic_and_consumer_compatible(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "distribution"
            manifest = BUILD.build(output, COMMIT, GENERATED_AT)
            self.assertEqual(manifest["counts"]["entries"], 1537)
            self.assertEqual(manifest["counts"]["humanReviewed"], 0)
            self.assertEqual(
                [item["entryCount"] for item in manifest["packets"]],
                [1537],
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
                        "release-closure.json",
                        "reviews/issue-0026.json",
                    ],
                )

    def test_build_rejects_a_stale_quarantined_output(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "distribution"
            stale = output / "records" / "volume-02.jsonl"
            stale.parent.mkdir(parents=True)
            stale.write_text("synthetic historical record\n", encoding="utf-8")
            with self.assertRaisesRegex(
                BUILD.DistributionError,
                "output directory must be empty",
            ):
                BUILD.build(output, COMMIT, GENERATED_AT)
            with self.assertRaises(BUILD.DistributionError):
                BUILD.package(output, Path(temp) / "stale.zip")

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

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch


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
ISSUE_0070_PROPOSAL_PATH = ROOT / "content" / "public-proposals" / "issue-0070.public-proposal.json"
ISSUE_0070_REVIEW_PATH = ROOT / "content" / "public-proposals" / "issue-0070.public-review.json"
ISSUE_0080_PROPOSAL_PATH = ROOT / "content" / "public-proposals" / "issue-0080.public-proposal.json"
ISSUE_0082_PROPOSAL_PATH = ROOT / "content" / "public-proposals" / "issue-0082.public-proposal.json"
ISSUE_0084_PROPOSAL_PATH = ROOT / "content" / "public-proposals" / "issue-0084.public-proposal.json"
ISSUE_0086_PROPOSAL_PATH = ROOT / "content" / "public-proposals" / "issue-0086.public-proposal.json"
ISSUE_0085_PROPOSAL_PATH = ROOT / "content" / "public-proposals" / "issue-0085.public-proposal.json"
ISSUE_0091_PROPOSAL_PATH = ROOT / "content" / "public-proposals" / "issue-0091.public-proposal.json"
ISSUE_0091_REVIEW_PATH = ROOT / "content" / "public-proposals" / "issue-0091.public-review.json"
ISSUE_0096_PROPOSAL_PATH = ROOT / "content" / "public-proposals" / "issue-0096.public-proposal.json"
ISSUE_0096_REVIEW_PATH = ROOT / "content" / "public-proposals" / "issue-0096.public-review.json"
ISSUE_0098_PROPOSAL_PATH = ROOT / "content" / "public-proposals" / "issue-0098.public-proposal.json"
ISSUE_0098_REVIEW_PATH = ROOT / "content" / "public-proposals" / "issue-0098.public-review.json"
ISSUE_0070_RUNTIME_PACKET = (
    ROOT / ".runtime" / "translation" / "packets" / "issue-0070-lineage.json"
)
EXPECTED_USER_FACING_SHA256 = "702a3af5543f3c8d83aa45559f62a132300cd6dabe7a3b3428940b73d8493047"
VOLUME2_USER_FACING_SHA256 = "60137418e7c1dbd3c9a1020bc290dcb1d8ec539d24fb58fbbc2793332b32b782"


class PublicDistributionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proposal = json.loads(PROPOSAL_PATH.read_text(encoding="utf-8"))
        cls.volume2_proposal = json.loads(VOLUME2_PROPOSAL_PATH.read_text(encoding="utf-8"))
        cls.issue_0070_proposal = json.loads(
            ISSUE_0070_PROPOSAL_PATH.read_text(encoding="utf-8")
        )
        cls.issue_0080_proposal = json.loads(
            ISSUE_0080_PROPOSAL_PATH.read_text(encoding="utf-8")
        )
        cls.issue_0082_proposal = json.loads(
            ISSUE_0082_PROPOSAL_PATH.read_text(encoding="utf-8")
        )
        cls.issue_0084_proposal = json.loads(
            ISSUE_0084_PROPOSAL_PATH.read_text(encoding="utf-8")
        )
        cls.issue_0086_proposal = json.loads(
            ISSUE_0086_PROPOSAL_PATH.read_text(encoding="utf-8")
        )
        cls.issue_0085_proposal = json.loads(
            ISSUE_0085_PROPOSAL_PATH.read_text(encoding="utf-8")
        )
        cls.issue_0091_proposal = json.loads(
            ISSUE_0091_PROPOSAL_PATH.read_text(encoding="utf-8")
        )
        cls.issue_0096_proposal = json.loads(
            ISSUE_0096_PROPOSAL_PATH.read_text(encoding="utf-8")
        )
        cls.issue_0098_proposal = json.loads(
            ISSUE_0098_PROPOSAL_PATH.read_text(encoding="utf-8")
        )

    def validate_against_frozen_current_closure(self, path):
        expected = json.loads(
            CURRENT_CLOSURE.CURRENT_CLOSURE.read_text(encoding="utf-8")
        )
        with patch.object(CURRENT_CLOSURE, "expected", return_value=(expected, [])):
            return CURRENT_CLOSURE.validate(path)

    def validate_distribution_with_verified_closure(self, path):
        with patch.object(VALIDATE, "validate_closure", return_value=[]):
            return VALIDATE.validate(path)

    def build_historical_issue_70_distribution(self, output):
        closure_path = ROOT / "compliance/publication/issue-0070.release-closure.v1.json"
        closure = json.loads(closure_path.read_text(encoding="utf-8"))
        proposals = [self.proposal, self.issue_0070_proposal]
        output.mkdir(parents=True)
        (output / "records").mkdir()
        (output / "reviews").mkdir()
        files = []
        all_records = []
        for volume, proposal in enumerate(proposals, start=1):
            records = proposal["records"]
            all_records.extend(records)
            record_bytes = b"".join(BOUNDARY.canonical_json(record) for record in records)
            relative = f"records/volume-{volume:02}.jsonl"
            (output / relative).write_bytes(record_bytes)
            files.append(
                {
                    "path": relative,
                    "sha256": BOUNDARY.sha256_bytes(record_bytes),
                    "bytes": len(record_bytes),
                    "recordCount": len(records),
                    "volume": volume,
                }
            )
        for item in closure["proposals"]:
            issue = item["proposalId"].split("-")[1]
            source = ROOT / item["publicReview"]["path"]
            (output / f"reviews/issue-{issue}.json").write_bytes(source.read_bytes())
        (output / "release-closure.json").write_bytes(closure_path.read_bytes())

        printed = {}
        for record in all_records:
            printed.setdefault(record["printedEntryNumber"], []).append(record["id"])
        rights_matrix = json.loads(
            (ROOT / "compliance/rights-matrix.al-isabah.v1.json").read_text(
                encoding="utf-8"
            )
        )
        license_record = rights_matrix["public_content_license"]
        authorities = {
            proposal["sourceAuthority"]["sourceId"]: proposal["sourceAuthority"]
            for proposal in proposals
        }
        manifest = {
            "schemaVersion": "2.0.0",
            "distributionId": f"al-isabah-public-working-{COMMIT[:12]}",
            "publicationStatus": "public-working",
            "canonicalPromotion": "blocked",
            "work": {
                "id": "ibn-hajar-al-isabah",
                "titleArabic": "الإصابة في تمييز الصحابة",
                "titleEnglish": "Al-Isabah fi Tamyiz al-Sahabah",
            },
            "repository": {
                "url": "https://github.com/yaqub0r/al-isabah",
                "commit": COMMIT,
            },
            "generatedAt": GENERATED_AT,
            "rights": {
                "matrixId": rights_matrix["matrix_id"],
                "license": {
                    "spdx": license_record["spdx"],
                    "url": license_record["url"],
                },
                "softwareLicenseGranted": license_record["software_license_granted"],
                "attribution": rights_matrix["attribution"],
                "excludedMaterial": rights_matrix["exclusions"],
            },
            "packets": [
                {
                    "packetId": item["proposalId"],
                    "sha256": item["publicProposal"]["sha256"],
                    "entryCount": item["projection"]["entryCount"],
                }
                for item in closure["proposals"]
            ],
            "authorities": [authorities[key] for key in sorted(authorities)],
            "counts": {
                "entries": len(all_records),
                "machinePassed": sum(p["review"]["machinePassed"] for p in proposals),
                "needsAttention": sum(p["review"]["needsAttention"] for p in proposals),
                "humanReviewed": sum(p["review"]["humanReviewed"] for p in proposals),
            },
            "duplicatePrintedEntryNumbers": [
                {"printedEntryNumber": number, "recordIds": ids}
                for number, ids in sorted(printed.items())
                if len(ids) > 1
            ],
            "files": files,
            "releaseClosure": {
                "closureId": closure["closureId"],
                "sha256": BOUNDARY.sha256_file(closure_path),
            },
        }
        (output / "manifest.json").write_bytes(BOUNDARY.canonical_json(manifest))

    def test_issue_98_volume_eight_proposal_and_review_are_current(self):
        proposal = self.issue_0098_proposal
        records = proposal["records"]

        self.assertEqual(PROPOSAL_VALIDATOR.validate(ISSUE_0098_PROPOSAL_PATH), [])
        self.assertEqual(
            REVIEW.canonical_json(REVIEW.review(ISSUE_0098_PROPOSAL_PATH)),
            ISSUE_0098_REVIEW_PATH.read_bytes(),
        )
        self.assertEqual(len(records), 879)
        self.assertEqual(
            [record["sourceOrdinal"] for record in records],
            list(range(11425, 12304)),
        )
        self.assertEqual(proposal["review"]["humanReviewed"], 0)
        self.assertEqual(proposal["review"]["humanUnreviewed"], 879)
        self.assertEqual(
            proposal["entryTitleDecisions"],
            {
                "profileId": "entry-title-decisions.v11",
                "profileSha256": "130a872700412dba03aa14ce2a6b9c43e3dc2e8afa629c7b4c8e3feeb74f33ef",
                "coveredRecordCount": 879,
            },
        )
        title_only = [
            record["sourceOrdinal"]
            for record in records
            if record["arabic"] == "" and record["english"] == ""
        ]
        self.assertEqual(title_only, [11930, 12023])
        owned = [
            item
            for record in records
            for item in record["precedingMaterial"]
            if item["kind"] != "continued_structural_heading"
        ]
        inherited = [
            item
            for record in records
            for item in record["precedingMaterial"]
            if item["kind"] == "continued_structural_heading"
        ]
        self.assertEqual(len(owned), 139)
        self.assertEqual(len(inherited), 3)
        self.assertEqual(proposal["canonicalPromotion"], "blocked")

    def test_current_cover_to_cover_proposals_are_exact_and_nonduplicative(self):
        proposals = [
            self.proposal,
            self.issue_0070_proposal,
            self.issue_0080_proposal,
            self.issue_0082_proposal,
            self.issue_0084_proposal,
            self.issue_0086_proposal,
            self.issue_0085_proposal,
            self.issue_0091_proposal,
            self.issue_0096_proposal,
            self.issue_0098_proposal,
        ]
        self.assertEqual(len(proposals), 10)
        self.assertIn("issue-0070-public-proposal-v1", {
            proposal["proposalId"] for proposal in proposals
        })
        self.assertNotIn("issue-0053-public-proposal-v1", {
            proposal["proposalId"] for proposal in proposals
        })
        ordinals = [
            record["sourceOrdinal"]
            for proposal in proposals
            for record in proposal["records"]
        ]
        self.assertEqual(ordinals, list(range(1, 12304)))
        owned = [
            item
            for proposal in proposals
            for record in proposal["records"]
            for item in record["precedingMaterial"]
            if item["kind"] != "continued_structural_heading"
        ]
        inherited_display = [
            item
            for proposal in proposals[:-1]
            for record in proposal["records"]
            for item in record["precedingMaterial"]
            if item["kind"] == "continued_structural_heading"
        ]
        self.assertEqual(len(owned), 1382)
        self.assertEqual(len(inherited_display), 23)
        self.assertEqual(len(owned) + len(inherited_display), 1405)

    def test_issue_96_volume_seven_proposal_and_review_are_current(self):
        proposal = self.issue_0096_proposal
        records = proposal["records"]

        self.assertEqual(PROPOSAL_VALIDATOR.validate(ISSUE_0096_PROPOSAL_PATH), [])
        self.assertEqual(
            REVIEW.canonical_json(REVIEW.review(ISSUE_0096_PROPOSAL_PATH)),
            ISSUE_0096_REVIEW_PATH.read_bytes(),
        )
        self.assertEqual(len(records), 1940)
        self.assertEqual(records[0]["sourceOrdinal"], 9485)
        self.assertEqual(records[-1]["sourceOrdinal"], 11424)
        self.assertEqual(proposal["review"]["humanReviewed"], 0)
        self.assertEqual(proposal["review"]["humanUnreviewed"], 1940)
        self.assertEqual(
            proposal["entryTitleDecisions"],
            {
                "profileId": "entry-title-decisions.v10",
                "profileSha256": "f99f48ff38a17ebff828580e26547ecdfb277d40dbaee8689b5e48bd4bf1fcfb",
                "coveredRecordCount": 1940,
            },
        )
        self.assertEqual(proposal["canonicalPromotion"], "blocked")

    def test_issue_91_volume_six_proposal_and_review_are_current(self):
        proposal = self.issue_0091_proposal
        records = proposal["records"]
        anonymous = next(record for record in records if record["sourceOrdinal"] == 8582)

        self.assertEqual(PROPOSAL_VALIDATOR.validate(ISSUE_0091_PROPOSAL_PATH), [])
        self.assertEqual(
            REVIEW.canonical_json(REVIEW.review(ISSUE_0091_PROPOSAL_PATH)),
            ISSUE_0091_REVIEW_PATH.read_bytes(),
        )
        self.assertEqual(len(records), 1722)
        self.assertEqual(records[0]["sourceOrdinal"], 7763)
        self.assertEqual(records[-1]["sourceOrdinal"], 9484)
        self.assertEqual(proposal["review"]["humanReviewed"], 0)
        self.assertEqual(proposal["review"]["humanUnreviewed"], 1722)
        self.assertEqual(
            proposal["entryTitleDecisions"],
            {
                "profileId": "entry-title-decisions.v9",
                "profileSha256": "e929ff952e8ed082bbd724d0fc009deca48cd3073fc6be9fb4095f9f92f147ab",
                "coveredRecordCount": 1722,
            },
        )
        self.assertEqual(anonymous["title"]["english"], "The Prophet's alms collector")
        self.assertEqual(anonymous["names"], [])
        self.assertEqual(proposal["canonicalPromotion"], "blocked")

    def test_issue_85_title_profile_binding_distinguishes_repository_and_working_copy_bytes(self):
        proposal = copy.deepcopy(self.issue_0085_proposal)
        key = (proposal["schemaVersion"], proposal["proposalId"])
        portable = PROPOSAL_VALIDATOR.PORTABLE_TITLE_PROFILE_BINDINGS[key]
        profile_path = ROOT / "profiles" / "entry-title-decisions.v8.json"
        lf_bytes = PROPOSAL_VALIDATOR._normalized_text_bytes(profile_path, "lf")
        crlf_bytes = PROPOSAL_VALIDATOR._normalized_text_bytes(profile_path, "crlf")

        self.assertEqual(PROPOSAL_VALIDATOR.validate(ISSUE_0085_PROPOSAL_PATH), [])
        self.assertEqual(BOUNDARY.sha256_bytes(lf_bytes), portable["repositorySha256"])
        self.assertEqual(BOUNDARY.sha256_bytes(crlf_bytes), portable["workingCopySha256"])
        self.assertEqual(
            proposal["entryTitleDecisions"]["profileSha256"],
            portable["workingCopySha256"],
        )

        with tempfile.TemporaryDirectory() as directory:
            temporary_root = Path(directory)
            temporary_profiles = temporary_root / "profiles"
            temporary_profiles.mkdir()
            temporary_profile = temporary_profiles / "entry-title-decisions.v8.json"
            with patch.object(PROPOSAL_VALIDATOR, "ROOT", temporary_root):
                for exact_bytes in (lf_bytes, crlf_bytes):
                    temporary_profile.write_bytes(exact_bytes)
                    self.assertEqual(
                        PROPOSAL_VALIDATOR._title_decision_errors(proposal), []
                    )

                temporary_profile.write_bytes(lf_bytes + b" ")
                self.assertTrue(
                    any(
                        "category=title-profile-mismatch" in error
                        for error in PROPOSAL_VALIDATOR._title_decision_errors(proposal)
                    )
                )

        proposal["entryTitleDecisions"]["profileSha256"] = portable[
            "repositorySha256"
        ]
        self.assertTrue(
            any(
                "category=title-profile-mismatch" in error
                for error in PROPOSAL_VALIDATOR._title_decision_errors(proposal)
            )
        )

    def test_title_profile_projection_hash_is_portable_across_line_endings(self):
        profile_path = ROOT / "profiles" / "entry-title-decisions.v8.json"
        lf_bytes = PROPOSAL_VALIDATOR._normalized_text_bytes(profile_path, "lf")
        crlf_bytes = PROPOSAL_VALIDATOR._normalized_text_bytes(profile_path, "crlf")
        expected = BOUNDARY.sha256_bytes(lf_bytes)
        with tempfile.TemporaryDirectory() as directory:
            temporary_profile = Path(directory) / "entry-title-decisions.v8.json"
            for exact_bytes in (lf_bytes, crlf_bytes):
                temporary_profile.write_bytes(exact_bytes)
                self.assertEqual(
                    PACKET_PROJECT.title_profile_sha256(temporary_profile), expected
                )

    def test_current_tree_and_exact_closure_are_valid(self):
        self.assertEqual(PROPOSAL_VALIDATOR.DEFAULT_PROPOSAL, ISSUE_0070_PROPOSAL_PATH)
        self.assertEqual(PROPOSAL_VALIDATOR.validate(), [])
        self.assertEqual(CLOSURE.validate(), [])
        self.assertEqual(CURRENT_CLOSURE.validate(), [])
        self.assertEqual(TREE.validate(), [])
        self.assertEqual(REVIEW.canonical_json(REVIEW.review()), (ROOT / "content" / "public-proposals" / "issue-0026.public-review.json").read_bytes())

    def test_bare_public_proposal_cli_validates_the_current_issue_70_artifact(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "validate_public_proposal.py")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(
            "proposal-sha256=9f1be4e740ea501fa1055e4298aab2add915342575723e377541da81cf762b11",
            result.stdout,
        )

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

    def test_historical_volume2_policy_binding_is_exact_and_fail_closed(self):
        proposal = copy.deepcopy(self.volume2_proposal)
        self.assertEqual(
            proposal["policy"]["bindingSha256"],
            PROPOSAL_VALIDATOR.HISTORICAL_POLICY_BINDINGS[
                ("1.1.0", "issue-0053-public-proposal-v1")
            ],
        )
        proposal["policy"]["bindingSha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "historical.public-proposal.json"
            path.write_bytes(BOUNDARY.canonical_json(proposal))
            errors = PROPOSAL_VALIDATOR.validate(path)
        self.assertTrue(any("category=policy-mismatch" in error for error in errors))

    def test_issue_80_historical_policy_binding_remains_exact_and_fail_closed(self):
        proposal = copy.deepcopy(self.issue_0080_proposal)
        self.assertEqual(PROPOSAL_VALIDATOR.validate(ISSUE_0080_PROPOSAL_PATH), [])
        self.assertEqual(
            proposal["policy"]["bindingSha256"],
            PROPOSAL_VALIDATOR.HISTORICAL_POLICY_BINDINGS[
                ("1.2.0", "issue-0080-public-proposal-v1")
            ],
        )
        proposal["policy"]["bindingSha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "issue-0080.public-proposal.json"
            path.write_bytes(BOUNDARY.canonical_json(proposal))
            errors = PROPOSAL_VALIDATOR.validate(path)
        self.assertTrue(any("category=policy-mismatch" in error for error in errors))

        proposal = copy.deepcopy(self.issue_0080_proposal)
        proposal["entryTitleDecisions"].update(
            PROPOSAL_VALIDATOR.PINNED_TITLE_PROFILE_BINDINGS[
                ("1.2.0", "issue-0082-public-proposal-v1")
            ]
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "issue-0080.public-proposal.json"
            path.write_bytes(BOUNDARY.canonical_json(proposal))
            errors = PROPOSAL_VALIDATOR.validate(path)
        self.assertTrue(
            any("category=title-profile-mismatch" in error for error in errors)
        )

    def test_issue_82_historical_policy_binding_remains_exact_and_fail_closed(self):
        proposal = copy.deepcopy(self.issue_0082_proposal)
        self.assertEqual(PROPOSAL_VALIDATOR.validate(ISSUE_0082_PROPOSAL_PATH), [])
        self.assertEqual(
            proposal["policy"]["bindingSha256"],
            PROPOSAL_VALIDATOR.HISTORICAL_POLICY_BINDINGS[
                ("1.2.0", "issue-0082-public-proposal-v1")
            ],
        )
        proposal["policy"]["bindingSha256"] = (
            PROPOSAL_VALIDATOR.sha256_text_file(
                ROOT / "compliance" / "policy-binding.v7.json"
            )
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "issue-0082.public-proposal.json"
            path.write_bytes(BOUNDARY.canonical_json(proposal))
            errors = PROPOSAL_VALIDATOR.validate(path)
        self.assertTrue(any("category=policy-mismatch" in error for error in errors))

    def test_schema_12_formula_snapshot_excludes_v15_variants(self):
        self.assertEqual(
            PROPOSAL_VALIDATOR.FORMULA_V15_SOURCES,
            {
                "صلى الله عليه وسلم وعلى آله وسلم",
                "صلى الله عليه وسلم وآله",
                "صلى الله عيه وآله وسلم",
                "صلى الله عليه وسلم وآوله وسلم",
                "صلى الله علي وآله وسلم",
                "صلى الله عليه وسلم وآله سلم",
                "صلى الله عيله وآله وسلم",
                "صلى الله عله وآله وسلم",
                "صلى الله عليه وسلم وآله ولم",
                "صلى الله عيله وسلم",
            },
        )
        legacy_sources = {
            rule["source"] for rule in PROPOSAL_VALIDATOR.LEGACY_FORMULA_RULES
        }
        self.assertTrue(
            PROPOSAL_VALIDATOR.FORMULA_V15_SOURCES.isdisjoint(legacy_sources)
        )

        record = next(
            item
            for item in self.issue_0084_proposal["records"]
            if item["sourceOrdinal"] == 3876
        )
        self.assertIn("صلى الله عليه وسلم وعلى آله وسلم", record["arabic"])
        self.assertEqual(
            PROPOSAL_VALIDATOR.public_formula_errors(
                record,
                "$.records[3876]",
                PROPOSAL_VALIDATOR.LEGACY_FORMULA_RULES,
            ),
            [],
        )
        self.assertTrue(
            PROPOSAL_VALIDATOR.public_formula_errors(
                record,
                "$.records[3876]",
                PROPOSAL_VALIDATOR.FORMULA_RULES,
            )
        )

    def test_schema_12_formula_snapshot_excludes_v16_rules(self):
        self.assertEqual(
            PROPOSAL_VALIDATOR.FORMULA_V16_SOURCES,
            {
                "والله الموفق",
                "ان شاء الله تعالى",
                "ان شاء الله",
                "نسأل الله التوفيق",
                "والله عنده حسن المآب",
                "والله سبحانه وتعالى اعلم",
                "وبالله التوفيق",
                "اللهم صل على النبي والوصي",
                "رحم الله عائشة",
                "رحم الله هشاما",
                "رحم الله عبادا",
                "رحم الله لبيدا",
                "رحم الله عروة",
                "رحم الله قسا",
                "يرحمك الله",
                "صلى الله عليه وسلم وأله وسلم",
                "صلى الله عليه وسلم آله وسلم",
                "صل الله عليه وآله وسلم",
                "صلى الله",
            },
        )
        legacy_sources = {
            rule["source"] for rule in PROPOSAL_VALIDATOR.LEGACY_FORMULA_RULES
        }
        self.assertTrue(
            PROPOSAL_VALIDATOR.FORMULA_V16_SOURCES.isdisjoint(legacy_sources)
        )

    def test_current_formula_rules_preserve_volume_five_exact_arabic(self):
        forward = PROPOSAL_VALIDATOR.registered_formula_occurrences(
            "وسيأتي بيانه ان شاء الله تعالى", "source"
        )
        self.assertEqual([hit["value"] for hit in forward], ["ان شاء الله تعالى"])
        self.assertEqual(
            [
                hit["value"]
                for hit in PROPOSAL_VALIDATOR.registered_formula_occurrences(
                    "قال: ان شاء الله تعالى نفعل ذلك", "source"
                )
            ],
            ["ان شاء الله تعالى"],
        )
        self.assertEqual(
            [
                hit["value"]
                for hit in PROPOSAL_VALIDATOR.registered_formula_occurrences(
                    "قال: ان شاء الله نفعل ذلك", "source"
                )
            ],
            ["ان شاء الله"],
        )
        self.assertEqual(
            PROPOSAL_VALIDATOR.registered_formula_occurrences(
                "والله عنده حسن المآب في الآخرة", "source"
            ),
            [],
        )
        truncated = PROPOSAL_VALIDATOR.registered_formula_occurrences(
            "made a garment for the Messenger of Allah صلى الله.", "target"
        )
        self.assertEqual([hit["value"] for hit in truncated], ["صلى الله"])

    def test_public_target_formula_matching_prefers_exact_target_over_expansion(self):
        exact = "صلى الله عليه وسلم وعلى آله وسلم"
        hits = PROPOSAL_VALIDATOR.registered_formula_occurrences(exact, "target")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["value"], exact)
        self.assertEqual(hits[0]["rule"]["source"], exact)

        volume_eight = "صلى الله عليه وسلم وعلى وآله وسلم"
        hits = PROPOSAL_VALIDATOR.registered_formula_occurrences(
            volume_eight, "target"
        )
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["rule"]["source"], volume_eight)

    def test_public_volume_eight_round_two_formulas_are_exact(self):
        for surface in (
            "ورضي عنها",
            "الله تعالى",
            "عليه وعلى آله وسلم",
            "إنا لله وإنا إليه راجعون",
            "عليه وآله وسلم",
        ):
            with self.subTest(surface=surface):
                source_hits = PROPOSAL_VALIDATOR.registered_formula_occurrences(
                    surface, "source"
                )
                target_hits = PROPOSAL_VALIDATOR.registered_formula_occurrences(
                    surface, "target"
                )
                self.assertEqual([hit["value"] for hit in source_hits], [surface])
                self.assertEqual([hit["value"] for hit in target_hits], [surface])
                self.assertEqual(target_hits[0]["rule"]["source"], surface)

    def test_public_formula_matching_requires_reviewed_complete_arabic_surfaces(self):
        for surface in (
            "فالحمد لله",
            "فلا حول ولا قوة إلا بالله",
            "والعلم عند الله",
            "والحمد لله",
            "ولا إله إلا الله",
            "والله أكبر",
        ):
            with self.subTest(surface=surface):
                exact = PROPOSAL_VALIDATOR.registered_formula_occurrences(
                    surface, "source", include_contextual=True
                )
                self.assertEqual([hit["value"] for hit in exact], [surface])
        self.assertEqual(
            PROPOSAL_VALIDATOR.registered_formula_occurrences(
                "كالحمد لله", "source", include_contextual=True
            ),
            [],
        )

    def test_family_suffix_before_rajulan_is_substantive_text(self):
        observed = "صلى الله عليه وسلم وآله"
        family = PROPOSAL_VALIDATOR.registered_formula_occurrences(
            observed,
            "source",
        )
        self.assertEqual(len(family), 1)
        self.assertEqual(family[0]["value"], observed)
        self.assertEqual(family[0]["rule"]["target"], "﵌")
        longer_word = PROPOSAL_VALIDATOR.registered_formula_occurrences(
            f"{observed} رجلان",
            "source",
        )
        self.assertEqual(longer_word[0]["value"], observed)
        self.assertEqual(longer_word[0]["rule"]["target"], "﵌")

        plain = "صلى الله عليه وسلم"
        plain_rule = next(
            rule
            for rule in PROPOSAL_VALIDATOR.FORMULA_RULES
            if rule["source"] == plain
        )
        self.assertEqual(
            PROPOSAL_VALIDATOR.registered_formula_occurrences(
                f"قال {observed} رجلا",
                "source",
            ),
            [{"value": plain, "rule": plain_rule}],
        )

    def test_current_public_record_rejects_process_residue_and_undeclared_arabic(self):
        record = copy.deepcopy(self.issue_0082_proposal["records"][0])
        for residue in (
            "Variant English rendering: internal alternative.",
            "Variant English rendering - internal alternative.",
            "This follows the pinned wording.",
            "ACO reads differently.",
        ):
            record["english"] = residue
            errors = PROPOSAL_VALIDATOR.record_semantic_errors(
                record, "$.records[0]", enforce_public_english=True
            )
            self.assertTrue(
                any("category=internal-process-language" in error for error in errors),
                residue,
            )

        record["english"] = "He said: اللهم اغفر لي."
        errors = PROPOSAL_VALIDATOR.record_semantic_errors(
            record, "$.records[0]", enforce_public_english=True
        )
        self.assertTrue(
            any("category=undeclared-arabic-in-english" in error for error in errors)
        )

        record["formulas"] = []
        governed = "بنو تميم"
        self.assertEqual(
            PROPOSAL_VALIDATOR.governed_arabic_literals(
                f"The source heading reads {governed}."
            ),
            [governed],
        )
        record["english"] = f"The source heading reads {governed}."
        errors = PROPOSAL_VALIDATOR.record_semantic_errors(
            record,
            "$.records[0]",
            enforce_public_english=True,
            allowed_arabic_literals=[governed],
        )
        self.assertFalse(
            any("category=undeclared-arabic-in-english" in error for error in errors)
        )
        record["english"] += " تميم"
        errors = PROPOSAL_VALIDATOR.record_semantic_errors(
            record,
            "$.records[0]",
            enforce_public_english=True,
            allowed_arabic_literals=[governed],
        )
        self.assertTrue(
            any("category=undeclared-arabic-in-english" in error for error in errors)
        )

        structural_record = copy.deepcopy(
            next(
                item
                for item in self.issue_0084_proposal["records"]
                if item["precedingMaterial"]
            )
        )
        structural_record["precedingMaterial"][0]["heading"]["english"] = (
            "Injected الله"
        )
        errors = PROPOSAL_VALIDATOR.record_semantic_errors(
            structural_record,
            "$.records[0]",
            enforce_public_english=True,
        )
        self.assertTrue(
            any(
                "precedingMaterial[0].heading.english" in error
                and "category=undeclared-arabic-in-english" in error
                for error in errors
            )
        )

        invented_formula_record = copy.deepcopy(
            self.issue_0084_proposal["records"][0]
        )
        invented_formula_record["english"] += " اللهم"
        invented_formula_record["formulas"] = [
            {
                "formulaId": "invented",
                "recordId": invented_formula_record["id"],
                "observedArabic": "not-in-source",
                "semanticClass": "invented",
                "targetRealization": "اللهم",
            }
        ]
        errors = PROPOSAL_VALIDATOR.record_semantic_errors(
            invented_formula_record,
            "$.records[0]",
            enforce_public_english=True,
        )
        self.assertTrue(
            any("category=formula-inventory-mismatch" in error for error in errors)
        )

        context_formula_record = copy.deepcopy(
            self.issue_0084_proposal["records"][0]
        )
        context = context_formula_record["precedingMaterial"][-1]
        context["arabic"] = "صلى الله عليه وسلم"
        context["english"] = "صلى الله عليه وسلم"
        context_formula_record["formulas"] = [
            {
                "formulaId": f"{context['id']}-arabic-formula-001",
                "recordId": context["id"],
                "observedArabic": "صلى الله عليه وسلم",
                "semanticClass": "prophetic_blessing",
                "targetRealization": "صلى الله عليه وسلم",
            }
        ]
        errors = PROPOSAL_VALIDATOR.record_semantic_errors(
            context_formula_record,
            "$.records[0]",
            enforce_public_english=True,
        )
        self.assertFalse(
            any("category=formula-inventory-mismatch" in error for error in errors)
        )
        self.assertFalse(
            any("category=undeclared-arabic-in-english" in error for error in errors)
        )
        context["heading"] = {
            "arabic": None,
            "english": None,
            "level": None,
        }
        errors = PROPOSAL_VALIDATOR.record_semantic_errors(
            context_formula_record,
            "$.records[0]",
            enforce_public_english=True,
        )
        self.assertFalse(
            any("category=formula-inventory-mismatch" in error for error in errors)
        )
        formula_text = "The Prophet صلى الله عليه وسلم spoke."
        self.assertEqual(
            PROPOSAL_VALIDATOR.governed_arabic_literals(formula_text), []
        )

        record["formulas"] = []
        record["english"] = "The source reads يأيت here."
        errors = PROPOSAL_VALIDATOR.record_semantic_errors(
            record,
            "$.records[0]",
            enforce_public_english=True,
            allowed_arabic_literals=["يأيت"],
        )
        self.assertFalse(
            any("category=undeclared-arabic-in-english" in error for error in errors)
        )

        record["arabic"] = "قال صلى الله عليه وسلم"
        record["formulas"] = [
            {
                "formulaId": f"{record['id']}-arabic-formula-001",
                "recordId": record["id"],
                "observedArabic": "صلى الله عليه وسلم",
                "semanticClass": "prophetic_blessing",
                "targetRealization": "صلى الله عليه وسلم",
            }
        ]
        record["english"] = "The Prophet صلى الله عليه وسلم spoke."
        errors = PROPOSAL_VALIDATOR.record_semantic_errors(
            record, "$.records[0]", enforce_public_english=True
        )
        self.assertFalse(
            any("category=undeclared-arabic-in-english" in error for error in errors)
        )

        record["english"] = "The Prophet spoke."
        errors = PROPOSAL_VALIDATOR.record_semantic_errors(
            record, "$.records[0]", enforce_public_english=True
        )
        self.assertTrue(
            any("category=missing-declared-formula-target" in error for error in errors)
        )

        record["english"] = (
            "The Prophet صلى الله عليه وسلم صلى الله عليه وسلم spoke."
        )
        errors = PROPOSAL_VALIDATOR.record_semantic_errors(
            record, "$.records[0]", enforce_public_english=True
        )
        self.assertTrue(
            any("category=undeclared-arabic-in-english" in error for error in errors)
        )

    def test_issue_70_corrected_proposal_is_strict_public_safe_and_current(self):
        proposal = self.issue_0070_proposal
        records = proposal["records"]
        self.assertEqual(PROPOSAL_VALIDATOR.validate(ISSUE_0070_PROPOSAL_PATH), [])
        self.assertEqual(
            REVIEW.canonical_json(REVIEW.review(ISSUE_0070_PROPOSAL_PATH)),
            ISSUE_0070_REVIEW_PATH.read_bytes(),
        )
        self.assertEqual(proposal["schemaVersion"], "1.2.0")
        self.assertEqual(len(records), 1497)
        self.assertEqual(proposal["review"], {
            "humanReviewed": 0,
            "humanUnreviewed": 1497,
            "machinePassed": 1435,
            "needsAttention": 62,
        })
        self.assertTrue(all(record["humanReview"] == "unreviewed" for record in records))
        unresolved = [item for record in records for item in record["unresolved"]]
        self.assertEqual(len(unresolved), 66)
        self.assertEqual(
            sum(bool(record["unresolved"]) for record in records),
            62,
        )
        self.assertTrue(all(set(item) == {"category", "priority"} for item in unresolved))
        self.assertEqual(BOUNDARY.boundary_errors(proposal), [])

        register = json.loads(
            (ROOT / "compliance" / "source-register.v1.json").read_text(
                encoding="utf-8"
            )
        )
        artifact = next(
            item
            for item in register["artifacts"]
            if item["id"] == "issue-0070-public-proposal-v1"
        )
        self.assertEqual(
            artifact["review_status"],
            CURRENT_CLOSURE.CURRENT_DISTRIBUTION_REVIEW_STATUS,
        )
        self.assertEqual(
            artifact["integrity"]["submitted_packet_sha256"],
            "5be390962508d54bb2ed0c82310bba6e17bfd1cc6d771e89ed91e592b89bf7d6",
        )
        self.assertEqual(
            artifact["integrity"]["submitted_review_sha256"],
            "a2aa7554db7f71a32010e6a7c9d166ff15648443e777b97245e8afb27432afbc",
        )

    def test_missing_review_state_disclosure_fails_at_every_public_boundary(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            proposal = copy.deepcopy(self.issue_0070_proposal)
            del proposal["review"]
            proposal_path = root / "proposal.json"
            proposal_path.write_bytes(BOUNDARY.canonical_json(proposal))
            self.assertTrue(
                any(
                    "category=missing-field" in error and ".review" in error
                    for error in PROPOSAL_VALIDATOR.validate(proposal_path)
                )
            )

            closure = json.loads(
                CURRENT_CLOSURE.CURRENT_CLOSURE.read_text(encoding="utf-8")
            )
            del closure["reviewDisclosure"]
            closure_path = root / "closure.json"
            closure_path.write_bytes(BOUNDARY.canonical_json(closure))
            self.assertTrue(
                any(
                    "category=current-closure-mismatch" in error
                    for error in self.validate_against_frozen_current_closure(closure_path)
                )
            )

            output = root / "distribution"
            with patch.object(BUILD, "validate_closure", return_value=[]):
                BUILD.build(output, COMMIT, GENERATED_AT)
            manifest_path = output / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            del manifest["counts"]["humanReviewed"]
            manifest_path.write_bytes(BOUNDARY.canonical_json(manifest))
            self.assertTrue(
                any(
                    "category=missing-field" in error
                    and ".counts.humanReviewed" in error
                    for error in self.validate_distribution_with_verified_closure(output)
                )
            )

    def test_current_closure_admits_full_book_and_quarantines_history(self):
        paths, errors = CURRENT_CLOSURE.current_proposal_paths()
        self.assertEqual(errors, [])
        self.assertEqual(
            paths,
            [
                PROPOSAL_PATH,
                ISSUE_0070_PROPOSAL_PATH,
                ISSUE_0080_PROPOSAL_PATH,
                ISSUE_0082_PROPOSAL_PATH,
                ISSUE_0084_PROPOSAL_PATH,
                ISSUE_0086_PROPOSAL_PATH,
                ISSUE_0085_PROPOSAL_PATH,
                ISSUE_0091_PROPOSAL_PATH,
                ISSUE_0096_PROPOSAL_PATH,
                ISSUE_0098_PROPOSAL_PATH,
            ],
        )
        closure = json.loads(
            CURRENT_CLOSURE.CURRENT_CLOSURE.read_text(encoding="utf-8")
        )
        self.assertEqual(
            [item["proposalId"] for item in closure["proposals"]],
            [
                "issue-0026-public-proposal-v1",
                "issue-0070-public-proposal-v1",
                "issue-0080-public-proposal-v1",
                "issue-0082-public-proposal-v1",
                "issue-0084-public-proposal-v1",
                "issue-0086-public-proposal-v1",
                "issue-0085-public-proposal-v1",
                "issue-0091-public-proposal-v1",
                "issue-0096-public-proposal-v1",
                "issue-0098-public-proposal-v1",
            ],
        )
        self.assertEqual(
            closure["previousClosure"]["path"],
            "compliance/publication/issue-0070.release-closure.v1.json",
        )
        self.assertEqual(
            closure["translationCoverage"]["path"],
            "compliance/translation-coverage.v1.json",
        )
        self.assertEqual(closure["sourceUnitCoverage"]["sourceUnitCount"], 12303)
        self.assertEqual(
            closure["structuralCoverage"]["ownedStructuralSegmentCount"], 1382
        )
        self.assertEqual(
            closure["structuralCoverage"]["inheritedDisplayContextCount"], 23
        )
        self.assertEqual(
            [(item["volume"], item["recordCount"]) for item in closure["volumeInventory"]],
            [(1, 1537), (2, 1497), (3, 1491), (4, 1633), (5, 1604), (6, 1722), (7, 1940), (8, 879)],
        )
        self.assertEqual(
            closure["volumeInventory"][2]["proposalIds"],
            [
                "issue-0080-public-proposal-v1",
                "issue-0082-public-proposal-v1",
                "issue-0084-public-proposal-v1",
            ],
        )
        self.assertEqual(closure["reviewDisclosure"]["humanReviewed"], 0)
        self.assertEqual(closure["reviewDisclosure"]["humanUnreviewed"], 12303)
        self.assertEqual(
            [(item["id"], item["recordCount"]) for item in closure["supersededInputs"]],
            [
                ("issue-0053-public-proposal-v1", 1497),
                ("legacy-volume-08-private-provisional", 1550),
            ],
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
        corrected_volume_two = next(
            item
            for item in register["artifacts"]
            if item["id"] == "issue-0070-public-proposal-v1"
        )
        self.assertEqual(
            corrected_volume_two["review_status"],
            CURRENT_CLOSURE.CURRENT_DISTRIBUTION_REVIEW_STATUS,
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

    def test_witness_bound_supply_displays_brackets_and_removes_only_source_prefix(self):
        profile = PACKET_PROJECT.load_title_profile(PACKET_PROJECT.ENTRY_TITLE_PROFILE)
        decision = PACKET_PROJECT.decision_index(profile)[2784]
        entry = {
            "sourceOrdinal": 2784,
            "source": {
                "headingArabic": "بن بدر بن امرئ القيس بن خلف",
                "arabic": "بن بدر بن امرئ القيس بن خلف خبر",
            },
            "adjudication": {
                "english": "Ibn Badr ibn Imriʾ al-Qays ibn Khalaf. Report."
            },
            "unresolved": [],
        }
        title, arabic, english = PACKET_PROJECT.title_and_body(entry, decision)
        self.assertEqual(title["arabic"], "[الزبرقان] بن بدر")
        self.assertEqual(title["english"], "[Al-Zibriqān] ibn Badr")
        self.assertEqual(arabic, "بن امرئ القيس بن خلف خبر")
        self.assertEqual(english, "ibn Imriʾ al-Qays ibn Khalaf. Report.")

    def test_witness_bound_supply_rejects_drifted_packet_prefix(self):
        profile = PACKET_PROJECT.load_title_profile(PACKET_PROJECT.ENTRY_TITLE_PROFILE)
        decision = PACKET_PROJECT.decision_index(profile)[2880]
        entry = {
            "sourceOrdinal": 2880,
            "source": {
                "headingArabic": "زيد بن أبي أوفى بن خالد بن الحارث",
                "arabic": "زيد بن أبي أوفى بن خالد بن الحارث خبر",
            },
            "adjudication": {
                "english": "Zayd ibn Abī Awfā ibn Khālid ibn al-Ḥārith. Report."
            },
            "unresolved": [],
        }
        with self.assertRaisesRegex(ValueError, "pinned Arabic source prefix"):
            PACKET_PROJECT.title_and_body(entry, decision)

    @unittest.skipUnless(
        ISSUE_0070_RUNTIME_PACKET.is_file(),
        "ignored issue-70 recovery packet is available only in the review workspace",
    )
    def test_issue_70_all_1497_records_and_runtime_review_use_governed_titles(self):
        packet = json.loads(ISSUE_0070_RUNTIME_PACKET.read_text(encoding="utf-8"))
        unit_2792 = packet["entries"][2792 - 1538]
        english_2792 = unit_2792["adjudication"]["english"]
        if "Ibn Mandahh transmitted" in english_2792:
            self.assertEqual(english_2792.count("Ibn Mandahh transmitted"), 1)
            english_2792 = english_2792.replace(
                "Ibn Mandahh transmitted",
                "Ibn Mandah transmitted",
                1,
            )
            unit_2792["adjudication"]["english"] = english_2792
        self.assertNotIn("Ibn Mandahh transmitted", english_2792)
        self.assertEqual(english_2792.count("Ibn Mandah transmitted"), 1)
        profile = PACKET_PROJECT.load_title_profile(
            PACKET_PROJECT.ENTRY_TITLE_PROFILE
        )
        decisions = PACKET_PROJECT.decision_index(profile)
        formulas = {}
        for occurrence in packet["formulaInventory"]["occurrences"]:
            formulas.setdefault(occurrence["recordId"], []).append(occurrence)
        records = [
            PACKET_PROJECT.public_record(
                packet,
                entry,
                formulas.get(entry["sourceUnitId"], []),
                decisions[entry["sourceEntryNumber"]],
            )
            for entry in packet["entries"]
        ]
        self.assertEqual(len(records), 1497)
        self.assertEqual(
            [record["sourceOrdinal"] for record in records],
            list(range(1538, 3035)),
        )
        supplied = {record["sourceOrdinal"]: record for record in records}
        self.assertEqual(
            supplied[2784]["title"]["english"], "[Al-Zibriqān] ibn Badr"
        )
        self.assertEqual(supplied[2784]["title"]["arabic"], "[الزبرقان] بن بدر")
        self.assertEqual(
            supplied[2880]["title"]["english"], "[Zayd] ibn Abī Awfā"
        )
        self.assertEqual(supplied[2880]["title"]["arabic"], "[زيد] بن أبي أوفى")

        review = PACKET_PROJECT.workflow.render_review(packet)
        self.assertEqual(review.count("### Governed bilingual title"), 1497)
        self.assertIn("**[Al-Zibriqān] ibn Badr**", review)
        self.assertIn("**[الزبرقان] بن بدر**", review)
        self.assertIn("**[Zayd] ibn Abī Awfā**", review)
        self.assertIn("**[زيد] بن أبي أوفى**", review)

    def test_current_title_binding_requires_exact_hash_and_source_unit_coverage(self):
        profile = PACKET_PROJECT.load_title_profile(PACKET_PROJECT.ENTRY_TITLE_PROFILE)
        decision = next(
            item
            for item in profile["decisions"]
            if item["sourceEntryNumber"] == 11426 and "sourceUnitId" in item
        )
        proposal = {
            "entryTitleDecisions": {
                "profileId": "entry-title-decisions.v11",
                "profileSha256": PACKET_PROJECT.title_profile_sha256(
                    PACKET_PROJECT.ENTRY_TITLE_PROFILE
                ),
                "coveredRecordCount": 1,
            },
            "records": [
                {
                    "id": decision["sourceUnitId"],
                    "printedEntryNumber": 11426,
                    "title": {
                        "arabic": decision["title"]["ar"],
                        "english": decision["title"]["en"],
                        "method": "profile-decision",
                    },
                    "arabic": decision["bodyOpening"]["ar"] + " synthetic",
                    "english": decision["bodyOpening"]["en"] + " synthetic",
                    "source": {"exactTextSha256": decision["sourceRawSha256"]},
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
        proposal["entryTitleDecisions"]["profileSha256"] = PACKET_PROJECT.title_profile_sha256(
            PACKET_PROJECT.ENTRY_TITLE_PROFILE
        )
        repeated = [
            item
            for item in profile["decisions"]
            if item["sourceEntryNumber"] == 6986
        ]
        self.assertEqual(len(repeated), 2)
        proposal["entryTitleDecisions"]["coveredRecordCount"] = 2
        proposal["records"] = [
            {
                "id": item["sourceUnitId"],
                "printedEntryNumber": 6986,
                "title": {
                    "arabic": item["title"]["ar"],
                    "english": item["title"]["en"],
                    "method": "profile-decision",
                },
                "arabic": item["bodyOpening"]["ar"] + " synthetic",
                "english": item["bodyOpening"]["en"] + " synthetic",
                "source": {"exactTextSha256": item["sourceRawSha256"]},
            }
            for item in repeated
        ]
        self.assertEqual(PROPOSAL_VALIDATOR._title_decision_errors(proposal), [])
        proposal["records"][1]["id"] = proposal["records"][0]["id"]
        errors = PROPOSAL_VALIDATOR._title_decision_errors(proposal)
        self.assertTrue(
            any("category=title-source-unit-mismatch" in error for error in errors),
            errors,
        )

    def test_literal_damaged_title_survives_public_split_with_disclosure(self):
        profile = PACKET_PROJECT.load_title_profile(PACKET_PROJECT.ENTRY_TITLE_PROFILE)
        decisions = PACKET_PROJECT.decision_index(profile)
        for number in (3052, 3317):
            with self.subTest(number=number):
                decision = decisions[number]
                note = "Editorial note: the quoted source spelling remains unresolved."
                source = decision["title"]["ar"] + " " + decision["bodyOpening"]["ar"]
                entry = {
                    "sourceOrdinal": number,
                    "source": {"headingArabic": source, "arabic": source},
                    "adjudication": {
                        "english": decision["title"]["en"] + ". "
                        + decision["bodyOpening"]["en"] + "\n\n" + note
                    },
                    "unresolved": [{"kind": "source-spelling", "severity": "material"}],
                }
                title, arabic, english = PACKET_PROJECT.title_and_body(entry, decision)
                self.assertEqual(title["english"], decision["title"]["en"])
                self.assertEqual(title["state"], "needs_attention")
                self.assertEqual(arabic, decision["bodyOpening"]["ar"])
                self.assertEqual(english, decision["bodyOpening"]["en"] + "\n\n" + note)
                for value in (title["english"], english):
                    self.assertEqual(PACKET_PROJECT.workflow.validate_public_english(value, "synthetic"), [])

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
            },
            "openiti-synthetic-unit-000001-name-001",
        )
        self.assertEqual(projected["kind"], "collective")
        self.assertEqual(
            projected["id"], "openiti-synthetic-unit-000001-name-001"
        )

    def test_packet_projection_allows_anonymous_profile_titled_entry(self):
        packet = {
            "workId": "ibn-hajar-al-isabah",
            "packetId": "synthetic-anonymous-packet",
            "authority": {
                "commit": "a" * 40,
                "sha256": "b" * 64,
                "license": {
                    "spdx": "CC-BY-NC-4.0",
                    "url": "https://example.test/license",
                    "attribution": "Synthetic test authority",
                },
            },
            "policy": {"bindingSha256": "c" * 64},
        }
        entry = {
            "sourceOrdinal": 8582,
            "sourceEntryNumber": 8581,
            "sourceUnitId": "openiti-synthetic-unit-008582",
            "canonicalEntryId": None,
            "source": {
                "headingArabic": "مصدق النبي ذكره المؤلف",
                "arabic": "مصدق النبي ذكره المؤلف",
                "rawSha256": "d" * 64,
                "locations": [{"volume": 6, "page": 360}],
                "precedingSegments": [],
            },
            "precedingTranslations": [],
            "adjudication": {
                "english": "The Prophet's alms collector. The author mentioned him."
            },
            "names": {"candidates": []},
            "unresolved": [],
            "humanReview": {"status": "unreviewed"},
        }
        decision = {
            "sourceEntryNumber": 8581,
            "sourceUnitId": "openiti-synthetic-unit-008582",
            "sourceRawSha256": "d" * 64,
            "bodyOpeningKind": "prose",
            "title": {"ar": "مصدق النبي", "en": "The Prophet's alms collector"},
            "bodyOpening": {"ar": "ذكره المؤلف", "en": "The author mentioned him"},
        }

        record = PACKET_PROJECT.public_record(packet, entry, [], decision)

        self.assertEqual(record["title"]["method"], "profile-decision")
        self.assertEqual(record["title"]["english"], "The Prophet's alms collector")
        self.assertEqual(record["names"], [])
        self.assertEqual(record["english"], "The author mentioned him.")

    def test_v2_build_is_deterministic_and_consumer_compatible(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "distribution"
            with patch.object(BUILD, "validate_closure", return_value=[]):
                manifest = BUILD.build(output, COMMIT, GENERATED_AT)
            self.assertEqual(manifest["counts"]["entries"], 12303)
            self.assertEqual(manifest["counts"]["humanReviewed"], 0)
            self.assertEqual(
                [item["entryCount"] for item in manifest["packets"]],
                [1537, 1497, 373, 373, 745, 1633, 1604, 1722, 1940, 879],
            )
            self.assertEqual(manifest["schemaVersion"], "2.0.0")
            self.assertEqual(manifest["canonicalPromotion"], "blocked")
            self.assertEqual(self.validate_distribution_with_verified_closure(output), [])
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
                        "records/volume-03.jsonl",
                        "records/volume-04.jsonl",
                        "records/volume-05.jsonl",
                        "records/volume-06.jsonl",
                        "records/volume-07.jsonl",
                        "records/volume-08.jsonl",
                        "release-closure.json",
                        "reviews/issue-0026.json",
                        "reviews/issue-0070.json",
                        "reviews/issue-0080.json",
                        "reviews/issue-0082.json",
                        "reviews/issue-0084.json",
                        "reviews/issue-0085.json",
                        "reviews/issue-0086.json",
                        "reviews/issue-0091.json",
                        "reviews/issue-0096.json",
                        "reviews/issue-0098.json",
                    ],
                )

    def test_cumulative_records_preserve_frozen_proposals_except_adjacent_context(self):
        proposals = [
            self.proposal,
            self.issue_0070_proposal,
            self.issue_0080_proposal,
            self.issue_0082_proposal,
            self.issue_0084_proposal,
            self.issue_0086_proposal,
            self.issue_0085_proposal,
            self.issue_0091_proposal,
            self.issue_0096_proposal,
            self.issue_0098_proposal,
        ]
        expected = []
        for proposal in proposals:
            for source_record in proposal["records"]:
                record = copy.deepcopy(source_record)
                if proposal["proposalId"] == "issue-0098-public-proposal-v1":
                    record["precedingMaterial"] = [
                        item
                        for item in record["precedingMaterial"]
                        if item["kind"] != "continued_structural_heading"
                    ]
                expected.append(record)

        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "distribution"
            with patch.object(BUILD, "validate_closure", return_value=[]):
                BUILD.build(output, COMMIT, GENERATED_AT)
            actual = []
            for path in sorted((output / "records").glob("volume-*.jsonl")):
                actual.extend(
                    json.loads(line)
                    for line in path.read_text(encoding="utf-8").splitlines()
                )
        self.assertEqual(actual, expected)

    def test_publication_workflow_is_manual_exact_commit_and_nonmutating(self):
        workflow = (ROOT / ".github/workflows/publish-public-distribution.yml").read_text(
            encoding="utf-8"
        )
        trigger = workflow.split("permissions:", 1)[0]
        self.assertIn("workflow_dispatch:", trigger)
        self.assertIn("repository_commit:", trigger)
        self.assertNotIn("push:", trigger)
        self.assertIn('ref: ${{ inputs.repository_commit }}', workflow)
        self.assertIn('git rev-parse origin/main)', workflow)
        self.assertIn('al-isabah-public-distribution-${REPOSITORY_COMMIT}.zip', workflow)
        self.assertIn(
            'sys.path.insert(0, str(Path("scripts").resolve())); '
            'from build_public_distribution import package',
            workflow,
        )
        self.assertIn(
            'sha256sum "${archive_name}" > "${archive_name}.sha256"', workflow
        )
        self.assertIn(
            'git ls-remote --exit-code --tags origin "refs/tags/${tag}"', workflow
        )
        self.assertIn('already exists; refusing to mutate or replace it.', workflow)

    def test_historical_schema_v2_distribution_remains_consumer_valid(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "distribution"
            self.build_historical_issue_70_distribution(output)
            self.assertEqual(VALIDATE.validate(output), [])

    def test_distribution_rejects_authority_and_rights_tampering(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "distribution"
            self.build_historical_issue_70_distribution(output)
            manifest_path = output / "manifest.json"
            original = json.loads(manifest_path.read_text(encoding="utf-8"))

            authority_tampering = copy.deepcopy(original)
            authority_tampering["authorities"][0]["commit"] = "0" * 40
            manifest_path.write_bytes(BOUNDARY.canonical_json(authority_tampering))
            self.assertTrue(
                any(
                    "category=source-mismatch" in error
                    for error in VALIDATE.validate(output)
                )
            )

            rights_tampering = copy.deepcopy(original)
            rights_tampering["rights"]["attribution"] += " synthetic drift"
            manifest_path.write_bytes(BOUNDARY.canonical_json(rights_tampering))
            self.assertTrue(
                any(
                    "category=rights-mismatch" in error
                    for error in VALIDATE.validate(output)
                )
            )

            commit_tampering = copy.deepcopy(original)
            commit_tampering["repository"]["commit"] = "0" * 40
            manifest_path.write_bytes(BOUNDARY.canonical_json(commit_tampering))
            self.assertTrue(
                any(
                    "category=distribution-id-mismatch" in error
                    for error in VALIDATE.validate(output)
                )
            )

            id_tampering = copy.deepcopy(original)
            id_tampering["distributionId"] = "al-isabah-public-working-synthetic"
            manifest_path.write_bytes(BOUNDARY.canonical_json(id_tampering))
            self.assertTrue(
                any(
                    "category=distribution-id-mismatch" in error
                    for error in VALIDATE.validate(output)
                )
            )

    def test_closure_authority_binding_expands_to_exact_manifest_authority(self):
        closure = json.loads(
            CURRENT_CLOSURE.CURRENT_CLOSURE.read_text(encoding="utf-8")
        )
        self.assertEqual(
            VALIDATE.expected_manifest_authorities(
                closure, VALIDATE.proposal_bindings(closure)
            ),
            [self.proposal["sourceAuthority"]],
        )

    def test_full_book_invariant_rejects_a_truncated_sequence(self):
        errors = VALIDATE.full_book_coverage_errors(
            ordinals=list(range(1, 12303)),
            unique_id_count=12302,
            expected_count=12303,
            file_volumes=list(range(1, 9)),
            volume_three_ordinals=list(range(3035, 4526)),
            owned_structural_ids=[f"owned-{index}" for index in range(1382)],
            inherited_structural_ids=[
                f"inherited-{index}" for index in range(23)
            ],
        )
        self.assertTrue(
            any("category=full-book-source-coverage-mismatch" in error for error in errors)
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
                with patch.object(BUILD, "validate_closure", return_value=[]):
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

    def test_current_closure_rejects_coverage_structure_and_governance_drift(self):
        mutations = [
            lambda value: value["sourceUnitCoverage"].__setitem__(
                "sourceUnitCount", 12302
            ),
            lambda value: value["sourceUnitCoverage"].__setitem__(
                "identityOrderSha256", "0" * 64
            ),
            lambda value: value["structuralCoverage"].__setitem__(
                "ownedStructuralSegmentCount", 1381
            ),
            lambda value: value["rights"].__setitem__("sha256", "0" * 64),
            lambda value: value["governance"][
                "translationGovernanceReference"
            ].__setitem__("sha256", "0" * 64),
            lambda value: value["proposals"][0]["policyBinding"].__setitem__(
                "sha256", "0" * 64
            ),
            lambda value: value["reviewDisclosure"].__setitem__(
                "humanReviewed", 1
            ),
        ]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "closure.json"
            for mutate in mutations:
                closure = json.loads(
                    CURRENT_CLOSURE.CURRENT_CLOSURE.read_text(encoding="utf-8")
                )
                mutate(closure)
                path.write_bytes(BOUNDARY.canonical_json(closure))
                self.assertTrue(
                    any(
                        "category=current-closure-mismatch" in error
                        for error in self.validate_against_frozen_current_closure(path)
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

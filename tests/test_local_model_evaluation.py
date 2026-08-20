import copy
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


MODULE = load_script("local_model_evaluation")
SCORER = load_script("score_local_model_evaluation")


class LocalModelEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads(
            (ROOT / "evaluations/local-model/v1/cases.json").read_text(encoding="utf-8")
        )
        self.configs = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in (
                ROOT / "evaluations/local-model/v1/configs/gemma4-xhigh-v1.json",
                ROOT / "evaluations/local-model/v1/configs/hermes-sol-xhigh-v1.json",
            )
        ]
        self.gates = json.loads(
            (ROOT / "evaluations/local-model/v1/role-gates.json").read_text(encoding="utf-8")
        )

    def outputs(self, prefix):
        return [
            {
                "caseId": case["caseId"],
                "titleEnglish": f"{prefix} title {case['caseId']}",
                "bodyEnglish": f"{prefix} body {case['caseId']}",
                "issues": [],
            }
            for case in self.manifest["cases"]
        ]

    def make_run(self, config_index, prefix, generated_at="2026-08-20T11:00:00Z"):
        packet = MODULE.prepare_blind_packet(self.manifest, self.configs[config_index])
        return MODULE.record_run(packet, self.outputs(prefix), generated_at)

    def artifacts(self):
        runs = [self.make_run(0, "Gemma"), self.make_run(1, "Sol")]
        packet, key = MODULE.build_blind_review_packet(self.manifest["cases"], runs, "issue-49-v1")
        reviews = {
            "schemaVersion": "1.0.0",
            "reviewPacketId": packet["reviewPacketId"],
            "reviewPacketSha256": MODULE.artifact_sha256(packet),
            "reviewerId": "human-reviewer-001",
            "cases": [
                {
                    "caseId": case["caseId"],
                    "candidates": [
                        {
                            "alias": candidate["alias"],
                            "fidelity": 2,
                            "structure": 2,
                            "uncertainty": 2,
                            "formula": 2,
                            "materialErrors": [],
                            "notes": "clear",
                        }
                        for candidate in case["candidates"]
                    ],
                }
                for case in packet["cases"]
            ],
        }
        return runs, packet, key, reviews

    def assert_evaluation_error(self, callable_, pattern):
        with self.assertRaisesRegex(MODULE.EvaluationError, pattern):
            callable_()

    def assert_scoring_error(self, callable_, pattern):
        with self.assertRaisesRegex(SCORER.ScoringError, pattern):
            callable_()

    def test_cli_rejects_generated_outputs_outside_ignored_runtime_tree(self):
        runner = ROOT / "scripts/local_model_evaluation.py"
        scorer = ROOT / "scripts/score_local_model_evaluation.py"
        commands = [
            ["python", str(runner), "prepare", "--config", "evaluations/local-model/v1/configs/gemma4-xhigh-v1.json", "--output", "tracked-packet.json"],
            ["python", str(runner), "record", "--packet", "missing.json", "--outputs", "missing.json", "--generated-at", "2026-08-20T11:00:00Z", "--output", "tracked-run.json"],
            ["python", str(runner), "anonymize", "--runs", "missing.json", "missing-2.json", "--seed", "x", "--packet-output", "tracked-review.json", "--key-output", "tracked-key.json"],
            ["python", str(scorer), "score", "--cases", "evaluations/local-model/v1/cases.json", "--runs", "missing.json", "--packet", "missing.json", "--key", "missing.json", "--reviews", "missing.json", "--output", "tracked-score.json"],
            ["python", str(scorer), "report", "--cases", "evaluations/local-model/v1/cases.json", "--runs", "missing.json", "--packet", "missing.json", "--key", "missing.json", "--reviews", "missing.json", "--score", "missing.json", "--output", "tracked-report.md"],
        ]
        for command in commands:
            completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn(".runtime/local-model-evaluation", completed.stderr)

    def test_prepare_cli_validates_config_schema_and_prompt_hash(self):
        bad_config = copy.deepcopy(self.configs[0])
        bad_config["promptSha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad-config.json"
            path.write_text(json.dumps(bad_config), encoding="utf-8")
            completed = subprocess.run(
                ["python", str(ROOT / "scripts/local_model_evaluation.py"), "prepare", "--config", str(path), "--output", ".runtime/local-model-evaluation/never-written.json"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("prompt hash", completed.stderr)

    def test_run_shape_preserves_title_body_and_rejects_string_issues(self):
        packet = MODULE.prepare_blind_packet(self.manifest, self.configs[0])
        run = MODULE.record_run(packet, self.outputs("Candidate"), "2026-08-20T11:00:00Z")
        output = run["outputs"][0]
        self.assertEqual(
            set(output),
            {"caseId", "titleEnglish", "titleEnglishSha256", "bodyEnglish", "bodyEnglishSha256", "issues"},
        )
        malformed = self.outputs("Candidate")
        malformed[0]["issues"] = "not-a-list"
        self.assert_evaluation_error(
            lambda: MODULE.record_run(packet, malformed, "2026-08-20T11:00:00Z"),
            "issues must be an array",
        )

    def test_anonymize_validates_runs_integrity_identity_and_exact_coverage(self):
        runs = [self.make_run(0, "Gemma"), self.make_run(1, "Sol")]
        mutations = []
        tampered_hash = copy.deepcopy(runs)
        tampered_hash[0]["outputs"][0]["bodyEnglish"] += " tampered"
        mutations.append((tampered_hash, "hash mismatch"))
        wrong_policy = copy.deepcopy(runs)
        wrong_policy[0]["policy"]["bindingSha256"] = "0" * 64
        mutations.append((wrong_policy, "policy"))
        duplicate_id = copy.deepcopy(runs)
        duplicate_id[1]["runId"] = duplicate_id[0]["runId"]
        mutations.append((duplicate_id, "duplicate run ID"))
        missing_case = copy.deepcopy(runs)
        missing_case[0]["outputs"].pop()
        mutations.append((missing_case, "exactly cover"))
        for values, pattern in mutations:
            self.assert_evaluation_error(
                lambda values=values: MODULE.build_blind_review_packet(self.manifest["cases"], values, "seed"),
                pattern,
            )

    def test_anonymize_rejects_runs_forged_to_a_different_manifest_policy(self):
        runs = [self.make_run(0, "Gemma"), self.make_run(1, "Sol")]
        for run in runs:
            run["policy"]["bindingSha256"] = "0" * 64
            run["policySha256"] = MODULE.artifact_sha256(run["policy"])
            run["runId"] = MODULE.run_id_for(run)
        self.assert_evaluation_error(
            lambda: MODULE.validate_anonymization_inputs(self.manifest, runs),
            "manifest policy",
        )

    def test_anonymize_rejects_more_than_26_runs(self):
        runs = []
        for index in range(27):
            run = self.make_run(0, f"Run {index}", f"2026-08-20T11:{index:02d}:00Z")
            runs.append(run)
        self.assert_evaluation_error(
            lambda: MODULE.build_blind_review_packet(self.manifest["cases"], runs, "seed"),
            "at most 26",
        )

    def test_blind_packet_and_key_are_integrity_bound_and_portable(self):
        runs, packet, key, _ = self.artifacts()
        self.assertRegex(packet["reviewPacketId"], r"^eval-review-packet-[a-f0-9]{16}$")
        self.assertEqual(key["reviewPacketId"], packet["reviewPacketId"])
        self.assertEqual(key["reviewPacketSha256"], MODULE.artifact_sha256(packet))
        self.assertEqual(key["runIds"], [run["runId"] for run in runs])
        visible = json.dumps(packet, ensure_ascii=False)
        self.assertNotIn("gemma4", visible.lower())
        self.assertNotIn("gpt-5", visible.lower())
        self.assertNotIn("runId", visible)
        candidate = packet["cases"][0]["candidates"][0]
        self.assertEqual(set(candidate), {"alias", "titleEnglish", "bodyEnglish", "issues"})

    def test_score_rejects_duplicate_aliases_and_string_material_errors(self):
        runs, packet, key, reviews = self.artifacts()
        duplicate = copy.deepcopy(reviews)
        duplicate["cases"][0]["candidates"][1]["alias"] = duplicate["cases"][0]["candidates"][0]["alias"]
        self.assert_scoring_error(
            lambda: SCORER.score_reviews(self.manifest["cases"], runs, packet, key, duplicate, self.gates),
            "duplicate candidate alias",
        )
        malformed = copy.deepcopy(reviews)
        malformed["cases"][0]["candidates"][0]["materialErrors"] = "name"
        self.assert_scoring_error(
            lambda: SCORER.score_reviews(self.manifest["cases"], runs, packet, key, malformed, self.gates),
            "review schema validation failed",
        )

    def test_score_validates_review_schema_at_cli_boundary_with_maximum_two(self):
        schema = json.loads(
            (ROOT / "schemas/local-model-evaluation-review.v1.schema.json").read_text(encoding="utf-8")
        )
        candidate = schema["properties"]["cases"]["items"]["properties"]["candidates"]["items"]["properties"]
        for dimension in ("fidelity", "structure", "uncertainty", "formula"):
            self.assertEqual(candidate[dimension]["maximum"], 2)
        runs, packet, key, reviews = self.artifacts()
        reviews["cases"][0]["candidates"][0]["fidelity"] = 3
        self.assert_scoring_error(
            lambda: SCORER.score_reviews(self.manifest["cases"], runs, packet, key, reviews, self.gates, ROOT),
            "review schema validation failed",
        )

    def test_score_binds_packet_key_review_and_rejects_unrelated_artifacts(self):
        runs, packet, key, reviews = self.artifacts()
        for value, pattern in (
            ((runs, packet, {**key, "reviewPacketId": "eval-review-packet-0000000000000000"}, reviews), "key"),
            ((runs, packet, key, {**reviews, "reviewPacketSha256": "0" * 64}), "review"),
        ):
            self.assert_scoring_error(
                lambda value=value: SCORER.score_reviews(self.manifest["cases"], *value, self.gates),
                pattern,
            )

    def test_score_rejects_self_consistent_packet_with_forged_candidate_text(self):
        runs, packet, key, reviews = self.artifacts()
        packet["cases"][0]["candidates"][0]["bodyEnglish"] += " forged"
        packet["reviewPacketId"] = MODULE.review_packet_id_for(packet)
        packet_hash = MODULE.artifact_sha256(packet)
        key["reviewPacketId"] = packet["reviewPacketId"]
        key["reviewPacketSha256"] = packet_hash
        reviews["reviewPacketId"] = packet["reviewPacketId"]
        reviews["reviewPacketSha256"] = packet_hash

        self.assert_scoring_error(
            lambda: SCORER.score_reviews(self.manifest["cases"], runs, packet, key, reviews, self.gates),
            "does not match supplied cases, runs, and seed",
        )

    def test_score_cli_rejects_fabricated_eligible_manifest_and_runs(self):
        fabricated_manifest = copy.deepcopy(self.manifest)
        template = fabricated_manifest["cases"][0]
        fabricated_manifest["cases"] = []
        for index in range(1, 31):
            case = copy.deepcopy(template)
            case["caseId"] = f"case-{index:03d}"
            case["sourceUnitId"] = f"fabricated-source-unit-{index:03d}"
            case["arabic"] = f"نص مختلق {index}"
            case["arabicSha256"] = MODULE.sha256_text(case["arabic"])
            case["referenceEnglish"] = f"Fabricated comparator {index}"
            case["referenceSha256"] = MODULE.sha256_text(case["referenceEnglish"])
            case["heldOut"] = True
            fabricated_manifest["cases"].append(case)

        packet = MODULE.prepare_blind_packet(fabricated_manifest, self.configs[0])
        runs = [
            MODULE.record_run(
                packet,
                [
                    {
                        "caseId": case["caseId"],
                        "titleEnglish": f"Run {run_index} title",
                        "bodyEnglish": f"Run {run_index} body",
                        "issues": [],
                    }
                    for case in fabricated_manifest["cases"]
                ],
                f"2026-08-20T11:0{run_index}:00Z",
            )
            for run_index in range(4)
        ]
        review_packet, key = MODULE.build_blind_review_packet(
            fabricated_manifest["cases"], runs, "fabricated-eligible"
        )
        reviews = {
            "schemaVersion": "1.0.0",
            "reviewPacketId": review_packet["reviewPacketId"],
            "reviewPacketSha256": MODULE.artifact_sha256(review_packet),
            "reviewerId": "fabricated-reviewer",
            "cases": [
                {
                    "caseId": case["caseId"],
                    "candidates": [
                        {
                            "alias": candidate["alias"],
                            "fidelity": 2,
                            "structure": 2,
                            "uncertainty": 2,
                            "formula": 2,
                            "materialErrors": [],
                            "notes": "fabricated passing review",
                        }
                        for candidate in case["candidates"]
                    ],
                }
                for case in review_packet["cases"]
            ],
        }

        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            artifacts = {
                "cases.json": fabricated_manifest,
                "packet.json": review_packet,
                "key.json": key,
                "reviews.json": reviews,
                **{f"run-{index}.json": run for index, run in enumerate(runs)},
            }
            for name, value in artifacts.items():
                (directory / name).write_text(json.dumps(value), encoding="utf-8")
            argv = [
                "score",
                "--cases", str(directory / "cases.json"),
                "--runs", *(str(directory / f"run-{index}.json") for index in range(4)),
                "--packet", str(directory / "packet.json"),
                "--key", str(directory / "key.json"),
                "--reviews", str(directory / "reviews.json"),
                "--output", ".runtime/local-model-evaluation/exploit-score.json",
            ]
            with mock.patch.object(SCORER.RUNNER, "_write_json") as write_score:
                self.assert_scoring_error(lambda: SCORER._main(argv), "tracked cases manifest")
                write_score.assert_not_called()

    def test_repeat_count_is_derived_from_distinct_comparable_runs(self):
        runs, packet, key, reviews = self.artifacts()
        score = SCORER.score_reviews(self.manifest["cases"], runs, packet, key, reviews, self.gates)
        self.assertEqual(score["minimumRepeatCount"], 1)
        repeated = [
            self.make_run(0, "Gemma one", "2026-08-20T11:00:00Z"),
            self.make_run(0, "Gemma two", "2026-08-20T11:01:00Z"),
            self.make_run(1, "Sol one", "2026-08-20T11:02:00Z"),
            self.make_run(1, "Sol two", "2026-08-20T11:03:00Z"),
        ]
        packet2, key2 = MODULE.build_blind_review_packet(self.manifest["cases"], repeated, "repeat")
        reviews2 = copy.deepcopy(reviews)
        reviews2["reviewPacketId"] = packet2["reviewPacketId"]
        reviews2["reviewPacketSha256"] = MODULE.artifact_sha256(packet2)
        aliases = [candidate["alias"] for candidate in packet2["cases"][0]["candidates"]]
        for case_review in reviews2["cases"]:
            template = case_review["candidates"][0]
            case_review["candidates"] = [{**template, "alias": alias} for alias in aliases]
        score2 = SCORER.score_reviews(self.manifest["cases"], repeated, packet2, key2, reviews2, self.gates)
        self.assertEqual(score2["minimumRepeatCount"], 2)
        self.assertNotIn("repeat_count", SCORER.score_reviews.__annotations__)

    def test_role_thresholds_are_loaded_from_tracked_role_gates(self):
        runs, packet, key, reviews = self.artifacts()
        custom = copy.deepcopy(self.gates)
        custom["roles"]["draft_assistance"]["minimumHeldOutCases"] = 1
        custom["roles"]["draft_assistance"]["minimumRepeats"] = 1
        score = SCORER.score_reviews(self.manifest["cases"], runs, packet, key, reviews, custom)
        self.assertEqual(score["roleGates"]["draft_assistance"]["status"], "eligible-for-decision")
        self.assertEqual(score["roleGatesSha256"], MODULE.artifact_sha256(custom))

    def test_report_requires_score_tied_to_supplied_runs_and_cases_and_preserves_boundary(self):
        runs, packet, key, reviews = self.artifacts()
        score = SCORER.score_reviews(self.manifest["cases"], runs, packet, key, reviews, self.gates)
        report = SCORER.render_report(self.manifest["cases"], runs, score, packet, key, reviews)
        self.assertIn("### Title", report)
        self.assertIn("### Body", report)
        self.assertIn(runs[0]["outputs"][0]["titleEnglish"], report)
        self.assertIn(runs[0]["outputs"][0]["bodyEnglish"], report)
        unrelated = copy.deepcopy(runs)
        unrelated[0]["runId"] = "eval-run-0000000000000000"
        self.assert_scoring_error(
            lambda: SCORER.render_report(self.manifest["cases"], unrelated, score, packet, key, reviews),
            "run identity/hash mismatch",
        )

    def test_report_rejects_rehashed_score_with_forged_semantic_role_gate(self):
        runs, packet, key, reviews = self.artifacts()
        score = SCORER.score_reviews(self.manifest["cases"], runs, packet, key, reviews, self.gates)
        score["roleGates"]["semantic_authority"]["status"] = "eligible-for-decision"
        score["roleGatesSha256"] = MODULE.artifact_sha256({"forged": True})
        score["scoreId"] = MODULE.score_id_for(score)

        self.assert_scoring_error(
            lambda: SCORER.render_report(self.manifest["cases"], runs, score, packet, key, reviews),
            "tracked role gates",
        )

    def test_report_requires_packet_key_and_reviewer_worksheet(self):
        runs, packet, key, reviews = self.artifacts()
        score = SCORER.score_reviews(self.manifest["cases"], runs, packet, key, reviews, self.gates)
        score["reviewerId"] = "forged-reviewer"
        first_run = next(iter(score["runs"].values()))
        first_run["reviews"][0]["dimensions"]["fidelity"] = 0
        dimensions = [
            value
            for review in first_run["reviews"]
            for value in review["dimensions"].values()
        ]
        first_run["averageDimensionScore"] = sum(dimensions) / len(dimensions)
        score["worksheetSha256"] = "0" * 64
        score["scoreId"] = MODULE.score_id_for(score)

        self.assert_scoring_error(
            lambda: SCORER.render_report(self.manifest["cases"], runs, score),
            "review packet, alias key, and reviewer worksheet are required",
        )
        self.assert_scoring_error(
            lambda: SCORER.render_report(
                self.manifest["cases"], runs, score, packet, key, reviews
            ),
            "score does not match rederived review evidence",
        )

    def test_malformed_collections_raise_domain_errors(self):
        packet = MODULE.prepare_blind_packet(self.manifest, self.configs[0])
        self.assert_evaluation_error(
            lambda: MODULE.record_run(packet, "not-an-array", "2026-08-20T11:00:00Z"),
            "outputs must be an array",
        )
        runs, review_packet, key, reviews = self.artifacts()
        malformed = copy.deepcopy(reviews)
        malformed["cases"] = "not-an-array"
        self.assert_scoring_error(
            lambda: SCORER.score_reviews(self.manifest["cases"], runs, review_packet, key, malformed, self.gates),
            "review schema validation failed",
        )

    def test_privacy_fields_are_normalized_case_insensitively_and_copied_fields_are_allowlisted(self):
        packet = MODULE.prepare_blind_packet(
            {**self.manifest, "apiKey": "secret", "untrackedMetadata": "do not copy"},
            {**self.configs[0], "untrackedMetadata": "do not copy"},
        )
        encoded = json.dumps(packet)
        self.assertNotIn("untrackedMetadata", encoded)
        for field in ("apiKey", "password", "accessToken", "private_path", "PRIVATE-PATH"):
            outputs = self.outputs("Candidate")
            outputs[0][field] = "secret"
            self.assert_evaluation_error(
                lambda outputs=outputs: MODULE.record_run(packet, outputs, "2026-08-20T11:00:00Z"),
                "forbidden field",
            )

    def test_report_escapes_html_remote_images_and_active_links(self):
        runs, packet, key, reviews = self.artifacts()
        runs[0]["outputs"][0]["titleEnglish"] = "<script>alert(1)</script> [click](https://evil.example)"
        runs[0]["outputs"][0]["bodyEnglish"] = "![pixel](https://evil.example/p.png)"
        runs[0]["outputs"][0]["titleEnglishSha256"] = MODULE.sha256_text(runs[0]["outputs"][0]["titleEnglish"])
        runs[0]["outputs"][0]["bodyEnglishSha256"] = MODULE.sha256_text(runs[0]["outputs"][0]["bodyEnglish"])
        # A report validates score/run linkage, so refresh all artifacts after changing the run.
        runs[0]["runId"] = MODULE.run_id_for(runs[0])
        packet, key = MODULE.build_blind_review_packet(self.manifest["cases"], runs, "safe-report")
        reviews["reviewPacketId"] = packet["reviewPacketId"]
        reviews["reviewPacketSha256"] = MODULE.artifact_sha256(packet)
        for case_review, packet_case in zip(reviews["cases"], packet["cases"]):
            for candidate, packet_candidate in zip(case_review["candidates"], packet_case["candidates"]):
                candidate["alias"] = packet_candidate["alias"]
        score = SCORER.score_reviews(self.manifest["cases"], runs, packet, key, reviews, self.gates)
        report = SCORER.render_report(self.manifest["cases"], runs, score, packet, key, reviews)
        self.assertNotIn("<script>", report)
        self.assertNotIn("](https://", report)
        self.assertNotIn(r"!\[", report)
        self.assertIn("&lt;script&gt;", report)

    def test_score_contains_hashes_for_every_input_and_sampling_seed_is_disclosed(self):
        for config in self.configs:
            self.assertIn("samplingSeed", config)
        runs, packet, key, reviews = self.artifacts()
        score = SCORER.score_reviews(self.manifest["cases"], runs, packet, key, reviews, self.gates)
        self.assertEqual(score["casesSha256"], MODULE.artifact_sha256(self.manifest["cases"]))
        self.assertEqual(score["reviewPacketSha256"], MODULE.artifact_sha256(packet))
        self.assertEqual(score["aliasKeySha256"], MODULE.artifact_sha256(key))
        self.assertEqual(score["worksheetSha256"], MODULE.artifact_sha256(reviews))
        self.assertEqual(score["roleGatesSha256"], MODULE.artifact_sha256(self.gates))
        self.assertRegex(score["rubricSha256"], r"^[a-f0-9]{64}$")
        self.assertEqual(set(score["runArtifactSha256"]), {run["runId"] for run in runs})

    def test_score_schema_is_closed_and_validates_generated_linkage(self):
        schema_path = ROOT / "schemas/local-model-evaluation-score.v1.schema.json"
        self.assertTrue(schema_path.is_file())
        runs, packet, key, reviews = self.artifacts()
        score = SCORER.score_reviews(self.manifest["cases"], runs, packet, key, reviews, self.gates)
        self.assertEqual(SCORER.validate_score_artifact(score, ROOT), [])
        tampered = copy.deepcopy(score)
        tampered["unexpected"] = True
        self.assertTrue(SCORER.validate_score_artifact(tampered, ROOT))

    def test_manifest_rejects_duplicate_case_and_source_ids(self):
        duplicate_case = copy.deepcopy(self.manifest)
        duplicate_case["cases"][1]["caseId"] = duplicate_case["cases"][0]["caseId"]
        self.assert_evaluation_error(lambda: MODULE.validate_manifest_integrity(duplicate_case), "duplicate case ID")
        duplicate_source = copy.deepcopy(self.manifest)
        duplicate_source["cases"][1]["sourceUnitId"] = duplicate_source["cases"][0]["sourceUnitId"]
        self.assert_evaluation_error(lambda: MODULE.validate_manifest_integrity(duplicate_source), "duplicate source unit ID")

    def test_protocol_is_non_governing_and_smoke_evidence_preserves_failures(self):
        protocol_path = ROOT / self.manifest["policy"]["evaluationProtocolPath"]
        protocol = protocol_path.read_text(encoding="utf-8")
        self.assertIn("cannot make translation decisions", protocol)
        self.assertNotIn(str(protocol_path.relative_to(ROOT)), (ROOT / "compliance/policy-binding.v1.json").read_text(encoding="utf-8"))
        smoke = json.loads((ROOT / "evaluations/local-model/v1/smoke-evidence.json").read_text(encoding="utf-8"))
        xhigh = [attempt for attempt in smoke["attempts"] if attempt["profile"] == "xhigh"]
        self.assertTrue(any(attempt["result"] != "passed" for attempt in xhigh))
        post_fix = next(attempt for attempt in xhigh if attempt["attemptId"] == "xhigh-post-fix-001")
        self.assertEqual((post_fix["smokeTemperature"], post_fix["profileTemperature"], post_fix["result"]), (0.0, 0.2, "passed"))

    def test_decision_log_has_append_only_hash_chain_anchor(self):
        decision = json.loads((ROOT / "evaluations/local-model/v1/decision-log.json").read_text(encoding="utf-8"))
        self.assertEqual(decision["entries"][0]["previousEntrySha256"], None)
        self.assertRegex(decision["logHeadSha256"], r"^[a-f0-9]{64}$")
        self.assertEqual(decision["logHeadSha256"], MODULE.artifact_sha256(decision["entries"][-1]))

    def test_repository_contract_is_self_contained_source_locked_and_schema_valid(self):
        self.assertEqual(MODULE.validate_repository_contract(ROOT), [])
        proposal = json.loads(
            (ROOT / "content/public-proposals/issue-0026.public-proposal.json").read_text(encoding="utf-8")
        )
        records = {record["id"]: record for record in proposal["records"]}
        for case in self.manifest["cases"]:
            record = records[case["sourceUnitId"]]
            self.assertEqual(case["arabic"], record["arabic"])
            self.assertEqual(case["referenceEnglish"], record["english"])


if __name__ == "__main__":
    unittest.main()

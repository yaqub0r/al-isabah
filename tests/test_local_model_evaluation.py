import copy
import importlib.util
import json
import subprocess
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "evaluations/local-model/v1/results"


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
                "publicSafety": {
                    "status": "admitted",
                    "provenance": "sanitized-final-model-output",
                    "admittedBy": f"config:{self.configs[0]['configId']}",
                },
            }
            for case in self.manifest["cases"]
        ]

    def make_run(self, config_index, prefix, generated_at="2026-08-20T11:00:00Z"):
        packet = MODULE.prepare_source_packet(self.manifest, self.configs[config_index])
        outputs = self.outputs(prefix)
        for output in outputs:
            output["publicSafety"]["admittedBy"] = f"config:{self.configs[config_index]['configId']}"
        return MODULE.record_run(
            packet,
            outputs,
            generated_at,
            {"status": "completed", "profile": "xhigh", "limitations": []},
        )

    def artifacts(self):
        runs = [self.make_run(0, "Gemma"), self.make_run(1, "Sol")]
        packet = MODULE.build_identified_review_packet(self.manifest, runs)
        reviews = {
            "schemaVersion": "1.0.0",
            "reviewPacketId": packet["reviewPacketId"],
            "reviewPacketSha256": MODULE.artifact_sha256(packet),
            "reviewer": {
                "publicId": "github:public-reviewer",
                "publicationConsent": True,
                "consentRecordedOn": "2026-08-20",
                "consentEvidence": "https://github.com/yaqub0r/al-isabah/issues/49#issuecomment-5357953603",
            },
            "status": "complete",
            "publicSafety": {
                "status": "admitted",
                "provenance": "identified-human-public-review",
                "admittedBy": "github:public-reviewer",
            },
            "cases": [
                {
                    "caseId": case["caseId"],
                    "assessments": [
                        {
                            "runId": candidate["runId"],
                            "fidelity": 2,
                            "structure": 2,
                            "uncertainty": 2,
                            "formula": 2,
                            "materialErrors": [],
                            "notes": "Source-based review: no material error found.",
                        }
                        for candidate in case["candidates"]
                    ],
                }
                for case in packet["cases"]
            ],
        }
        return runs, packet, reviews

    def assert_eval_error(self, callback, pattern):
        with self.assertRaisesRegex(MODULE.EvaluationError, pattern):
            callback()

    def assert_score_error(self, callback, pattern):
        with self.assertRaisesRegex(SCORER.ScoringError, pattern):
            callback()

    def test_every_case_requires_closed_public_eligibility_evidence(self):
        for case in self.manifest["cases"]:
            eligibility = case["publicEligibility"]
            self.assertEqual(eligibility["decision"], "approved")
            self.assertEqual(eligibility["authorityStatus"], "public-approved-authority")
            self.assertTrue(eligibility["publicRationale"].strip())
            self.assertRegex(eligibility["reviewedOn"], r"^20[0-9]{2}-[0-9]{2}-[0-9]{2}$")
            self.assertIn("issues/49#issuecomment-", eligibility["issueEvidence"])
            for field in (
                "restrictedWitnessText", "credentials", "internalPathsOrObjectLocators",
                "privateCorrespondence", "livingPersonPersonalInformation",
            ):
                self.assertIs(eligibility[field], False)
        for field in (
            "restrictedWitnessText", "credentials", "internalPathsOrObjectLocators",
            "privateCorrespondence", "livingPersonPersonalInformation",
        ):
            ineligible = copy.deepcopy(self.manifest)
            ineligible["cases"][0]["publicEligibility"][field] = True
            self.assert_eval_error(
                lambda ineligible=ineligible: MODULE.validate_manifest_integrity(ineligible),
                "not eligible for public evaluation",
            )

    def test_public_eligibility_recursively_rejects_unsafe_evidence_and_fields(self):
        for mutation in (
            lambda eligibility: eligibility.__setitem__("publicRationale", "password=hunter2 at /home/reviewer/file"),
            lambda eligibility: eligibility.__setitem__("reviewedBy", "reviewer@example.com"),
            lambda eligibility: eligibility.__setitem__("private_path", "redacted"),
        ):
            attacked = copy.deepcopy(self.manifest)
            mutation(attacked["cases"][0]["publicEligibility"])
            self.assert_eval_error(
                lambda attacked=attacked: MODULE.validate_manifest_integrity(attacked),
                "public eligibility|unsafe public text|forbidden field",
            )

    def test_source_packet_is_reference_free_and_all_runs_share_locked_inputs(self):
        packets = [MODULE.prepare_source_packet(self.manifest, config) for config in self.configs]
        self.assertNotIn("referenceEnglish", json.dumps(packets, ensure_ascii=False))
        self.assertEqual(packets[0]["cases"], packets[1]["cases"])
        self.assertEqual(packets[0]["casesSha256"], packets[1]["casesSha256"])
        self.assertEqual(packets[0]["policy"], packets[1]["policy"])
        self.assertEqual(
            [case["caseId"] for case in packets[0]["cases"]],
            [case["caseId"] for case in self.manifest["cases"]],
        )
        mismatched_prompt = copy.deepcopy(self.configs[0])
        mismatched_prompt["promptSha256"] = "0" * 64
        self.assert_eval_error(
            lambda: MODULE.prepare_source_packet(self.manifest, mismatched_prompt),
            "prompt binding",
        )

    def test_run_rejects_unequal_case_sets_missing_model_identity_and_private_fields(self):
        packet = MODULE.prepare_source_packet(self.manifest, self.configs[0])
        missing = self.outputs("candidate")[:-1]
        self.assert_eval_error(
            lambda: MODULE.record_run(packet, missing, "2026-08-20T11:00:00Z"),
            "exactly cover",
        )
        bad_config = copy.deepcopy(self.configs[0])
        bad_config["model"] = ""
        self.assert_eval_error(
            lambda: MODULE.prepare_source_packet(self.manifest, bad_config),
            "model identity",
        )
        for field in ("apiKey", "PRIVATE-PATH", "object_locator", "livingPersonPersonalInformation"):
            outputs = self.outputs("candidate")
            outputs[0][field] = "secret"
            self.assert_eval_error(
                lambda outputs=outputs: MODULE.record_run(packet, outputs, "2026-08-20T11:00:00Z"),
                "forbidden field",
            )

    def test_every_external_public_text_field_is_scanned_fail_closed(self):
        packet = MODULE.prepare_source_packet(self.manifest, self.configs[0], ROOT)
        attacks = {
            "titleEnglish": "Bearer ghp_abcdefghijklmnopqrstuvwxyz123456",
            "bodyEnglish": "private path /home/reviewer/notes.txt",
            "issues": "raw reasoning trace: hidden steps",
            "limitations": "contact reviewer@example.com",
            "admittedBy": "password=hunter2",
        }
        for field, payload in attacks.items():
            outputs = self.outputs("candidate")
            outcome = {"status": "completed", "profile": "xhigh", "limitations": []}
            if field == "limitations":
                outcome["limitations"] = [payload]
            elif field == "admittedBy":
                outputs[0]["publicSafety"][field] = payload
            elif field == "issues":
                outputs[0][field] = [payload]
            else:
                outputs[0][field] = payload
            self.assert_eval_error(
                lambda outputs=outputs, outcome=outcome: MODULE.record_run(
                    packet, outputs, "2026-08-20T11:00:00Z", outcome
                ),
                "unsafe public text",
            )

        runs, review_packet, reviews = self.artifacts()
        review_attacks = (
            ("publicId", "Jane Doe 212-555-0199"),
            ("materialErrors", "restricted witness evidence says otherwise"),
            ("notes", "see www.evil.example for details"),
            ("admittedBy", "C:\\Users\\Reviewer\\private.txt"),
        )
        for field, payload in review_attacks:
            attacked = copy.deepcopy(reviews)
            if field == "publicId":
                attacked["reviewer"][field] = payload
            elif field == "materialErrors":
                attacked["cases"][0]["assessments"][0][field] = [payload]
            elif field == "notes":
                attacked["cases"][0]["assessments"][0][field] = payload
            else:
                attacked["publicSafety"][field] = payload
            self.assert_score_error(
                lambda attacked=attacked: SCORER.score_reviews(
                    self.manifest, runs, review_packet, attacked, self.gates, ROOT
                ),
                "unsafe public text",
            )

    def test_repository_authored_report_phrase_does_not_allow_same_external_phrase(self):
        phrase = "restricted evidence"
        packet = MODULE.prepare_source_packet(self.manifest, self.configs[0], ROOT)
        outputs = self.outputs("candidate")
        outputs[0]["bodyEnglish"] = phrase
        self.assert_eval_error(
            lambda: MODULE.record_run(packet, outputs, "2026-08-20T11:00:00Z"),
            "unsafe public text",
        )

        runs, review_packet, reviews = self.artifacts()
        reviews["cases"][0]["assessments"][0]["notes"] = phrase
        self.assert_score_error(
            lambda: SCORER.score_reviews(self.manifest, runs, review_packet, reviews, self.gates, ROOT),
            "unsafe public text",
        )

    def test_public_text_rejects_protocol_relative_repository_relative_and_angle_gfm(self):
        attacks = (
            "![pixel](//private.example/collect)",
            "[private](../../private/review.md)",
            "<//private.example/path>",
            "[nested [private](../../x)](//private.example/y)",
        )
        packet = MODULE.prepare_source_packet(self.manifest, self.configs[0], ROOT)
        for attack in attacks:
            outputs = self.outputs("candidate")
            outputs[0]["bodyEnglish"] = attack
            self.assert_eval_error(
                lambda outputs=outputs: MODULE.record_run(packet, outputs, "2026-08-20T11:00:00Z"),
                "unsafe public text",
            )
            rendered = SCORER._safe_markdown(attack).lower()
            self.assertNotIn("](//", rendered)
            self.assertNotIn("](../", rendered)
            self.assertNotIn("<//", rendered)

    def test_model_outputs_and_reviews_require_explicit_public_safety_admission(self):
        packet = MODULE.prepare_source_packet(self.manifest, self.configs[0], ROOT)
        outputs = self.outputs("candidate")
        del outputs[0]["publicSafety"]
        self.assert_eval_error(
            lambda: MODULE.record_run(packet, outputs, "2026-08-20T11:00:00Z"),
            "public-safety admission",
        )
        runs, review_packet, reviews = self.artifacts()
        del reviews["publicSafety"]
        self.assert_score_error(
            lambda: SCORER.score_reviews(self.manifest, runs, review_packet, reviews, self.gates, ROOT),
            "public-safety admission",
        )

    def test_public_safety_admission_identity_is_governed(self):
        packet = MODULE.prepare_source_packet(self.manifest, self.configs[0], ROOT)
        outputs = self.outputs("candidate")
        outputs[0]["publicSafety"]["admittedBy"] = "github:unrelated-person"
        self.assert_eval_error(
            lambda: MODULE.record_run(packet, outputs, "2026-08-20T11:00:00Z"),
            "admitting identity",
        )
        forged_run = self.make_run(0, "Gemma")
        forged_run["outputs"][0]["publicSafety"]["admittedBy"] = "github:unrelated-person"
        forged_run["runId"] = MODULE.run_id_for(forged_run)
        self.assertTrue(
            any("admitting identity" in error for error in MODULE.validate_run_artifact(forged_run, ROOT))
        )
        runs, review_packet, reviews = self.artifacts()
        reviews["publicSafety"]["admittedBy"] = "github:unrelated-person"
        self.assert_score_error(
            lambda: SCORER.score_reviews(self.manifest, runs, review_packet, reviews, self.gates, ROOT),
            "admitting identity",
        )

    def test_runs_are_pending_public_evidence_with_provenance_and_resource_outcome(self):
        run = self.make_run(0, "Gemma")
        self.assertEqual(run["reviewStatus"], "unreviewed")
        self.assertEqual(run["roleStatus"], "no-role")
        self.assertEqual(run["promotionStatus"], "blocked")
        self.assertEqual(run["resourceOutcome"]["status"], "completed")
        self.assertEqual(run["config"]["model"], self.configs[0]["model"])
        self.assertRegex(run["runId"], r"^eval-run-[a-f0-9]{16}$")
        self.assertEqual(MODULE.validate_run_artifact(run, ROOT), [])

    def test_cli_outputs_are_constrained_to_public_tracked_results_root(self):
        allowed = MODULE.validated_public_result_output_path(
            ROOT, "evaluations/local-model/v1/results/issue-49/example.json"
        )
        self.assertEqual(allowed, RESULTS / "issue-49/example.json")
        for path in ("outside.json", ".runtime/local-model-evaluation/result.json"):
            self.assert_eval_error(
                lambda path=path: MODULE.validated_public_result_output_path(ROOT, path),
                "evaluations/local-model/v1/results",
            )
            self.assert_eval_error(
                lambda path=path: MODULE.validated_public_result_input_path(ROOT, path),
                "evaluations/local-model/v1/results",
            )
        runner = ROOT / "scripts/local_model_evaluation.py"
        completed = subprocess.run(
            ["python", str(runner), "prepare", "--config",
             "evaluations/local-model/v1/configs/gemma4-xhigh-v1.json", "--output", "outside.json"],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("evaluations/local-model/v1/results", completed.stderr)

    def test_identified_packet_discloses_each_model_config_and_supports_pending_report(self):
        runs = [self.make_run(0, "Gemma"), self.make_run(1, "Sol")]
        packet = MODULE.build_identified_review_packet(self.manifest, runs)
        candidate = packet["cases"][0]["candidates"][0]
        self.assertEqual(set(candidate), {"runId", "runSha256", "config", "titleEnglish", "bodyEnglish", "issues", "publicSafety"})
        self.assertTrue(candidate["config"]["model"])
        self.assertEqual(packet["reviewStatus"], "unreviewed")
        report = SCORER.render_report(self.manifest, runs, packet)
        self.assertIn("Review status: **unreviewed**", report)
        self.assertIn("Role status: **no-role**", report)
        self.assertIn(self.manifest["cases"][0]["arabic"], report)
        for run in runs:
            self.assertIn(run["config"]["model"], report)
            self.assertIn(run["outputs"][0]["titleEnglish"], report)
            self.assertIn(run["outputs"][0]["bodyEnglish"], report)

    def test_identified_packet_rejects_unequal_or_forged_run_evidence(self):
        runs = [self.make_run(0, "Gemma"), self.make_run(1, "Sol")]
        missing = copy.deepcopy(runs)
        missing[0]["outputs"].pop()
        self.assert_eval_error(
            lambda: MODULE.build_identified_review_packet(self.manifest, missing), "exactly cover"
        )
        forged = copy.deepcopy(runs)
        forged[0]["outputs"][0]["bodyEnglish"] += " forged"
        self.assert_eval_error(
            lambda: MODULE.build_identified_review_packet(self.manifest, forged), "hash mismatch"
        )
        wrong_policy = copy.deepcopy(runs)
        wrong_policy[0]["policy"]["bindingSha256"] = "0" * 64
        wrong_policy[0]["policySha256"] = MODULE.artifact_sha256(wrong_policy[0]["policy"])
        wrong_policy[0]["runId"] = MODULE.run_id_for(wrong_policy[0])
        self.assert_eval_error(
            lambda: MODULE.build_identified_review_packet(self.manifest, wrong_policy),
            "manifest policy",
        )

    def test_review_requires_stable_public_id_and_explicit_publication_consent(self):
        runs, packet, reviews = self.artifacts()
        missing_consent = copy.deepcopy(reviews)
        missing_consent["reviewer"]["publicationConsent"] = False
        self.assert_score_error(
            lambda: SCORER.score_reviews(self.manifest, runs, packet, missing_consent, self.gates),
            "publication consent",
        )
        missing_id = copy.deepcopy(reviews)
        missing_id["reviewer"]["publicId"] = ""
        self.assert_score_error(
            lambda: SCORER.score_reviews(self.manifest, runs, packet, missing_id, self.gates),
            "review schema validation failed",
        )

    def test_scoring_is_fully_bound_and_rejects_forged_evidence(self):
        runs, packet, reviews = self.artifacts()
        score = SCORER.score_reviews(self.manifest, runs, packet, reviews, self.gates)
        self.assertEqual(score["reviewerPublicId"], reviews["reviewer"]["publicId"])
        self.assertEqual(score["reviewPacketSha256"], MODULE.artifact_sha256(packet))
        self.assertEqual(score["worksheetSha256"], MODULE.artifact_sha256(reviews))
        self.assertEqual(set(score["runArtifactSha256"]), {run["runId"] for run in runs})
        forged = copy.deepcopy(packet)
        forged["cases"][0]["candidates"][0]["bodyEnglish"] += " forged"
        forged["reviewPacketId"] = MODULE.review_packet_id_for(forged)
        forged_reviews = copy.deepcopy(reviews)
        forged_reviews["reviewPacketId"] = forged["reviewPacketId"]
        forged_reviews["reviewPacketSha256"] = MODULE.artifact_sha256(forged)
        self.assert_score_error(
            lambda: SCORER.score_reviews(self.manifest, runs, forged, forged_reviews, self.gates),
            "does not match supplied manifest and runs",
        )

    def test_score_rejects_incomplete_or_reordered_review_coverage(self):
        runs, packet, reviews = self.artifacts()
        incomplete = copy.deepcopy(reviews)
        incomplete["cases"].pop()
        self.assert_score_error(
            lambda: SCORER.score_reviews(self.manifest, runs, packet, incomplete, self.gates),
            "exactly cover cases in order",
        )
        reordered = copy.deepcopy(reviews)
        reordered["cases"][0]["assessments"].reverse()
        self.assert_score_error(
            lambda: SCORER.score_reviews(self.manifest, runs, packet, reordered, self.gates),
            "runs in packet order",
        )

    def test_failed_or_partial_runs_cannot_enter_identified_scoring_or_repeats(self):
        for status in ("failed", "partial"):
            runs, packet, reviews = self.artifacts()
            ineligible = copy.deepcopy(runs)
            ineligible[0]["resourceOutcome"]["status"] = status
            ineligible[0]["resourceOutcome"]["limitations"] = [f"{status} execution"]
            ineligible[0]["runId"] = MODULE.run_id_for(ineligible[0])

            self.assert_eval_error(
                lambda ineligible=ineligible: MODULE.build_identified_review_packet(
                    self.manifest, ineligible, ROOT
                ),
                "completed",
            )
            self.assert_score_error(
                lambda ineligible=ineligible: SCORER.score_reviews(
                    self.manifest, ineligible, packet, reviews, self.gates, ROOT
                ),
                "completed",
            )
            self.assert_score_error(
                lambda ineligible=ineligible: SCORER._repeat_counts(ineligible),
                "completed",
            )

    def test_attempt_summary_is_closed_provenance_bound_and_permanently_ineligible(self):
        packet = MODULE.prepare_source_packet(self.manifest, self.configs[0], ROOT)
        summary = MODULE.record_attempt_summary(
            packet,
            [
                {"caseId": "case-001", "attemptCount": 1, "outcome": "completed"},
                {"caseId": "case-002", "attemptCount": 2, "outcome": "timeout"},
                {"caseId": "case-003", "attemptCount": 0, "outcome": "controller-unavailable"},
            ],
            "2026-08-20T18:00:00Z",
            "Two case-002 attempts timed out; a later availability check did not complete.",
            ROOT,
        )
        self.assertRegex(summary["attemptSummaryId"], r"^eval-attempt-summary-[a-f0-9]{16}$")
        self.assertEqual(summary["packetId"], packet["packetId"])
        self.assertEqual(summary["packetSha256"], MODULE.artifact_sha256(packet))
        self.assertEqual(summary["configSha256"], packet["configSha256"])
        self.assertEqual(summary["promptSha256"], packet["policy"]["promptSha256"])
        self.assertEqual(summary["casesSha256"], packet["casesSha256"])
        self.assertEqual(summary["resourceIdentity"]["profile"], self.configs[0]["houseProfile"])
        self.assertEqual(summary["publicSafety"], {
            "status": "admitted",
            "provenance": "sanitized-attempt-summary",
            "admittedBy": f"config:{self.configs[0]['configId']}",
        })
        self.assertEqual(summary["eligibility"], {
            "identifiedReview": "excluded",
            "scoring": "excluded",
            "repeats": "excluded",
            "role": "no-role",
            "promotion": "blocked",
        })
        self.assertNotIn("titleEnglish", json.dumps(summary))
        self.assertEqual(MODULE.validate_attempt_summary_artifact(summary, ROOT), [])
        schema = json.loads(
            (ROOT / "schemas/local-model-evaluation-attempt-summary.v1.schema.json").read_text(encoding="utf-8")
        )
        self.assertIs(schema["additionalProperties"], False)

    def test_attempt_summary_rejects_forged_untracked_mismatched_and_private_evidence(self):
        packet = MODULE.prepare_source_packet(self.manifest, self.configs[0], ROOT)
        outcomes = [
            {"caseId": case["caseId"], "attemptCount": 1, "outcome": "timeout"}
            for case in packet["cases"]
        ]
        for attacked, pattern in (
            (lambda: MODULE.record_attempt_summary(
                packet, outcomes[:-1], "2026-08-20T18:00:00Z", "Execution did not complete.", ROOT
            ), "exactly cover"),
            (lambda: MODULE.record_attempt_summary(
                packet, outcomes, "2026-08-20 18:00:00", "Execution did not complete.", ROOT
            ), "UTC"),
            (lambda: MODULE.record_attempt_summary(
                packet, outcomes, "2026-99-99T18:00:00Z", "Execution did not complete.", ROOT
            ), "UTC"),
            (lambda: MODULE.record_attempt_summary(
                packet, outcomes, "2026-08-20T18:00:00Z", "/home/operator/raw.log", ROOT
            ), "unsafe public text"),
        ):
            self.assert_eval_error(attacked, pattern)

        summary = MODULE.record_attempt_summary(
            packet, outcomes, "2026-08-20T18:00:00Z", "Execution did not complete.", ROOT
        )
        forged = copy.deepcopy(summary)
        forged["configSha256"] = "0" * 64
        forged["attemptSummaryId"] = MODULE.attempt_summary_id_for(forged)
        self.assertTrue(any("config" in error for error in MODULE.validate_attempt_summary_artifact(forged, ROOT)))
        self.assert_eval_error(
            lambda: MODULE.build_identified_review_packet(self.manifest, [summary], ROOT),
            "outputs|run",
        )

    def test_attempt_summary_cli_derives_all_ids_and_hashes_from_public_packet(self):
        packet = MODULE.prepare_source_packet(self.manifest, self.configs[0], ROOT)
        directory = Path(tempfile.mkdtemp(prefix="attempt-summary-cli-", dir=RESULTS))
        try:
            packet_path = directory / "packet.json"
            outcomes_path = directory / "outcomes.json"
            summary_path = directory / "summary.json"
            packet_path.write_text(json.dumps(packet), encoding="utf-8")
            outcomes_path.write_text(json.dumps([
                {"caseId": case["caseId"], "attemptCount": 1, "outcome": "timeout"}
                for case in packet["cases"]
            ]), encoding="utf-8")
            completed = subprocess.run(
                [
                    "python", str(ROOT / "scripts/local_model_evaluation.py"), "attempt-summary",
                    "--packet", packet_path.relative_to(ROOT).as_posix(),
                    "--outcomes", outcomes_path.relative_to(ROOT).as_posix(),
                    "--generated-at", "2026-08-20T18:00:00Z",
                    "--limitation", "Execution did not complete.",
                    "--output", summary_path.relative_to(ROOT).as_posix(),
                ],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(MODULE.validate_attempt_summary_artifact(summary, ROOT), [])
            self.assertIn(summary["attemptSummaryId"], completed.stdout)
            self.assertIn("no role", completed.stdout)
        finally:
            shutil.rmtree(directory)

    def test_repeat_count_is_derived_and_role_gates_come_from_tracked_file(self):
        runs, packet, reviews = self.artifacts()
        score = SCORER.score_reviews(self.manifest, runs, packet, reviews, self.gates)
        self.assertEqual(score["minimumRepeatCount"], 1)
        self.assertNotIn("repeat_count", SCORER.score_reviews.__annotations__)
        custom = copy.deepcopy(self.gates)
        custom["roles"]["draft_assistance"]["minimumHeldOutCases"] = 1
        custom["roles"]["draft_assistance"]["minimumRepeats"] = 1
        self.assert_score_error(
            lambda: SCORER.score_reviews(self.manifest, runs, packet, reviews, custom),
            "tracked role gates",
        )

    def test_tracked_configs_are_exact_authorized_roots_at_every_stage(self):
        forged = copy.deepcopy(self.configs[0])
        forged["configId"] = "forged-but-rehashed"
        forged["model"] = "attacker/model"
        self.assert_eval_error(
            lambda: MODULE.prepare_source_packet(self.manifest, forged, ROOT),
            "authorized tracked config",
        )
        run = self.make_run(0, "Gemma")
        run["config"]["model"] = "attacker/model"
        run["configSha256"] = MODULE.artifact_sha256(run["config"])
        packet = MODULE.prepare_source_packet(self.manifest, run["config"], root=None)
        run["packetId"] = packet["packetId"]
        run["packetSha256"] = MODULE.artifact_sha256(packet)
        run["runId"] = MODULE.run_id_for(run)
        self.assert_eval_error(
            lambda: MODULE.validate_runs_against_manifest(self.manifest, [run], ROOT),
            "authorized tracked config",
        )

    def test_untracked_config_under_authorized_directory_fails_direct_api(self):
        attacked = copy.deepcopy(self.configs[0])
        attacked["configId"] = "untracked-config-exploit"
        path = ROOT / "evaluations/local-model/v1/configs/untracked-config-exploit.json"
        try:
            path.write_text(json.dumps(attacked), encoding="utf-8")
            self.assert_eval_error(
                lambda: MODULE.prepare_source_packet(self.manifest, attacked, ROOT),
                "authorized tracked config",
            )
        finally:
            path.unlink(missing_ok=True)

    def test_modified_tracked_config_fails_exact_index_equality(self):
        path = ROOT / "evaluations/local-model/v1/configs/gemma4-xhigh-v1.json"
        original = path.read_bytes()
        attacked = copy.deepcopy(self.configs[0])
        attacked["model"] = "attacker/modified-worktree-model"
        try:
            path.write_text(json.dumps(attacked, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self.assert_eval_error(
                lambda: MODULE.prepare_source_packet(self.manifest, attacked, ROOT),
                "authorized tracked config",
            )
        finally:
            path.write_bytes(original)

    def test_direct_packet_boundaries_require_exact_tracked_cases_manifest(self):
        forged_manifest = copy.deepcopy(self.manifest)
        forged_manifest["cases"][0]["referenceEnglish"] += " forged"
        forged_manifest["cases"][0]["referenceSha256"] = MODULE.sha256_text(
            forged_manifest["cases"][0]["referenceEnglish"]
        )
        self.assert_eval_error(
            lambda: MODULE.prepare_source_packet(forged_manifest, self.configs[0], ROOT),
            "tracked cases manifest",
        )
        runs = [self.make_run(0, "Gemma"), self.make_run(1, "Sol")]
        self.assert_eval_error(
            lambda: MODULE.build_identified_review_packet(forged_manifest, runs),
            "tracked cases manifest",
        )

    def test_record_boundary_rejects_self_consistent_packet_from_forged_arabic(self):
        forged_manifest = copy.deepcopy(self.manifest)
        forged_manifest["cases"][0]["arabic"] += " مزور"
        forged_manifest["cases"][0]["arabicSha256"] = MODULE.sha256_text(
            forged_manifest["cases"][0]["arabic"]
        )
        forged_packet = MODULE.prepare_source_packet(
            forged_manifest, self.configs[0], root=None
        )
        outputs = self.outputs("candidate")

        self.assert_eval_error(
            lambda: MODULE.record_run(
                forged_packet, outputs, "2026-08-20T11:00:00Z"
            ),
            "tracked cases manifest|tracked cases and authorized config",
        )

        directory = Path(tempfile.mkdtemp(prefix="record-boundary-", dir=RESULTS))
        try:
            packet_path = directory / "forged-packet.json"
            outputs_path = directory / "outputs.json"
            run_path = directory / "run.json"
            packet_path.write_text(json.dumps(forged_packet), encoding="utf-8")
            outputs_path.write_text(json.dumps(outputs), encoding="utf-8")
            completed = subprocess.run(
                [
                    "python", str(ROOT / "scripts/local_model_evaluation.py"), "record",
                    "--packet", packet_path.relative_to(ROOT).as_posix(),
                    "--outputs", outputs_path.relative_to(ROOT).as_posix(),
                    "--generated-at", "2026-08-20T11:00:00Z",
                    "--output", run_path.relative_to(ROOT).as_posix(),
                ],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertRegex(
                completed.stderr,
                "tracked cases manifest|tracked cases and authorized config",
            )
            self.assertFalse(run_path.exists())
        finally:
            shutil.rmtree(directory)

    def test_modified_worktree_cases_cannot_redefine_direct_api_trust_root(self):
        path = ROOT / "evaluations/local-model/v1/cases.json"
        original = path.read_bytes()
        attacked = copy.deepcopy(self.manifest)
        attacked["cases"][0]["referenceEnglish"] += " worktree substitution"
        attacked["cases"][0]["referenceSha256"] = MODULE.sha256_text(
            attacked["cases"][0]["referenceEnglish"]
        )
        try:
            path.write_text(json.dumps(attacked, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self.assert_eval_error(
                lambda: MODULE.prepare_source_packet(attacked, self.configs[0], ROOT),
                "tracked cases manifest",
            )
        finally:
            path.write_bytes(original)

    def test_resource_profile_must_equal_authorized_config_house_profile(self):
        packet = MODULE.prepare_source_packet(self.manifest, self.configs[0], ROOT)
        self.assert_eval_error(
            lambda: MODULE.record_run(
                packet, self.outputs("candidate"), "2026-08-20T11:00:00Z",
                {"status": "completed", "profile": "low", "limitations": []},
            ),
            "resource profile",
        )

    def test_reviewed_report_is_identified_bilingual_safe_and_rederived(self):
        runs, packet, reviews = self.artifacts()
        score = SCORER.score_reviews(self.manifest, runs, packet, reviews, self.gates)
        report = SCORER.render_report(self.manifest, runs, packet, reviews, score)
        self.assertIn("Review status: **complete**", report)
        self.assertIn(reviews["reviewer"]["publicId"], report)
        self.assertIn("Scores:", report)
        self.assertIn("Reviewer notes:", report)
        self.assertIn("Limitations", report)

        forged_score = copy.deepcopy(score)
        forged_score["reviewerPublicId"] = "github:forged"
        forged_score["scoreId"] = MODULE.score_id_for(forged_score)
        self.assert_score_error(
            lambda: SCORER.render_report(self.manifest, runs, packet, reviews, forged_score),
            "does not match rederived review evidence",
        )

    def test_markdown_neutralizes_all_gfm_link_and_autolink_forms(self):
        attacks = (
            "https://evil.example/x", "http://evil.example/x", "www.evil.example",
            "javascript:alert(1)", "data:text/html,boom", "mailto:evil@example.com", "tel:+15550199",
            "<https://evil.example>", "<evil@example.com>", "[x][ref]\n[ref]: https://evil.example",
            "[outer [inner](https://evil.example)](https://evil.example)",
            "![alt](https://evil.example/pixel.png)",
            "![alt](//evil.example/pixel.png)", "[x](../../private.md)", "<//evil.example/x>",
        )
        for attack in attacks:
            rendered = SCORER._safe_markdown(attack)
            lowered = rendered.lower()
            for marker in ("http://", "https://", "www.", "javascript:", "data:", "mailto:", "tel:", "](", "]["):
                self.assertNotIn(marker, lowered, attack)

    def test_documentation_artifact_type_is_not_unrestricted(self):
        self.assertNotIn("documentation", MODULE.SUPPORTED_RESULT_TYPES)
        schema = json.loads(
            (ROOT / "schemas/local-model-evaluation-results-manifest.v1.schema.json").read_text(encoding="utf-8")
        )
        artifact_types = schema["properties"]["artifacts"]["items"]["properties"]["artifactType"]["enum"]
        self.assertNotIn("documentation", artifact_types)

    def test_results_manifest_is_closed_hash_bound_schema_validated_and_report_deterministic(self):
        self.assertEqual(MODULE.validate_repository_contract(ROOT), [])
        manifest_path = ROOT / "evaluations/local-model/v1/results-manifest.json"
        admission = json.loads(manifest_path.read_text(encoding="utf-8"))
        declared = {item["path"] for item in admission["artifacts"]}
        self.assertEqual(declared, {
            "evaluations/local-model/v1/results/README.md",
            "evaluations/local-model/v1/results/issue-49/gemma-packet.json",
            "evaluations/local-model/v1/results/issue-49/gemma-attempt-summary.json",
            "evaluations/local-model/v1/results/issue-49/sol-packet.json",
            "evaluations/local-model/v1/results/issue-49/sol-run.json",
            "evaluations/local-model/v1/results/issue-49/identified-review-packet.json",
            "evaluations/local-model/v1/results/issue-49/pending-report.md",
        })
        with mock.patch.object(MODULE, "_tracked_result_paths", return_value=[
            "evaluations/local-model/v1/results/raw-agent-log.json"
        ]):
            errors = MODULE._validate_results_admission(ROOT, admission)
        self.assertTrue(any("undeclared" in error for error in errors), errors)

    def test_results_manifest_rejects_absent_declared_artifact(self):
        readme = RESULTS / "README.md"
        content = readme.read_bytes()
        readme.unlink()
        try:
            errors = MODULE.validate_repository_contract(ROOT)
        finally:
            readme.write_bytes(content)
        self.assertTrue(any("README.md" in error and "regular file" in error for error in errors), errors)

    def test_results_manifest_rejects_symlink_and_non_regular_declared_artifacts(self):
        readme = RESULTS / "README.md"
        content = readme.read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "README.md"
            target.write_bytes(content)
            readme.unlink()
            try:
                readme.symlink_to(target)
                symlink_errors = MODULE.validate_repository_contract(ROOT)
                readme.unlink()
                readme.mkdir()
                directory_errors = MODULE.validate_repository_contract(ROOT)
            finally:
                if readme.is_symlink():
                    readme.unlink()
                elif readme.is_dir():
                    readme.rmdir()
                readme.write_bytes(content)
        for errors in (symlink_errors, directory_errors):
            self.assertTrue(any("README.md" in error and "regular file" in error for error in errors), errors)

    def test_results_admission_rederives_full_declared_graph_and_upstream_hashes(self):
        runs, packet, reviews = self.artifacts()
        score = SCORER.score_reviews(self.manifest, runs, packet, reviews, self.gates, ROOT)
        source_packets = [MODULE.prepare_source_packet(self.manifest, run["config"], ROOT) for run in runs]
        directory = Path(tempfile.mkdtemp(prefix="graph-regression-", dir=RESULTS))
        try:
            values = {
                "source-0.json": ("source-packet", source_packets[0]),
                "source-1.json": ("source-packet", source_packets[1]),
                "run-0.json": ("run", runs[0]),
                "run-1.json": ("run", runs[1]),
                "packet.json": ("identified-review-packet", packet),
                "review.json": ("review", reviews),
                "score.json": ("score", score),
            }
            for name, (_, value) in values.items():
                (directory / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            report = SCORER.render_report(self.manifest, runs, packet, reviews, score)
            (directory / "report.md").write_text(report, encoding="utf-8")
            values["report.md"] = ("report", report)
            relative = {name: (directory / name).relative_to(ROOT).as_posix() for name in values}
            file_hash = {
                name: __import__("hashlib").sha256((directory / name).read_bytes()).hexdigest()
                for name in values
            }
            static = MODULE._dependency_hashes(ROOT)
            upstream = {
                "source-0.json": {}, "source-1.json": {},
                "run-0.json": {relative["source-0.json"]: file_hash["source-0.json"]},
                "run-1.json": {relative["source-1.json"]: file_hash["source-1.json"]},
                "packet.json": {
                    relative["run-0.json"]: file_hash["run-0.json"],
                    relative["run-1.json"]: file_hash["run-1.json"],
                },
                "review.json": {relative["packet.json"]: file_hash["packet.json"]},
                "score.json": {
                    relative["run-0.json"]: file_hash["run-0.json"],
                    relative["run-1.json"]: file_hash["run-1.json"],
                    relative["packet.json"]: file_hash["packet.json"],
                    relative["review.json"]: file_hash["review.json"],
                },
                "report.md": {
                    relative["run-0.json"]: file_hash["run-0.json"],
                    relative["run-1.json"]: file_hash["run-1.json"],
                    relative["packet.json"]: file_hash["packet.json"],
                    relative["review.json"]: file_hash["review.json"],
                    relative["score.json"]: file_hash["score.json"],
                },
            }
            artifacts = []
            for name, (artifact_type, _) in values.items():
                artifact = {"path": relative[name], "artifactType": artifact_type, "sha256": file_hash[name],
                            "dependencySha256": {**static, **upstream[name]}}
                if artifact_type == "report":
                    artifact["reportInputs"] = {
                        "cases": "evaluations/local-model/v1/cases.json",
                        "runs": [relative["run-0.json"], relative["run-1.json"]],
                        "packet": relative["packet.json"], "reviews": relative["review.json"],
                        "score": relative["score.json"],
                    }
                artifacts.append(artifact)
            admission = {"schemaVersion": "1.0.0", "dependencySha256": static, "artifacts": artifacts}
            with mock.patch.object(MODULE, "_tracked_result_paths", return_value=sorted(relative.values())):
                self.assertEqual(MODULE._validate_results_admission(ROOT, admission), [])

            admission["artifacts"] = [item for item in artifacts if item["artifactType"] != "report"]
            tracked_without_report = sorted(value for name, value in relative.items() if name != "report.md")
            forged = copy.deepcopy(score)
            forged["roleGates"]["draft_assistance"] = {"status": "eligible-for-decision", "reasons": []}
            forged["minimumRepeatCount"] = 99
            forged["scoreId"] = MODULE.score_id_for(forged)
            (directory / "score.json").write_text(json.dumps(forged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            score_artifact = next(item for item in artifacts if item["artifactType"] == "score")
            score_artifact["sha256"] = __import__("hashlib").sha256((directory / "score.json").read_bytes()).hexdigest()
            with mock.patch.object(MODULE, "_tracked_result_paths", return_value=tracked_without_report):
                errors = MODULE._validate_results_admission(ROOT, admission)
            self.assertTrue(any("rederived" in error or "graph" in error for error in errors), errors)
        finally:
            shutil.rmtree(directory)

    def test_results_graph_admits_attempt_summary_only_from_exact_declared_source_packet(self):
        packet = MODULE.prepare_source_packet(self.manifest, self.configs[0], ROOT)
        summary = MODULE.record_attempt_summary(
            packet,
            [
                {"caseId": case["caseId"], "attemptCount": 1, "outcome": "timeout"}
                for case in packet["cases"]
            ],
            "2026-08-20T18:00:00Z", "Execution did not complete.", ROOT,
        )
        directory = Path(tempfile.mkdtemp(prefix="attempt-summary-graph-", dir=RESULTS))
        try:
            source_path, summary_path = directory / "packet.json", directory / "summary.json"
            source_path.write_text(json.dumps(packet, sort_keys=True) + "\n", encoding="utf-8")
            summary_path.write_text(json.dumps(summary, sort_keys=True) + "\n", encoding="utf-8")
            source_relative = source_path.relative_to(ROOT).as_posix()
            summary_relative = summary_path.relative_to(ROOT).as_posix()
            source_hash = __import__("hashlib").sha256(source_path.read_bytes()).hexdigest()
            summary_hash = __import__("hashlib").sha256(summary_path.read_bytes()).hexdigest()
            static = MODULE._dependency_hashes(ROOT)
            admission = {
                "schemaVersion": "1.0.0", "dependencySha256": static,
                "artifacts": [
                    {"path": source_relative, "artifactType": "source-packet", "sha256": source_hash,
                     "dependencySha256": static},
                    {"path": summary_relative, "artifactType": "attempt-summary", "sha256": summary_hash,
                     "dependencySha256": {**static, source_relative: source_hash}},
                ],
            }
            tracked = [source_relative, summary_relative]
            with mock.patch.object(MODULE, "_tracked_result_paths", return_value=tracked):
                self.assertEqual(MODULE._validate_results_admission(ROOT, admission), [])

            forged = copy.deepcopy(summary)
            forged["packetSha256"] = "0" * 64
            forged["attemptSummaryId"] = MODULE.attempt_summary_id_for(forged)
            summary_path.write_text(json.dumps(forged, sort_keys=True) + "\n", encoding="utf-8")
            admission["artifacts"][1]["sha256"] = __import__("hashlib").sha256(
                summary_path.read_bytes()
            ).hexdigest()
            with mock.patch.object(MODULE, "_tracked_result_paths", return_value=tracked):
                errors = MODULE._validate_results_admission(ROOT, admission)
            self.assertTrue(any("packet" in error or "rederive" in error for error in errors), errors)
        finally:
            shutil.rmtree(directory)

    def test_report_manifest_inputs_cannot_escape_or_reference_undeclared_artifacts(self):
        declared = {
            "evaluations/local-model/v1/results/report.md": {"artifactType": "report"},
            "evaluations/local-model/v1/results/run.json": {"artifactType": "run"},
        }
        for inputs in (
            {"cases": "../cases.json", "runs": ["evaluations/local-model/v1/results/run.json"], "packet": "evaluations/local-model/v1/results/run.json"},
            {"cases": "evaluations/local-model/v1/cases.json", "runs": ["evaluations/local-model/v1/results/undeclared.json"], "packet": "evaluations/local-model/v1/results/run.json"},
            {"cases": "evaluations/local-model/v1/cases.json", "runs": ["evaluations/local-model/v1/results/run.json"], "packet": "evaluations/local-model/v1/results/run.json"},
        ):
            self.assert_eval_error(
                lambda inputs=inputs: MODULE._validate_report_inputs(inputs, declared),
                "report inputs",
            )

    def test_schemas_are_closed_and_superseded_alias_artifacts_are_deleted(self):
        for name in (
            "local-model-evaluation-cases.v1.schema.json",
            "local-model-evaluation-config.v1.schema.json",
            "local-model-evaluation-packet.v1.schema.json",
            "local-model-evaluation-attempt-summary.v1.schema.json",
            "local-model-evaluation-run.v1.schema.json",
            "local-model-evaluation-identified-packet.v1.schema.json",
            "local-model-evaluation-review.v1.schema.json",
            "local-model-evaluation-score.v1.schema.json",
            "local-model-evaluation-results-manifest.v1.schema.json",
        ):
            schema = json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
            self.assertIs(schema["additionalProperties"], False, name)
        self.assertFalse((ROOT / "schemas/local-model-evaluation-alias-key.v1.schema.json").exists())
        self.assertFalse((ROOT / "schemas/local-model-evaluation-blind-packet.v1.schema.json").exists())
        identified = json.loads(
            (ROOT / "schemas/local-model-evaluation-identified-packet.v1.schema.json").read_text(encoding="utf-8")
        )
        candidate_config = identified["properties"]["cases"]["items"]["properties"]["candidates"]["items"]["properties"]["config"]
        self.assertIs(candidate_config["additionalProperties"], False)
        self.assertIn("model", candidate_config["required"])

    def test_protocol_public_language_smoke_evidence_and_decision_chain(self):
        protocol = (ROOT / "docs/contracts/local-model-translation-evaluation-protocol.md").read_text(encoding="utf-8")
        self.assertIn("identified public review", protocol.lower())
        self.assertIn("source-only translation pass", protocol.lower())
        self.assertNotIn("model-anonymous", protocol.lower())
        self.assertNotIn("alias key", protocol.lower())
        decision = json.loads((ROOT / "evaluations/local-model/v1/decision-log.json").read_text(encoding="utf-8"))
        self.assertEqual(decision["entries"][0]["previousEntrySha256"], None)
        self.assertEqual(decision["logHeadSha256"], MODULE.artifact_sha256(decision["entries"][-1]))
        self.assertEqual(decision["entries"][-1]["promotionStatus"], "blocked")
        self.assertNotIn("blind", json.dumps(decision).lower())
        smoke = json.loads((ROOT / "evaluations/local-model/v1/smoke-evidence.json").read_text(encoding="utf-8"))
        xhigh = [attempt for attempt in smoke["attempts"] if attempt["profile"] == "xhigh"]
        self.assertTrue(any(attempt["result"] != "passed" for attempt in xhigh))
        post_fix = next(attempt for attempt in xhigh if attempt["attemptId"] == "xhigh-post-fix-001")
        self.assertEqual(
            (post_fix["smokeTemperature"], post_fix["profileTemperature"], post_fix["result"]),
            (0.0, 0.2, "passed"),
        )

    def test_repository_contract_is_self_contained_source_locked_and_valid(self):
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

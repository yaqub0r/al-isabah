"""Synthetic Codex metadata only: no model calls, credentials, or user sessions."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from test_translation_workflow import (
    MODULE as WORKFLOW, FIXTURE_MANIFEST, FIXTURE_SOURCE,
    assignment_issue, complete_autonomous_stages,
)
import execution_governance as GOVERNANCE
import host_runtime as HOST
from public_boundary import canonical_json, sha256_text_file

METHOD = "sol-xhigh-explicit-host-v1"
FIELDS = dict(zip(GOVERNANCE.STAGES, (
    "blindTranslation", "independentCritique", "witnessResolution", "adjudication", "names")))


class HostRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def log(self, session="worker", model="gpt-5.6-sol", reasoning="xhigh", prior=False, forked=False):
        path = self.root / (session + ".jsonl")
        records = [
            {"type": "session_meta", "payload": {
                "id": session, "model_provider": "openai", "forked_from_id": "old" if forked else None,
                "cwd": "C:/synthetic/private", "base_instructions": "synthetic private instructions",
            }},
            {"type": "response_item", "payload": {"text": "synthetic private response; never retained"}},
        ]
        if prior:
            records.append({"type": "turn_context", "payload": {"turn_id": "prior", "model": model, "effort": reasoning}})
        records.append({"type": "turn_context", "payload": {"turn_id": "turn", "model": model, "effort": reasoning}})
        path.write_text("".join(json.dumps(row) + "\n" for row in records), encoding="utf-8")
        return path

    def launch(self, kind="codex-worker", session="worker", **kwargs):
        return HOST.capture_launch(HOST.launch_request(kind, "gpt-5.6-sol", "xhigh"),
                                   self.log(session=session, **kwargs), session, "turn", kind, METHOD)

    def attach(self, provenance, stage):
        task = self.launch("codex-task", "task", prior=True)
        worker = self.launch(session="worker-" + provenance["runId"])
        provenance["execution"] = HOST.capture_execution(provenance, stage, METHOD, task, worker)

    def provenance(self, stage="blind_translation"):
        value = {"runId": "run", "model": "gpt-5.6-sol", "reasoning": "xhigh",
                 "fingerprint": "1" * 64, "inputSha256": "2" * 64,
                 "outputSha256": "3" * 64, "origin": "direct_execution"}
        self.attach(value, stage)
        return value

    def test_exact_sol_xhigh_all_stages_pass_without_signer(self):
        with mock.patch.object(GOVERNANCE, "verify_signature", side_effect=AssertionError("No signer gate")):
            for stage in GOVERNANCE.STAGES:
                self.assertEqual(GOVERNANCE.validate_execution(self.provenance(stage), stage), [])

    def test_missing_implicit_high_ultra_unknown_requests_fail(self):
        cases = [lambda e: e.update(methodId="unknown"),
                 lambda e: e.update(methodId="sol-xhigh-explicit-attested-v1")]
        for owner in ("task", "worker"):
            for field in ("model", "thinking" if owner == "task" else "reasoning_effort"):
                cases.append(lambda e, o=owner, f=field: e[o]["request"]["overrides"].pop(f))
                for value in ("high", "ultra", "unknown", "inherited", None):
                    cases.append(lambda e, o=owner, f=field, v=value: e[o]["request"]["overrides"].update({f: v}))
        for change in cases:
            value = self.provenance()
            change(value["execution"])
            self.assertTrue(GOVERNANCE.validate_execution(value, "blind_translation"))

    def test_effective_host_mismatch_and_self_report_fail(self):
        for owner in ("task", "worker"):
            for field, bad in (("reasoning", "high"), ("reasoning", "ultra"), ("model", "unknown"),
                               ("provider", "unknown"), ("source", "worker-self-report")):
                value = self.provenance()
                value["execution"][owner]["observed"][field] = bad
                self.assertTrue(GOVERNANCE.validate_execution(value, "blind_translation"))
        for missing in ("execution",):
            value = self.provenance()
            value.pop(missing)
            self.assertTrue(GOVERNANCE.validate_execution(value, "blind_translation"))
        value = self.provenance()
        value["reasoning"] = "high"
        self.assertTrue(GOVERNANCE.validate_execution(value, "blind_translation"))

    def test_stage_scope_and_orchestration_are_not_inferred(self):
        value = self.provenance()
        registry = GOVERNANCE.load_active_registry()
        registry["methods"][0]["stages"] = ["name_inventory"]
        with mock.patch.object(GOVERNANCE, "load_active_registry", return_value=registry):
            self.assertTrue(GOVERNANCE.validate_execution(value, "blind_translation"))
        registry["methods"][0]["stages"] = list(GOVERNANCE.STAGES)
        registry["methods"][0]["configuration"]["orchestration"] = "unknown-orchestration"
        with mock.patch.object(GOVERNANCE, "load_active_registry", return_value=registry):
            self.assertTrue(GOVERNANCE.validate_execution(value, "blind_translation"))

    def test_session_turn_run_input_output_checkpoint_mismatches_fail(self):
        for field in ("sessionId", "turnId", "runId", "inputSha256", "outputSha256", "checkpointSha256", "stage"):
            value = self.provenance()
            value["execution"]["binding"][field] = "9" * 64
            self.assertTrue(GOVERNANCE.validate_execution(value, "blind_translation"), field)
        value = self.provenance()
        value["execution"]["registrySha256"] = "9" * 64
        self.assertTrue(GOVERNANCE.validate_execution(value, "blind_translation"))

    def test_capture_rejects_wrong_or_missing_actual_host_metadata(self):
        for kwargs in ({"reasoning": "high"}, {"reasoning": None}, {"model": None}, {"prior": True}, {"forked": True}):
            with self.assertRaises(ValueError):
                self.launch(**kwargs)
        for session, turn in (("wrong", "turn"), ("worker", "wrong")):
            with self.assertRaises(ValueError):
                HOST.observe_session(self.log(), session, turn)
        path = self.log()
        path.write_text(json.dumps({"type": "response_item", "payload": {"model": "gpt-5.6-sol", "effort": "xhigh"}}), encoding="utf-8")
        with self.assertRaises(ValueError):
            HOST.observe_session(path, "worker", "turn")

    def test_conflicting_host_turn_settings_and_malformed_logs_fail_safely(self):
        path = self.log()
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"type": "turn_context", "payload": {"turn_id": "turn", "model": "gpt-5.6-sol", "effort": "high"}}) + "\n")
        with self.assertRaises(ValueError):
            HOST.observe_session(path, "worker", "turn")
        path.write_text("synthetic-private-secret invalid JSON", encoding="utf-8")
        with self.assertRaises(ValueError) as caught:
            HOST.observe_session(path, "worker", "turn")
        self.assertNotIn("synthetic-private-secret", str(caught.exception))
        self.assertNotIn(str(path), str(caught.exception))
        for raw in ('{"type":"session_meta","payload":[]}',
                    '{"type":"turn_context","payload":{"model":"high","model":"xhigh"}}'):
            path.write_text(raw + "\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                HOST.observe_session(path, "worker", "turn")

    def test_context_inheritance_and_task_session_reuse_fail(self):
        for mutate in (
            lambda e: e["worker"]["request"]["overrides"].update(fork_turns="all"),
            lambda e: e["worker"]["observed"].update(firstTurn=False),
            lambda e: e["worker"]["observed"].update(forked=True),
            lambda e: e["task"]["observed"].update(sessionId=e["worker"]["observed"]["sessionId"]),
        ):
            value = self.provenance("independent_critique")
            mutate(value["execution"])
            self.assertTrue(GOVERNANCE.validate_execution(value, "independent_critique"))

    def test_capture_minimizes_metadata_and_rejects_private_fields(self):
        value = self.provenance()
        self.assertNotIn("synthetic private", json.dumps(value))
        self.assertNotIn("C:/", json.dumps(value))
        for key in ("rawTrace", "privatePath", "responseText", "englishSample"):
            changed = copy.deepcopy(value)
            changed["execution"][key] = "synthetic forbidden data"
            self.assertTrue(GOVERNANCE.validate_execution(changed, "blind_translation"))

    def completed_packet(self):
        issue = assignment_issue()
        packet = WORKFLOW.build_packet(issue, WORKFLOW.parse_claims([issue]), FIXTURE_SOURCE,
                                       FIXTURE_MANIFEST, WORKFLOW.DEFAULT_POLICY)
        complete_autonomous_stages(packet)
        for entry in packet["entries"]:
            for owner in [entry, *entry["precedingTranslations"]]:
                for stage, field in FIELDS.items():
                    self.attach(owner[field]["provenance"], stage)
        packet["formulaInventory"], errors = WORKFLOW.formula_inventory(packet)
        self.assertEqual(errors, [])
        packet["reviewPresentation"] = {"status": "ready", "path": "review.md", "sha256": "a" * 64}
        packet["machineReadiness"].update(status="ready", validatedAt="2026-08-30T12:00:00Z")
        packet["reviewPresentation"]["sha256"] = WORKFLOW.text_sha256(WORKFLOW.render_review(packet))
        return packet

    def test_full_packet_and_independent_upstream_session_reuse(self):
        packet = self.completed_packet()
        self.assertEqual(WORKFLOW.validate_packet(packet, machine_ready=True), [])
        first = packet["entries"][0]
        target = first["names"]["provenance"]["execution"]
        previous = first["independentCritique"]["provenance"]["execution"]["worker"]["observed"]["sessionId"]
        target["worker"]["observed"]["sessionId"] = target["binding"]["sessionId"] = previous
        self.assertTrue(any("reused the upstream runtime session" in error for error in WORKFLOW.validate_packet(packet, machine_ready=True)))
        first["blindTranslation"]["provenance"]["execution"] = None
        self.assertTrue(any("captured host evidence is required" in error for error in WORKFLOW.validate_packet(packet, machine_ready=True)))

    def test_shard_merge_rejects_uncaptured_output_atomically(self):
        issue = assignment_issue()
        packet = WORKFLOW.build_packet(issue, WORKFLOW.parse_claims([issue]), FIXTURE_SOURCE,
                                       FIXTURE_MANIFEST, WORKFLOW.DEFAULT_POLICY)
        completed = copy.deepcopy(packet)
        complete_autonomous_stages(completed)
        fields = ("sourceOrdinal", "sourceUnitId", "blindTranslation", "independentCritique",
                  "witnessResolution", "adjudication", "names", "unresolved", "humanReview")
        shard = {"schemaVersion": "3.0.0", "packetId": packet["packetId"], "issueNumber": 25,
                 "startUnit": 1, "endUnit": 2,
                 "entries": [{field: entry[field] for field in fields} for entry in completed["entries"]]}
        packet_path, shard_path = self.root / "packet.json", self.root / "shard.json"
        packet_path.write_bytes(WORKFLOW.json_bytes(packet))
        shard_path.write_bytes(WORKFLOW.json_bytes(shard))
        before = packet_path.read_bytes()
        with self.assertRaisesRegex(WORKFLOW.WorkflowError, "captured host evidence"):
            WORKFLOW.merge_entry_shard(packet_path, shard_path)
        self.assertEqual(packet_path.read_bytes(), before)

    def test_new_and_historical_schema_pins_and_decision_supersession(self):
        standalone = GOVERNANCE.read_json(HOST.SCHEMA)
        standalone.pop("$schema")
        standalone.pop("title")
        self.assertEqual(GOVERNANCE.read_json(WORKFLOW.DEFAULT_PACKET_SCHEMA)["$defs"]["execution"], standalone)
        registry = GOVERNANCE.load_active_registry()
        self.assertEqual(registry["runtimeTrustStatus"], "trusted-local-host")
        self.assertNotIn("runtimeAuthorities", registry)
        self.assertEqual(len(registry["evaluations"]), 6)
        self.assertEqual(registry["methods"][0]["methodId"], METHOD)
        self.assertEqual(sha256_text_file(GOVERNANCE.ROOT / "docs/contracts/translation-governance-reference.v3.json"),
                         "7b6f04c9954a67dda51f049a1f0fc584cbb495df10f4eaddd7708110c0191906")
        self.assertEqual(sha256_text_file(GOVERNANCE.ROOT / "compliance/policy-binding.v4.json"),
                         "8de2dbe3c1700dc20532507a6b75f64344d23111d4737cd265c237eae0d00a54")

    def test_unsigned_metadata_is_not_claimed_to_resist_a_malicious_editor(self):
        # Consistently editing both local copies is outside the trust model.
        # This explicitly prevents tests/docs claiming cryptographic authenticity.
        value = self.provenance()
        value["execution"]["worker"]["observed"]["sessionId"] = "edited"
        value["execution"]["binding"]["sessionId"] = "edited"
        self.assertEqual(GOVERNANCE.validate_execution(value, "blind_translation"), [])


    def test_executable_request_capture_bind_path_and_output_boundary(self):
        runtime = GOVERNANCE.ROOT / ".runtime"
        runtime.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="issue-78-test-", dir=runtime) as directory:
            target = Path(directory)
            def run(*arguments):
                return subprocess.run([sys.executable, str(GOVERNANCE.ROOT / "scripts/host_runtime.py"),
                                       *map(str, arguments)], capture_output=True, text=True)
            launches = {}
            for kind, session in (("codex-task", "task"), ("codex-worker", "worker")):
                request = target / (session + "-request.json")
                command = ("request", "--kind", kind, "--method-id", METHOD, "--model", "gpt-5.6-sol",
                           "--reasoning", "xhigh", "--output", request)
                self.assertEqual(run(*command).returncode, 0)
                self.assertNotEqual(run(*command).returncode, 0)  # immutable local capture
                capture = target / (session + "-launch.json")
                result = run("capture-launch", "--kind", kind, "--method-id", METHOD, "--request", request,
                             "--session-log", self.log(session=session), "--session-id", session,
                             "--turn-id", "turn", "--output", capture)
                self.assertEqual(result.returncode, 0, result.stdout)
                launches[session] = capture
                self.assertNotIn("synthetic private", capture.read_text())
            value = self.provenance()
            value.pop("execution")
            provenance = target / "provenance.json"
            provenance.write_bytes(canonical_json(value))
            output = target / "execution.json"
            result = run("bind", "--method-id", METHOD, "--stage", "blind_translation",
                         "--provenance", provenance, "--task-launch", launches["task"],
                         "--worker-launch", launches["worker"], "--output", output)
            self.assertEqual(result.returncode, 0, result.stdout)
            value["execution"] = GOVERNANCE.read_json(output)
            self.assertEqual(GOVERNANCE.validate_execution(value, "blind_translation"), [])
            outside = self.root / "not-runtime.json"
            self.assertNotEqual(run("request", "--kind", "codex-task", "--method-id", METHOD,
                                    "--model", "gpt-5.6-sol", "--reasoning", "xhigh", "--output", outside).returncode, 0)
            self.assertFalse(outside.exists())
            self.assertNotEqual(run("request", "--kind", "codex-worker", "--method-id", METHOD,
                                    "--model", "gpt-5.6-sol", "--output", target / "missing.json").returncode, 0)

    def test_current_registry_keeps_history_and_requires_reviewed_successor(self):
        import shutil
        root = self.root / "governance"
        (root / "profiles").mkdir(parents=True)
        (root / "compliance/execution-evaluations").mkdir(parents=True)
        original = GOVERNANCE.load_active_registry()
        for ref in original["evaluations"]:
            shutil.copyfile(GOVERNANCE.ROOT / ref["path"], root / ref["path"])
        for name in ("execution-methods.v1.json", "execution-methods.v2.json"):
            shutil.copyfile(GOVERNANCE.ROOT / "profiles" / name, root / "profiles" / name)
        future = copy.deepcopy(original)
        future["registryVersion"] = "3.0.0"
        future["supersedes"] = {"path": "profiles/execution-methods.v2.json",
                                "sha256": sha256_text_file(root / "profiles/execution-methods.v2.json")}
        decision = GOVERNANCE.read_json(root / original["evaluations"][-1]["path"])
        decision.update(recordId="execution-decision-0007", methodId="future-reviewed", supersedes=[])
        decision["configuration"].update(model="future-model", reasoning="future-reviewed-level")
        decision["stages"] = ["name_inventory"]
        path = root / "compliance/execution-evaluations/execution-decision-0007.v1.json"
        path.write_bytes(canonical_json(decision))
        future["evaluations"].append({"recordId": decision["recordId"], "path": path.relative_to(root).as_posix(), "sha256": sha256_text_file(path)})
        future["methods"].append({"methodId": decision["methodId"], "configuration": decision["configuration"],
                                  "stages": decision["stages"], "decisionId": decision["recordId"]})
        self.assertEqual(GOVERNANCE.validate_registry(future, root), [])
        with mock.patch.object(GOVERNANCE, "load_active_registry", return_value=future):
            self.assertEqual(HOST.configuration_for("future-reviewed"), decision["configuration"])
        future["evaluations"].pop(0)
        self.assertTrue(GOVERNANCE.validate_registry(future, root))


if __name__ == "__main__":
    unittest.main()

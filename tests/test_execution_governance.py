"""Synthetic authentication tests; ephemeral keys never enroll production trust."""

import copy
import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from test_translation_workflow import (
    MODULE as WORKFLOW, FIXTURE_MANIFEST, FIXTURE_SOURCE,
    assignment_issue, complete_autonomous_stages,
)
import execution_governance as GOVERNANCE
from public_boundary import canonical_json, sha256_text_file


class ExecutionGovernanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix="isabah-runtime-tests-")
        cls.root = Path(cls.directory.name)
        cls.key = cls.root / "ephemeral-test-key"
        executable = shutil.which("ssh-keygen")
        if not executable:
            raise RuntimeError("OpenSSH ssh-keygen is required for runtime signature tests")
        subprocess.run([executable, "-q", "-t", "ed25519", "-N", "", "-f", str(cls.key)],
                       check=True, capture_output=True)
        cls.public_key = " ".join(cls.key.with_suffix(".pub").read_text().split()[:2])
        cls.registry = GOVERNANCE.read_json(GOVERNANCE.REGISTRY_PATH)
        cls.registry["runtimeAuthorities"] = [{
            "authorityId": "synthetic-runtime", "publicKey": cls.public_key,
            "decisionId": "execution-decision-0006",
            "methodIds": [cls.registry["methods"][0]["methodId"]],
        }]
        cls.registry["runtimeTrustStatus"] = "enrolled"
        cls.registry_path = cls.root / "synthetic-registry.json"
        cls.registry_path.write_bytes(canonical_json(cls.registry))

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def setUp(self):
        # Inject only the trusted registry source, not signature/admission logic.
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(GOVERNANCE, "load_active_registry", return_value=copy.deepcopy(self.registry)).start()
        mock.patch.object(GOVERNANCE, "REGISTRY_PATH", self.registry_path).start()

    def sign(self, payload):
        result = subprocess.run(
            [shutil.which("ssh-keygen"), "-Y", "sign", "-f", str(self.key),
             "-n", GOVERNANCE.SIGNATURE_NAMESPACE],
            input=canonical_json(payload), capture_output=True, check=True,
        )
        return result.stdout.decode("ascii").replace("\r\n", "\n")

    def attest(self, provenance, stage):
        method = self.registry["methods"][0]
        payload = {
            "schemaVersion": "1.0.0", "authorityId": "synthetic-runtime",
            "methodId": method["methodId"], "registrySha256": sha256_text_file(self.registry_path),
            "stage": stage, "configuration": copy.deepcopy(method["configuration"]),
            "runId": provenance["runId"], "sessionId": "synthetic-session-" + provenance["runId"],
            "checkpointSha256": provenance["fingerprint"],
            "inputSha256": provenance["inputSha256"], "outputSha256": provenance["outputSha256"],
            "telemetrySha256": "a" * 64, "issuedAt": "2026-08-30T12:00:00Z",
            "independentContext": {"freshContext": True, "priorStageContextExcluded": True},
        }
        provenance["execution"] = {
            "methodId": method["methodId"], "registrySha256": payload["registrySha256"],
            "requested": copy.deepcopy(method["configuration"]),
            "attestation": {"payload": payload, "signature": self.sign(payload)},
        }

    def provenance(self, stage="blind_translation"):
        value = {"runId": "synthetic-run", "model": "gpt-5.6-sol", "reasoning": "xhigh",
                 "fingerprint": "1" * 64, "inputSha256": "2" * 64,
                 "outputSha256": "3" * 64, "origin": "direct_execution"}
        self.attest(value, stage)
        return value

    def test_exact_approved_method_passes_every_stage_with_real_signature(self):
        for stage in GOVERNANCE.STAGES:
            with self.subTest(stage=stage):
                self.assertEqual(GOVERNANCE.validate_execution(self.provenance(stage), stage), [])

    def test_unapproved_high_ultra_unknown_and_inherited_settings_fail(self):
        cases = [
            lambda e: e["requested"].update(reasoning="high"),
            lambda e: e["requested"].update(reasoning="ultra"),
            lambda e: e["requested"].update(orchestration="codex-ultra"),
            lambda e: e.update(methodId="unknown-method"),
            lambda e: e["requested"].update(configurationOrigin="inherited"),
            lambda e: e["requested"].pop("reasoning"),
            lambda e: e["requested"].pop("model"),
            lambda e: e["requested"].update(model="gpt-5.6"),
            lambda e: e["requested"].update(provider="unknown-provider"),
        ]
        for change in cases:
            value = self.provenance()
            change(value["execution"])
            self.assertTrue(GOVERNANCE.validate_execution(value, "blind_translation"))

    def test_missing_attestation_and_worker_self_report_fail(self):
        value = self.provenance()
        value["execution"].pop("attestation")
        self.assertTrue(GOVERNANCE.validate_execution(value, "blind_translation"))
        value.pop("execution")
        self.assertIn("execution: trusted runtime attestation is required",
                      GOVERNANCE.validate_execution(value, "blind_translation"))

    def test_historical_rebinding_is_not_a_new_approved_execution(self):
        for origin in ("legacy_migration", "deterministic_rebinding"):
            value = self.provenance()
            value["origin"] = origin
            self.assertIn("execution: historical rebinding is not a new approved execution",
                          GOVERNANCE.validate_execution(value, "blind_translation"))

    def test_signed_effective_high_cannot_be_labeled_xhigh(self):
        value = self.provenance()
        payload = value["execution"]["attestation"]["payload"]
        payload["configuration"]["reasoning"] = "high"
        value["execution"]["attestation"]["signature"] = self.sign(payload)
        errors = GOVERNANCE.validate_execution(value, "blind_translation")
        self.assertIn("execution: runtime telemetry and worker provenance disagree", errors)

    def test_run_checkpoint_session_and_signature_tampering_fail(self):
        for field in ("runId", "sessionId", "checkpointSha256", "inputSha256", "outputSha256", "telemetrySha256"):
            value = self.provenance()
            payload = value["execution"]["attestation"]["payload"]
            payload[field] = "f" * 64
            self.assertTrue(GOVERNANCE.validate_execution(value, "blind_translation"), field)
        value = self.provenance()
        value["execution"]["attestation"]["signature"] = "-----BEGIN SSH SIGNATURE-----\nAAAA\n-----END SSH SIGNATURE-----\n"
        self.assertTrue(GOVERNANCE.validate_execution(value, "blind_translation"))

    def test_unenrolled_key_and_missing_verifier_fail_closed(self):
        value = self.provenance()
        registry = copy.deepcopy(self.registry)
        registry["runtimeAuthorities"] = []
        with mock.patch.object(GOVERNANCE, "load_active_registry", return_value=registry):
            self.assertTrue(GOVERNANCE.validate_execution(value, "blind_translation"))
        with mock.patch.object(GOVERNANCE.shutil, "which", return_value=None):
            self.assertTrue(GOVERNANCE.validate_execution(value, "blind_translation"))

    def test_stage_scope_and_context_separation_are_not_inferred(self):
        value = self.provenance("independent_critique")
        payload = value["execution"]["attestation"]["payload"]
        payload["independentContext"]["freshContext"] = False
        value["execution"]["attestation"]["signature"] = self.sign(payload)
        self.assertTrue(GOVERNANCE.validate_execution(value, "independent_critique"))
        registry = copy.deepcopy(self.registry)
        registry["methods"][0]["stages"] = ["blind_translation"]
        with mock.patch.object(GOVERNANCE, "load_active_registry", return_value=registry):
            self.assertTrue(GOVERNANCE.validate_execution(self.provenance("adjudication"), "adjudication"))

    def test_full_packet_readiness_really_uses_runtime_gate(self):
        issue = assignment_issue()
        packet = WORKFLOW.build_packet(issue, WORKFLOW.parse_claims([issue]), FIXTURE_SOURCE,
                                       FIXTURE_MANIFEST, WORKFLOW.DEFAULT_POLICY)
        complete_autonomous_stages(packet)
        fields = dict(zip(GOVERNANCE.STAGES, (
            "blindTranslation", "independentCritique", "witnessResolution", "adjudication", "names")))
        for entry in packet["entries"]:
            for owner in [entry, *entry["precedingTranslations"]]:
                for stage, field in fields.items():
                    self.attest(owner[field]["provenance"], stage)
        packet["formulaInventory"], errors = WORKFLOW.formula_inventory(packet)
        self.assertEqual(errors, [])
        packet["reviewPresentation"] = {"status": "ready", "path": "review.md", "sha256": "a" * 64}
        packet["machineReadiness"].update(status="ready", validatedAt="2026-08-30T12:00:00Z")
        packet["reviewPresentation"]["sha256"] = WORKFLOW.text_sha256(WORKFLOW.render_review(packet))
        self.assertEqual(WORKFLOW.validate_packet(packet, machine_ready=True), [])
        packet["entries"][0]["blindTranslation"]["provenance"]["execution"] = None
        self.assertIn("execution: trusted runtime attestation is required",
                      WORKFLOW.validate_packet(packet, machine_ready=True))
        packet["entries"][0]["independentCritique"]["provenance"]["execution"] = {"attestation": None}
        self.assertTrue(WORKFLOW.validate_packet(packet, machine_ready=True))

    def test_shard_merge_rejects_unattested_outputs_without_writing(self):
        issue = assignment_issue()
        packet = WORKFLOW.build_packet(issue, WORKFLOW.parse_claims([issue]), FIXTURE_SOURCE,
                                       FIXTURE_MANIFEST, WORKFLOW.DEFAULT_POLICY)
        completed = copy.deepcopy(packet)
        complete_autonomous_stages(completed)
        fields = ("sourceOrdinal", "sourceUnitId", "blindTranslation", "independentCritique",
                  "witnessResolution", "adjudication", "names", "unresolved", "humanReview")
        shard = {"schemaVersion": "2.0.0", "packetId": packet["packetId"],
                 "issueNumber": 25, "startUnit": 1, "endUnit": 2,
                 "entries": [{field: entry[field] for field in fields} for entry in completed["entries"]]}
        with tempfile.TemporaryDirectory() as directory:
            packet_path = Path(directory) / "packet.json"
            shard_path = Path(directory) / "shard.json"
            packet_path.write_bytes(WORKFLOW.json_bytes(packet))
            shard_path.write_bytes(WORKFLOW.json_bytes(shard))
            before = packet_path.read_bytes()
            with self.assertRaisesRegex(WORKFLOW.WorkflowError, "trusted runtime attestation"):
                WORKFLOW.merge_entry_shard(packet_path, shard_path)
            self.assertEqual(packet_path.read_bytes(), before)

    def test_signature_namespace_cannot_be_replayed_from_another_protocol(self):
        value = self.provenance()
        payload = value["execution"]["attestation"]["payload"]
        result = subprocess.run([shutil.which("ssh-keygen"), "-Y", "sign", "-f", str(self.key),
                                 "-n", "another-protocol"], input=canonical_json(payload),
                                capture_output=True, check=True)
        value["execution"]["attestation"]["signature"] = result.stdout.decode("ascii")
        self.assertTrue(GOVERNANCE.validate_execution(value, "blind_translation"))


class ExecutionArtifactTests(unittest.TestCase):
    def test_embedded_packet_attestation_schema_matches_standalone_schema(self):
        packet_schema = GOVERNANCE.read_json(WORKFLOW.DEFAULT_PACKET_SCHEMA)
        standalone = GOVERNANCE.read_json(GOVERNANCE.ATTESTATION_SCHEMA)
        standalone.pop("$schema")
        standalone.pop("title")
        self.assertEqual(packet_schema["$defs"]["execution"], standalone)

    def test_real_initial_registry_is_valid_but_no_signer_is_fabricated(self):
        self.assertEqual(GOVERNANCE.validate(), [])
        registry = GOVERNANCE.load_active_registry()
        self.assertEqual(registry["runtimeAuthorities"], [])
        self.assertEqual(registry["runtimeTrustStatus"], "unprovisioned")
        self.assertEqual(len(registry["methods"]), 1)
        self.assertEqual(registry["methods"][0]["configuration"]["reasoning"], "xhigh")
        changed = copy.deepcopy(registry)
        changed["methods"][0]["configuration"]["reasoning"] = "high"
        self.assertIn("execution: initial registry is immutable; add a successor version",
                      GOVERNANCE.validate_registry(changed))

    def test_initial_decisions_do_not_invent_quality_evidence(self):
        records = [GOVERNANCE.read_json(GOVERNANCE.ROOT / ref["path"])
                   for ref in GOVERNANCE.load_active_registry()["evaluations"]]
        self.assertEqual([record["status"] for record in records],
                         ["approved", "unevaluated", "unevaluated", "rejected", "rejected"])
        for record in records:
            self.assertFalse(record["evaluation"]["blindedComparison"]["performed"])
            self.assertTrue(all(value is None for value in record["measurements"].values()))
            self.assertTrue(record["limitations"])
        self.assertIsNone(records[2]["configuration"]["reasoning"])

    def test_evaluation_artifacts_must_not_be_filesystem_links(self):
        registry = GOVERNANCE.load_active_registry()
        with mock.patch.object(Path, "is_symlink", return_value=True):
            self.assertIn("execution: evaluation hash mismatch",
                          GOVERNANCE.validate_registry(registry))

    def test_public_schema_and_boundary_reject_private_evidence_and_traces(self):
        path = GOVERNANCE.EVALUATION_ROOT / "execution-decision-0001.v1.json"
        record = GOVERNANCE.read_json(path)
        for key in ("arabicSample", "englishSample", "rawTrace", "chainOfThought", "privatePath", "credentials", "witnessPassage"):
            changed = copy.deepcopy(record)
            changed[key] = "synthetic forbidden data"
            self.assertTrue(GOVERNANCE.validate_evaluation(changed), key)
        for value in ("C:" + "\\" + "private\\file", "https://example.invalid/private",
                      "ghp_" + "9" * 30, "<think>synthetic</think>", "نص تجريبي"):
            changed = copy.deepcopy(record)
            changed["limitations"] = [value]
            errors = GOVERNANCE.validate_evaluation(changed)
            self.assertTrue(errors)
            self.assertNotIn(value, "\n".join(errors))

    def test_future_method_requires_new_reviewed_record_and_registry_lineage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "profiles").mkdir()
            (root / "compliance/execution-evaluations").mkdir(parents=True)
            original = GOVERNANCE.read_json(GOVERNANCE.REGISTRY_PATH)
            for ref in original["evaluations"]:
                shutil.copyfile(GOVERNANCE.ROOT / ref["path"], root / ref["path"])
            previous = root / "profiles/execution-methods.v1.json"
            previous.write_bytes(canonical_json(original))
            future = copy.deepcopy(original)
            future["registryVersion"] = "2.0.0"
            future["supersedes"] = {"path": "profiles/execution-methods.v1.json", "sha256": sha256_text_file(previous)}
            decision = GOVERNANCE.read_json(root / original["evaluations"][0]["path"])
            decision.update(recordId="execution-decision-0006", methodId="future-reviewed-method")
            decision["configuration"].update(provider="future-provider", model="future-model", reasoning="reviewed-setting")
            decision["stages"] = ["name_inventory"]
            decision["supersedes"] = []
            path = root / "compliance/execution-evaluations/execution-decision-0006.v1.json"
            path.write_bytes(canonical_json(decision))
            future["evaluations"].append({"recordId": decision["recordId"], "path": path.relative_to(root).as_posix(), "sha256": sha256_text_file(path)})
            future["methods"].append({"methodId": decision["methodId"], "configuration": decision["configuration"], "stages": decision["stages"], "decisionId": decision["recordId"]})
            self.assertEqual(GOVERNANCE.validate_registry(future, root), [])
            removed = copy.deepcopy(future)
            removed["evaluations"].pop(1)
            self.assertIn("execution: evaluation history must be append-only", GOVERNANCE.validate_registry(removed, root))
            altered = copy.deepcopy(future)
            altered["methods"][-1]["configuration"]["reasoning"] = "unreviewed"
            self.assertTrue(GOVERNANCE.validate_registry(altered, root))

            # An authenticated enrollment is a separate reviewed decision,
            # not permission to attach a worker-selected key to the baseline.
            enrolled = copy.deepcopy(future)
            enrolled["runtimeTrustStatus"] = "enrolled"
            enrolled["runtimeAuthorities"] = [{
                "authorityId": "future-runtime", "publicKey": "ssh-ed25519 AAAA",
                "methodIds": [original["methods"][0]["methodId"]],
                "decisionId": "execution-decision-0001",
            }]
            self.assertIn("execution: runtime authority lacks reviewed admission",
                          GOVERNANCE.validate_registry(enrolled, root))

            key_path = root / "ephemeral-enrollment-test-key"
            subprocess.run([shutil.which("ssh-keygen"), "-q", "-t", "ed25519", "-N", "",
                            "-f", str(key_path)], check=True, capture_output=True)
            public_key = " ".join(key_path.with_suffix(".pub").read_text().split()[:2])
            admission = GOVERNANCE.read_json(root / original["evaluations"][0]["path"])
            admission.update(recordId="execution-decision-0008", runtimeAuthority={
                "authorityId": "future-runtime",
                "publicKeySha256": hashlib.sha256(public_key.encode("ascii")).hexdigest(),
            })
            admission_path = root / "compliance/execution-evaluations/execution-decision-0008.v1.json"
            admission_path.write_bytes(canonical_json(admission))
            enrolled["evaluations"].append({"recordId": admission["recordId"],
                                          "path": admission_path.relative_to(root).as_posix(),
                                          "sha256": sha256_text_file(admission_path)})
            enrolled["runtimeAuthorities"][0].update(publicKey=public_key, decisionId=admission["recordId"])
            self.assertEqual(GOVERNANCE.validate_registry(enrolled, root), [])

            wrong_key = copy.deepcopy(enrolled)
            wrong_key["runtimeAuthorities"][0]["publicKey"] = "ssh-ed25519 AAAA"
            self.assertTrue(GOVERNANCE.validate_registry(wrong_key, root))

            successor = copy.deepcopy(decision)
            successor.update(recordId="execution-decision-0007", status="superseded")
            successor["supersedes"] = [original["evaluations"][0]]
            supersession_path = root / "compliance/execution-evaluations/execution-decision-0007.v1.json"
            supersession_path.write_bytes(canonical_json(successor))
            retired = copy.deepcopy(future)
            retired["evaluations"].append({"recordId": successor["recordId"],
                                           "path": supersession_path.relative_to(root).as_posix(),
                                           "sha256": sha256_text_file(supersession_path)})
            self.assertIn("execution: active method lacks exact unsuperseded approval",
                          GOVERNANCE.validate_registry(retired, root))

    def test_historical_policy_references_and_packet_schema_remain_immutable(self):
        expected = {
            "compliance/policy-binding.v3.json": "cfdd5d5baab74a21930e549cc4418574decc07e20e84bf6438e0b9527e360a0b",
            "docs/contracts/translation-governance-reference.v2.json": "7d73170d384f417733134e5ca09263ba73c92e941c5590d534d9eb38ec6704ae",
        }
        for path, digest in expected.items():
            self.assertEqual(sha256_text_file(GOVERNANCE.ROOT / path), digest)
        old = GOVERNANCE.read_json(GOVERNANCE.ROOT / "schemas/translation-work-packet.v1.schema.json")
        self.assertEqual(old["properties"]["schemaVersion"]["const"], "1.5.0")
        self.assertNotIn("execution", old["$defs"]["stageProvenance"]["properties"])


if __name__ == "__main__":
    unittest.main()

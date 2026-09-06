#!/usr/bin/env python3
"""Fail-closed method admission, with immutable signed-history validation.

Current execution uses unsigned trusted-host metadata; historical signature
verification is retained explicitly, never used as a new production gate.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

from schema_validation import validate_schema_instance
from public_boundary import TOKEN_SHAPES, canonical_json, sha256_text_file

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "profiles/execution-methods.v2.json"
POLICY_PATH = ROOT / "compliance/policy-binding.v6.json"
EVALUATION_ROOT = ROOT / "compliance/execution-evaluations"
REGISTRY_SCHEMA = ROOT / "schemas/execution-method-registry.v1.schema.json"
EVALUATION_SCHEMA = ROOT / "schemas/execution-evaluation.v1.schema.json"
ATTESTATION_SCHEMA = ROOT / "schemas/runtime-attestation.v1.schema.json"
SIGNATURE_NAMESPACE = "al-isabah-runtime-v1"
INITIAL_REGISTRY_CONTENT_SHA256 = "c6623c840dc915fa5158e2889f403c734720b38c6dcdbb0351e8dc1955a874f4"
STAGES = (
    "blind_translation", "independent_critique", "witness_resolution",
    "adjudication", "name_inventory",
)


def parse_json(text: str) -> Any:
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result
    def reject_constant(_value):
        raise ValueError("non-finite JSON number")
    return json.loads(text, object_pairs_hook=unique_pairs,
                      parse_constant=reject_constant)


def read_json(path: Path) -> Any:
    return parse_json(path.read_text(encoding="utf-8"))


def schema_errors(value: Any, path: Path) -> list[str]:
    # Do not echo rejected keys or values (which may themselves be secrets).
    return ["execution: schema mismatch"] if validate_schema_instance(
        value, read_json(path)
    ) else []


def regular_artifact(root: Path, relative: str) -> Path | None:
    path = root / relative
    if not path.resolve().is_relative_to(root.resolve()):
        return None
    current = path
    while current != root:
        if current.is_symlink():
            return None
        current = current.parent
    return path if path.is_file() else None


def public_errors(value: Any) -> list[str]:
    """Governance has its own closed schema, not the book-output allowlist.

    Model/configuration identifiers and aggregate metrics are legitimate here;
    samples, raw traces, arbitrary evidence fields, and private locators are not.
    Schema checks are also required: this scan alone is not an admission gate.
    """
    errors = []
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = re.sub(r"[^a-z]", "", key.casefold())
            if any(word in normalized for word in (
                "sample", "excerpt", "rawtrace", "chainofthought", "credential",
                "password", "privatepath", "objectkey", "transcript", "prompttext",
                "responsetext", "witnesspassage", "secret",
            )):
                errors.append("execution: prohibited public field")
            errors.extend(public_errors(child))
    elif isinstance(value, list):
        for child in value:
            errors.extend(public_errors(child))
    elif isinstance(value, str):
        if re.search(r"[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff\ufb50-\ufdff\ufe70-\ufeff]|[A-Za-z]:[\\/]|\\\\|(?:^|\s)/[A-Za-z]|\.\.[/\\]", value):
            errors.append("execution: private locator or source expression")
        if re.search(r"https?://|s3://|file://|-----BEGIN (?:OPENSSH |RSA |EC )?PRIVATE KEY|<think>|analysis\s*:|chain.of.thought|raw model trace", value, re.I):
            errors.append("execution: non-public evidence or locator")
        if any(pattern.search(value) for pattern in TOKEN_SHAPES) or re.search(r"\bsk-[A-Za-z0-9_-]{16,}", value):
            errors.append("execution: token-shaped secret")
    return errors


def validate_evaluation(record: Any) -> list[str]:
    errors = schema_errors(record, EVALUATION_SCHEMA) + public_errors(record)
    if errors:
        return errors
    try:
        date.fromisoformat(record["recordedOn"])
    except ValueError:
        errors.append("execution: invalid decision date")
    if str(record["configuration"]["reasoning"]).casefold() == "ultra":
        errors.append("execution: orchestration label is not a reasoning level")
    evaluation = record["evaluation"]
    if evaluation["kind"] == "controlled-comparison":
        if any(value is None for value in record["inputHashes"].values()):
            errors.append("execution: controlled comparison requires exact input hashes")
        if not evaluation["blindedComparison"]["performed"] or not evaluation["blindedComparison"]["evidenceSha256"]:
            errors.append("execution: controlled comparison requires blinded evidence")
    elif evaluation["blindedComparison"]["performed"]:
        errors.append("execution: non-comparison must not claim blinded evidence")
    if record["status"] == "superseded" and not record["supersedes"]:
        errors.append("execution: supersession requires a predecessor")
    return errors


def validate_registry(registry: Any, root: Path = ROOT, seen: frozenset[str] = frozenset()) -> list[str]:
    schema = REGISTRY_SCHEMA
    if isinstance(registry, dict) and registry.get("schema") == "al-isabah.execution-method-registry.v2":
        schema = ROOT / "schemas/execution-method-registry.v2.schema.json"
    errors = schema_errors(registry, schema) + public_errors(registry)
    if errors:
        return errors
    if registry["registryVersion"] == "1.0.0" and hashlib.sha256(canonical_json(registry)).hexdigest() != INITIAL_REGISTRY_CONTENT_SHA256:
        errors.append("execution: initial registry is immutable; add a successor version")
    records = {}
    references = {}
    for reference in registry["evaluations"]:
        record_id = reference["recordId"]
        if record_id in references:
            errors.append("execution: duplicate evaluation identity")
        references[record_id] = reference
        path = regular_artifact(root, reference["path"])
        if path is None or sha256_text_file(path) != reference["sha256"]:
            errors.append("execution: evaluation hash mismatch")
            continue
        record = read_json(path)
        record_errors = validate_evaluation(record)
        errors.extend(record_errors)
        if not record_errors:
            if record["recordId"] != record_id:
                errors.append("execution: evaluation identity mismatch")
            records[record_id] = record
    superseded = set()
    for record_id, record in records.items():
        for previous in record["supersedes"]:
            if previous != references.get(previous["recordId"]) or previous["recordId"] == record_id:
                errors.append("execution: invalid decision supersession binding")
            elif records.get(previous["recordId"], {}).get("recordedOn", "") > record["recordedOn"]:
                errors.append("execution: supersession predates its predecessor")
            superseded.add(previous["recordId"])
    # Acyclic lineage prevents mutually superseding records from looking final.
    def visit(record_id, ancestors):
        if record_id in ancestors:
            return False
        return all(visit(item["recordId"], ancestors | {record_id})
                   for item in records.get(record_id, {}).get("supersedes", []))
    if not all(visit(record_id, set()) for record_id in records):
        errors.append("execution: cyclic decision supersession")
    method_ids = set()
    covered = set()
    for method in registry["methods"]:
        if method["methodId"] in method_ids:
            errors.append("execution: duplicate method identity")
        method_ids.add(method["methodId"])
        covered.update(method["stages"])
        decision = records.get(method["decisionId"], {})
        if (decision.get("status") != "approved" or method["decisionId"] in superseded
                or decision.get("methodId") != method["methodId"]
                or decision.get("configuration") != method["configuration"]
                or not set(method["stages"]).issubset(decision.get("stages", []))):
            errors.append("execution: active method lacks exact unsuperseded approval")
    if covered != set(STAGES):
        errors.append("execution: every semantic stage needs explicit method coverage")
    authorities = set()
    for authority in registry.get("runtimeAuthorities", []):
        try:
            key_bytes = base64.b64decode(authority["publicKey"].split()[1], validate=True)
            if len(key_bytes) != 51 or not key_bytes.startswith(b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20"):
                errors.append("execution: invalid Ed25519 public key encoding")
        except (ValueError, IndexError, binascii.Error):
            errors.append("execution: invalid Ed25519 public key encoding")
        if authority["authorityId"] in authorities:
            errors.append("execution: duplicate runtime authority")
        authorities.add(authority["authorityId"])
        decision = records.get(authority["decisionId"], {})
        if (decision.get("status") != "approved" or authority["decisionId"] in superseded
                or not set(authority["methodIds"]).issubset(method_ids)
                or decision.get("runtimeAuthority") != {
                    "authorityId": authority["authorityId"],
                    "publicKeySha256": hashlib.sha256(authority["publicKey"].encode("ascii")).hexdigest(),
                }):
            errors.append("execution: runtime authority lacks reviewed admission")
    if registry["runtimeTrustStatus"] == "trusted-local-host":
        decision = records.get(registry["trustDecisionId"], {})
        if decision.get("status") != "approved" or registry["trustDecisionId"] in superseded:
            errors.append("execution: host trust lacks an unsuperseded reviewed decision")
    elif (registry["runtimeTrustStatus"] == "enrolled") != bool(authorities):
        errors.append("execution: runtime trust status is inconsistent")
    previous = registry["supersedes"]
    if previous:
        if previous["path"] in seen:
            return errors + ["execution: cyclic registry lineage"]
        path = regular_artifact(root, previous["path"])
        if path is None or sha256_text_file(path) != previous["sha256"]:
            return errors + ["execution: predecessor registry hash mismatch"]
        old = read_json(path)
        errors.extend(validate_registry(old, root, seen | {previous["path"]}))
        if int(registry["registryVersion"].split(".")[0]) != int(old["registryVersion"].split(".")[0]) + 1:
            errors.append("execution: registry revision must advance exactly one version")
        if any(reference not in registry["evaluations"] for reference in old["evaluations"]):
            errors.append("execution: evaluation history must be append-only")
    elif registry["registryVersion"] != "1.0.0":
        errors.append("execution: later registry requires a predecessor")
    return errors


def load_active_registry() -> dict[str, Any]:
    policy = read_json(POLICY_PATH)
    bindings = [item for item in policy["contracts"] if item["id"] == "execution-method-registry"]
    if len(bindings) != 1 or bindings[0]["path"] != REGISTRY_PATH.relative_to(ROOT).as_posix() or bindings[0]["sha256"] != sha256_text_file(REGISTRY_PATH):
        raise ValueError("execution: active registry is not policy-bound")
    registry = read_json(REGISTRY_PATH)
    if validate_registry(registry):
        raise ValueError("execution: active registry is invalid")
    return registry


def verify_signature(payload: dict[str, Any], signature: str, public_key: str) -> bool:
    executable = shutil.which("ssh-keygen")
    if not executable:
        return False
    # OpenSSH's namespace prevents reuse of a signature from another protocol.
    try:
        with tempfile.TemporaryDirectory(prefix="al-isabah-attestation-") as directory:
            root = Path(directory)
            signers = root / "allowed-signers"
            receipt = root / "receipt.sig"
            signers.write_text(f"{payload['authorityId']} {public_key}\n", encoding="utf-8")
            receipt.write_text(signature, encoding="ascii")
            result = subprocess.run(
                [executable, "-Y", "verify", "-f", str(signers), "-I", payload["authorityId"],
                 "-n", SIGNATURE_NAMESPACE, "-s", str(receipt)],
                input=canonical_json(payload), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=10, check=False,
            )
            return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def validate_signed_execution(provenance: dict[str, Any], stage: str) -> list[str]:
    """Historical verifier; callers must supply the original pinned registry."""
    execution = provenance.get("execution")
    if not isinstance(execution, dict):
        return ["execution: trusted runtime attestation is required"]
    errors = schema_errors(execution, ATTESTATION_SCHEMA)
    if errors:
        return errors
    try:
        registry = load_active_registry()
    except (OSError, ValueError, KeyError):
        return ["execution: active registry is unavailable or invalid"]
    methods = [method for method in registry["methods"]
               if method["methodId"] == execution["methodId"] and stage in method["stages"]]
    if len(methods) != 1:
        return ["execution: method is not active for this semantic stage"]
    method = methods[0]
    registry_hash = sha256_text_file(REGISTRY_PATH)
    payload = execution["attestation"]["payload"]
    if execution["registrySha256"] != registry_hash or payload["registrySha256"] != registry_hash:
        errors.append("execution: registry binding mismatch")
    if execution["requested"] != method["configuration"] or payload["configuration"] != method["configuration"]:
        errors.append("execution: requested or effective configuration is unapproved")
    if payload["configuration"]["model"] != provenance.get("model") or payload["configuration"]["reasoning"] != provenance.get("reasoning"):
        errors.append("execution: runtime telemetry and worker provenance disagree")
    if payload["methodId"] != method["methodId"] or payload["stage"] != stage:
        errors.append("execution: stage or method attestation mismatch")
    for attested, field in (("runId", "runId"), ("checkpointSha256", "fingerprint"),
                            ("inputSha256", "inputSha256"), ("outputSha256", "outputSha256")):
        if payload[attested] != provenance.get(field):
            errors.append("execution: run or checkpoint attestation mismatch")
    if provenance.get("origin") != "direct_execution":
        errors.append("execution: historical rebinding is not a new approved execution")
    if stage in {"independent_critique", "name_inventory"} and payload["independentContext"] != {"freshContext": True, "priorStageContextExcluded": True}:
        errors.append("execution: independent stage lacks trusted context separation")
    authorities = [authority for authority in registry["runtimeAuthorities"]
                   if authority["authorityId"] == payload["authorityId"]
                   and method["methodId"] in authority["methodIds"]]
    if len(authorities) != 1:
        errors.append("execution: runtime signer is not enrolled for this method")
    elif not errors and not verify_signature(payload, execution["attestation"]["signature"], authorities[0]["publicKey"]):
        errors.append("execution: runtime signature verification failed")
    return errors


def validate_execution(provenance: dict[str, Any], stage: str) -> list[str]:
    from host_runtime import validate_execution as validate_host_execution
    return validate_host_execution(provenance, stage)


def validate() -> list[str]:
    try:
        registry = load_active_registry()
        expected = {item["path"] for item in registry["evaluations"]}
        actual = {path.relative_to(ROOT).as_posix() for path in EVALUATION_ROOT.rglob("*") if path.is_file() and path != EVALUATION_ROOT / "README.md"}
        return [] if actual == expected else ["execution: unregistered public evaluation artifact"]
    except (OSError, ValueError, KeyError):
        return ["execution: governance artifact is unavailable or invalid"]


def main() -> int:
    errors = validate()
    if errors:
        print("\n".join(errors))
        return 1
    registry = load_active_registry()
    print(f"Execution governance valid; runtime trust: {registry['runtimeTrustStatus']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

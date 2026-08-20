#!/usr/bin/env python3
"""Portable, privacy-safe local-model evaluation utilities for Al-Isabah."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import random
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


class EvaluationError(RuntimeError):
    """Raised when an evaluation artifact violates the local protocol."""


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_RELATIVE = Path(".runtime/local-model-evaluation")
FORBIDDEN_NORMALIZED_FIELDS = {
    "accesstoken",
    "apikey",
    "chainofthought",
    "credential",
    "credentials",
    "objectlocator",
    "password",
    "privatepath",
    "rawlog",
    "reasoningtrace",
    "token",
}
POLICY_FIELDS = (
    "bindingPath",
    "bindingSha256",
    "evaluationProtocolPath",
    "evaluationProtocolSha256",
    "glossaryPath",
    "glossarySha256",
    "promptPath",
    "promptSha256",
)
CONFIG_FIELDS = (
    "schemaVersion",
    "configId",
    "role",
    "engine",
    "runtimeVersion",
    "model",
    "modelDigest",
    "artifactDisclosure",
    "quantization",
    "houseProfile",
    "nativeThinkingRequested",
    "nativeThinkingObserved",
    "contextTokens",
    "maxOutputTokens",
    "temperature",
    "samplingSeed",
    "promptVersion",
    "promptSha256",
)


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def artifact_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _without(value: dict[str, Any], field: str) -> dict[str, Any]:
    result = dict(value)
    result.pop(field, None)
    return result


def packet_id_for(packet: dict[str, Any]) -> str:
    return "eval-packet-" + artifact_sha256(_without(packet, "packetId"))[:16]


def run_id_for(run: dict[str, Any]) -> str:
    return "eval-run-" + artifact_sha256(_without(run, "runId"))[:16]


def review_packet_id_for(packet: dict[str, Any]) -> str:
    return "eval-review-packet-" + artifact_sha256(_without(packet, "reviewPacketId"))[:16]


def score_id_for(score: dict[str, Any]) -> str:
    return "eval-score-" + artifact_sha256(_without(score, "scoreId"))[:16]


def _allowlist(value: dict[str, Any], fields: tuple[str, ...], label: str) -> dict[str, Any]:
    try:
        return {field: value[field] for field in fields}
    except (KeyError, TypeError) as exc:
        raise EvaluationError(f"{label}: missing required field {exc}") from exc


def _normalized_field(key: Any) -> str:
    return "".join(character.lower() for character in str(key) if character.isalnum())


def _reject_forbidden_fields(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if _normalized_field(key) in FORBIDDEN_NORMALIZED_FIELDS:
                raise EvaluationError(f"{path}: forbidden field {key!r}")
            _reject_forbidden_fields(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_forbidden_fields(child, f"{path}[{index}]")


def validate_manifest_integrity(manifest: dict[str, Any]) -> None:
    cases = manifest.get("cases")
    if not isinstance(cases, list):
        raise EvaluationError("manifest cases must be an array")
    case_ids = [case.get("caseId") for case in cases if isinstance(case, dict)]
    source_ids = [case.get("sourceUnitId") for case in cases if isinstance(case, dict)]
    if len(case_ids) != len(cases):
        raise EvaluationError("manifest cases must contain objects")
    if len(set(case_ids)) != len(case_ids):
        raise EvaluationError("duplicate case ID")
    if len(set(source_ids)) != len(source_ids):
        raise EvaluationError("duplicate source unit ID")
    for case in cases:
        if case.get("arabicSha256") != sha256_text(case.get("arabic", "")):
            raise EvaluationError(f"{case.get('caseId')}: Arabic hash mismatch")
        if case.get("referenceSha256") != sha256_text(case.get("referenceEnglish", "")):
            raise EvaluationError(f"{case.get('caseId')}: reference hash mismatch")


def prepare_blind_packet(manifest: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    validate_manifest_integrity(manifest)
    cases = [
        {
            "caseId": case["caseId"],
            "sourceUnitId": case["sourceUnitId"],
            "category": case["category"],
            "arabic": case["arabic"],
            "arabicSha256": case["arabicSha256"],
            "heldOut": case["heldOut"],
        }
        for case in manifest["cases"]
    ]
    packet = {
        "schemaVersion": "1.0.0",
        "evaluationId": manifest["evaluationId"],
        "issue": manifest["issue"],
        "policy": _allowlist(manifest["policy"], POLICY_FIELDS, "policy"),
        "config": _allowlist(config, CONFIG_FIELDS, "config"),
        "configSha256": artifact_sha256(_allowlist(config, CONFIG_FIELDS, "config")),
        "cases": cases,
    }
    packet["packetId"] = packet_id_for(packet)
    return packet


def _validate_packet(packet: dict[str, Any]) -> None:
    _reject_forbidden_fields(packet)
    if packet.get("packetId") != packet_id_for(packet):
        raise EvaluationError("packet identity/hash mismatch")
    config = packet.get("config")
    if not isinstance(config, dict) or packet.get("configSha256") != artifact_sha256(config):
        raise EvaluationError("packet config hash mismatch")
    cases = packet.get("cases")
    if not isinstance(cases, list) or not cases:
        raise EvaluationError("packet cases must be a non-empty array")
    ids = []
    for case in cases:
        if not isinstance(case, dict):
            raise EvaluationError("packet cases must contain objects")
        ids.append(case.get("caseId"))
        if case.get("arabicSha256") != sha256_text(case.get("arabic", "")):
            raise EvaluationError(f"{case.get('caseId')}: packet Arabic hash mismatch")
    if len(ids) != len(set(ids)):
        raise EvaluationError("packet has duplicate case IDs")


def record_run(packet: dict[str, Any], outputs: list[dict[str, Any]], generated_at: str) -> dict[str, Any]:
    _validate_packet(packet)
    _reject_forbidden_fields(outputs)
    if not isinstance(outputs, list):
        raise EvaluationError("outputs must be an array")
    if not all(isinstance(output, dict) for output in outputs):
        raise EvaluationError("outputs must contain objects")
    expected = [case["caseId"] for case in packet["cases"]]
    observed = [output.get("caseId") for output in outputs]
    if observed != expected:
        raise EvaluationError("outputs must exactly cover packet cases in order")
    normalized = []
    expected_fields = {"caseId", "titleEnglish", "bodyEnglish", "issues"}
    for output in outputs:
        extras = set(output) - expected_fields
        if extras:
            raise EvaluationError(f"{output.get('caseId')}: unexpected output fields: {sorted(extras)}")
        title = output.get("titleEnglish")
        body = output.get("bodyEnglish")
        issues = output.get("issues")
        if not isinstance(title, str) or not title.strip():
            raise EvaluationError(f"{output.get('caseId')}: titleEnglish is required")
        if not isinstance(body, str) or not body.strip():
            raise EvaluationError(f"{output.get('caseId')}: bodyEnglish is required")
        if not isinstance(issues, list) or not all(isinstance(issue, str) for issue in issues):
            raise EvaluationError(f"{output.get('caseId')}: issues must be an array of strings")
        normalized.append(
            {
                "caseId": output["caseId"],
                "titleEnglish": title,
                "titleEnglishSha256": sha256_text(title),
                "bodyEnglish": body,
                "bodyEnglishSha256": sha256_text(body),
                "issues": issues,
            }
        )
    run = {
        "schemaVersion": "1.0.0",
        "packetId": packet["packetId"],
        "packetSha256": artifact_sha256(packet),
        "evaluationId": packet["evaluationId"],
        "issue": packet["issue"],
        "policy": packet["policy"],
        "policySha256": artifact_sha256(packet["policy"]),
        "config": packet["config"],
        "configSha256": packet["configSha256"],
        "generatedAt": generated_at,
        "outputs": normalized,
        "humanReview": {"status": "unreviewed"},
        "promotionStatus": "blocked",
    }
    run["runId"] = run_id_for(run)
    return run


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvaluationError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise EvaluationError(f"{path}: top level must be an object")
    return value


def _load_json_value(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvaluationError(f"cannot read JSON {path}: {exc}") from exc


def _schema_validator(root: Path):
    path = root / "scripts/translation_workflow.py"
    spec = importlib.util.spec_from_file_location("translation_workflow_for_evaluation", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.validate_schema_instance


def _schema_errors(value: Any, schema_name: str, root: Path = ROOT) -> list[str]:
    schema = _load_json(root / "schemas" / schema_name)
    return _schema_validator(root)(value, schema)


def validate_run_artifact(run: dict[str, Any], root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    try:
        _reject_forbidden_fields(run)
    except EvaluationError as exc:
        errors.append(str(exc))
    errors.extend(_schema_errors(run, "local-model-evaluation-run.v1.schema.json", root))
    if errors:
        return errors
    if run.get("runId") != run_id_for(run):
        errors.append("run identity/hash mismatch")
    if run.get("configSha256") != artifact_sha256(run["config"]):
        errors.append("config hash mismatch")
    if run.get("policySha256") != artifact_sha256(run["policy"]):
        errors.append("policy hash mismatch")
    case_ids = []
    for output in run["outputs"]:
        case_ids.append(output["caseId"])
        if output["titleEnglishSha256"] != sha256_text(output["titleEnglish"]):
            errors.append(f"{output['caseId']}: title hash mismatch")
        if output["bodyEnglishSha256"] != sha256_text(output["bodyEnglish"]):
            errors.append(f"{output['caseId']}: body hash mismatch")
    if len(case_ids) != len(set(case_ids)):
        errors.append("run has duplicate case IDs")
    return errors


def _validate_runs_for_cases(cases: list[dict[str, Any]], runs: list[dict[str, Any]]) -> None:
    if not isinstance(runs, list):
        raise EvaluationError("runs must be an array")
    if len(runs) < 2:
        raise EvaluationError("blind review requires at least two runs")
    if len(runs) > 26:
        raise EvaluationError("blind review supports at most 26 runs")
    if not all(isinstance(run, dict) for run in runs):
        raise EvaluationError("runs must contain objects")
    run_ids = [run.get("runId") for run in runs]
    if len(run_ids) != len(set(run_ids)):
        raise EvaluationError("duplicate run ID")
    expected = [case.get("caseId") for case in cases]
    expected_arabic = {case.get("caseId"): case.get("arabicSha256") or sha256_text(case.get("arabic", "")) for case in cases}
    evaluation_ids = set()
    issues = set()
    policy_hashes = set()
    for run in runs:
        outputs = run.get("outputs")
        if not isinstance(outputs, list):
            raise EvaluationError(f"{run.get('runId')}: outputs must be an array")
        observed = [output.get("caseId") for output in outputs if isinstance(output, dict)]
        if len(observed) != len(outputs) or observed != expected:
            raise EvaluationError(f"{run.get('runId')}: outputs must exactly cover cases in order")
        errors = validate_run_artifact(run)
        if errors:
            raise EvaluationError("run validation failed: " + "; ".join(errors))
        evaluation_ids.add(run["evaluationId"])
        issues.add(run["issue"])
        policy_hashes.add(run["policySha256"])
        for case_id in observed:
            if case_id not in expected_arabic:
                raise EvaluationError(f"{run['runId']}: unrelated case {case_id}")
    if len(evaluation_ids) != 1:
        raise EvaluationError("runs have inconsistent evaluation identity")
    if len(issues) != 1:
        raise EvaluationError("runs have inconsistent issue identity")
    if len(policy_hashes) != 1:
        raise EvaluationError("runs have inconsistent policy identity")


def validate_anonymization_inputs(manifest: dict[str, Any], runs: list[dict[str, Any]]) -> None:
    validate_manifest_integrity(manifest)
    _validate_runs_for_cases(manifest["cases"], runs)
    expected_policy = _allowlist(manifest["policy"], POLICY_FIELDS, "manifest policy")
    expected_policy_hash = artifact_sha256(expected_policy)
    for run in runs:
        if run.get("evaluationId") != manifest.get("evaluationId"):
            raise EvaluationError(f"{run.get('runId')}: evaluation identity does not match manifest")
        if run.get("issue") != manifest.get("issue"):
            raise EvaluationError(f"{run.get('runId')}: issue identity does not match manifest")
        if run.get("policy") != expected_policy or run.get("policySha256") != expected_policy_hash:
            raise EvaluationError(f"{run.get('runId')}: manifest policy identity mismatch")
        expected_packet = prepare_blind_packet(manifest, run["config"])
        if run.get("packetId") != expected_packet["packetId"] or run.get("packetSha256") != artifact_sha256(expected_packet):
            raise EvaluationError(f"{run.get('runId')}: packet identity does not match manifest and config")


def build_blind_review_packet(
    cases: list[dict[str, Any]], runs: list[dict[str, Any]], seed: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(cases, list) or not all(isinstance(case, dict) for case in cases):
        raise EvaluationError("cases must be an array of objects")
    _validate_runs_for_cases(cases, runs)
    order = list(range(len(runs)))
    random.Random(seed).shuffle(order)
    aliases = {runs[run_index]["runId"]: chr(ord("A") + position) for position, run_index in enumerate(order)}
    outputs_by_run = {
        run["runId"]: {item["caseId"]: item for item in run["outputs"]}
        for run in runs
    }
    review_cases = []
    for case in cases:
        candidates = []
        for run_index in order:
            output = outputs_by_run[runs[run_index]["runId"]][case["caseId"]]
            candidates.append(
                {
                    "alias": aliases[runs[run_index]["runId"]],
                    "titleEnglish": output["titleEnglish"],
                    "bodyEnglish": output["bodyEnglish"],
                    "issues": output["issues"],
                }
            )
        review_cases.append(
            {
                "caseId": case["caseId"],
                "arabic": case["arabic"],
                "arabicSha256": case.get("arabicSha256") or sha256_text(case["arabic"]),
                "candidates": candidates,
            }
        )
    packet = {
        "schemaVersion": "1.0.0",
        "evaluationId": runs[0]["evaluationId"],
        "policySha256": runs[0]["policySha256"],
        "casesSha256": artifact_sha256(cases),
        "seedSha256": sha256_text(seed),
        "reviewState": "blind-unreviewed",
        "runArtifactSha256": [artifact_sha256(run) for run in runs],
        "cases": review_cases,
    }
    packet["reviewPacketId"] = review_packet_id_for(packet)
    key = {
        "schemaVersion": "1.0.0",
        "evaluationId": runs[0]["evaluationId"],
        "policySha256": runs[0]["policySha256"],
        "casesSha256": artifact_sha256(cases),
        "reviewPacketId": packet["reviewPacketId"],
        "reviewPacketSha256": artifact_sha256(packet),
        "seed": seed,
        "runIds": [run["runId"] for run in runs],
        "runArtifactSha256": {run["runId"]: artifact_sha256(run) for run in runs},
        "aliases": aliases,
    }
    return packet, key


def _validate_protocol_hashes(root: Path, manifest: dict[str, Any]) -> list[str]:
    errors = []
    policy = manifest.get("policy", {})
    for path_key, hash_key in (
        ("bindingPath", "bindingSha256"),
        ("evaluationProtocolPath", "evaluationProtocolSha256"),
        ("glossaryPath", "glossarySha256"),
        ("promptPath", "promptSha256"),
    ):
        relative = policy.get(path_key)
        if not isinstance(relative, str):
            errors.append(f"policy: missing {path_key}")
            continue
        target = (root / relative).resolve()
        try:
            target.relative_to(root.resolve())
        except ValueError:
            errors.append(f"policy: path escapes repository: {relative}")
            continue
        if not target.is_file():
            errors.append(f"policy: missing {relative}")
        elif hashlib.sha256(target.read_bytes()).hexdigest() != policy.get(hash_key):
            errors.append(f"policy: hash mismatch for {relative}")
    return errors


def validate_repository_contract(root: Path) -> list[str]:
    errors: list[str] = []
    base = root / "evaluations/local-model/v1"
    try:
        manifest = _load_json(base / "cases.json")
        configs = [_load_json(path) for path in sorted((base / "configs").glob("*.json"))]
        smoke = _load_json(base / "smoke-evidence.json")
        gates = _load_json(base / "role-gates.json")
        decision = _load_json(base / "decision-log.json")
        rubric = _load_json(base / "rubric.json")
        errors.extend(_schema_errors(manifest, "local-model-evaluation-cases.v1.schema.json", root))
        for config in configs:
            errors.extend(_schema_errors(config, "local-model-evaluation-config.v1.schema.json", root))
        if errors:
            return errors
        validate_manifest_integrity(manifest)
    except EvaluationError as exc:
        return [str(exc)]
    errors.extend(_validate_protocol_hashes(root, manifest))
    prompt_hash = manifest["policy"]["promptSha256"]
    for config in configs:
        if config["promptSha256"] != prompt_hash:
            errors.append(f"{config['configId']}: prompt hash does not match selected protocol prompt hash")
    try:
        proposal = _load_json(root / "content/public-proposals/issue-0026.public-proposal.json")
        records = {record["id"]: record for record in proposal["records"]}
        for case in manifest["cases"]:
            record = records.get(case["sourceUnitId"])
            if record is None:
                errors.append(f"{case['caseId']}: source unit is absent from public proposal")
                continue
            if case["arabic"] != record.get("arabic"):
                errors.append(f"{case['caseId']}: Arabic differs from locked public source")
            if case["referenceEnglish"] != record.get("english"):
                errors.append(f"{case['caseId']}: reference differs from frozen public comparator")
            if case["sourceExactTextSha256"] != record.get("source", {}).get("exactTextSha256"):
                errors.append(f"{case['caseId']}: exact source-text anchor mismatch")
    except (EvaluationError, KeyError, TypeError) as exc:
        errors.append(f"source validation failed: {exc}")
    attempts = smoke.get("attempts", [])
    passed_profiles = {attempt.get("profile") for attempt in attempts if attempt.get("result") == "passed"}
    if passed_profiles != {"low", "high", "xhigh"}:
        errors.append("smoke evidence: low, high, and xhigh must each have a passing attempt")
    xhigh = [attempt for attempt in attempts if attempt.get("profile") == "xhigh"]
    post_fix = [attempt for attempt in xhigh if attempt.get("attemptId") == "xhigh-post-fix-001"]
    if not any(attempt.get("result") != "passed" for attempt in xhigh):
        errors.append("smoke evidence: pre-fix xhigh failures must be preserved")
    if len(post_fix) != 1 or any(post_fix[0].get(key) != value for key, value in {"result": "passed", "smokeTemperature": 0.0, "profileTemperature": 0.2}.items()):
        errors.append("smoke evidence: deterministic post-fix xhigh evidence is invalid")
    if smoke.get("controllerReturnedTo") != "off":
        errors.append("smoke evidence: controller must be returned to off")
    if gates.get("roles", {}).get("semantic_authority", {}).get("status") != "prohibited":
        errors.append("role gates: local semantic authority must remain prohibited")
    entries = decision.get("entries")
    if not isinstance(entries, list) or not entries:
        errors.append("decision log: entries are required")
    else:
        previous = None
        for entry in entries:
            if entry.get("previousEntrySha256") != previous:
                errors.append("decision log: broken append-only hash chain")
                break
            previous = artifact_sha256(entry)
        if decision.get("logHeadSha256") != previous:
            errors.append("decision log: head hash mismatch")
        if entries[-1].get("promotionStatus") != "blocked":
            errors.append("decision log: promotion must remain blocked")
    if not rubric.get("dimensions"):
        errors.append("rubric: dimensions are required")
    return errors


def validate_prepare_inputs(root: Path, manifest: dict[str, Any], config: dict[str, Any]) -> None:
    errors = _schema_errors(manifest, "local-model-evaluation-cases.v1.schema.json", root)
    errors.extend(_schema_errors(config, "local-model-evaluation-config.v1.schema.json", root))
    if errors:
        raise EvaluationError("prepare schema validation failed: " + "; ".join(errors))
    validate_manifest_integrity(manifest)
    hash_errors = _validate_protocol_hashes(root, manifest)
    if hash_errors:
        raise EvaluationError("prepare protocol validation failed: " + "; ".join(hash_errors))
    if config["promptSha256"] != manifest["policy"]["promptSha256"]:
        raise EvaluationError("selected config prompt hash does not match protocol prompt hash")


def validated_runtime_output_path(root: Path, raw_path: str) -> Path:
    root = root.resolve()
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve(strict=False)
    runtime = (root / RUNTIME_RELATIVE).resolve(strict=False)
    try:
        relative = resolved.relative_to(runtime)
    except ValueError as exc:
        raise EvaluationError(f"output must be inside {RUNTIME_RELATIVE}/") from exc
    if not relative.parts:
        raise EvaluationError(f"output must be a file inside {RUNTIME_RELATIVE}/")
    try:
        repository_relative = resolved.relative_to(root)
    except ValueError as exc:
        raise EvaluationError(f"output path escapes {RUNTIME_RELATIVE}/") from exc
    ignored = subprocess.run(
        ["git", "check-ignore", "--quiet", "--", str(repository_relative)],
        cwd=root,
        check=False,
        capture_output=True,
    )
    if ignored.returncode != 0:
        raise EvaluationError(f"output is not git-ignored under {RUNTIME_RELATIVE}/")
    return resolved


def _write_json(path: Path, value: Any) -> None:
    _write(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _write(path: Path, content: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        raise EvaluationError(f"cannot write {path}: {exc}") from exc


def _main(argv: list[str] | None = None) -> int:
    root = ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate", help="validate the tracked evaluation protocol")
    prepare_parser = subparsers.add_parser("prepare", help="write a reference-free blind packet")
    prepare_parser.add_argument("--config", required=True)
    prepare_parser.add_argument("--output", required=True)
    record_parser = subparsers.add_parser("record", help="record frozen final outputs for one blind run")
    record_parser.add_argument("--packet", required=True)
    record_parser.add_argument("--outputs", required=True)
    record_parser.add_argument("--generated-at", required=True)
    record_parser.add_argument("--output", required=True)
    anonymize_parser = subparsers.add_parser("anonymize", help="build a seeded model-anonymous review packet")
    anonymize_parser.add_argument("--runs", nargs="+", required=True)
    anonymize_parser.add_argument("--seed", required=True)
    anonymize_parser.add_argument("--packet-output", required=True)
    anonymize_parser.add_argument("--key-output", required=True)
    args = parser.parse_args(argv)
    if args.command == "validate":
        errors = validate_repository_contract(root)
        if errors:
            raise EvaluationError("; ".join(errors))
        print("evaluation protocol: valid")
        return 0
    if args.command == "prepare":
        output_path = validated_runtime_output_path(root, args.output)
        manifest = _load_json(root / "evaluations/local-model/v1/cases.json")
        config_path = Path(args.config)
        if not config_path.is_absolute():
            config_path = root / config_path
        config = _load_json(config_path)
        validate_prepare_inputs(root, manifest, config)
        packet = prepare_blind_packet(manifest, config)
        errors = _schema_errors(packet, "local-model-evaluation-packet.v1.schema.json", root)
        if errors:
            raise EvaluationError("packet schema validation failed: " + "; ".join(errors))
        _write_json(output_path, packet)
        print(f"blind packet: {packet['packetId']}")
        return 0
    if args.command == "record":
        output_path = validated_runtime_output_path(root, args.output)
        packet = _load_json(Path(args.packet))
        outputs = _load_json_value(Path(args.outputs))
        run = record_run(packet, outputs, args.generated_at)
        errors = validate_run_artifact(run, root)
        if errors:
            raise EvaluationError("run schema validation failed: " + "; ".join(errors))
        _write_json(output_path, run)
        print(f"run: {run['runId']}")
        return 0
    packet_output = validated_runtime_output_path(root, args.packet_output)
    key_output = validated_runtime_output_path(root, args.key_output)
    manifest = _load_json(root / "evaluations/local-model/v1/cases.json")
    runs = [_load_json(Path(path)) for path in args.runs]
    validate_anonymization_inputs(manifest, runs)
    packet, key = build_blind_review_packet(manifest["cases"], runs, args.seed)
    packet_errors = _schema_errors(packet, "local-model-evaluation-blind-packet.v1.schema.json", root)
    key_errors = _schema_errors(key, "local-model-evaluation-alias-key.v1.schema.json", root)
    if packet_errors or key_errors:
        raise EvaluationError("blind artifact schema validation failed: " + "; ".join(packet_errors + key_errors))
    _write_json(packet_output, packet)
    _write_json(key_output, key)
    print(f"blind review packet: {len(packet['cases'])} cases")
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        return _main(argv)
    except EvaluationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

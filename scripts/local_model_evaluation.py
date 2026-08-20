#!/usr/bin/env python3
"""Build integrity-bound public local-model evaluation evidence."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


class EvaluationError(RuntimeError):
    """Raised when public evaluation evidence violates the protocol."""


ROOT = Path(__file__).resolve().parents[1]
RESULTS_RELATIVE = Path("evaluations/local-model/v1/results")
FORBIDDEN_NORMALIZED_FIELDS = {
    "accesstoken", "agentlog", "apikey", "chainofthought", "credential",
    "credentials", "internalpath", "livingpersonpersonalinformation",
    "nonconsentingreviewerpersonalinformation", "objectlocator", "password",
    "privatecorrespondence", "privatepath", "rawcontrollerlog", "rawlog",
    "reasoningtrace", "restrictedevidence", "restrictedwitnesstext", "thoughttrace",
    "token",
}
POLICY_FIELDS = (
    "bindingPath", "bindingSha256", "evaluationProtocolPath",
    "evaluationProtocolSha256", "glossaryPath", "glossarySha256",
    "promptPath", "promptSha256",
)
CONFIG_FIELDS = (
    "schemaVersion", "configId", "role", "engine", "runtimeVersion", "model",
    "modelDigest", "artifactDisclosure", "quantization", "houseProfile",
    "nativeThinkingRequested", "nativeThinkingObserved", "contextTokens",
    "maxOutputTokens", "temperature", "samplingSeed", "promptVersion", "promptSha256",
)
PUBLIC_SAFETY_FIELDS = ("status", "provenance", "admittedBy")
SUPPORTED_RESULT_TYPES = {
    "public-index": None,
    "source-packet": "local-model-evaluation-packet.v1.schema.json",
    "attempt-summary": "local-model-evaluation-attempt-summary.v1.schema.json",
    "run": "local-model-evaluation-run.v1.schema.json",
    "identified-review-packet": "local-model-evaluation-identified-packet.v1.schema.json",
    "review": "local-model-evaluation-review.v1.schema.json",
    "score": "local-model-evaluation-score.v1.schema.json",
    "report": None,
}
UNSAFE_PUBLIC_TEXT_PATTERNS = (
    (re.compile(r"(?i)\b(?:password|passphrase|api[_ -]?key|access[_ -]?token)\b|\b(?:secret|token)\s*[:=]"), "credential assignment"),
    (re.compile(r"(?i)\b(?:bearer\s+[a-z0-9._~+/-]{8,}|gh[pousr]_[a-z0-9]{20,}|sk-[a-z0-9]{16,})"), "credential/token"),
    (re.compile(r"(?i)-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"), "private key"),
    (re.compile(r"(?i)(?:^|[\s'\"])(?:/home/|/opt/|/mnt/|/var/(?:lib|log|run)/|[a-z]:\\|\.runtime(?:/|\\))"), "private/internal path"),
    (re.compile(r"(?i)\b(?:chain[- ]of[- ]thought|reasoning trace|thought trace|raw (?:agent|controller) log|agent log|stack trace|traceback)\b"), "raw trace/log marker"),
    (re.compile(r"(?i)\b(?:restricted (?:witness|evidence)|private evidence|confidential witness|private correspondence)\b"), "restricted/private evidence marker"),
    (re.compile(r"(?i)(?:https?://|www\.|(?:javascript|data|file|ftp|mailto|tel|sms|ssh|xmpp|irc|ircs|blob):)"), "unsafe URL or URI"),
    (re.compile(r"(?i)(?:!?)\[[^\]]*\]\(\s*(?://|(?:\.\./)+)[^)]*\)|<\s*//[^>]*>"), "unsafe GFM link or image"),
    (re.compile(r"(?<![\w.+-])[\w.+-]+@[a-z0-9.-]+\.[a-z]{2,}(?![\w.-])", re.I), "email address"),
    (re.compile(r"(?<!\d)(?:\+?1[-. ]?)?\(?\d{3}\)?[-. ]\d{3}[-. ]\d{4}(?!\d)"), "phone number"),
    (re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)"), "government identifier"),
)
DISQUALIFYING_ELIGIBILITY_FIELDS = (
    "restrictedWitnessText", "credentials", "internalPathsOrObjectLocators",
    "privateCorrespondence", "livingPersonPersonalInformation",
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


def attempt_summary_id_for(summary: dict[str, Any]) -> str:
    return "eval-attempt-summary-" + artifact_sha256(
        _without(summary, "attemptSummaryId")
    )[:16]


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


def scan_public_text(value: Any, path: str = "$") -> None:
    """Reject machine-verifiable unsafe text at a public artifact boundary."""
    if isinstance(value, str):
        for pattern, label in UNSAFE_PUBLIC_TEXT_PATTERNS:
            if pattern.search(value):
                raise EvaluationError(f"{path}: unsafe public text ({label})")
    elif isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise EvaluationError(f"{path}: public field names must be strings")
            for pattern, label in UNSAFE_PUBLIC_TEXT_PATTERNS:
                if pattern.search(key):
                    raise EvaluationError(f"{path}: unsafe public field name ({label})")
            scan_public_text(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            scan_public_text(child, f"{path}[{index}]")


def _public_safety(
    value: Any, provenance: str, label: str, admitted_by: str | None = None
) -> dict[str, str]:
    if not isinstance(value, dict):
        raise EvaluationError(f"{label}: explicit public-safety admission is required")
    if set(value) != set(PUBLIC_SAFETY_FIELDS):
        raise EvaluationError(f"{label}: public-safety admission must be closed")
    admitted = _allowlist(value, PUBLIC_SAFETY_FIELDS, f"{label} public safety")
    if admitted.get("status") != "admitted" or admitted.get("provenance") != provenance:
        raise EvaluationError(f"{label}: explicit public-safety admission/provenance is required")
    if not isinstance(admitted.get("admittedBy"), str) or not admitted["admittedBy"].strip():
        raise EvaluationError(f"{label}: public-safety admitting identity is required")
    scan_public_text(admitted, f"{label}.publicSafety")
    if admitted_by is not None and admitted["admittedBy"] != admitted_by:
        raise EvaluationError(f"{label}: public-safety admitting identity must equal {admitted_by}")
    return admitted


def _authorized_configs(root: Path) -> list[dict[str, Any]]:
    repository = root.resolve()
    completed = subprocess.run(
        ["git", "ls-files", "--", "evaluations/local-model/v1/configs/*.json"],
        cwd=repository, check=False, capture_output=True, text=True,
    )
    if completed.returncode != 0:
        raise EvaluationError(f"cannot enumerate tracked configs: {completed.stderr.strip()}")
    authorized: list[dict[str, Any]] = []
    for line in sorted(completed.stdout.splitlines()):
        if not line:
            continue
        authorized.append(_load_indexed_json(repository, line))
    return authorized


def _load_indexed_json(root: Path, relative: str) -> dict[str, Any]:
    indexed = subprocess.run(
        ["git", "show", f":{relative}"], cwd=root, check=False,
        capture_output=True, text=True,
    )
    if indexed.returncode != 0:
        raise EvaluationError(f"cannot read tracked JSON {relative}: {indexed.stderr.strip()}")
    try:
        value = json.loads(indexed.stdout)
    except json.JSONDecodeError as exc:
        raise EvaluationError(f"tracked JSON {relative} is invalid: {exc}") from exc
    if not isinstance(value, dict):
        raise EvaluationError(f"tracked JSON {relative} must be an object")
    return value


def _require_authorized_config(config: dict[str, Any], root: Path) -> None:
    if not any(config == tracked for tracked in _authorized_configs(root)):
        raise EvaluationError("config does not exactly match an authorized tracked config")


def validate_manifest_integrity(manifest: dict[str, Any]) -> None:
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not cases or not all(isinstance(case, dict) for case in cases):
        raise EvaluationError("manifest cases must be a non-empty array of objects")
    case_ids = [case.get("caseId") for case in cases]
    source_ids = [case.get("sourceUnitId") for case in cases]
    if len(set(case_ids)) != len(case_ids):
        raise EvaluationError("duplicate case ID")
    if len(set(source_ids)) != len(source_ids):
        raise EvaluationError("duplicate source unit ID")
    for case in cases:
        case_id = case.get("caseId")
        if case.get("arabicSha256") != sha256_text(case.get("arabic", "")):
            raise EvaluationError(f"{case_id}: Arabic hash mismatch")
        if case.get("referenceSha256") != sha256_text(case.get("referenceEnglish", "")):
            raise EvaluationError(f"{case_id}: reference hash mismatch")
        eligibility = case.get("publicEligibility")
        expected_eligibility_fields = {
            "decision", "authorityStatus", *DISQUALIFYING_ELIGIBILITY_FIELDS,
            "publicRationale", "reviewedBy", "reviewedOn", "issueEvidence",
        }
        if (
            not isinstance(eligibility, dict)
            or set(eligibility) != expected_eligibility_fields
            or eligibility.get("decision") != "approved"
            or eligibility.get("authorityStatus") != "public-approved-authority"
            or any(eligibility.get(field) is not False for field in DISQUALIFYING_ELIGIBILITY_FIELDS)
            or not isinstance(eligibility.get("publicRationale"), str)
            or not eligibility["publicRationale"].strip()
            or not isinstance(eligibility.get("reviewedBy"), str)
            or not eligibility["reviewedBy"].strip()
            or not isinstance(eligibility.get("reviewedOn"), str)
            or not eligibility["reviewedOn"].strip()
            or not isinstance(eligibility.get("issueEvidence"), str)
            or not eligibility["issueEvidence"].strip()
        ):
            raise EvaluationError(f"{case_id}: public eligibility evidence is not closed; not eligible for public evaluation")
        try:
            _reject_forbidden_fields(
                {key: value for key, value in eligibility.items()
                 if key not in DISQUALIFYING_ELIGIBILITY_FIELDS},
                f"{case_id}.publicEligibility",
            )
            scan_public_text(
                {key: eligibility[key] for key in ("publicRationale", "reviewedBy", "reviewedOn")},
                f"{case_id}.publicEligibility",
            )
        except EvaluationError as exc:
            raise EvaluationError(f"{case_id}: unsafe public eligibility evidence: {exc}") from exc


def _require_tracked_manifest(manifest: dict[str, Any], root: Path) -> None:
    tracked = _load_indexed_json(root.resolve(), "evaluations/local-model/v1/cases.json")
    if manifest != tracked:
        raise EvaluationError("supplied cases artifact does not exactly match the tracked cases manifest")


def _source_cases(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "caseId": case["caseId"], "sourceUnitId": case["sourceUnitId"],
            "category": case["category"], "arabic": case["arabic"],
            "arabicSha256": case["arabicSha256"], "heldOut": case["heldOut"],
        }
        for case in manifest["cases"]
    ]


def prepare_source_packet(
    manifest: dict[str, Any], config: dict[str, Any], root: Path | None = ROOT
) -> dict[str, Any]:
    validate_manifest_integrity(manifest)
    if root is not None:
        _require_tracked_manifest(manifest, root)
    clean_config = _allowlist(config, CONFIG_FIELDS, "config")
    if not isinstance(clean_config.get("model"), str) or not clean_config["model"].strip():
        raise EvaluationError("model identity is required")
    if not isinstance(clean_config.get("configId"), str) or not clean_config["configId"].strip():
        raise EvaluationError("config identity is required")
    if clean_config.get("promptSha256") != manifest.get("policy", {}).get("promptSha256"):
        raise EvaluationError("config prompt binding does not match the locked evaluation prompt")
    if root is not None:
        _require_authorized_config(clean_config, root)
    cases = _source_cases(manifest)
    packet = {
        "schemaVersion": "1.0.0",
        "evaluationId": manifest["evaluationId"],
        "issue": manifest["issue"],
        "policy": _allowlist(manifest["policy"], POLICY_FIELDS, "policy"),
        "casesSha256": artifact_sha256(cases),
        "config": clean_config,
        "configSha256": artifact_sha256(clean_config),
        "cases": cases,
    }
    packet["packetId"] = packet_id_for(packet)
    return packet



def _validate_packet(packet: dict[str, Any]) -> None:
    _reject_forbidden_fields(packet)
    if packet.get("packetId") != packet_id_for(packet):
        raise EvaluationError("packet identity/hash mismatch")
    if not isinstance(packet.get("config"), dict) or not packet["config"].get("model"):
        raise EvaluationError("packet model identity is missing")
    if packet.get("configSha256") != artifact_sha256(packet["config"]):
        raise EvaluationError("packet config hash mismatch")
    cases = packet.get("cases")
    if not isinstance(cases, list) or not cases:
        raise EvaluationError("packet cases must be a non-empty array")
    if packet.get("casesSha256") != artifact_sha256(cases):
        raise EvaluationError("packet cases hash mismatch")
    ids = []
    for case in cases:
        if not isinstance(case, dict):
            raise EvaluationError("packet cases must contain objects")
        ids.append(case.get("caseId"))
        if case.get("arabicSha256") != sha256_text(case.get("arabic", "")):
            raise EvaluationError(f"{case.get('caseId')}: packet Arabic hash mismatch")
    if len(ids) != len(set(ids)):
        raise EvaluationError("packet has duplicate case IDs")


def record_run(
    packet: dict[str, Any], outputs: list[dict[str, Any]], generated_at: str,
    resource_outcome: dict[str, Any] | None = None, root: Path = ROOT,
) -> dict[str, Any]:
    _validate_packet(packet)
    tracked_manifest = _load_indexed_json(
        root.resolve(), "evaluations/local-model/v1/cases.json"
    )
    expected_packet = prepare_source_packet(tracked_manifest, packet["config"], root)
    if packet != expected_packet:
        raise EvaluationError(
            "packet does not exactly match tracked cases and authorized config"
        )
    _reject_forbidden_fields(outputs)
    if not isinstance(outputs, list) or not all(isinstance(output, dict) for output in outputs):
        raise EvaluationError("outputs must be an array of objects")
    expected = [case["caseId"] for case in packet["cases"]]
    observed = [output.get("caseId") for output in outputs]
    if observed != expected:
        raise EvaluationError("outputs must exactly cover packet cases in order")
    normalized = []
    expected_fields = {"caseId", "titleEnglish", "bodyEnglish", "issues", "publicSafety"}
    for output in outputs:
        extras = set(output) - expected_fields
        if extras:
            raise EvaluationError(f"{output.get('caseId')}: unexpected output fields: {sorted(extras)}")
        title, body, issues = output.get("titleEnglish"), output.get("bodyEnglish"), output.get("issues")
        if not isinstance(title, str) or not title.strip():
            raise EvaluationError(f"{output.get('caseId')}: titleEnglish is required")
        if not isinstance(body, str) or not body.strip():
            raise EvaluationError(f"{output.get('caseId')}: bodyEnglish is required")
        if not isinstance(issues, list) or not all(isinstance(issue, str) for issue in issues):
            raise EvaluationError(f"{output.get('caseId')}: issues must be an array of strings")
        safety = _public_safety(
            output.get("publicSafety"), "sanitized-final-model-output", str(output.get("caseId")),
            f"config:{packet['config']['configId']}",
        )
        scan_public_text(
            {"titleEnglish": title, "bodyEnglish": body, "issues": issues},
            f"outputs.{output.get('caseId')}",
        )
        normalized.append({
            "caseId": output["caseId"], "titleEnglish": title,
            "titleEnglishSha256": sha256_text(title), "bodyEnglish": body,
            "bodyEnglishSha256": sha256_text(body), "issues": issues,
            "publicSafety": safety,
        })
    if resource_outcome is None:
        resource_outcome = {"status": "completed", "profile": packet["config"]["houseProfile"], "limitations": []}
    _reject_forbidden_fields(resource_outcome)
    if (
        not isinstance(resource_outcome, dict)
        or resource_outcome.get("status") not in {"completed", "failed", "partial"}
        or not isinstance(resource_outcome.get("profile"), str)
        or not isinstance(resource_outcome.get("limitations"), list)
        or not all(isinstance(item, str) for item in resource_outcome["limitations"])
    ):
        raise EvaluationError("resource outcome is malformed")
    if resource_outcome["profile"] != packet["config"]["houseProfile"]:
        raise EvaluationError("resource profile must equal the authorized config house profile")
    scan_public_text(resource_outcome["limitations"], "resourceOutcome.limitations")
    run = {
        "schemaVersion": "1.0.0", "packetId": packet["packetId"],
        "packetSha256": artifact_sha256(packet), "evaluationId": packet["evaluationId"],
        "issue": packet["issue"], "policy": packet["policy"],
        "policySha256": artifact_sha256(packet["policy"]), "casesSha256": packet["casesSha256"],
        "config": packet["config"], "configSha256": packet["configSha256"],
        "generatedAt": generated_at, "resourceOutcome": resource_outcome,
        "outputs": normalized, "reviewStatus": "unreviewed", "roleStatus": "no-role",
        "promotionStatus": "blocked",
    }
    run["runId"] = run_id_for(run)
    return run


def _authorized_config_by_id(config_id: Any, root: Path) -> dict[str, Any]:
    matches = [config for config in _authorized_configs(root) if config.get("configId") == config_id]
    if len(matches) != 1:
        raise EvaluationError("attempt summary config must identify exactly one authorized tracked config")
    return matches[0]


def record_attempt_summary(
    packet: dict[str, Any], cases: list[dict[str, Any]], generated_at: str,
    limitation: str, root: Path = ROOT,
) -> dict[str, Any]:
    """Record sanitized execution outcomes without creating a reviewable run."""
    _validate_packet(packet)
    tracked_manifest = _load_indexed_json(
        root.resolve(), "evaluations/local-model/v1/cases.json"
    )
    expected_packet = prepare_source_packet(tracked_manifest, packet["config"], root)
    if packet != expected_packet:
        raise EvaluationError("packet does not exactly match tracked cases and authorized config")
    if not isinstance(generated_at, str) or re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?Z",
        generated_at,
    ) is None:
        raise EvaluationError("generated time must be an exact UTC date-time ending in Z")
    try:
        datetime.fromisoformat(generated_at[:-1] + "+00:00")
    except ValueError as exc:
        raise EvaluationError("generated time must be a valid UTC date-time") from exc
    if not isinstance(limitation, str) or not limitation.strip() or len(limitation) > 280:
        raise EvaluationError("attempt summary limitation must contain 1 to 280 characters")
    scan_public_text(limitation, "attemptSummary.limitation")
    _reject_forbidden_fields(cases)
    expected_case_ids = [case["caseId"] for case in packet["cases"]]
    if (
        not isinstance(cases, list)
        or not all(isinstance(case, dict) for case in cases)
        or [case.get("caseId") for case in cases] != expected_case_ids
    ):
        raise EvaluationError("attempt summary cases must exactly cover packet cases in order")
    normalized = []
    outcomes = {"completed", "empty-response", "timeout", "controller-unavailable"}
    for case in cases:
        if set(case) != {"caseId", "attemptCount", "outcome"}:
            raise EvaluationError(f"{case.get('caseId')}: attempt summary case must be closed")
        count, outcome = case["attemptCount"], case["outcome"]
        if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= 100:
            raise EvaluationError(f"{case['caseId']}: attempt count must be an integer from 0 to 100")
        if outcome not in outcomes:
            raise EvaluationError(f"{case['caseId']}: unsupported attempt outcome")
        if outcome != "controller-unavailable" and count < 1:
            raise EvaluationError(f"{case['caseId']}: attempted outcome requires a positive attempt count")
        normalized.append(dict(case))
    config = packet["config"]
    summary = {
        "schemaVersion": "1.0.0",
        "packetId": packet["packetId"],
        "packetSha256": artifact_sha256(packet),
        "evaluationId": packet["evaluationId"],
        "issue": packet["issue"],
        "configId": config["configId"],
        "configSha256": packet["configSha256"],
        "promptSha256": packet["policy"]["promptSha256"],
        "casesSha256": packet["casesSha256"],
        "generatedAt": generated_at,
        "resourceIdentity": {
            "profile": config["houseProfile"], "engine": config["engine"],
            "runtimeVersion": config["runtimeVersion"], "model": config["model"],
            "modelDigest": config["modelDigest"],
        },
        "cases": normalized,
        "limitation": limitation,
        "publicSafety": {
            "status": "admitted", "provenance": "sanitized-attempt-summary",
            "admittedBy": f"config:{config['configId']}",
        },
        "eligibility": {
            "identifiedReview": "excluded", "scoring": "excluded",
            "repeats": "excluded", "role": "no-role", "promotion": "blocked",
        },
    }
    summary["attemptSummaryId"] = attempt_summary_id_for(summary)
    return summary


def validate_attempt_summary_artifact(
    summary: dict[str, Any], root: Path = ROOT
) -> list[str]:
    errors = _schema_errors(
        summary, "local-model-evaluation-attempt-summary.v1.schema.json", root
    )
    try:
        _reject_forbidden_fields(summary)
        scan_public_text(
            {
                "limitation": summary.get("limitation"),
                "publicSafety": summary.get("publicSafety"),
            },
            "$attemptSummary",
        )
        config = _authorized_config_by_id(summary.get("configId"), root)
        manifest = _load_indexed_json(
            root.resolve(), "evaluations/local-model/v1/cases.json"
        )
        packet = prepare_source_packet(manifest, config, root)
        expected = record_attempt_summary(
            packet, summary.get("cases"), summary.get("generatedAt"),
            summary.get("limitation"), root,
        )
        if summary != expected:
            errors.append("attempt summary does not exactly rederive from tracked packet, config, prompt, and cases")
    except (EvaluationError, KeyError, TypeError) as exc:
        errors.append(str(exc))
    if summary.get("attemptSummaryId") != attempt_summary_id_for(summary):
        errors.append("attempt summary identity/hash mismatch")
    return errors


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
    return _schema_validator(root)(value, _load_json(root / "schemas" / schema_name))


def validate_run_artifact(run: dict[str, Any], root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    try:
        _reject_forbidden_fields(run)
        scan_public_text(
            {
                "outputs": [
                    {
                        "titleEnglish": item.get("titleEnglish"), "bodyEnglish": item.get("bodyEnglish"),
                        "issues": item.get("issues"), "publicSafety": item.get("publicSafety"),
                    }
                    for item in run.get("outputs", []) if isinstance(item, dict)
                ],
                "limitations": run.get("resourceOutcome", {}).get("limitations", []),
            },
            "$run",
        )
        config_id = run.get("config", {}).get("configId")
        if isinstance(config_id, str) and config_id:
            for item in run.get("outputs", []):
                if isinstance(item, dict):
                    _public_safety(
                        item.get("publicSafety"), "sanitized-final-model-output",
                        f"$run.outputs.{item.get('caseId')}", f"config:{config_id}",
                    )
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
    try:
        _require_authorized_config(run["config"], root)
    except EvaluationError as exc:
        errors.append(str(exc))
    if run.get("resourceOutcome", {}).get("profile") != run.get("config", {}).get("houseProfile"):
        errors.append("resource profile must equal the authorized config house profile")
    ids = []
    for output in run["outputs"]:
        ids.append(output["caseId"])
        if output["titleEnglishSha256"] != sha256_text(output["titleEnglish"]):
            errors.append(f"{output['caseId']}: title hash mismatch")
        if output["bodyEnglishSha256"] != sha256_text(output["bodyEnglish"]):
            errors.append(f"{output['caseId']}: body hash mismatch")
    if len(ids) != len(set(ids)):
        errors.append("run has duplicate case IDs")
    return errors


def validate_runs_against_manifest(
    manifest: dict[str, Any], runs: list[dict[str, Any]], root: Path = ROOT
) -> None:
    validate_manifest_integrity(manifest)
    _require_tracked_manifest(manifest, root)
    if not isinstance(runs, list) or not runs or not all(isinstance(run, dict) for run in runs):
        raise EvaluationError("runs must be a non-empty array of objects")
    run_ids = [run.get("runId") for run in runs]
    if len(run_ids) != len(set(run_ids)):
        raise EvaluationError("duplicate run ID")
    expected_case_ids = [case["caseId"] for case in manifest["cases"]]
    expected_policy = _allowlist(manifest["policy"], POLICY_FIELDS, "manifest policy")
    expected_policy_hash = artifact_sha256(expected_policy)
    for run in runs:
        observed = [output.get("caseId") for output in run.get("outputs", []) if isinstance(output, dict)]
        if observed != expected_case_ids:
            raise EvaluationError(f"{run.get('runId')}: outputs must exactly cover cases in order")
        errors = validate_run_artifact(run, root)
        if errors:
            raise EvaluationError("run validation failed: " + "; ".join(errors))
        if not run.get("config", {}).get("model"):
            raise EvaluationError(f"{run.get('runId')}: model identity is missing")
        if run.get("evaluationId") != manifest.get("evaluationId") or run.get("issue") != manifest.get("issue"):
            raise EvaluationError(f"{run.get('runId')}: evaluation identity mismatch")
        if run.get("policy") != expected_policy or run.get("policySha256") != expected_policy_hash:
            raise EvaluationError(f"{run.get('runId')}: manifest policy identity mismatch")
        expected_packet = prepare_source_packet(manifest, run["config"], root)
        if run.get("packetId") != expected_packet["packetId"] or run.get("packetSha256") != artifact_sha256(expected_packet):
            raise EvaluationError(f"{run.get('runId')}: packet identity does not match manifest and config")
        if run.get("casesSha256") != expected_packet["casesSha256"]:
            raise EvaluationError(f"{run.get('runId')}: locked case-set identity mismatch")


def build_identified_review_packet(
    manifest: dict[str, Any], runs: list[dict[str, Any]], root: Path = ROOT
) -> dict[str, Any]:
    _require_tracked_manifest(manifest, root)
    validate_runs_against_manifest(manifest, runs, root)
    ineligible = [
        run.get("runId") for run in runs
        if run.get("resourceOutcome", {}).get("status") != "completed"
    ]
    if ineligible:
        raise EvaluationError(
            "identified review requires completed runs only: " + ", ".join(map(str, ineligible))
        )
    outputs = {run["runId"]: {item["caseId"]: item for item in run["outputs"]} for run in runs}
    cases = []
    for case in manifest["cases"]:
        candidates = []
        for run in runs:
            output = outputs[run["runId"]][case["caseId"]]
            candidates.append({
                "runId": run["runId"], "runSha256": artifact_sha256(run),
                "config": run["config"], "titleEnglish": output["titleEnglish"],
                "bodyEnglish": output["bodyEnglish"], "issues": output["issues"],
                "publicSafety": output["publicSafety"],
            })
        cases.append({
            "caseId": case["caseId"], "arabic": case["arabic"],
            "arabicSha256": case["arabicSha256"], "candidates": candidates,
        })
    packet = {
        "schemaVersion": "1.0.0", "evaluationId": manifest["evaluationId"],
        "issue": manifest["issue"], "policySha256": runs[0]["policySha256"],
        "casesSha256": artifact_sha256(manifest["cases"]),
        "runArtifactSha256": {run["runId"]: artifact_sha256(run) for run in runs},
        "reviewStatus": "unreviewed", "roleStatus": "no-role",
        "promotionStatus": "blocked",
        "limitations": [
            "Model identity is visible; scores must still be based on Arabic source evidence.",
            "Unreviewed candidates grant no workflow role and cannot be promoted.",
            "Raw thought traces and controller or agent logs are excluded.",
        ],
        "cases": cases,
    }
    packet["reviewPacketId"] = review_packet_id_for(packet)
    return packet


def _validate_protocol_hashes(root: Path, manifest: dict[str, Any]) -> list[str]:
    errors = []
    policy = manifest.get("policy", {})
    for path_key, hash_key in (
        ("bindingPath", "bindingSha256"), ("evaluationProtocolPath", "evaluationProtocolSha256"),
        ("glossaryPath", "glossarySha256"), ("promptPath", "promptSha256"),
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


def _tracked_result_paths(root: Path) -> list[str]:
    completed = subprocess.run(
        ["git", "ls-files", "--", RESULTS_RELATIVE.as_posix()],
        cwd=root, check=False, capture_output=True, text=True,
    )
    if completed.returncode != 0:
        raise EvaluationError(f"cannot enumerate tracked public results: {completed.stderr.strip()}")
    return sorted(line for line in completed.stdout.splitlines() if line)


def _dependency_hashes(root: Path) -> dict[str, str]:
    paths = [
        "evaluations/local-model/v1/cases.json",
        "docs/contracts/local-model-translation-evaluation-protocol.md",
        "evaluations/local-model/v1/rubric.json",
        "evaluations/local-model/v1/role-gates.json",
    ]
    paths.extend(
        path.relative_to(root).as_posix()
        for path in sorted((root / "evaluations/local-model/v1/configs").glob("*.json"))
    )
    return {path: hashlib.sha256((root / path).read_bytes()).hexdigest() for path in paths}


def _validate_report_inputs(inputs: Any, declared: dict[str, dict[str, Any]]) -> None:
    if not isinstance(inputs, dict) or inputs.get("cases") != "evaluations/local-model/v1/cases.json":
        raise EvaluationError("report inputs must use the exact tracked cases manifest")
    expected = {"runs": "run", "packet": "identified-review-packet", "reviews": "review", "score": "score"}
    for field, artifact_type in expected.items():
        values = inputs.get(field)
        if field == "runs":
            if not isinstance(values, list) or not values:
                raise EvaluationError("report inputs must contain declared runs")
        elif values is None:
            continue
        else:
            values = [values]
        for relative in values:
            item = declared.get(relative) if isinstance(relative, str) else None
            if item is None or item.get("artifactType") != artifact_type:
                raise EvaluationError(f"report inputs field {field} must reference a declared {artifact_type} artifact")


def render_public_results_index() -> str:
    return (
        "# Public local-model evaluation results\n\n"
        "This directory contains sanitized, declared evidence for issue #49.\n\n"
        "Every file is listed in the closed results manifest with its byte hash, static trusted "
        "dependencies, and any upstream result artifact hashes. Machine-readable evidence is "
        "schema-validated and reports regenerate byte-for-byte from declared inputs.\n\n"
        "Unreviewed runs remain no-role and promotion-blocked. Publication-admitted final outputs, "
        "review evidence, and sanitized attempt summaries may be admitted here.\n\n"
        "Attempt summaries bind to one exact declared source packet and its tracked config, prompt, "
        "and ordered cases. They contain only controlled per-case outcomes and counts, bounded "
        "limitations, resource identity, generated UTC time, and config-owned public-safety "
        "admission. They never contain partial model text, raw errors or logs, paths, URLs, traces, "
        "credentials, private data, or thought text. Attempt summaries are permanently excluded "
        "from identified review, scoring, repeat counts, and role eligibility; they grant no role "
        "and cannot be promoted.\n\n"
        "Create one with `python scripts/local_model_evaluation.py attempt-summary --packet <public "
        "packet> --outcomes <public temporary JSON array> --generated-at <UTC-date-time> --limitation "
        "<sanitized text> --output <public summary>`. Each outcomes item contains only `caseId`, "
        "`attemptCount`, and one of `completed`, `empty-response`, `timeout`, or "
        "`controller-unavailable`. Remove the temporary outcomes input after creating the summary; "
        "only manifest-declared evidence may remain tracked.\n"
    )


def _validate_declared_result_graph(
    root: Path, declared: dict[str, dict[str, Any]], static: dict[str, str],
    loaded: dict[str, dict[str, Any]],
) -> list[str]:
    """Rebuild every declared result from independently trusted graph roots."""
    errors: list[str] = []
    manifest = _load_json(root / "evaluations/local-model/v1/cases.json")
    by_type: dict[str, dict[str, dict[str, Any]]] = {}
    for path, value in loaded.items():
        by_type.setdefault(declared[path]["artifactType"], {})[path] = value
    expected_upstream: dict[str, dict[str, str]] = {path: {} for path in declared}
    sources = by_type.get("source-packet", {})
    attempt_summaries = by_type.get("attempt-summary", {})
    runs = by_type.get("run", {})
    packets = by_type.get("identified-review-packet", {})
    reviews = by_type.get("review", {})
    scores = by_type.get("score", {})

    for path, packet in sources.items():
        try:
            if packet != prepare_source_packet(manifest, packet["config"], root):
                errors.append(f"{path}: graph source packet does not match tracked cases and config")
        except (EvaluationError, KeyError, TypeError) as exc:
            errors.append(f"{path}: graph source packet rebuild failed: {exc}")
    for path, summary in attempt_summaries.items():
        matches = [
            source_path for source_path, packet in sources.items()
            if summary.get("packetId") == packet.get("packetId")
            and summary.get("packetSha256") == artifact_sha256(packet)
        ]
        if len(matches) != 1:
            errors.append(f"{path}: graph attempt summary must bind exactly one declared source packet")
        else:
            expected_upstream[path][matches[0]] = declared[matches[0]]["sha256"]
        summary_errors = validate_attempt_summary_artifact(summary, root)
        errors.extend(f"{path}: graph attempt summary validation failed: {error}" for error in summary_errors)
    for path, run in runs.items():
        matches = [source_path for source_path, packet in sources.items()
                   if run.get("packetId") == packet.get("packetId")
                   and run.get("packetSha256") == artifact_sha256(packet)]
        if len(matches) != 1:
            errors.append(f"{path}: graph run must bind exactly one declared source packet")
        else:
            expected_upstream[path][matches[0]] = declared[matches[0]]["sha256"]
        try:
            validate_runs_against_manifest(manifest, [run], root)
        except EvaluationError as exc:
            errors.append(f"{path}: graph run validation failed: {exc}")
    for path, packet in packets.items():
        run_hashes = packet.get("runArtifactSha256", {})
        selected = [(run_path, run) for run_path, run in runs.items()
                    if isinstance(run_hashes, dict)
                    and run_hashes.get(run.get("runId")) == artifact_sha256(run)]
        if len(selected) != len(run_hashes) or not selected:
            errors.append(f"{path}: graph packet must bind exact declared runs")
            continue
        selected.sort(key=lambda pair: list(run_hashes).index(pair[1]["runId"]))
        expected_upstream[path] = {run_path: declared[run_path]["sha256"] for run_path, _ in selected}
        try:
            if packet != build_identified_review_packet(manifest, [run for _, run in selected], root):
                errors.append(f"{path}: graph identified packet does not rederive from declared runs")
        except EvaluationError as exc:
            errors.append(f"{path}: graph identified packet rebuild failed: {exc}")

    scorer_path = root / "scripts/score_local_model_evaluation.py"
    spec = importlib.util.spec_from_file_location("score_for_graph_validation", scorer_path)
    scorer = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(scorer)
    gates = _load_json(root / "evaluations/local-model/v1/role-gates.json")
    for path, review in reviews.items():
        matches = [(packet_path, packet) for packet_path, packet in packets.items()
                   if review.get("reviewPacketId") == packet.get("reviewPacketId")
                   and review.get("reviewPacketSha256") == artifact_sha256(packet)]
        if len(matches) != 1:
            errors.append(f"{path}: graph review must bind exactly one declared identified packet")
            continue
        packet_path, packet = matches[0]
        expected_upstream[path][packet_path] = declared[packet_path]["sha256"]
        selected_runs = [runs[p] for p in expected_upstream[packet_path]]
        try:
            scorer._validate_review(manifest, selected_runs, packet, review, root)
        except scorer.ScoringError as exc:
            errors.append(f"{path}: graph review validation failed: {exc}")
    for path, score in scores.items():
        packet_matches = [(packet_path, packet) for packet_path, packet in packets.items()
                          if score.get("reviewPacketId") == packet.get("reviewPacketId")
                          and score.get("reviewPacketSha256") == artifact_sha256(packet)]
        review_matches = [(review_path, review) for review_path, review in reviews.items()
                          if score.get("worksheetSha256") == artifact_sha256(review)]
        run_hashes = score.get("runArtifactSha256", {})
        selected = [(run_path, run) for run_path, run in runs.items()
                    if isinstance(run_hashes, dict)
                    and run_hashes.get(run.get("runId")) == artifact_sha256(run)]
        if len(packet_matches) != 1 or len(review_matches) != 1 or len(selected) != len(run_hashes) or not selected:
            errors.append(f"{path}: graph score must bind exact declared packet, review, and runs")
            continue
        packet_path, packet = packet_matches[0]
        review_path, review = review_matches[0]
        selected.sort(key=lambda pair: list(run_hashes).index(pair[1]["runId"]))
        expected_upstream[path] = {
            **{run_path: declared[run_path]["sha256"] for run_path, _ in selected},
            packet_path: declared[packet_path]["sha256"],
            review_path: declared[review_path]["sha256"],
        }
        try:
            expected = scorer.score_reviews(manifest, [run for _, run in selected], packet, review, gates, root)
            if score != expected:
                errors.append(f"{path}: graph score does not match rederived evidence")
        except scorer.ScoringError as exc:
            errors.append(f"{path}: graph score rederivation failed: {exc}")
    for path, item in declared.items():
        if item.get("artifactType") == "report":
            inputs = item.get("reportInputs", {})
            referenced = list(inputs.get("runs", []))
            referenced.extend(inputs.get(key) for key in ("packet", "reviews", "score") if inputs.get(key))
            expected_upstream[path] = {value: declared[value]["sha256"] for value in referenced if value in declared}
        if item.get("dependencySha256") != {**static, **expected_upstream[path]}:
            errors.append(f"{path}: graph dependency hashes do not match exact upstream artifacts")
    return errors


def _validate_results_admission(root: Path, admission: dict[str, Any]) -> list[str]:
    errors = _schema_errors(admission, "local-model-evaluation-results-manifest.v1.schema.json", root)
    if errors:
        return errors
    declared_items = admission["artifacts"]
    declared = {item["path"]: item for item in declared_items}
    loaded: dict[str, dict[str, Any]] = {}
    if len(declared) != len(declared_items):
        errors.append("results manifest: duplicate artifact path")
    try:
        tracked = set(_tracked_result_paths(root))
    except EvaluationError as exc:
        return [str(exc)]
    undeclared = sorted(tracked - set(declared))
    missing = sorted(set(declared) - tracked)
    if undeclared:
        errors.append("results manifest: undeclared tracked files: " + ", ".join(undeclared))
    if missing:
        errors.append("results manifest: declared files are not tracked: " + ", ".join(missing))
    try:
        dependencies = _dependency_hashes(root)
    except OSError as exc:
        errors.append(f"results manifest: cannot hash trusted dependency: {exc}")
        return errors
    if admission.get("dependencySha256") != dependencies:
        errors.append("results manifest: trusted dependency hashes do not match")
    for relative, item in declared.items():
        artifact_type = item.get("artifactType")
        if artifact_type not in SUPPORTED_RESULT_TYPES:
            errors.append(f"{relative}: unsupported result artifact type {artifact_type!r}")
            continue
        path = root / relative
        try:
            is_regular_file = stat.S_ISREG(path.lstat().st_mode)
        except OSError:
            is_regular_file = False
        if not is_regular_file:
            errors.append(f"{relative}: declared artifact is absent or not an exact regular file")
            continue
        if hashlib.sha256(path.read_bytes()).hexdigest() != item.get("sha256"):
            errors.append(f"{relative}: artifact SHA-256 mismatch")
        schema_name = SUPPORTED_RESULT_TYPES[artifact_type]
        if schema_name:
            try:
                value = _load_json(path)
                loaded[relative] = value
                errors.extend(f"{relative}: {error}" for error in _schema_errors(value, schema_name, root))
                if artifact_type == "source-packet":
                    _validate_packet(value)
                    _require_authorized_config(value["config"], root)
                elif artifact_type == "attempt-summary":
                    errors.extend(
                        f"{relative}: {error}"
                        for error in validate_attempt_summary_artifact(value, root)
                    )
                elif artifact_type == "run":
                    errors.extend(f"{relative}: {error}" for error in validate_run_artifact(value, root))
                elif artifact_type == "identified-review-packet":
                    for case in value.get("cases", []):
                        for candidate in case.get("candidates", []):
                            _public_safety(
                                candidate.get("publicSafety"), "sanitized-final-model-output",
                                f"{relative}.{case.get('caseId')}.{candidate.get('runId')}",
                            )
                            _require_authorized_config(candidate["config"], root)
                            scan_public_text(
                                {key: candidate.get(key) for key in ("titleEnglish", "bodyEnglish", "issues", "publicSafety")},
                                relative,
                            )
                elif artifact_type == "review":
                    _public_safety(
                        value.get("publicSafety"), "identified-human-public-review", relative,
                        value.get("reviewer", {}).get("publicId"),
                    )
                    scan_public_text(
                        {
                            "reviewerPublicId": value.get("reviewer", {}).get("publicId"),
                            "publicSafety": value.get("publicSafety"),
                            "assessments": [
                                {"materialErrors": assessment.get("materialErrors"), "notes": assessment.get("notes")}
                                for case in value.get("cases", [])
                                for assessment in case.get("assessments", [])
                            ],
                        },
                        relative,
                    )
                elif artifact_type == "score":
                    scan_public_text(
                        {
                            "reviewerPublicId": value.get("reviewerPublicId"),
                            "reviews": [review
                                for run in value.get("runs", {}).values()
                                for review in run.get("reviews", [])],
                            "roleGates": value.get("roleGates"),
                        },
                        relative,
                    )
            except (EvaluationError, KeyError, TypeError) as exc:
                errors.append(f"{relative}: public artifact validation failed: {exc}")
        if artifact_type == "report":
            try:
                scan_public_text(path.read_text(encoding="utf-8"), relative)
                inputs = item["reportInputs"]
                _validate_report_inputs(inputs, declared)
                scorer_path = root / "scripts/score_local_model_evaluation.py"
                spec = importlib.util.spec_from_file_location("score_for_result_validation", scorer_path)
                scorer = importlib.util.module_from_spec(spec)
                assert spec.loader is not None
                spec.loader.exec_module(scorer)
                cases = _load_json(root / inputs["cases"])
                runs = [_load_json(root / value) for value in inputs["runs"]]
                packet = _load_json(root / inputs["packet"])
                reviews = _load_json(root / inputs["reviews"]) if inputs.get("reviews") else None
                score = _load_json(root / inputs["score"]) if inputs.get("score") else None
                if scorer.render_report(cases, runs, packet, reviews, score) != path.read_text(encoding="utf-8"):
                    errors.append(f"{relative}: report is not deterministic/reproducible")
            except (EvaluationError, OSError, KeyError, TypeError) as exc:
                errors.append(f"{relative}: report regeneration failed: {exc}")
        if artifact_type == "public-index":
            try:
                content = path.read_text(encoding="utf-8")
                scan_public_text(content, relative)
                if relative != "evaluations/local-model/v1/results/README.md":
                    errors.append(f"{relative}: public index must be the declared results README")
                elif content != render_public_results_index():
                    errors.append(f"{relative}: public index is not deterministic/reproducible")
            except (EvaluationError, OSError, UnicodeError) as exc:
                errors.append(f"{relative}: public index validation failed: {exc}")
    try:
        errors.extend(_validate_declared_result_graph(root, declared, dependencies, loaded))
    except (EvaluationError, OSError, KeyError, TypeError) as exc:
        errors.append(f"results manifest: graph validation failed: {exc}")
    return errors


def validate_repository_contract(root: Path) -> list[str]:
    errors: list[str] = []
    base = root / "evaluations/local-model/v1"
    try:
        manifest = _load_json(base / "cases.json")
        configs = [_load_json(path) for path in sorted((base / "configs").glob("*.json"))]
        smoke, gates = _load_json(base / "smoke-evidence.json"), _load_json(base / "role-gates.json")
        decision, rubric = _load_json(base / "decision-log.json"), _load_json(base / "rubric.json")
        admission = _load_json(base / "results-manifest.json")
        errors.extend(_schema_errors(manifest, "local-model-evaluation-cases.v1.schema.json", root))
        for config in configs:
            errors.extend(_schema_errors(config, "local-model-evaluation-config.v1.schema.json", root))
        if errors:
            return errors
        validate_manifest_integrity(manifest)
    except EvaluationError as exc:
        return [str(exc)]
    errors.extend(_validate_protocol_hashes(root, manifest))
    for config in configs:
        if config["promptSha256"] != manifest["policy"]["promptSha256"]:
            errors.append(f"{config['configId']}: prompt hash does not match selected protocol prompt hash")
        try:
            prepare_source_packet(manifest, config)
        except EvaluationError as exc:
            errors.append(str(exc))
    try:
        proposal = _load_json(root / "content/public-proposals/issue-0026.public-proposal.json")
        records = {record["id"]: record for record in proposal["records"]}
        for case in manifest["cases"]:
            record = records.get(case["sourceUnitId"])
            if record is None:
                errors.append(f"{case['caseId']}: source unit is absent from public proposal")
            elif case["arabic"] != record.get("arabic") or case["referenceEnglish"] != record.get("english"):
                errors.append(f"{case['caseId']}: case differs from locked public source/comparator")
            elif case["sourceExactTextSha256"] != record.get("source", {}).get("exactTextSha256"):
                errors.append(f"{case['caseId']}: exact source-text anchor mismatch")
    except (EvaluationError, KeyError, TypeError) as exc:
        errors.append(f"source validation failed: {exc}")
    attempts = smoke.get("attempts", [])
    passed = {item.get("profile") for item in attempts if item.get("result") == "passed"}
    if passed != {"low", "high", "xhigh"}:
        errors.append("smoke evidence: low, high, and xhigh must each have a passing attempt")
    xhigh = [item for item in attempts if item.get("profile") == "xhigh"]
    post_fix = [item for item in xhigh if item.get("attemptId") == "xhigh-post-fix-001"]
    if not any(item.get("result") != "passed" for item in xhigh):
        errors.append("smoke evidence: pre-fix xhigh failures must be preserved")
    if len(post_fix) != 1 or any(post_fix[0].get(key) != value for key, value in {
        "result": "passed", "smokeTemperature": 0.0, "profileTemperature": 0.2,
    }.items()):
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
    if not (base / "results").is_dir():
        errors.append("public results directory is missing")
    else:
        errors.extend(_validate_results_admission(root, admission))
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
    prepare_source_packet(manifest, config)


def validated_config_input_path(root: Path, raw_path: str) -> Path:
    repository = root.resolve()
    configs = (repository / "evaluations/local-model/v1/configs").resolve()
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = repository / candidate
    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(configs)
    except ValueError as exc:
        raise EvaluationError("config must resolve under the tracked configs directory") from exc
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", resolved.relative_to(repository).as_posix()],
        cwd=repository, check=False, capture_output=True,
    )
    if tracked.returncode != 0:
        raise EvaluationError("config must be an authorized tracked config")
    return resolved


def validated_public_result_output_path(root: Path, raw_path: str) -> Path:
    repository = root.resolve()
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = repository / candidate
    resolved = candidate.resolve(strict=False)
    results = (repository / RESULTS_RELATIVE).resolve(strict=False)
    try:
        relative = resolved.relative_to(results)
    except ValueError as exc:
        raise EvaluationError(f"output must be inside {RESULTS_RELATIVE}/") from exc
    if not relative.parts:
        raise EvaluationError(f"output must be a file inside {RESULTS_RELATIVE}/")
    ignored = subprocess.run(
        ["git", "check-ignore", "--quiet", "--", str(resolved.relative_to(repository))],
        cwd=repository, check=False, capture_output=True,
    )
    if ignored.returncode == 0:
        raise EvaluationError(f"public output must not be ignored under {RESULTS_RELATIVE}/")
    return resolved


def validated_public_result_input_path(root: Path, raw_path: str) -> Path:
    path = validated_public_result_output_path(root, raw_path)
    if not path.is_file():
        raise EvaluationError(f"public result input does not exist under {RESULTS_RELATIVE}/: {path.name}")
    return path


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
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("validate", help="validate tracked public evaluation contracts")
    prepare = commands.add_parser("prepare", help="write a source-only model packet")
    prepare.add_argument("--config", required=True); prepare.add_argument("--output", required=True)
    record = commands.add_parser("record", help="record sanitized final outputs as public evidence")
    record.add_argument("--packet", required=True); record.add_argument("--outputs", required=True)
    record.add_argument("--generated-at", required=True); record.add_argument("--resource-status", default="completed")
    record.add_argument("--resource-profile", default="xhigh"); record.add_argument("--limitation", action="append", default=[])
    record.add_argument("--output", required=True)
    attempt = commands.add_parser(
        "attempt-summary", help="record sanitized failed-attempt outcomes as ineligible public evidence"
    )
    attempt.add_argument("--packet", required=True); attempt.add_argument("--outcomes", required=True)
    attempt.add_argument("--generated-at", required=True); attempt.add_argument("--limitation", required=True)
    attempt.add_argument("--output", required=True)
    review = commands.add_parser("review-packet", help="build an identified public review packet")
    review.add_argument("--runs", nargs="+", required=True); review.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    if args.command == "validate":
        errors = validate_repository_contract(ROOT)
        if errors:
            raise EvaluationError("; ".join(errors))
        print("public identified evaluation protocol: valid")
        return 0
    output = validated_public_result_output_path(ROOT, args.output)
    manifest = _load_json(ROOT / "evaluations/local-model/v1/cases.json")
    if args.command == "prepare":
        config_path = validated_config_input_path(ROOT, args.config)
        config = _load_json(config_path)
        validate_prepare_inputs(ROOT, manifest, config)
        packet = prepare_source_packet(manifest, config)
        errors = _schema_errors(packet, "local-model-evaluation-packet.v1.schema.json", ROOT)
        if errors:
            raise EvaluationError("packet schema validation failed: " + "; ".join(errors))
        _write_json(output, packet); print(f"source-only packet: {packet['packetId']}"); return 0
    if args.command == "record":
        packet_path = validated_public_result_input_path(ROOT, args.packet)
        outputs_path = validated_public_result_input_path(ROOT, args.outputs)
        packet = _load_json(packet_path); outputs = _load_json_value(outputs_path)
        run = record_run(packet, outputs, args.generated_at, {
            "status": args.resource_status, "profile": args.resource_profile,
            "limitations": args.limitation,
        })
        errors = validate_run_artifact(run, ROOT)
        if errors:
            raise EvaluationError("run schema validation failed: " + "; ".join(errors))
        _write_json(output, run); print(f"public run: {run['runId']}; review unreviewed; no role"); return 0
    if args.command == "attempt-summary":
        packet_path = validated_public_result_input_path(ROOT, args.packet)
        outcomes_path = validated_public_result_input_path(ROOT, args.outcomes)
        packet = _load_json(packet_path)
        outcomes = _load_json_value(outcomes_path)
        summary = record_attempt_summary(
            packet, outcomes, args.generated_at, args.limitation, ROOT
        )
        errors = validate_attempt_summary_artifact(summary, ROOT)
        if errors:
            raise EvaluationError("attempt summary validation failed: " + "; ".join(errors))
        _write_json(output, summary)
        print(
            f"public attempt summary: {summary['attemptSummaryId']}; excluded from review, "
            "scoring, repeats, and role eligibility; no role"
        )
        return 0
    runs = [_load_json(validated_public_result_input_path(ROOT, path)) for path in args.runs]
    packet = build_identified_review_packet(manifest, runs)
    errors = _schema_errors(packet, "local-model-evaluation-identified-packet.v1.schema.json", ROOT)
    if errors:
        raise EvaluationError("identified packet schema validation failed: " + "; ".join(errors))
    _write_json(output, packet); print(f"identified review packet: {len(packet['cases'])} cases; unreviewed"); return 0


def main(argv: list[str] | None = None) -> int:
    try:
        return _main(argv)
    except EvaluationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

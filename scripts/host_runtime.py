#!/usr/bin/env python3
"""Local operational provenance, not authentication against a malicious host.

Read only an explicitly selected Codex rollout. Never retain prompts, responses,
paths, or raw logs. The coordinator records actual explicit tool overrides;
effective settings come separately from host-written turn_context metadata.
"""
from __future__ import annotations

import argparse
import copy
from pathlib import Path
from typing import Any

import execution_governance as governance
from public_boundary import canonical_json, sha256_text_file
from schema_validation import validate_schema_instance

SCHEMA = governance.ROOT / "schemas/runtime-host-evidence.v1.schema.json"


def configuration_for(method_id: str) -> dict[str, Any]:
    methods = [method for method in governance.load_active_registry()["methods"]
               if method["methodId"] == method_id]
    if len(methods) != 1:
        fail("unknown active method")
    return methods[0]["configuration"]


def fail(message: str) -> None:
    raise ValueError("host runtime: " + message)


def launch_request(kind: str, model: str, reasoning: str) -> dict[str, Any]:
    """Record the literal tool overrides; never infer either required setting."""
    if kind == "codex-task":
        return {"kind": kind, "overrides": {"model": model, "thinking": reasoning}}
    if kind == "codex-worker":
        return {"kind": kind, "overrides": {
            "model": model, "reasoning_effort": reasoning, "fork_turns": "none",
        }}
    fail("unsupported launch interface")


def request_errors(request: Any, configuration: dict[str, Any], kind: str) -> list[str]:
    if not isinstance(request, dict) or request != launch_request(
        kind, configuration["model"], configuration["reasoning"]
    ):
        return ["host runtime: explicit approved launch overrides required"]
    return []


def observe_session(path: Path, session_id: str, turn_id: str) -> dict[str, Any]:
    """Versioned adapter for Codex session_meta / turn_context JSONL records.

    The log may contain private expression: parse it in memory, select metadata
    only, and never include raw lines, parser exceptions, or locators in errors.
    No directory discovery, session listing, or fallback to packet labels.
    """
    metadata = []
    turns = []
    selected = []
    try:
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                row = governance.parse_json(line)
                if not isinstance(row, dict):
                    fail("invalid session record")
                payload = row.get("payload", {})
                if row.get("type") in {"session_meta", "turn_context"} and not isinstance(payload, dict):
                    fail("invalid host metadata object")
                if row.get("type") == "session_meta":
                    metadata.append(payload)
                elif row.get("type") == "turn_context":
                    current = payload.get("turn_id")
                    if not isinstance(current, str) or not current:
                        fail("missing host turn identity")
                    if current not in turns:
                        turns.append(current)
                    if current == turn_id:
                        selected.append({"model": payload.get("model"), "reasoning": payload.get("effort")})
    except (OSError, ValueError, TypeError, AttributeError):
        fail("selected session metadata is unreadable or malformed")
    if len(metadata) != 1 or not selected:
        fail("exact session and turn metadata required")
    meta = metadata[0]
    if meta.get("id") != session_id or meta.get("session_id", session_id) != session_id:
        fail("session identity mismatch")
    if any(item != selected[0] for item in selected):
        fail("effective settings changed within the selected turn")
    if not all(isinstance(value, str) and value for value in selected[0].values()):
        fail("effective host model and reasoning are required")
    provider = meta.get("model_provider")
    if not isinstance(provider, str) or not provider:
        fail("effective host provider is required")
    return {
        "source": "codex-session-metadata", "sessionId": session_id, "turnId": turn_id,
        "provider": provider, **selected[0], "firstTurn": turns[0] == turn_id,
        "forked": bool(meta.get("forked_from_id") or meta.get("forked_from")),
    }


def launch_errors(launch: dict[str, Any], configuration: dict[str, Any], kind: str) -> list[str]:
    errors = request_errors(launch["request"], configuration, kind)
    if configuration["orchestration"] != "explicit-fresh-host-runtime-v1" or configuration["configurationOrigin"] != "explicit":
        errors.append("host runtime: configuration does not describe this host launch adapter")
    observed = launch["observed"]
    if any(observed[field] != configuration[field] for field in ("provider", "model", "reasoning")):
        errors.append("host runtime: requested and effective settings disagree or are unapproved")
    if kind == "codex-worker" and (not observed["firstTurn"] or observed["forked"]):
        errors.append("host runtime: semantic worker must use fresh non-forked context")
    return errors


def validate_execution(provenance: dict[str, Any], stage: str) -> list[str]:
    execution = provenance.get("execution")
    if not isinstance(execution, dict):
        return ["host runtime: captured host evidence is required; self-report is insufficient"]
    errors = governance.schema_errors(execution, SCHEMA) + governance.public_errors(execution)
    if errors:
        return errors
    try:
        registry = governance.load_active_registry()
        registry_hash = sha256_text_file(governance.REGISTRY_PATH)
    except (OSError, ValueError, KeyError):
        return ["host runtime: active registry unavailable or invalid"]
    methods = [method for method in registry["methods"]
               if method["methodId"] == execution["methodId"] and stage in method["stages"]]
    if len(methods) != 1 or registry["runtimeTrustStatus"] != "trusted-local-host":
        return ["host runtime: method not active for this stage and trust model"]
    if execution["registrySha256"] != registry_hash:
        errors.append("host runtime: stale registry binding")
    configuration = methods[0]["configuration"]
    errors.extend(launch_errors(execution["task"], configuration, "codex-task"))
    errors.extend(launch_errors(execution["worker"], configuration, "codex-worker"))
    observed = execution["worker"]["observed"]
    binding = execution["binding"]
    if binding["stage"] != stage:
        errors.append("host runtime: wrong semantic stage")
    for field in ("sessionId", "turnId"):
        if binding[field] != observed[field]:
            errors.append("host runtime: session or turn binding mismatch")
    for field, source in (("runId", "runId"), ("inputSha256", "inputSha256"),
                          ("outputSha256", "outputSha256"), ("checkpointSha256", "fingerprint")):
        if binding[field] != provenance.get(source):
            errors.append("host runtime: run, input, output or checkpoint mismatch")
    if any(provenance.get(field) != observed[field] for field in ("model", "reasoning")):
        errors.append("host runtime: effective settings and worker self-report disagree")
    if provenance.get("origin") != "direct_execution":
        errors.append("host runtime: historical rebinding is not new execution")
    if observed["sessionId"] == execution["task"]["observed"]["sessionId"]:
        errors.append("host runtime: worker reused the production task context")
    return errors


def capture_launch(request: dict[str, Any], log: Path, session_id: str,
                   turn_id: str, kind: str, method_id: str) -> dict[str, Any]:
    configuration = configuration_for(method_id)
    if request_errors(request, configuration, kind):
        fail("explicit approved launch overrides required")
    launch = {"request": copy.deepcopy(request), "observed": observe_session(log, session_id, turn_id)}
    launch_schema = governance.read_json(SCHEMA)["properties"]["task"]
    if validate_schema_instance(launch, launch_schema) or governance.public_errors(launch) or launch_errors(launch, configuration, kind):
        fail("launch metadata does not match approved configuration or context")
    return launch


def capture_execution(provenance: dict[str, Any], stage: str, method_id: str,
                      task: dict[str, Any], worker: dict[str, Any]) -> dict[str, Any]:
    evidence = {
        "schemaVersion": "1.0.0", "trustModel": "trusted-local-host",
        "methodId": method_id, "registrySha256": sha256_text_file(governance.REGISTRY_PATH),
        "task": copy.deepcopy(task), "worker": copy.deepcopy(worker),
        "binding": {
            "stage": stage, "runId": provenance.get("runId"),
            "sessionId": worker["observed"]["sessionId"], "turnId": worker["observed"]["turnId"],
            "inputSha256": provenance.get("inputSha256"), "outputSha256": provenance.get("outputSha256"),
            "checkpointSha256": provenance.get("fingerprint"),
        },
    }
    errors = validate_execution({**provenance, "execution": evidence}, stage)
    if errors:
        fail("capture rejected: " + "; ".join(errors))
    return evidence


def write_runtime(path: Path, value: Any) -> None:
    if not path.resolve().is_relative_to(governance.ROOT.resolve() / ".runtime"):
        fail("output must remain under ignored repository runtime")
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        fail("capture output must not traverse filesystem links")
    # Exclusive creation prevents silently replacing previously captured evidence.
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(canonical_json(value))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    request = commands.add_parser("request", help="record actual explicit launch overrides before launching")
    request.add_argument("--kind", choices=("codex-task", "codex-worker"), required=True)
    request.add_argument("--model", required=True)
    request.add_argument("--method-id", required=True)
    request.add_argument("--reasoning", required=True)
    request.add_argument("--output", type=Path, required=True)
    capture = commands.add_parser("capture-launch", help="project allowlisted host metadata for a selected session/turn")
    capture.add_argument("--kind", choices=("codex-task", "codex-worker"), required=True)
    capture.add_argument("--method-id", required=True)
    capture.add_argument("--request", type=Path, required=True)
    capture.add_argument("--session-log", type=Path, required=True)
    capture.add_argument("--session-id", required=True)
    capture.add_argument("--turn-id", required=True)
    capture.add_argument("--output", type=Path, required=True)
    bind = commands.add_parser("bind", help="bind captured task/worker metadata to completed stage provenance")
    bind.add_argument("--provenance", type=Path, required=True)
    bind.add_argument("--stage", choices=governance.STAGES, required=True)
    bind.add_argument("--method-id", required=True)
    bind.add_argument("--task-launch", type=Path, required=True)
    bind.add_argument("--worker-launch", type=Path, required=True)
    bind.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "request":
            value = launch_request(args.kind, args.model, args.reasoning)
            configuration = configuration_for(args.method_id)
            if request_errors(value, configuration, args.kind):
                fail("explicit approved launch overrides required")
        elif args.command == "capture-launch":
            value = capture_launch(governance.read_json(args.request), args.session_log,
                                   args.session_id, args.turn_id, args.kind, args.method_id)
        else:
            value = capture_execution(governance.read_json(args.provenance), args.stage, args.method_id,
                                      governance.read_json(args.task_launch), governance.read_json(args.worker_launch))
        write_runtime(args.output, value)
    except (OSError, ValueError, KeyError, TypeError):
        print("Host runtime capture rejected; check explicit settings, selected metadata, bindings and fresh output path.")
        return 1
    print("Minimal host metadata written under ignored runtime; trusted-host assumption, not cryptographic proof.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

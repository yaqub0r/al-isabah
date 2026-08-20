#!/usr/bin/env python3
"""Score and render local-model evaluation artifacts separately from execution."""

from __future__ import annotations

import argparse
import html
import importlib.util
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _load_runner():
    spec = importlib.util.spec_from_file_location(
        "local_model_evaluation_for_scoring", ROOT / "scripts/local_model_evaluation.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


RUNNER = _load_runner()


class ScoringError(RuntimeError):
    """Raised when blinded human-review evidence is incomplete or inconsistent."""


def _fail(label: str, errors: list[str]) -> None:
    if errors:
        raise ScoringError(f"{label} schema validation failed: " + "; ".join(errors))


def _schema_errors(value: Any, schema_name: str, root: Path) -> list[str]:
    try:
        return RUNNER._schema_errors(value, schema_name, root)
    except RUNNER.EvaluationError as exc:
        raise ScoringError(str(exc)) from exc


def _validate_runs(cases: list[dict[str, Any]], runs: list[dict[str, Any]]) -> None:
    try:
        RUNNER._validate_runs_for_cases(cases, runs)
    except RUNNER.EvaluationError as exc:
        raise ScoringError(str(exc)) from exc


def _validate_tracked_manifest_and_runs(
    manifest: dict[str, Any], runs: list[dict[str, Any]], root: Path = ROOT
) -> None:
    tracked_manifest = _load_json(root / "evaluations/local-model/v1/cases.json")
    if manifest != tracked_manifest:
        raise ScoringError("supplied cases artifact does not exactly match the tracked cases manifest")
    try:
        RUNNER.validate_anonymization_inputs(tracked_manifest, runs)
    except RUNNER.EvaluationError as exc:
        raise ScoringError(str(exc)) from exc


def _validate_bindings(
    cases: list[dict[str, Any]],
    runs: list[dict[str, Any]],
    packet: dict[str, Any],
    key: dict[str, Any],
    reviews: dict[str, Any],
) -> None:
    _validate_runs(cases, runs)
    try:
        expected_packet, expected_key = RUNNER.build_blind_review_packet(cases, runs, key.get("seed"))
    except RUNNER.EvaluationError as exc:
        raise ScoringError(str(exc)) from exc
    if packet != expected_packet or key != expected_key:
        raise ScoringError("review packet or alias key does not match supplied cases, runs, and seed")
    if packet.get("reviewPacketId") != RUNNER.review_packet_id_for(packet):
        raise ScoringError("review packet identity/hash mismatch")
    packet_hash = RUNNER.artifact_sha256(packet)
    cases_hash = RUNNER.artifact_sha256(cases)
    if packet.get("casesSha256") != cases_hash:
        raise ScoringError("review packet is unrelated to supplied cases")
    if key.get("reviewPacketId") != packet.get("reviewPacketId") or key.get("reviewPacketSha256") != packet_hash:
        raise ScoringError("alias key is not bound to review packet")
    if reviews.get("reviewPacketId") != packet.get("reviewPacketId") or reviews.get("reviewPacketSha256") != packet_hash:
        raise ScoringError("review worksheet is not bound to review packet")
    run_ids = [run["runId"] for run in runs]
    if key.get("runIds") != run_ids:
        raise ScoringError("alias key is unrelated to supplied runs")
    aliases = key.get("aliases")
    if not isinstance(aliases, dict) or set(aliases) != set(run_ids):
        raise ScoringError("alias key does not exactly cover supplied runs")
    alias_values = list(aliases.values())
    if len(alias_values) != len(set(alias_values)):
        raise ScoringError("alias key contains duplicate aliases")
    expected_hashes = {run["runId"]: RUNNER.artifact_sha256(run) for run in runs}
    if key.get("runArtifactSha256") != expected_hashes:
        raise ScoringError("alias key run hashes do not match supplied runs")
    if packet.get("runArtifactSha256") != [expected_hashes[run_id] for run_id in run_ids]:
        raise ScoringError("review packet run hashes do not match supplied runs")
    if packet.get("evaluationId") != runs[0]["evaluationId"] or key.get("evaluationId") != runs[0]["evaluationId"]:
        raise ScoringError("evaluation identity mismatch")
    if packet.get("policySha256") != runs[0]["policySha256"] or key.get("policySha256") != runs[0]["policySha256"]:
        raise ScoringError("policy identity mismatch")


def _comparable_config_key(run: dict[str, Any]) -> str:
    return RUNNER.artifact_sha256(run["config"])


def _repeat_counts(runs: list[dict[str, Any]]) -> tuple[dict[str, int], int]:
    counts = Counter(_comparable_config_key(run) for run in runs)
    by_config = {
        run["config"]["configId"]: counts[_comparable_config_key(run)]
        for run in runs
    }
    return by_config, min(counts.values())


def _role_gates(
    held_out_count: int,
    minimum_repeat_count: int,
    runs: dict[str, Any],
    gates: dict[str, Any],
) -> dict[str, Any]:
    roles = gates.get("roles")
    if not isinstance(roles, dict):
        raise ScoringError("role gates must contain roles")
    try:
        draft = roles["draft_assistance"]
        draft_reasons = []
        if held_out_count < draft["minimumHeldOutCases"]:
            draft_reasons.append(
                f"requires at least {draft['minimumHeldOutCases']} held-out cases; observed {held_out_count}"
            )
        if minimum_repeat_count < draft["minimumRepeats"]:
            draft_reasons.append(
                f"requires at least {draft['minimumRepeats']} repeats; observed {minimum_repeat_count}"
            )
        maximum_errors = draft["maximumMaterialErrors"]
        if any(run["materialErrorCount"] > maximum_errors for run in runs.values()):
            draft_reasons.append(f"requires at most {maximum_errors} material errors in every candidate run")
        critique = roles["critique_triage"]
        semantic = roles["semantic_authority"]
    except (KeyError, TypeError) as exc:
        raise ScoringError(f"malformed role gates: {exc}") from exc
    return {
        "draft_assistance": {
            "status": "blocked" if draft_reasons else "eligible-for-decision",
            "reasons": draft_reasons,
        },
        "critique_triage": {
            "status": "blocked",
            "reasons": [
                f"requires a separate set of at least {critique['minimumSeededErrorCases']} seeded-error cases, "
                f"recall of at least {critique['minimumRecall']}, and {critique['minimumRepeats']} repeats"
            ],
        },
        "semantic_authority": {
            "status": semantic["status"],
            "reasons": [semantic["decision"]],
        },
    }


def score_reviews(
    cases: list[dict[str, Any]],
    runs: list[dict[str, Any]],
    packet: dict[str, Any],
    key: dict[str, Any],
    reviews: dict[str, Any],
    gates: dict[str, Any],
    root: Path = ROOT,
) -> dict[str, Any]:
    _fail("review", _schema_errors(reviews, "local-model-evaluation-review.v1.schema.json", root))
    try:
        dimensions = [
            candidate[name]
            for case_review in reviews["cases"]
            for candidate in case_review["candidates"]
            for name in ("fidelity", "structure", "uncertainty", "formula")
        ]
    except (KeyError, TypeError) as exc:
        raise ScoringError(f"review schema validation failed: malformed dimensions: {exc}") from exc
    if any(not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 2 for value in dimensions):
        raise ScoringError("review schema validation failed: dimensions must be integers from 0 to 2")
    _fail("review packet", _schema_errors(packet, "local-model-evaluation-blind-packet.v1.schema.json", root))
    _fail("alias key", _schema_errors(key, "local-model-evaluation-alias-key.v1.schema.json", root))
    _validate_bindings(cases, runs, packet, key, reviews)
    run_by_id = {run["runId"]: run for run in runs}
    alias_to_run = {alias: run_id for run_id, alias in key["aliases"].items()}
    expected_cases = [case["caseId"] for case in cases]
    observed_cases = [case["caseId"] for case in reviews["cases"]]
    if observed_cases != expected_cases:
        raise ScoringError("reviews must exactly cover cases in order")
    accumulators: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"scoreTotal": 0, "ratingCount": 0, "materialErrorCount": 0, "reviews": []}
    )
    for case_review in reviews["cases"]:
        candidate_aliases = [item["alias"] for item in case_review["candidates"]]
        if len(candidate_aliases) != len(set(candidate_aliases)):
            raise ScoringError(f"{case_review['caseId']}: duplicate candidate alias")
        if candidate_aliases != [candidate["alias"] for candidate in next(case for case in packet["cases"] if case["caseId"] == case_review["caseId"])["candidates"]]:
            raise ScoringError(f"{case_review['caseId']}: candidates do not match review packet aliases in order")
        if set(candidate_aliases) != set(alias_to_run):
            raise ScoringError(f"{case_review['caseId']}: candidates do not cover every alias")
        for candidate in case_review["candidates"]:
            run_id = alias_to_run[candidate["alias"]]
            dimensions = [candidate[name] for name in ("fidelity", "structure", "uncertainty", "formula")]
            entry = accumulators[run_id]
            entry["scoreTotal"] += sum(dimensions)
            entry["ratingCount"] += len(dimensions)
            entry["materialErrorCount"] += len(candidate["materialErrors"])
            entry["reviews"].append(
                {
                    "caseId": case_review["caseId"],
                    "dimensions": dict(zip(("fidelity", "structure", "uncertainty", "formula"), dimensions)),
                    "materialErrors": candidate["materialErrors"],
                    "notes": candidate["notes"],
                }
            )
    scored_runs = {}
    for run_id in [run["runId"] for run in runs]:
        values = accumulators[run_id]
        scored_runs[run_id] = {
            "configId": run_by_id[run_id]["config"]["configId"],
            "averageDimensionScore": values["scoreTotal"] / values["ratingCount"],
            "materialErrorCount": values["materialErrorCount"],
            "reviews": values["reviews"],
        }
    held_out_count = sum(case.get("heldOut") is True for case in cases)
    repeats_by_config, minimum_repeat_count = _repeat_counts(runs)
    rubric = RUNNER._load_json(root / "evaluations/local-model/v1/rubric.json")
    score = {
        "schemaVersion": "1.0.0",
        "evaluationId": runs[0]["evaluationId"],
        "reviewPacketId": packet["reviewPacketId"],
        "reviewPacketSha256": RUNNER.artifact_sha256(packet),
        "casesSha256": RUNNER.artifact_sha256(cases),
        "runArtifactSha256": {run["runId"]: RUNNER.artifact_sha256(run) for run in runs},
        "aliasKeySha256": RUNNER.artifact_sha256(key),
        "worksheetSha256": RUNNER.artifact_sha256(reviews),
        "rubricSha256": RUNNER.artifact_sha256(rubric),
        "roleGatesSha256": RUNNER.artifact_sha256(gates),
        "reviewerId": reviews["reviewerId"],
        "caseCount": len(cases),
        "heldOutCount": held_out_count,
        "repeatsByConfig": repeats_by_config,
        "minimumRepeatCount": minimum_repeat_count,
        "runs": scored_runs,
        "roleGates": _role_gates(held_out_count, minimum_repeat_count, scored_runs, gates),
        "promotionStatus": "blocked",
    }
    score["scoreId"] = RUNNER.score_id_for(score)
    return score


def _safe_markdown(value: Any) -> str:
    text = str(value)
    text = re.sub(r"!\[([^]]*)\]\(([^)]+)\)", r"[remote image disabled: \1]", text)
    text = re.sub(r"\[([^]]+)\]\(([^)]+)\)", r"[link disabled: \1]", text)
    text = html.escape(text, quote=True)
    for character in ("\\", "`", "*", "_", "[", "]"):
        text = text.replace(character, "\\" + character)
    return text


def validate_score_artifact(score: dict[str, Any], root: Path = ROOT) -> list[str]:
    errors = _schema_errors(score, "local-model-evaluation-score.v1.schema.json", root)
    if not errors and score.get("scoreId") != RUNNER.score_id_for(score):
        errors.append("score identity/hash mismatch")
    return errors


def _validate_score_for_report(
    cases: list[dict[str, Any]],
    runs: list[dict[str, Any]],
    score: dict[str, Any],
    packet: dict[str, Any],
    key: dict[str, Any],
    reviews: dict[str, Any],
    root: Path = ROOT,
) -> None:
    errors = validate_score_artifact(score, root)
    if errors:
        raise ScoringError("score schema validation failed: " + "; ".join(errors))
    if score.get("casesSha256") != RUNNER.artifact_sha256(cases):
        raise ScoringError("score is not tied to supplied cases")
    expected_runs = {run["runId"]: RUNNER.artifact_sha256(run) for run in runs}
    if score.get("runArtifactSha256") != expected_runs or set(score.get("runs", {})) != set(expected_runs):
        raise ScoringError("score is not tied to supplied runs")
    rubric = RUNNER._load_json(root / "evaluations/local-model/v1/rubric.json")
    gates = RUNNER._load_json(root / "evaluations/local-model/v1/role-gates.json")
    if score.get("rubricSha256") != RUNNER.artifact_sha256(rubric):
        raise ScoringError("score does not match the tracked rubric")
    if score.get("roleGatesSha256") != RUNNER.artifact_sha256(gates):
        raise ScoringError("score does not match the tracked role gates")
    expected_cases = [case["caseId"] for case in cases]
    run_by_id = {run["runId"]: run for run in runs}
    derived_runs = {}
    dimension_names = ("fidelity", "structure", "uncertainty", "formula")
    for run_id, run_score in score["runs"].items():
        embedded_reviews = run_score.get("reviews", [])
        if [review.get("caseId") for review in embedded_reviews] != expected_cases:
            raise ScoringError(f"score review coverage does not match supplied cases for {run_id}")
        try:
            dimensions = [review["dimensions"][name] for review in embedded_reviews for name in dimension_names]
            material_error_count = sum(len(review["materialErrors"]) for review in embedded_reviews)
        except (KeyError, TypeError) as exc:
            raise ScoringError(f"malformed score review evidence for {run_id}: {exc}") from exc
        if any(not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 2 for value in dimensions):
            raise ScoringError(f"malformed score review dimensions for {run_id}")
        if not dimensions:
            raise ScoringError(f"score review evidence is empty for {run_id}")
        derived_runs[run_id] = {
            "configId": run_by_id[run_id]["config"]["configId"],
            "averageDimensionScore": sum(dimensions) / len(dimensions),
            "materialErrorCount": material_error_count,
            "reviews": embedded_reviews,
        }
    held_out_count = sum(case.get("heldOut") is True for case in cases)
    repeats_by_config, minimum_repeat_count = _repeat_counts(runs)
    if any(
        (
            score.get("caseCount") != len(cases),
            score.get("heldOutCount") != held_out_count,
            score.get("repeatsByConfig") != repeats_by_config,
            score.get("minimumRepeatCount") != minimum_repeat_count,
            score.get("runs") != derived_runs,
        )
    ):
        raise ScoringError("score totals do not match bound review evidence")
    expected_role_gates = _role_gates(held_out_count, minimum_repeat_count, derived_runs, gates)
    if score.get("roleGates") != expected_role_gates:
        raise ScoringError("score role-gate outcomes do not match bound evidence and tracked role gates")
    rederived_score = score_reviews(cases, runs, packet, key, reviews, gates, root)
    if score != rederived_score:
        raise ScoringError("score does not match rederived review evidence")


def render_report(
    cases: list[dict[str, Any]],
    runs: list[dict[str, Any]],
    score: dict[str, Any],
    packet: dict[str, Any] | None = None,
    key: dict[str, Any] | None = None,
    reviews: dict[str, Any] | None = None,
) -> str:
    if packet is None or key is None or reviews is None:
        raise ScoringError("review packet, alias key, and reviewer worksheet are required")
    tracked_manifest = _load_json(ROOT / "evaluations/local-model/v1/cases.json")
    if cases != tracked_manifest.get("cases"):
        raise ScoringError("supplied cases do not exactly match the tracked cases manifest")
    try:
        RUNNER.validate_anonymization_inputs(tracked_manifest, runs)
    except RUNNER.EvaluationError as exc:
        raise ScoringError(str(exc)) from exc
    _validate_score_for_report(cases, runs, score, packet, key, reviews)
    lines = [
        "# Al-Isabah local-model evaluation report",
        "",
        f"Human reviewer: `{_safe_markdown(score['reviewerId'])}`",
        f"Cases: {score['caseCount']} (held out: {score['heldOutCount']}); minimum comparable repeats: {score['minimumRepeatCount']}",
        "Promotion: **blocked**",
        "",
        "This report presents final outputs and review evidence only. Private reasoning traces and raw controller logs are excluded.",
        "",
    ]
    outputs = {run["runId"]: {item["caseId"]: item for item in run["outputs"]} for run in runs}
    review_evidence = {
        (run_id, item["caseId"]): item
        for run_id, run_score in score["runs"].items()
        for item in run_score["reviews"]
    }
    for case in cases:
        lines.extend([f"## {_safe_markdown(case['caseId'])}", "", "### Arabic source", "", _safe_markdown(case["arabic"]), ""])
        for run in runs:
            run_id = run["runId"]
            output = outputs[run_id][case["caseId"]]
            evidence = review_evidence[(run_id, case["caseId"])]
            lines.extend(
                [
                    f"### Candidate — `{_safe_markdown(run['config']['configId'])}`",
                    "",
                    "### Title",
                    "",
                    _safe_markdown(output["titleEnglish"]),
                    "",
                    "### Body",
                    "",
                    _safe_markdown(output["bodyEnglish"]),
                    "",
                    f"Declared issues: {_safe_markdown(output['issues'] or 'none')}",
                    f"Scores: {_safe_markdown(evidence['dimensions'])}; material errors: {_safe_markdown(evidence['materialErrors'] or 'none')}",
                    f"Reviewer notes: {_safe_markdown(evidence['notes'] or 'none')}",
                    "",
                ]
            )
    lines.extend(["## Role gates", ""])
    for role, gate in score["roleGates"].items():
        reasons = "; ".join(gate["reasons"]) or "all predeclared gates satisfied"
        lines.append(f"- **{_safe_markdown(role)}**: `{_safe_markdown(gate['status'])}` — {_safe_markdown(reasons)}")
    return "\n".join(lines) + "\n"


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return RUNNER._load_json(path)
    except RUNNER.EvaluationError as exc:
        raise ScoringError(str(exc)) from exc


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    score_parser = subparsers.add_parser("score", help="unblind and score completed human reviews")
    score_parser.add_argument("--cases", required=True)
    score_parser.add_argument("--runs", nargs="+", required=True)
    score_parser.add_argument("--packet", required=True)
    score_parser.add_argument("--key", required=True)
    score_parser.add_argument("--reviews", required=True)
    score_parser.add_argument("--output", required=True)
    report_parser = subparsers.add_parser("report", help="render the bilingual human report")
    report_parser.add_argument("--cases", required=True)
    report_parser.add_argument("--runs", nargs="+", required=True)
    report_parser.add_argument("--packet", required=True)
    report_parser.add_argument("--key", required=True)
    report_parser.add_argument("--reviews", required=True)
    report_parser.add_argument("--score", required=True)
    report_parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    output_path = RUNNER.validated_runtime_output_path(ROOT, args.output)
    manifest = _load_json(Path(args.cases))
    cases = manifest.get("cases")
    if not isinstance(cases, list):
        raise ScoringError("cases artifact must contain a cases array")
    runs = [_load_json(Path(path)) for path in args.runs]
    if args.command == "score":
        _validate_tracked_manifest_and_runs(manifest, runs, ROOT)
        packet = _load_json(Path(args.packet))
        key = _load_json(Path(args.key))
        reviews = _load_json(Path(args.reviews))
        gates = _load_json(ROOT / "evaluations/local-model/v1/role-gates.json")
        score = score_reviews(cases, runs, packet, key, reviews, gates, ROOT)
        _fail("score", validate_score_artifact(score, ROOT))
        RUNNER._write_json(output_path, score)
        print(f"score: {len(score['runs'])} runs; promotion blocked")
        return 0
    packet = _load_json(Path(args.packet))
    key = _load_json(Path(args.key))
    reviews = _load_json(Path(args.reviews))
    score = _load_json(Path(args.score))
    report = render_report(cases, runs, score, packet, key, reviews)
    RUNNER._write(output_path, report)
    print(f"report: {output_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        return _main(argv)
    except (ScoringError, RUNNER.EvaluationError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Score and report identified public local-model review evidence."""

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
    """Raised when identified public review evidence is incomplete or inconsistent."""


def _fail(label: str, errors: list[str]) -> None:
    if errors:
        raise ScoringError(f"{label} schema validation failed: " + "; ".join(errors))


def _schema_errors(value: Any, schema_name: str, root: Path) -> list[str]:
    try:
        return RUNNER._schema_errors(value, schema_name, root)
    except RUNNER.EvaluationError as exc:
        raise ScoringError(str(exc)) from exc


def _validate_tracked_manifest(manifest: dict[str, Any], root: Path = ROOT) -> None:
    tracked = _load_json(root / "evaluations/local-model/v1/cases.json")
    if manifest != tracked:
        raise ScoringError("supplied cases artifact does not exactly match the tracked cases manifest")


def _validate_packet(
    manifest: dict[str, Any], runs: list[dict[str, Any]], packet: dict[str, Any], root: Path = ROOT
) -> None:
    try:
        expected = RUNNER.build_identified_review_packet(manifest, runs, root)
    except RUNNER.EvaluationError as exc:
        raise ScoringError(str(exc)) from exc
    if packet != expected:
        raise ScoringError("identified review packet does not match supplied manifest and runs")
    if packet.get("reviewPacketId") != RUNNER.review_packet_id_for(packet):
        raise ScoringError("review packet identity/hash mismatch")


def _comparable_config_key(run: dict[str, Any]) -> str:
    return RUNNER.artifact_sha256(run["config"])


def _repeat_counts(runs: list[dict[str, Any]]) -> tuple[dict[str, int], int]:
    if any(run.get("resourceOutcome", {}).get("status") != "completed" for run in runs):
        raise ScoringError("repeat derivation requires completed runs only")
    counts = Counter(_comparable_config_key(run) for run in runs)
    by_config = {run["config"]["configId"]: counts[_comparable_config_key(run)] for run in runs}
    return by_config, min(counts.values())


def _role_gates(
    held_out_count: int, minimum_repeat_count: int, runs: dict[str, Any], gates: dict[str, Any]
) -> dict[str, Any]:
    roles = gates.get("roles")
    if not isinstance(roles, dict):
        raise ScoringError("role gates must contain roles")
    try:
        draft = roles["draft_assistance"]
        reasons = []
        if held_out_count < draft["minimumHeldOutCases"]:
            reasons.append(f"requires at least {draft['minimumHeldOutCases']} held-out cases; observed {held_out_count}")
        if minimum_repeat_count < draft["minimumRepeats"]:
            reasons.append(f"requires at least {draft['minimumRepeats']} repeats; observed {minimum_repeat_count}")
        maximum_errors = draft["maximumMaterialErrors"]
        if any(run["materialErrorCount"] > maximum_errors for run in runs.values()):
            reasons.append(f"requires at most {maximum_errors} material errors in every candidate run")
        critique, semantic = roles["critique_triage"], roles["semantic_authority"]
    except (KeyError, TypeError) as exc:
        raise ScoringError(f"malformed role gates: {exc}") from exc
    return {
        "draft_assistance": {"status": "blocked" if reasons else "eligible-for-decision", "reasons": reasons},
        "critique_triage": {
            "status": "blocked",
            "reasons": [
                f"requires a separate set of at least {critique['minimumSeededErrorCases']} seeded-error cases, "
                f"recall of at least {critique['minimumRecall']}, and {critique['minimumRepeats']} repeats"
            ],
        },
        "semantic_authority": {"status": semantic["status"], "reasons": [semantic["decision"]]},
    }


def _validate_review(
    manifest: dict[str, Any], runs: list[dict[str, Any]], packet: dict[str, Any],
    reviews: dict[str, Any], root: Path,
) -> None:
    reviewer = reviews.get("reviewer")
    if isinstance(reviewer, dict) and reviewer.get("publicationConsent") is not True:
        raise ScoringError("reviewer publication consent is required")
    if not isinstance(reviews.get("publicSafety"), dict):
        try:
            RUNNER._public_safety(
                reviews.get("publicSafety"), "identified-human-public-review", "review evidence"
            )
        except RUNNER.EvaluationError as exc:
            raise ScoringError(str(exc)) from exc
    _fail("review", _schema_errors(reviews, "local-model-evaluation-review.v1.schema.json", root))
    try:
        RUNNER.scan_public_text(
            {
                "reviewerPublicId": reviewer.get("publicId") if isinstance(reviewer, dict) else None,
                "publicSafety": reviews.get("publicSafety"),
                "assessments": [
                    {"materialErrors": assessment.get("materialErrors"), "notes": assessment.get("notes")}
                    for case in reviews.get("cases", []) if isinstance(case, dict)
                    for assessment in case.get("assessments", []) if isinstance(assessment, dict)
                ],
            },
            "$review",
        )
        RUNNER._public_safety(
            reviews.get("publicSafety"), "identified-human-public-review", "review evidence",
            reviewer.get("publicId") if isinstance(reviewer, dict) else None,
        )
    except RUNNER.EvaluationError as exc:
        raise ScoringError(str(exc)) from exc
    _validate_packet(manifest, runs, packet, root)
    packet_hash = RUNNER.artifact_sha256(packet)
    if reviews.get("reviewPacketId") != packet.get("reviewPacketId") or reviews.get("reviewPacketSha256") != packet_hash:
        raise ScoringError("review worksheet is not bound to the identified review packet")
    expected_cases = [case["caseId"] for case in manifest["cases"]]
    observed_cases = [case.get("caseId") for case in reviews["cases"]]
    if observed_cases != expected_cases:
        raise ScoringError("reviews must exactly cover cases in order")
    expected_runs = [run["runId"] for run in runs]
    for case_review in reviews["cases"]:
        observed_runs = [assessment.get("runId") for assessment in case_review["assessments"]]
        if observed_runs != expected_runs:
            raise ScoringError(f"{case_review['caseId']}: assessments must exactly cover runs in packet order")


def score_reviews(
    manifest: dict[str, Any], runs: list[dict[str, Any]], packet: dict[str, Any],
    reviews: dict[str, Any], gates: dict[str, Any], root: Path = ROOT,
) -> dict[str, Any]:
    _validate_tracked_manifest(manifest, root)
    trusted_gates = _load_json(root / "evaluations/local-model/v1/role-gates.json")
    if gates != trusted_gates:
        raise ScoringError("supplied role gates do not exactly match tracked role gates")
    gates = trusted_gates
    _validate_review(manifest, runs, packet, reviews, root)
    dimensions = ("fidelity", "structure", "uncertainty", "formula")
    accumulators: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"scoreTotal": 0, "ratingCount": 0, "materialErrorCount": 0, "reviews": []}
    )
    for case_review in reviews["cases"]:
        for assessment in case_review["assessments"]:
            values = [assessment[name] for name in dimensions]
            entry = accumulators[assessment["runId"]]
            entry["scoreTotal"] += sum(values)
            entry["ratingCount"] += len(values)
            entry["materialErrorCount"] += len(assessment["materialErrors"])
            entry["reviews"].append({
                "caseId": case_review["caseId"], "dimensions": dict(zip(dimensions, values)),
                "materialErrors": assessment["materialErrors"], "notes": assessment["notes"],
            })
    scored_runs = {}
    by_id = {run["runId"]: run for run in runs}
    for run in runs:
        values = accumulators[run["runId"]]
        scored_runs[run["runId"]] = {
            "configId": run["config"]["configId"], "model": run["config"]["model"],
            "averageDimensionScore": values["scoreTotal"] / values["ratingCount"],
            "materialErrorCount": values["materialErrorCount"], "reviews": values["reviews"],
        }
    held_out_count = sum(case.get("heldOut") is True for case in manifest["cases"])
    repeats_by_config, minimum_repeat_count = _repeat_counts(runs)
    rubric = RUNNER._load_json(root / "evaluations/local-model/v1/rubric.json")
    score = {
        "schemaVersion": "1.0.0", "evaluationId": manifest["evaluationId"],
        "reviewPacketId": packet["reviewPacketId"],
        "reviewPacketSha256": RUNNER.artifact_sha256(packet),
        "casesSha256": RUNNER.artifact_sha256(manifest["cases"]),
        "runArtifactSha256": {run["runId"]: RUNNER.artifact_sha256(run) for run in runs},
        "worksheetSha256": RUNNER.artifact_sha256(reviews),
        "rubricSha256": RUNNER.artifact_sha256(rubric),
        "roleGatesSha256": RUNNER.artifact_sha256(gates),
        "reviewerPublicId": reviews["reviewer"]["publicId"], "publicationConsent": True,
        "caseCount": len(manifest["cases"]), "heldOutCount": held_out_count,
        "repeatsByConfig": repeats_by_config, "minimumRepeatCount": minimum_repeat_count,
        "runs": scored_runs,
        "roleGates": _role_gates(held_out_count, minimum_repeat_count, scored_runs, gates),
        "reviewStatus": "complete", "promotionStatus": "blocked",
    }
    score["scoreId"] = RUNNER.score_id_for(score)
    return score


def validate_score_artifact(score: dict[str, Any], root: Path = ROOT) -> list[str]:
    errors = _schema_errors(score, "local-model-evaluation-score.v1.schema.json", root)
    if not errors and score.get("scoreId") != RUNNER.score_id_for(score):
        errors.append("score identity/hash mismatch")
    return errors


def _safe_markdown(value: Any) -> str:
    text = str(value)
    # Remove every GFM autolink/link target before escaping Markdown punctuation.
    text = re.sub(r"(?i)\b(?:https?://|www\.)[^\s<>\])]+", "[external URL disabled]", text)
    text = re.sub(r"(?i)\b(?:javascript|data|file|ftp|mailto|tel|sms|ssh|xmpp|irc|ircs|blob):[^\s<>\])]*", "[URI disabled]", text)
    text = re.sub(r"(?i)(?<![\w.+-])[\w.+-]+@[a-z0-9.-]+\.[a-z]{2,}(?![\w.-])", "[email disabled]", text)
    text = re.sub(r"!\[([^]]*)\]\([^)]*\)", r"[remote image disabled: \1]", text)
    text = re.sub(r"\[([^]]*)\]\([^)]*\)", r"[link disabled: \1]", text)
    text = re.sub(r"\[([^]]*)\]\s*\[[^]]*\]", r"[link disabled: \1]", text)
    text = re.sub(r"(?m)^\s*\[[^]]+\]:.*$", "[reference link disabled]", text)
    text = html.escape(text, quote=True)
    for character in ("\\", "`", "*", "_", "[", "]", "(", ")", "<", ">"):
        text = text.replace(character, "\\" + character)
    return text


def _config_identity(config: dict[str, Any]) -> str:
    digest = config.get("modelDigest") or "not disclosed"
    return (
        f"config={config['configId']}; model={config['model']}; engine={config['engine']} "
        f"{config['runtimeVersion']}; quantization={config['quantization']}; "
        f"profile={config['houseProfile']}; digest={digest}"
    )


def render_report(
    manifest: dict[str, Any], runs: list[dict[str, Any]], packet: dict[str, Any],
    reviews: dict[str, Any] | None = None, score: dict[str, Any] | None = None,
) -> str:
    _validate_tracked_manifest(manifest, ROOT)
    _validate_packet(manifest, runs, packet)
    if (reviews is None) != (score is None):
        raise ScoringError("review worksheet and score must be supplied together")
    if reviews is None:
        review_status, reviewer_id = "unreviewed", "none"
        review_by_key: dict[tuple[str, str], dict[str, Any]] = {}
        role_gates = {
            "all roles": {"status": "no-role", "reasons": ["human review is pending"]}
        }
    else:
        gates = RUNNER._load_json(ROOT / "evaluations/local-model/v1/role-gates.json")
        expected_score = score_reviews(manifest, runs, packet, reviews, gates, ROOT)
        if score != expected_score:
            raise ScoringError("score does not match rederived review evidence")
        errors = validate_score_artifact(score, ROOT)
        if errors:
            raise ScoringError("score schema validation failed: " + "; ".join(errors))
        review_status, reviewer_id = "complete", reviews["reviewer"]["publicId"]
        review_by_key = {
            (run_id, item["caseId"]): item
            for run_id, run_score in score["runs"].items()
            for item in run_score["reviews"]
        }
        role_gates = score["roleGates"]
    lines = [
        "# Al-Isabah identified public local-model evaluation report", "",
        f"Review status: **{review_status}**", "Role status: **no-role**",
        "Promotion status: **blocked**", f"Public reviewer ID: `{_safe_markdown(reviewer_id)}`", "",
        "Model identity is disclosed as evidence. Scoring remains source-based and identity must not be used as a shortcut.",
        "Only sanitized final outputs and public provenance are shown; thought traces, raw controller/agent logs, credentials, private paths, non-public evidence, and non-consenting personal information are excluded.", "",
    ]
    output_by_run = {run["runId"]: {item["caseId"]: item for item in run["outputs"]} for run in runs}
    for case in manifest["cases"]:
        lines.extend([f"## {_safe_markdown(case['caseId'])}", "", "### Arabic", "", _safe_markdown(case["arabic"]), ""])
        for run in runs:
            output = output_by_run[run["runId"]][case["caseId"]]
            evidence = review_by_key.get((run["runId"], case["caseId"]))
            lines.extend([
                f"### Model/config — {_safe_markdown(_config_identity(run['config']))}", "",
                "#### Title", "", _safe_markdown(output["titleEnglish"]), "",
                "#### Body", "", _safe_markdown(output["bodyEnglish"]), "",
                f"Declared issues: {_safe_markdown(output['issues'] or 'none')}",
                f"Review status: {'complete' if evidence else 'unreviewed'}",
            ])
            if evidence:
                lines.extend([
                    f"Scores: {_safe_markdown(evidence['dimensions'])}; material errors: {_safe_markdown(evidence['materialErrors'] or 'none')}",
                    f"Reviewer notes: {_safe_markdown(evidence['notes'])}",
                ])
            else:
                lines.extend(["Scores: not yet reviewed", "Reviewer notes: not yet reviewed"])
            lines.append("")
    lines.extend(["## Role gates", ""])
    for role, gate in role_gates.items():
        reasons = "; ".join(gate["reasons"]) or "all numerical prerequisites satisfied; human decision still required"
        lines.append(f"- **{_safe_markdown(role)}**: `{_safe_markdown(gate['status'])}` — {_safe_markdown(reasons)}")
    lines.extend([
        "", "## Limitations", "",
        "- This locked three-case slice is insufficient to grant a workflow role.",
        "- Reference English is a working comparator, not an unquestioned gold standard.",
        "- Numerical eligibility never grants promotion or semantic authority automatically.",
    ])
    return "\n".join(lines) + "\n"


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return RUNNER._load_json(path)
    except RUNNER.EvaluationError as exc:
        raise ScoringError(str(exc)) from exc


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    score_parser = commands.add_parser("score", help="score completed identified public reviews")
    report_parser = commands.add_parser("report", help="render pending or reviewed identified report")
    for item in (score_parser, report_parser):
        item.add_argument("--cases", required=True); item.add_argument("--runs", nargs="+", required=True)
        item.add_argument("--packet", required=True); item.add_argument("--output", required=True)
    score_parser.add_argument("--reviews", required=True)
    report_parser.add_argument("--reviews"); report_parser.add_argument("--score")
    args = parser.parse_args(argv)
    output = RUNNER.validated_public_result_output_path(ROOT, args.output)
    manifest = _load_json(Path(args.cases)); _validate_tracked_manifest(manifest, ROOT)
    runs = [_load_json(RUNNER.validated_public_result_input_path(ROOT, path)) for path in args.runs]
    packet = _load_json(RUNNER.validated_public_result_input_path(ROOT, args.packet))
    if args.command == "score":
        reviews = _load_json(RUNNER.validated_public_result_input_path(ROOT, args.reviews))
        gates = _load_json(ROOT / "evaluations/local-model/v1/role-gates.json")
        score = score_reviews(manifest, runs, packet, reviews, gates, ROOT)
        _fail("score", validate_score_artifact(score, ROOT))
        RUNNER._write_json(output, score); print(f"identified score: {len(runs)} runs; promotion blocked"); return 0
    if bool(args.reviews) != bool(args.score):
        raise ScoringError("--reviews and --score must be supplied together")
    reviews = _load_json(RUNNER.validated_public_result_input_path(ROOT, args.reviews)) if args.reviews else None
    score = _load_json(RUNNER.validated_public_result_input_path(ROOT, args.score)) if args.score else None
    RUNNER._write(output, render_report(manifest, runs, packet, reviews, score))
    print(f"public identified report: {output}"); return 0


def main(argv: list[str] | None = None) -> int:
    try:
        return _main(argv)
    except (ScoringError, RUNNER.EvaluationError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

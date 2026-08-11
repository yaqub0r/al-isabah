#!/usr/bin/env python3
"""Run blind, independent-critic, and adjudication passes on cohort context."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path


VERSIONS = {
    "blind": "khadijah-context-blind-v1",
    "critic": "khadijah-context-critic-v1",
    "adjudicate": "khadijah-context-adjudicate-v1",
}


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + ".tmp")
    pending.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pending.replace(path)


def context_items(classification: dict) -> list[dict]:
    sources = {item["result_id"]: item for item in classification["source_results"]}
    selected = []
    for item in classification["items"]:
        if item["decision"] != "include_context":
            continue
        selected.append({
            "result_id": item["result_id"],
            "source": sources[item["result_id"]],
            "relationship": item["relationship"],
            "rationale": item["rationale"],
            "arabic_text": item["relevant_arabic"],
            "arabic_sha256": sha256_text(item["relevant_arabic"]),
        })
    return selected


def assert_complete(items: list[dict], result: dict) -> None:
    expected = {item["result_id"] for item in items}
    observed = [item["result_id"] for item in result["items"]]
    if len(observed) != len(set(observed)) or set(observed) != expected:
        raise RuntimeError("Pass did not return every context result ID exactly once")


def prompt_for(stage: str, items: list[dict], prior: dict | None, critic: dict | None, witnesses: dict | None) -> str:
    common = """Translate Arabic as the authoritative text. Preserve attributions, qualifications, weak-report language, negations, numbers, genealogy, poetry, editorial brackets, and footnotes. Do not summarize. Use conventional English names and stable search-friendly transliteration without scholarly diacritics otherwise."""
    if stage == "blind":
        return f"""Make an independent scholarly Arabic-to-English translation of every supplied contextual passage from Ibn Hajar's al-Isabah. These passages add Khadijah material outside already translated complete entries. {common}

Return every result_id exactly once. Record genuine uncertainty without omitting a strongest rendering.

CONTEXT PASSAGES:
{json.dumps(items, ensure_ascii=False, indent=2)}
"""
    prior_by_id = {item["result_id"]: item for item in prior["items"]}
    review_items = [{**item, "proposed_english": prior_by_id[item["result_id"]]["english_text"]} for item in items]
    if stage == "critic":
        return f"""Act as an independent fidelity critic. Audit every proposed English passage line by line against its Arabic. You did not write these translations. {common}

Use witness_required only for a genuinely damaged or ambiguous reading that another edition could resolve. Return every result_id exactly once.

PASSAGES AND PROPOSED ENGLISH:
{json.dumps(review_items, ensure_ascii=False, indent=2)}
"""
    critic_by_id = {item["result_id"]: item for item in critic["items"]}
    witness_by_id = {item["result_id"]: item for item in (witnesses or {}).get("items", [])}
    final_items = [{**item, "blind_translation": prior_by_id[item["result_id"]], "independent_critique": critic_by_id[item["result_id"]], "collateral_witness_evidence": witness_by_id.get(item["result_id"], [])} for item in items]
    return f"""Act as the final autonomous adjudicator for these contextual passages from Ibn Hajar's al-Isabah. {common}

Correct every valid critic finding. Retain a human-facing unresolved item only when the Arabic itself remains damaged or ambiguous after the available evidence. Return every result_id exactly once.

PASSAGES, BLIND TRANSLATIONS, AND CRITIQUES:
{json.dumps(final_items, ensure_ascii=False, indent=2)}
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--classification", type=Path, required=True)
    parser.add_argument("--stage", choices=["blind", "critic", "adjudicate"], required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--codex", type=Path, required=True)
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--reasoning-effort", default="high")
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--witnesses", type=Path)
    args = parser.parse_args()
    for name in ("classification", "out_dir", "output", "codex", "schema"):
        setattr(args, name, getattr(args, name).resolve())
    classification = json.loads(args.classification.read_text(encoding="utf-8"))
    items = context_items(classification)
    prior_path = args.out_dir / "blind.json"
    critic_path = args.out_dir / "critic.json"
    prior = json.loads(prior_path.read_text(encoding="utf-8")) if prior_path.exists() else None
    critic = json.loads(critic_path.read_text(encoding="utf-8")) if critic_path.exists() else None
    witnesses = json.loads(args.witnesses.resolve().read_text(encoding="utf-8")) if args.witnesses else None
    if args.stage != "blind" and prior is None:
        raise RuntimeError("Blind context pass is required first")
    if args.stage == "adjudicate" and critic is None:
        raise RuntimeError("Critic context pass is required first")
    prompt = prompt_for(args.stage, items, prior, critic, witnesses)
    prompt_sha = sha256_text(prompt)
    output = args.out_dir / f"{args.stage}.json"
    if output.exists():
        current = json.loads(output.read_text(encoding="utf-8"))
        if current.get("prompt_sha256") == prompt_sha:
            atomic_json(args.output, current)
            print(json.dumps({"stage": args.stage, "state": "current", "items": len(items), "output": str(output)}, indent=2))
            return 0
    raw = args.out_dir / "raw" / f"{args.stage}.json"
    raw.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(args.codex), "--ask-for-approval", "never", "exec", "--ephemeral",
        "--skip-git-repo-check", "--sandbox", "read-only", "--model", args.model,
        "--config", f'model_reasoning_effort="{args.reasoning_effort}"',
        "--output-schema", str(args.schema), "--output-last-message", str(raw), "-",
    ]
    completed = subprocess.run(command, input=prompt, text=True, encoding="utf-8", errors="replace", capture_output=True, cwd=args.out_dir, env=os.environ.copy(), timeout=args.timeout_seconds)
    if completed.returncode != 0:
        raise RuntimeError(f"Codex failed ({completed.returncode}): {completed.stderr[-3000:]}")
    result = json.loads(raw.read_text(encoding="utf-8"))
    assert_complete(items, result)
    source_by_id = {item["result_id"]: item for item in items}
    records = []
    for item in result["items"]:
        source = source_by_id[item["result_id"]]
        records.append({
            "source": {key: source[key] for key in ("result_id", "source", "relationship", "rationale", "arabic_sha256")},
            **item,
        })
    payload = {
        "schema": f"al-isabah.cohort-context-{args.stage}.v1",
        "cohort_id": "khadijah-immediate",
        "stage": args.stage,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "model": args.model,
        "reasoning_effort": args.reasoning_effort,
        "prompt_version": VERSIONS[args.stage],
        "prompt_sha256": prompt_sha,
        "item_count": len(records),
        "items": records,
    }
    atomic_json(output, payload)
    atomic_json(args.output, payload)
    print(json.dumps({"stage": args.stage, "state": "completed", "items": len(records), "output": str(output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

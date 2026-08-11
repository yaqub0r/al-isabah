#!/usr/bin/env python3
"""Run resumable blind, critic, and adjudication passes over cohort entries."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path


PASS_VERSIONS = {"blind": "isabah-entry-blind-v1", "critic": "isabah-entry-critic-v1", "adjudicate": "isabah-entry-adjudication-v1"}


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + ".tmp")
    pending.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pending.replace(path)


def load_sources(manifest_path: Path, cache_root: Path) -> list[tuple[dict, dict]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    records = []
    for entry in manifest["entries"]:
        cached = json.loads((cache_root / entry["cache_key"]).read_text(encoding="utf-8"))
        if cached["arabic_text_sha256"] != entry["arabic_text_sha256"]:
            raise RuntimeError(f"Source hash mismatch for entry {entry['entry_number']}")
        records.append((entry, cached))
    return records


def prompt_for(stage: str, entry: dict, source: dict, prior: dict | None, critic: dict | None, witnesses: object) -> str:
    arabic = source["arabic_text"]
    common = """Preserve every substantive element: heading and entry number, genealogy, isnad links, quotations, negations, numbers, variants, poems, cross-references, editorial sigla, and footnotes. Do not summarize or silently omit. Use conventional English forms for established names and stable search-friendly transliteration without scholarly diacritics otherwise. Preserve ibn, bint, Abu, Umm, and al-. Arabic is authoritative."""
    if stage == "blind":
        return f"""You are making a blind scholarly Arabic-to-English translation of entry {entry['entry_number']} in Ibn Hajar al-Asqalani's al-Isabah fi Tamyiz al-Sahabah. You have no earlier English draft.

{common}

Translate the complete Arabic entry below. Record genuine textual or semantic uncertainty, but still give the strongest supported rendering. Return only schema-valid JSON.

CANONICAL ARABIC:
{arabic}
"""
    if stage == "critic":
        return f"""You are an independent fidelity critic. Audit the proposed English for entry {entry['entry_number']} line by line against the canonical Arabic. You did not write the translation. Fluent prose does not compensate for omitted or invented material.

{common}

Use pass only when there is no fidelity or name-policy defect. Use witness_required only for a genuine ambiguity or damaged reading another edition or language could help resolve. Return only schema-valid JSON.

CANONICAL ARABIC:
{arabic}

PROPOSED ENGLISH:
{prior['english_text']}
"""
    return f"""You are the final autonomous adjudicator for entry {entry['entry_number']} of Ibn Hajar al-Asqalani's al-Isabah fi Tamyiz al-Sahabah.

{common}

Produce the strongest complete English. Correct every valid critic finding. Treat witness material as diagnostic only: it may clarify shared names or syntax but must never replace or add to the canonical Arabic. Keep a matter unresolved only after the supplied autonomous evidence cannot decide it. Return only schema-valid JSON.

CANONICAL ARABIC:
{arabic}

BLIND TRANSLATION:
{prior['english_text']}

INDEPENDENT CRITIQUE:
{json.dumps(critic, ensure_ascii=False, indent=2)}

COLLATERAL WITNESS EVIDENCE:
{json.dumps(witnesses, ensure_ascii=False, indent=2)}
"""


def run_codex(codex: Path, schema: Path, prompt: str, result_path: Path, model: str, reasoning: str, timeout: int, work_dir: Path) -> None:
    command = [str(codex), "--ask-for-approval", "never", "exec", "--ephemeral", "--skip-git-repo-check", "--sandbox", "read-only", "--model", model, "--config", f'model_reasoning_effort="{reasoning}"', "--output-schema", str(schema), "--output-last-message", str(result_path), "-"]
    completed = subprocess.run(command, input=prompt, text=True, encoding="utf-8", errors="replace", capture_output=True, cwd=work_dir, env=os.environ.copy(), timeout=timeout)
    if completed.returncode != 0:
        raise RuntimeError(f"Codex failed ({completed.returncode}): {completed.stderr[-2000:]}")


def stage_one(stage: str, entry: dict, source: dict, args: argparse.Namespace) -> tuple[int, str]:
    number = int(entry["entry_number"])
    destination = args.out_dir / stage / f"{number:05d}.json"
    prior_path = args.out_dir / "blind" / f"{number:05d}.json"
    critic_path = args.out_dir / "critic" / f"{number:05d}.json"
    prior = json.loads(prior_path.read_text(encoding="utf-8")) if prior_path.exists() else None
    critique = json.loads(critic_path.read_text(encoding="utf-8")) if critic_path.exists() else None
    witnesses_path = args.out_dir / "witness" / f"{number:05d}.json"
    witnesses = json.loads(witnesses_path.read_text(encoding="utf-8")) if witnesses_path.exists() else []
    prompt = prompt_for(stage, entry, source, prior, critique, witnesses)
    expected = {"schema": f"al-isabah.cohort-{stage}-pass.v1", "cohort_id": args.cohort_id, "entry_number": number, "source_sha256": entry["arabic_text_sha256"], "model": args.model, "reasoning_effort": args.reasoning_effort, "prompt_version": PASS_VERSIONS[stage], "prompt_sha256": sha256_text(prompt)}
    if destination.exists():
        current = json.loads(destination.read_text(encoding="utf-8"))
        if all(current.get(key) == value for key, value in expected.items()):
            return number, "current"
    temporary = args.out_dir / "raw" / stage / f"{number:05d}.json"
    temporary.parent.mkdir(parents=True, exist_ok=True)
    run_codex(args.codex, args.schemas[stage], prompt, temporary, args.model, args.reasoning_effort, args.timeout_seconds, args.out_dir / "sandbox")
    model_output = json.loads(temporary.read_text(encoding="utf-8"))
    atomic_json(destination, {**expected, "completed_at": now_utc(), **model_output})
    return number, "completed"


def aggregate(stage: str, out_dir: Path, destination: Path) -> None:
    records = [json.loads(path.read_text(encoding="utf-8")) for path in sorted((out_dir / stage).glob("*.json"))]
    atomic_json(destination, {"schema": f"al-isabah.cohort-{stage}-aggregate.v1", "stage": stage, "entry_count": len(records), "entries": records})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-manifest", type=Path, required=True); parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True); parser.add_argument("--aggregate-output", type=Path, required=True)
    parser.add_argument("--codex", type=Path, required=True); parser.add_argument("--stage", choices=["blind", "critic", "adjudicate"], required=True)
    parser.add_argument("--cohort-id", default="khadijah-immediate"); parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--reasoning-effort", default="high"); parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--timeout-seconds", type=int, default=900); parser.add_argument("--entry", type=int, action="append", default=[])
    args = parser.parse_args()
    args.source_manifest = args.source_manifest.resolve()
    args.cache_root = args.cache_root.resolve()
    args.out_dir = args.out_dir.resolve()
    args.aggregate_output = args.aggregate_output.resolve()
    args.codex = args.codex.resolve()
    schema_root = Path(__file__).resolve().parents[1] / "evidence" / "schemas"
    args.schemas = {"blind": schema_root / "cohort-translation-pass.v1.schema.json", "critic": schema_root / "cohort-critique-pass.v1.schema.json", "adjudicate": schema_root / "cohort-adjudication-pass.v1.schema.json"}
    args.out_dir.mkdir(parents=True, exist_ok=True); (args.out_dir / "sandbox").mkdir(parents=True, exist_ok=True)
    selected = set(args.entry)
    sources = [(entry, source) for entry, source in load_sources(args.source_manifest, args.cache_root) if not selected or int(entry["entry_number"]) in selected]
    if args.stage in {"critic", "adjudicate"}:
        prerequisite = "blind" if args.stage == "critic" else "critic"
        missing = [entry["entry_number"] for entry, _ in sources if not (args.out_dir / prerequisite / f"{int(entry['entry_number']):05d}.json").exists()]
        if missing: raise RuntimeError(f"Missing {prerequisite} results: {missing}")
    results = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = [pool.submit(stage_one, args.stage, entry, source, args) for entry, source in sources]
        for future in as_completed(futures):
            number, state = future.result(); results.append((number, state)); print(f"{args.stage} {number}: {state}", flush=True)
    aggregate(args.stage, args.out_dir, args.aggregate_output)
    print(json.dumps({"stage": args.stage, "entries": len(results), "completed": sum(state == "completed" for _, state in results), "current": sum(state == "current" for _, state in results), "aggregate": str(args.aggregate_output)}, indent=2))
    return 0


if __name__ == "__main__": raise SystemExit(main())

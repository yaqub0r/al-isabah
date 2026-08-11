#!/usr/bin/env python3
"""Classify every literal Khadijah search result into the cohort coverage plan."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path


SCHEMA = "al-isabah.cohort-mention-classification.v1"
PROMPT_VERSION = "khadijah-exhaustive-mention-classification-v1"


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + ".tmp")
    pending.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pending.replace(path)


def unique_literal_results(discovery: dict, cache_root: Path) -> list[dict]:
    unique = {}
    for record in discovery["results"]:
        if record.get("literal_match"):
            unique.setdefault(record["result_id"], record)
    items = []
    for result_id, record in unique.items():
        cached = json.loads((cache_root / record["cache_key"]).read_text(encoding="utf-8"))
        if cached["sha256"] != record["text_sha256"]:
            raise RuntimeError(f"Search-result hash mismatch: {result_id}")
        result = cached["result"]
        items.append({
            "result_id": result_id,
            "pages": result["metadata"]["pages"],
            "text_sha256": record["text_sha256"],
            "text": result["text"],
        })
    return sorted(items, key=lambda item: (int(item["pages"][0]["index"]), item["result_id"]))


def build_prompt(items: list[dict], selected_entries: list[int]) -> str:
    return f"""You are performing exhaustive source triage for Khadijah bint Khuwaylid, wife of the Prophet Muhammad, in Ibn Hajar's al-Isabah. Classify every supplied literal Arabic search result exactly once.

The goal is the fullest defensible account of her life and immediate associates, including trade and marriage, household and children, earliest belief and revelation, death and remembrance, and conflicts in names, genealogy, or chronology.

Use these decisions:
- covered_selected_entry: the relevant passage belongs to one of the already translated complete entries {selected_entries}.
- covered_volume8: the relevant passage concerns the correct Khadijah and is in volume 8, whose complete entries are already translated.
- include_context: it adds a substantive fact about the correct Khadijah but is neither of the two covered categories.
- exclude_bare_relation: it merely says someone is her sibling, niece, nephew, or other relation and adds no fact about her or an immediate associate.
- exclude_other_person: it concerns another person named Khadijah or the masculine name Khudayj.
- exclude_non_narrative: incidental narrator, citation, or other occurrence that adds no story fact.

For include_context, copy the complete relevant Arabic passage verbatim into relevant_arabic; include enough surrounding isnad, attribution, qualification, and footnotes to preserve meaning. For all other decisions, relevant_arabic must be an empty string. Candidate entry numbers must include only printed biography numbers visibly supported by the block. Do not infer away weak reports or contradictions: they are relevant when they concern the subject. Return every result ID once and only once.

RESULTS:
{json.dumps(items, ensure_ascii=False, indent=2)}
"""


def is_extractive_excerpt(source: str, excerpt: str) -> bool:
    """Accept one or more exact source lines, including non-contiguous notes."""
    lines = [" ".join(line.split()) for line in excerpt.splitlines() if line.strip()]
    normalized_source = " ".join(source.split())
    return bool(lines) and all(line in normalized_source for line in lines)


def selected_source_texts(manifest_path: Path, cache_root: Path) -> list[tuple[int, str]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    sources = []
    for entry in manifest["entries"]:
        cached = json.loads((cache_root / entry["cache_key"]).read_text(encoding="utf-8"))
        sources.append((int(entry["entry_number"]), cached["arabic_text"]))
    return sources


def covered_selected_entry(excerpt: str, sources: list[tuple[int, str]]) -> int | None:
    lines = [" ".join(line.split()) for line in excerpt.splitlines() if line.strip() and set(line.strip()) != {"_"}]
    for entry_number, source in sources:
        normalized_source = " ".join(source.split())
        if lines and all(line in normalized_source for line in lines):
            return entry_number
    return None


def classify(
    items: list[dict],
    selected_entries: list[int],
    selected_sources: list[tuple[int, str]],
    args: argparse.Namespace,
) -> dict:
    prompt = build_prompt(items, selected_entries)
    raw = args.runtime_dir / "mention-classification.raw.json"
    raw.parent.mkdir(parents=True, exist_ok=True)
    if args.raw_input:
        result = json.loads(args.raw_input.read_text(encoding="utf-8"))
    else:
        command = [
            str(args.codex), "--ask-for-approval", "never", "exec", "--ephemeral",
            "--skip-git-repo-check", "--sandbox", "read-only", "--model", args.model,
            "--config", f'model_reasoning_effort="{args.reasoning_effort}"',
            "--output-schema", str(args.schema), "--output-last-message", str(raw), "-",
        ]
        completed = subprocess.run(
            command, input=prompt, text=True, encoding="utf-8", errors="replace",
            capture_output=True, cwd=args.runtime_dir, env=os.environ.copy(),
            timeout=args.timeout_seconds,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"Codex failed ({completed.returncode}): {completed.stderr[-3000:]}")
        result = json.loads(raw.read_text(encoding="utf-8"))
    expected = {item["result_id"] for item in items}
    observed = [item["result_id"] for item in result["items"]]
    if len(observed) != len(set(observed)) or set(observed) != expected:
        raise RuntimeError("Classifier did not return every result ID exactly once")
    source_by_id = {item["result_id"]: item for item in items}
    for item in result["items"]:
        excerpt = item["relevant_arabic"]
        if item["decision"] == "include_context":
            if not is_extractive_excerpt(source_by_id[item["result_id"]]["text"], excerpt):
                raise RuntimeError(f"Non-verbatim relevant excerpt: {item['result_id']}")
            covered_entry = covered_selected_entry(excerpt, selected_sources)
            if covered_entry is not None:
                item["decision"] = "covered_selected_entry"
                item["candidate_entry_numbers"] = sorted(set(item["candidate_entry_numbers"] + [covered_entry]))
                item["relevant_arabic"] = ""
                item["rationale"] = (
                    f"Deterministic source-span match: the passage is already covered by complete entry "
                    f"{covered_entry}. " + item["rationale"]
                )
        elif excerpt:
            raise RuntimeError(f"Covered/excluded item retained excerpt: {item['result_id']}")
    return {
        "schema": SCHEMA,
        "cohort_id": "khadijah-immediate",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "model": args.model,
        "reasoning_effort": args.reasoning_effort,
        "prompt_version": PROMPT_VERSION,
        "prompt_sha256": sha256_text(prompt),
        "source_result_count": len(items),
        "source_results": [{key: item[key] for key in ("result_id", "pages", "text_sha256")} for item in items],
        "items": sorted(result["items"], key=lambda item: source_by_id[item["result_id"]]["pages"][0]["index"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--discovery", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--selected-source-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runtime-dir", type=Path, required=True)
    parser.add_argument("--codex", type=Path, required=True)
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--reasoning-effort", default="high")
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--raw-input", type=Path)
    args = parser.parse_args()
    for name in ("discovery", "cache_root", "spec", "selected_source_manifest", "output", "runtime_dir", "codex", "schema"):
        setattr(args, name, getattr(args, name).resolve())
    if args.raw_input:
        args.raw_input = args.raw_input.resolve()
    discovery = json.loads(args.discovery.read_text(encoding="utf-8"))
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    items = unique_literal_results(discovery, args.cache_root)
    selected = [int(item["entry_number"]) for item in spec["entry_targets"]]
    selected_sources = selected_source_texts(args.selected_source_manifest, args.cache_root)
    payload = classify(items, selected, selected_sources, args)
    atomic_json(args.output, payload)
    counts = {}
    for item in payload["items"]:
        counts[item["decision"]] = counts.get(item["decision"], 0) + 1
    print(json.dumps({"output": str(args.output), "results": len(items), "decisions": counts}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

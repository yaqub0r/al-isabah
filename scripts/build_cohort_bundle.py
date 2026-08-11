#!/usr/bin/env python3
"""Build the review bundle for a translated story cohort."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + ".tmp")
    pending.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pending.replace(path)


def build(spec: dict, classification: dict, context: dict, import_report: dict, content_root: Path) -> dict:
    counts = {}
    for item in classification["items"]:
        counts[item["decision"]] = counts.get(item["decision"], 0) + 1
    context_by_id = {item["result_id"]: item for item in context["items"]}
    contexts = []
    for item in classification["items"]:
        if item["decision"] != "include_context":
            continue
        final = context_by_id[item["result_id"]]
        contexts.append({
            "result_id": item["result_id"],
            "source": final["source"]["source"],
            "relationship": item["relationship"],
            "rationale": item["rationale"],
            "arabic": item["relevant_arabic"],
            "english": final["english_text"],
            "names": final["names"],
            "unresolved": final["unresolved"],
            "decisions": final["decisions"],
        })
    entries = []
    for target in spec["entry_targets"]:
        number = int(target["entry_number"])
        entry_id = f"isabah-entry-{number:08d}"
        entry = load(content_root / f"{entry_id}.json")
        entries.append({
            "id": entry_id,
            "printed_entry_number": number,
            "volume": int(spec["entry_volume_map"][str(number)]),
            "name": target["name"],
            "relationship": target["relationship"],
            "machine_assessment": entry["translation"]["machine_assessment"],
            "human_review": entry["translation"]["human_review"],
            "unresolved_count": len(entry["unresolved"]),
        })
    unresolved_entries = sum(item["unresolved_count"] for item in entries)
    unresolved_context = sum(len(item["unresolved"]) for item in contexts)
    return {
        "schema": "al-isabah.story-cohort-bundle.v1",
        "cohort_id": spec["cohort_id"],
        "title": spec["title"],
        "review_state": "ready_for_human_review",
        "summary": {
            "unique_literal_source_results": classification["source_result_count"],
            "coverage_decisions": counts,
            "canonical_complete_entries": len(entries),
            "contextual_passages": len(contexts),
            "unresolved_entry_items": unresolved_entries,
            "unresolved_context_items": unresolved_context,
            "unresolved_total": unresolved_entries + unresolved_context,
            "autonomous_stages_complete": [
                "source-lock", "exhaustive-search", "mention-classification",
                "canonical-extraction", "facsimile-collation", "blind-translation",
                "independent-critique", "targeted-witness-check", "adjudication",
                "deterministic-import",
            ],
        },
        "fill_contract": spec["fill_contract"],
        "entries": entries,
        "contexts": contexts,
        "evidence": {
            "mention_classification": "derived/cohorts/khadijah-immediate.mention-classification.json",
            "entry_adjudication": "derived/cohorts/khadijah-immediate.adjudicated.json",
            "context_adjudication": "derived/cohorts/khadijah-immediate.context-adjudicated.json",
            "context_witnesses": "evidence/cohorts/khadijah-immediate.context-witnesses.json",
            "operator_review": "derived/cohorts/khadijah-immediate.review.md",
            "cohort_artifact_manifest": "evidence/manifests/khadijah-immediate-artifacts.v1.json",
            "import_report": import_report,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--classification", type=Path, required=True)
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--import-report", type=Path, required=True)
    parser.add_argument("--content-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = build(load(args.spec), load(args.classification), load(args.context), load(args.import_report), args.content_root)
    payload["evidence_sha256"] = {
        "spec": sha256_file(args.spec),
        "classification": sha256_file(args.classification),
        "context": sha256_file(args.context),
        "import_report": sha256_file(args.import_report),
    }
    atomic_json(args.output, payload)
    print(json.dumps({"output": str(args.output), **payload["summary"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

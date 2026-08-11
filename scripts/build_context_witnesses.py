#!/usr/bin/env python3
"""Build targeted Urdu and collateral-Arabic witnesses for context passages."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines" / "translation"))
from urdu_witness_index import UrduWitnessIndex, read_jsonl  # noqa: E402
from usul_secondary_witness import WITNESS_SOURCES, search_source  # noqa: E402


def atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + ".tmp")
    pending.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pending.replace(path)


def artifact_for_volume(manifest: dict, volume: int) -> dict:
    suffix = f"urdu_witness_v1/volume_{volume:02d}.translation-units.jsonl"
    matches = [item for item in manifest["artifacts"] if str(item.get("origin", {}).get("repository_path") or "").endswith(suffix)]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one Urdu translation-unit artifact for volume {volume}")
    return matches[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--classification", type=Path, required=True)
    parser.add_argument("--critic", type=Path, required=True)
    parser.add_argument("--artifact-manifest", type=Path, required=True)
    parser.add_argument("--artifact-cache", type=Path, required=True)
    parser.add_argument("--usul-cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    classification = json.loads(args.classification.read_text(encoding="utf-8"))
    critic = json.loads(args.critic.read_text(encoding="utf-8"))
    artifacts = json.loads(args.artifact_manifest.read_text(encoding="utf-8"))
    source_by_id = {item["result_id"]: item for item in classification["source_results"]}
    class_by_id = {item["result_id"]: item for item in classification["items"]}
    critic_by_id = {item["result_id"]: item for item in critic["items"]}
    result_by_index = {int(item["pages"][0]["index"]): result_id for result_id, item in source_by_id.items()}
    records = []
    for planned in plan["items"]:
        result_id = result_by_index[int(planned["reader_index"])]
        passage = class_by_id[result_id]["relevant_arabic"]
        concern = critic_by_id[result_id]
        if concern["verdict"] != "witness_required":
            raise RuntimeError(f"Context {planned['context_id']} no longer requires a witness")
        artifact = artifact_for_volume(artifacts, int(planned["volume"]))
        artifact_path = args.artifact_cache / artifact["object_key"]
        if hashlib.sha256(artifact_path.read_bytes()).hexdigest() != artifact["sha256"]:
            raise RuntimeError(f"Urdu artifact hash mismatch for volume {planned['volume']}")
        index = UrduWitnessIndex(read_jsonl(artifact_path))
        urdu = index.rank(
            arabic_text=passage,
            arabic_names=[],
            heading_names=[planned["queries"][0]],
            entry_numbers=[],
            top_k=4,
            first_body_scan=1,
            last_body_scan=max(index.units),
        )
        collateral = []
        for query in planned["queries"]:
            for source in WITNESS_SOURCES:
                collateral.append(search_source(source=source, query=query, cache_root=args.usul_cache, hit_limit=3, max_text_chars=7000, retries=3))
        records.append({
            **planned,
            "result_id": result_id,
            "arabic_sha256": hashlib.sha256(passage.encode("utf-8")).hexdigest(),
            "critic_issues": [item for item in concern["issues"] if item["witness_recommended"]],
            "urdu": {"artifact_id": artifact["artifact_id"], "artifact_sha256": artifact["sha256"], "candidates": urdu},
            "collateral_arabic": collateral,
        })
        print(f"witness {planned['context_id']}: Urdu={len(urdu)} collateral={len(collateral)}", flush=True)
    atomic_json(args.output, {"schema": "al-isabah.context-witness-evidence.v1", "cohort_id": plan["cohort_id"], "items": records})
    print(json.dumps({"output": str(args.output), "items": len(records)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Build targeted Urdu and collateral-Arabic evidence for critic-raised issues."""
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
        raise RuntimeError(f"Expected one Urdu witness artifact for volume {volume}, found {len(matches)}")
    return matches[0]


def clipped_rank(item: dict, max_chars: int = 7000) -> dict:
    result = dict(item)
    text = str(result.get("text") or "")
    result["text"] = text[:max_chars]
    result["text_truncated"] = len(text) > max_chars
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--source-cache", type=Path, required=True)
    parser.add_argument("--translation-dir", type=Path, required=True)
    parser.add_argument("--artifact-manifest", type=Path, required=True)
    parser.add_argument("--artifact-cache", type=Path, required=True)
    parser.add_argument("--usul-cache", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    parser.add_argument("--entry", type=int, action="append", default=[])
    args = parser.parse_args()
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    source_manifest = json.loads(args.source_manifest.read_text(encoding="utf-8"))
    artifact_manifest = json.loads(args.artifact_manifest.read_text(encoding="utf-8"))
    by_entry = {int(item["entry_number"]): item for item in source_manifest["entries"]}
    volume_map = {int(key): int(value) for key, value in spec["entry_volume_map"].items()}
    selected = set(args.entry)
    target_numbers = sorted(int(key) for key in spec["witness_queries"] if not selected or int(key) in selected)
    urdu_indexes = {}
    summary = []
    for number in target_numbers:
        entry = by_entry[number]
        source = json.loads((args.source_cache / entry["cache_key"]).read_text(encoding="utf-8"))
        blind = json.loads((args.translation_dir / "blind" / f"{number:05d}.json").read_text(encoding="utf-8"))
        critic = json.loads((args.translation_dir / "critic" / f"{number:05d}.json").read_text(encoding="utf-8"))
        concerns = [item for item in critic["issues"] if item.get("witness_recommended")]
        if not concerns:
            destination = args.translation_dir / "witness" / f"{number:05d}.json"
            atomic_json(destination, {
                "schema": "al-isabah.cohort-witness-evidence.v1",
                "cohort_id": spec["cohort_id"],
                "entry_number": number,
                "source_sha256": entry["arabic_text_sha256"],
                "state": "not_required_after_critique",
                "critic_concerns": [],
                "urdu": {"candidates": []},
                "collateral_arabic": [],
            })
            summary.append({
                "entry_number": number,
                "concern_count": 0,
                "urdu_candidates": 0,
                "collateral_queries": 0,
                "collateral_states": {},
                "evidence_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
            })
            print(f"witness {number}: not required after critique", flush=True)
            continue
        volume = volume_map[number]
        if volume not in urdu_indexes:
            artifact = artifact_for_volume(artifact_manifest, volume)
            path = args.artifact_cache / artifact["object_key"]
            observed = hashlib.sha256(path.read_bytes()).hexdigest()
            if observed != artifact["sha256"]:
                raise RuntimeError(f"Urdu witness artifact hash mismatch for volume {volume}")
            urdu_indexes[volume] = (UrduWitnessIndex(read_jsonl(path)), artifact)
        urdu_index, urdu_artifact = urdu_indexes[volume]
        heading_query = spec["witness_queries"][str(number)][0]
        urdu = urdu_index.rank(
            arabic_text=source["arabic_text"],
            arabic_names=[item["arabic"] for item in blind.get("names", [])],
            heading_names=[heading_query],
            entry_numbers=[number],
            top_k=4,
            first_body_scan=1,
            last_body_scan=max(urdu_index.units),
        )
        collateral = []
        for query in spec["witness_queries"][str(number)]:
            for witness_source in WITNESS_SOURCES:
                collateral.append(search_source(
                    source=witness_source,
                    query=query,
                    cache_root=args.usul_cache,
                    hit_limit=3,
                    max_text_chars=7000,
                    retries=3,
                ))
        payload = {
            "schema": "al-isabah.cohort-witness-evidence.v1",
            "cohort_id": spec["cohort_id"],
            "entry_number": number,
            "source_sha256": entry["arabic_text_sha256"],
            "critic_concerns": concerns,
            "urdu": {
                "artifact_id": urdu_artifact["artifact_id"],
                "artifact_sha256": urdu_artifact["sha256"],
                "candidates": [clipped_rank(item) for item in urdu],
            },
            "collateral_arabic": collateral,
        }
        destination = args.translation_dir / "witness" / f"{number:05d}.json"
        atomic_json(destination, payload)
        states = {}
        for item in collateral:
            states[item["retrieval_state"]] = states.get(item["retrieval_state"], 0) + 1
        summary.append({
            "entry_number": number,
            "concern_count": len(concerns),
            "urdu_candidates": len(urdu),
            "collateral_queries": len(collateral),
            "collateral_states": states,
            "evidence_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
        })
        print(f"witness {number}: Urdu={len(urdu)} collateral={states}", flush=True)
    atomic_json(args.summary_output, {"schema": "al-isabah.cohort-witness-summary.v1", "cohort_id": spec["cohort_id"], "entries": summary})
    print(json.dumps({"entries": len(summary), "summary": str(args.summary_output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

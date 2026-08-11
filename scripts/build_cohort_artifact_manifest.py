#!/usr/bin/env python3
"""Build the minimal external-artifact manifest required by a story cohort."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


FACSIMILE_SUFFIX = "ibn_hajar_isabah_v1/usul_canonical_facsimile_v1.pdf"
URDU_SUFFIX = "urdu_witness_v1/volume_{volume:02d}.translation-units.jsonl"


def select(global_manifest: dict, witness_plan: dict) -> dict:
    required_suffixes = {FACSIMILE_SUFFIX}
    required_suffixes.update(URDU_SUFFIX.format(volume=int(item["volume"])) for item in witness_plan["items"])
    selected = []
    for artifact in global_manifest["artifacts"]:
        path = str((artifact.get("origin") or {}).get("repository_path") or "")
        if any(path.endswith(suffix) for suffix in required_suffixes):
            selected.append(artifact)
    matched = {
        suffix for suffix in required_suffixes
        if any(str((item.get("origin") or {}).get("repository_path") or "").endswith(suffix) for item in selected)
    }
    if matched != required_suffixes:
        raise RuntimeError(f"Cohort artifact selection is incomplete: {sorted(required_suffixes - matched)}")
    return {
        "schema": global_manifest["schema"],
        "work_id": global_manifest["work_id"],
        "generated_from": global_manifest["generated_from"],
        "cohort_id": witness_plan["cohort_id"],
        "selection": {
            "purpose": "Hydrate only immutable external evidence required to reproduce the cohort.",
            "artifact_count": len(selected),
        },
        "artifacts": sorted(selected, key=lambda item: item["artifact_id"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--global-manifest", type=Path, required=True)
    parser.add_argument("--witness-plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = select(
        json.loads(args.global_manifest.read_text(encoding="utf-8")),
        json.loads(args.witness_plan.read_text(encoding="utf-8")),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"output": str(args.output), "artifacts": len(payload["artifacts"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

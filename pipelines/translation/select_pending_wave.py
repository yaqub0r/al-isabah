#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description="Select next N pending chunks from a chunk set using global translation state.")
    ap.add_argument("--chunks", required=True, help="Input chunks JSONL (full or focused subset)")
    ap.add_argument("--state", required=True, help="State JSON")
    ap.add_argument("--out", required=True, help="Output selected wave JSONL")
    ap.add_argument("--limit", type=int, default=10)
    args = ap.parse_args()

    chunks = _load_jsonl(Path(args.chunks))
    state = json.loads(Path(args.state).read_text(encoding="utf-8"))
    completed = set((state.get("completed") or {}).keys())

    pending = [r for r in sorted(chunks, key=lambda x: int(x.get("order") or 0)) if str(r.get("chunk_id")) not in completed]
    selected = pending[: max(1, int(args.limit))]
    _write_jsonl(Path(args.out), selected)

    print(json.dumps({
        "input_chunks": len(chunks),
        "completed_in_state": len(completed),
        "pending_in_input": len(pending),
        "selected": len(selected),
        "selected_chunk_ids": [r.get("chunk_id") for r in selected],
        "out": args.out,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

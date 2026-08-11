#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _load_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def main() -> None:
    ap = argparse.ArgumentParser(description="Estimate translation token cost from chunk manifest.")
    ap.add_argument("--chunks", required=True, help="chunks.jsonl from build_translation_chunks.py")
    ap.add_argument("--in-tok-per-char", type=float, default=0.30, help="Arabic-ish heuristic")
    ap.add_argument("--out-multiplier", type=float, default=0.90, help="Output tokens = input * multiplier")
    ap.add_argument("--overhead-multiplier", type=float, default=1.08, help="Prompt/chunk overhead factor")
    args = ap.parse_args()

    total_chars = 0
    n = 0
    for rec in _load_jsonl(Path(args.chunks)):
        total_chars += int(rec.get("char_len") or len(str(rec.get("source_text") or "")))
        n += 1

    in_tokens = total_chars * args.in_tok_per_char
    out_tokens = in_tokens * args.out_multiplier
    billed = (in_tokens + out_tokens) * args.overhead_multiplier

    report = {
        "chunks": n,
        "total_chars": total_chars,
        "est_input_tokens": int(in_tokens),
        "est_output_tokens": int(out_tokens),
        "est_total_billed_tokens": int(billed),
        "params": {
            "in_tok_per_char": args.in_tok_per_char,
            "out_multiplier": args.out_multiplier,
            "overhead_multiplier": args.overhead_multiplier,
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

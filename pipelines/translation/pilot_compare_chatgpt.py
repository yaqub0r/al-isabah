#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import dataclass, asdict
from pathlib import Path


def normalize(s: str) -> str:
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def tokens(s: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9'\-]+", s.lower())


def token_f1(ref: list[str], hyp: list[str]) -> dict[str, float]:
    ref_c = Counter(ref)
    hyp_c = Counter(hyp)
    inter = sum((ref_c & hyp_c).values())
    p = inter / max(1, sum(hyp_c.values()))
    r = inter / max(1, sum(ref_c.values()))
    f1 = (2 * p * r / (p + r)) if (p + r) else 0.0
    return {"precision": p, "recall": r, "f1": f1}


@dataclass
class ChunkResult:
    chunk_id: str
    candidate_chars: int
    candidate_tokens: int
    best_window_start_token: int
    best_window_end_token: int
    best_window_chars: int
    precision: float
    recall: float
    f1: float
    candidate_text: str
    matched_reference_excerpt: str


def best_match_window(ref_tokens: list[str], hyp_tokens: list[str], ref_text: str) -> tuple[int, int, dict[str, float], str]:
    n = len(hyp_tokens)
    if n == 0:
        return 0, 0, {"precision": 0.0, "recall": 0.0, "f1": 0.0}, ""

    # Search around comparable sizes.
    size_candidates = sorted(set(max(20, int(n * r)) for r in (0.7, 0.85, 1.0, 1.15, 1.3)))
    step = max(10, n // 4)

    best = {"f1": -1.0, "p": 0.0, "r": 0.0, "i": 0, "j": 0}
    for win in size_candidates:
        for i in range(0, max(1, len(ref_tokens) - win + 1), step):
            j = i + win
            m = token_f1(ref_tokens[i:j], hyp_tokens)
            if m["f1"] > best["f1"]:
                best = {"f1": m["f1"], "p": m["precision"], "r": m["recall"], "i": i, "j": j}

    # Build excerpt from token window with rough char reconstruction.
    excerpt = " ".join(ref_tokens[best["i"] : best["j"]])
    return best["i"], best["j"], {"precision": best["p"], "recall": best["r"], "f1": best["f1"]}, excerpt


def main() -> None:
    ap = argparse.ArgumentParser(description="Pilot compare ChatGPT translations vs licensed human reference.")
    ap.add_argument("--reference", required=True)
    ap.add_argument("--candidate-json", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    ref_text = normalize(Path(args.reference).read_text(encoding="utf-8", errors="ignore"))
    ref_tokens = tokens(ref_text)

    chunks = json.loads(Path(args.candidate_json).read_text(encoding="utf-8"))
    results: list[ChunkResult] = []

    for c in chunks:
        cid = c["chunk_id"]
        hyp = normalize(c["chatgpt_translation"])
        hyp_t = tokens(hyp)

        i, j, m, excerpt = best_match_window(ref_tokens, hyp_t, ref_text)
        results.append(
            ChunkResult(
                chunk_id=cid,
                candidate_chars=len(hyp),
                candidate_tokens=len(hyp_t),
                best_window_start_token=i,
                best_window_end_token=j,
                best_window_chars=len(excerpt),
                precision=m["precision"],
                recall=m["recall"],
                f1=m["f1"],
                candidate_text=hyp,
                matched_reference_excerpt=excerpt,
            )
        )

    summary = {
        "reference": args.reference,
        "candidate_json": args.candidate_json,
        "chunks": [asdict(r) for r in results],
        "macro_avg": {
            "precision": sum(r.precision for r in results) / max(1, len(results)),
            "recall": sum(r.recall for r in results) / max(1, len(results)),
            "f1": sum(r.f1 for r in results) / max(1, len(results)),
        },
        "note": "Best-window token overlap is a rough pilot metric, not definitive scholarly equivalence.",
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote: {out}")
    print(json.dumps(summary["macro_avg"], ensure_ascii=False))


if __name__ == "__main__":
    main()

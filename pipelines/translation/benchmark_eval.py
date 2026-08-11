#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def normalize(s: str) -> str:
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def tokens(s: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9'\-]+", s.lower())


def token_overlap(ref: list[str], hyp: list[str]) -> dict:
    ref_c = Counter(ref)
    hyp_c = Counter(hyp)
    inter = sum((ref_c & hyp_c).values())
    p = inter / max(1, sum(hyp_c.values()))
    r = inter / max(1, sum(ref_c.values()))
    f1 = (2 * p * r / (p + r)) if (p + r) else 0.0
    return {"precision": p, "recall": r, "f1": f1, "intersection": inter}


def count_lineage_markers(s: str) -> int:
    # Simple heuristic for genealogy density in English output.
    return len(re.findall(r"\bibn\b", s.lower())) + len(re.findall(r"\bbin\b", s.lower()))


def name_coverage(reference: str, candidate: str, names: list[str]) -> dict:
    out: dict[str, dict] = {}
    ref_l = reference.lower()
    can_l = candidate.lower()
    for name in names:
        n = name.lower()
        out[name] = {
            "in_reference": n in ref_l,
            "in_candidate": n in can_l,
        }
    in_ref = [k for k, v in out.items() if v["in_reference"]]
    kept = [k for k in in_ref if out[k]["in_candidate"]]
    coverage = len(kept) / max(1, len(in_ref))
    return {"items": out, "reference_names": in_ref, "kept_names": kept, "coverage": coverage}


def main() -> None:
    ap = argparse.ArgumentParser(description="Evaluate translation candidate against benchmark reference text.")
    ap.add_argument("--reference", required=True, help="Path to benchmark reference English text (licensed/private allowed)")
    ap.add_argument("--candidate", required=True, help="Path to candidate translation text")
    ap.add_argument("--out", required=True, help="Output JSON report path")
    ap.add_argument(
        "--names",
        nargs="*",
        default=[
            "Muhammad",
            "Abd Allah",
            "Abd al-Muttalib",
            "Shaybah",
            "Hashim",
            "Amr",
            "Abd Manaf",
            "al-Mughira",
            "Qusayy",
            "Kilab",
            "Ibn Hisham",
            "Ibn Ishaq",
        ],
        help="Names/terms to track for consistency",
    )
    args = ap.parse_args()

    ref_path = Path(args.reference)
    cand_path = Path(args.candidate)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    ref_raw = read_text(ref_path)
    cand_raw = read_text(cand_path)
    ref = normalize(ref_raw)
    cand = normalize(cand_raw)

    ref_t = tokens(ref)
    cand_t = tokens(cand)

    report = {
        "reference": str(ref_path),
        "candidate": str(cand_path),
        "length": {
            "reference_chars": len(ref),
            "candidate_chars": len(cand),
            "reference_tokens": len(ref_t),
            "candidate_tokens": len(cand_t),
            "char_ratio_candidate_over_reference": (len(cand) / max(1, len(ref))),
        },
        "similarity": {
            "sequence_match_ratio": SequenceMatcher(None, ref, cand).ratio(),
            "token_overlap": token_overlap(ref_t, cand_t),
        },
        "lineage_markers": {
            "reference_ibn_bin_count": count_lineage_markers(ref),
            "candidate_ibn_bin_count": count_lineage_markers(cand),
        },
        "name_consistency": name_coverage(ref, cand, args.names),
    }

    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote report: {out_path}")
    print(json.dumps({
        "sequence_match_ratio": report["similarity"]["sequence_match_ratio"],
        "token_f1": report["similarity"]["token_overlap"]["f1"],
        "name_coverage": report["name_consistency"]["coverage"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()

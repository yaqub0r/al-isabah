#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PRESET_DIR = REPO_ROOT / "config" / "focus-presets"


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


def _compile_patterns(terms: list[str], case_sensitive: bool) -> list[re.Pattern[str]]:
    flags = 0 if case_sensitive else re.IGNORECASE
    return [re.compile(re.escape(t.strip()), flags) for t in terms if str(t).strip()]


def _term_hits(text: str, patterns: list[re.Pattern[str]]) -> list[str]:
    hits: list[str] = []
    for p in patterns:
        if p.search(text):
            hits.append(p.pattern.replace("\\", ""))
    return hits


def _dedupe_terms(xs: list[str]) -> list[str]:
    seen = set()
    out: list[str] = []
    for t in xs:
        k = str(t).strip()
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(k)
    return out


def _load_focus_spec(focus_spec: Path | None, preset: str | None, preset_dir: Path) -> dict[str, Any]:
    if focus_spec:
        return json.loads(focus_spec.read_text(encoding="utf-8"))

    if not preset:
        raise SystemExit("provide either --focus-spec or --preset")

    p = preset_dir / f"{preset}.json"
    if not p.exists():
        raise SystemExit(f"preset not found: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def main() -> None:
    ap = argparse.ArgumentParser(description="Build generic topic-focused chunk subset from a focus spec.")
    ap.add_argument("--chunks", required=True, help="Input chunks.jsonl")
    ap.add_argument("--out", required=True, help="Output focused chunks JSONL")
    ap.add_argument("--report", required=True, help="Output report JSON")
    ap.add_argument("--focus-spec", help="Path to focus spec JSON")
    ap.add_argument("--preset", default="khadijah", help="Focus preset name in config/focus-presets")
    ap.add_argument("--preset-dir", default=str(DEFAULT_PRESET_DIR), help="Preset directory")
    ap.add_argument("--terms", help="Optional JSON array of extra primary terms to append")
    ap.add_argument("--context-window", type=int, default=None, help="Override context window from spec")
    ap.add_argument("--case-sensitive", action="store_true")
    args = ap.parse_args()

    chunks = _load_jsonl(Path(args.chunks))
    if not chunks:
        raise SystemExit("no chunks loaded")

    spec = _load_focus_spec(
        focus_spec=Path(args.focus_spec) if args.focus_spec else None,
        preset=args.preset,
        preset_dir=Path(args.preset_dir),
    )

    topic_id = str(spec.get("topic_id") or spec.get("topic") or args.preset or "custom")
    primary_terms = _dedupe_terms(list(spec.get("primary_terms") or []))
    ambiguous_terms = _dedupe_terms(list(spec.get("ambiguous_terms") or []))

    if args.terms:
        extra = json.loads(Path(args.terms).read_text(encoding="utf-8"))
        if isinstance(extra, list):
            primary_terms = _dedupe_terms(primary_terms + [str(x) for x in extra])

    if not primary_terms:
        raise SystemExit("focus spec has no primary_terms")

    w = int(args.context_window) if args.context_window is not None else int(spec.get("context_window", 1))
    w = max(0, w)

    primary_pats = _compile_patterns(primary_terms, case_sensitive=args.case_sensitive)
    ambiguous_pats = _compile_patterns(ambiguous_terms, case_sensitive=args.case_sensitive)

    direct_match_orders: set[int] = set()
    contextual_match_orders: set[int] = set()
    hit_map: dict[int, list[str]] = {}

    # Pass 1: direct/high-confidence matches.
    for row in chunks:
        order = int(row.get("order") or 0)
        text = str(row.get("source_text") or "")
        hits = _term_hits(text, primary_pats)
        if hits:
            direct_match_orders.add(order)
            hit_map.setdefault(order, []).extend(hits)

    # Pass 2: ambiguous matches only if adjacent to a direct match.
    if ambiguous_pats:
        direct_neighbors = set(direct_match_orders)
        for o in direct_match_orders:
            direct_neighbors.add(o - 1)
            direct_neighbors.add(o + 1)

        for row in chunks:
            order = int(row.get("order") or 0)
            if order in direct_match_orders:
                continue
            text = str(row.get("source_text") or "")
            amb_hits = _term_hits(text, ambiguous_pats)
            if amb_hits and order in direct_neighbors:
                contextual_match_orders.add(order)
                hit_map.setdefault(order, []).extend(amb_hits)

    all_match_orders = direct_match_orders | contextual_match_orders

    include_orders: set[int] = set(all_match_orders)
    if w > 0 and all_match_orders:
        max_order = max(int(r.get("order") or 0) for r in chunks)
        for o in list(all_match_orders):
            for i in range(max(1, o - w), min(max_order, o + w) + 1):
                include_orders.add(i)

    focused: list[dict[str, Any]] = []
    for row in chunks:
        o = int(row.get("order") or 0)
        if o not in include_orders:
            continue
        out_row = dict(row)
        out_row["focus_topic"] = topic_id
        out_row["focus_match"] = o in all_match_orders
        out_row["focus_match_confidence"] = (
            "direct" if o in direct_match_orders else ("contextual_ambiguous" if o in contextual_match_orders else "none")
        )
        out_row["focus_hits"] = hit_map.get(o, [])
        focused.append(out_row)

    focused.sort(key=lambda r: int(r.get("order") or 0))
    _write_jsonl(Path(args.out), focused)

    report = {
        "topic": topic_id,
        "spec_source": args.focus_spec or str(Path(args.preset_dir) / f"{args.preset}.json"),
        "terms_count_primary": len(primary_terms),
        "terms_primary": primary_terms,
        "terms_count_ambiguous": len(ambiguous_terms),
        "terms_ambiguous": ambiguous_terms,
        "input_chunk_count": len(chunks),
        "direct_match_chunk_count": len([r for r in focused if r.get("focus_match_confidence") == "direct"]),
        "contextual_ambiguous_match_chunk_count": len([r for r in focused if r.get("focus_match_confidence") == "contextual_ambiguous"]),
        "focused_chunk_count": len(focused),
        "context_window": w,
        "output": args.out,
    }
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

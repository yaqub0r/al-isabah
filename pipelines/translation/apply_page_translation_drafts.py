#!/usr/bin/env python3
"""Apply page-keyed English drafts to reviewable translation-unit JSONL."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_units(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def apply_drafts(
    units_path: Path,
    drafts_path: Path,
    *,
    model: str,
    generated_at_utc: str,
) -> dict[str, int]:
    units = load_units(units_path)
    draft_set = json.loads(drafts_path.read_text(encoding="utf-8"))
    drafts = {int(page["scan_page"]): page for page in draft_set["pages"]}
    if len(drafts) != len(draft_set["pages"]):
        raise ValueError("draft file contains duplicate scan pages")

    applied = 0
    unit_pages = {int(unit["source"]["scan_page"]) for unit in units}
    missing_units = sorted(set(drafts) - unit_pages)
    if missing_units:
        raise ValueError(f"draft pages have no translation units: {missing_units}")

    for unit in units:
        scan_page = int(unit["source"]["scan_page"])
        page = drafts.get(scan_page)
        if page is None:
            continue
        english = str(page.get("english") or "").strip()
        if not english:
            raise ValueError(f"draft for scan page {scan_page} has no English text")
        unit["target"] = {
            "language": "en",
            "text": english,
            "state": str(page.get("state") or "draft"),
            "flags": list(page.get("flags") or []),
            "printed_page": page.get("printed_page"),
        }
        unit["translation"] = {
            "method": "codex_current_session",
            "model": model,
            "prompt_version": draft_set["prompt_version"],
            "generated_at_utc": generated_at_utc,
            "authority": draft_set["authority"],
        }
        applied += 1

    pending = units_path.with_suffix(units_path.suffix + ".tmp")
    with pending.open("w", encoding="utf-8", newline="\n") as output:
        for unit in units:
            output.write(json.dumps(unit, ensure_ascii=False, separators=(",", ":")) + "\n")
    pending.replace(units_path)
    return {"units": len(units), "drafts": len(drafts), "applied": applied}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--units", required=True)
    parser.add_argument("--drafts", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--generated-at-utc", required=True)
    args = parser.parse_args()
    report = apply_drafts(
        Path(args.units),
        Path(args.drafts),
        model=args.model,
        generated_at_utc=args.generated_at_utc,
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

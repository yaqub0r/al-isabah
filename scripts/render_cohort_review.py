#!/usr/bin/env python3
"""Render a bilingual operator review document from the canonical cohort bundle."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def unresolved_markdown(items: list[dict]) -> list[str]:
    if not items:
        return ["Unresolved: none.", ""]
    lines = ["Unresolved:", ""]
    for item in items:
        lines.append(f"- {item['issue']} Best available rendering: {item.get('best_rendering') or 'not established'}")
    lines.append("")
    return lines


def render(bundle: dict, content_root: Path) -> str:
    summary = bundle["summary"]
    lines = [
        f"# {bundle['title']} — bilingual review",
        "",
        f"Review state: **{bundle['review_state'].replace('_', ' ')}**",
        "",
        f"This dossier contains {summary['canonical_complete_entries']} complete biographies and "
        f"{summary['contextual_passages']} additional contextual passages. The exhaustive direct-name "
        f"inventory classified {summary['unique_literal_source_results']} unique result blocks. "
        f"{summary['unresolved_total']} source-level questions remain explicit for human review.",
        "",
        "## Complete biographies",
        "",
    ]
    for index in bundle["entries"]:
        entry = load(content_root / f"{index['id']}.json")
        segment = entry["segments"][0]
        lines.extend([
            f"### {entry['printed_entry_number']} — {entry['title']['english']}",
            "",
            f"Relationship: {index['relationship']}. Volume {index['volume']}; "
            f"reader pages {', '.join(str(page) for page in segment.get('reader_pages', [segment['reader_page']]))}. "
            f"Machine assessment: {entry['translation']['machine_assessment']}; human review: {entry['translation']['human_review']}.",
            f"Canonical reader: [{segment['reader_url']}]({segment['reader_url']})",
            "",
            "#### Arabic",
            "",
            '<div dir="rtl" lang="ar">',
            "",
            segment["arabic"],
            "",
            "</div>",
            "",
            "#### English",
            "",
            segment["english"],
            "",
        ])
        lines.extend(unresolved_markdown(entry["unresolved"]))
    lines.extend(["## Additional contextual passages", ""])
    for context in bundle["contexts"]:
        page = context["source"]["pages"][0]
        lines.extend([
            f"### Volume {page['volume']}, reader index {page['index']}",
            "",
            f"Relationship: {context['relationship']}. {context['rationale']}",
            f"Canonical reader: [https://usul.ai/t/isaba-fi-tamyiz/{int(page['index']) + 1}]"
            f"(https://usul.ai/t/isaba-fi-tamyiz/{int(page['index']) + 1})",
            "",
            "#### Arabic",
            "",
            '<div dir="rtl" lang="ar">',
            "",
            context["arabic"],
            "",
            "</div>",
            "",
            "#### English",
            "",
            context["english"],
            "",
        ])
        lines.extend(unresolved_markdown(context["unresolved"]))
    lines.extend([
        "## Coverage accounting",
        "",
        "Every unique literal search result has a decision in "
        "`khadijah-immediate.mention-classification.json`; excluded namesakes and bare relations are "
        "retained there so the operator can audit omissions without rereading the full corpus.",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--content-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    text = render(load(args.bundle), args.content_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8", newline="\n")
    print(json.dumps({"output": str(args.output), "characters": len(text)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

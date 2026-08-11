#!/usr/bin/env python3
"""Render reviewable English HTML from FirstLight translation-unit JSONL.

The JSONL remains authoritative. This renderer deliberately has no editing or
approval controls, so an HTML copy cannot become a second source of truth.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path


ALIGNED_VOLUME_SOURCE_PDF = (
    "/docs/narrative/sources/T1_primaries/ibn_hajar_isabah_v1/"
    "volume_08.pdf"
)
URDU_VOLUME_WITNESS_PDF = (
    "/docs/narrative/sources/T1_primaries/ibn_hajar_isabah_v1/"
    "urdu_witness_v1/volume_08.pdf"
)


def read_units(path: Path) -> list[dict]:
    units: list[dict] = []
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                unit = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"Invalid JSON on {path}:{line_number}: {error}") from error
            if unit.get("target", {}).get("text"):
                units.append(unit)
    return units


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def language_markup(value: object) -> tuple[str, str]:
    normalized = str(value or "").strip().casefold()
    code = {
        "arabic": "ar", "ar": "ar",
        "urdu": "ur", "ur": "ur",
        "persian": "fa", "farsi": "fa", "fa": "fa",
        "turkish": "tr", "tr": "tr",
        "english": "en", "en": "en",
    }.get(normalized, "und")
    return code, "rtl" if code in {"ar", "ur", "fa"} else "ltr"


def render_flags(flags: list[str]) -> str:
    if not flags:
        return '<span class="flag is-clear">No explicit flags</span>'
    return "".join(f'<span class="flag">{esc(flag)}</span>' for flag in flags)


def render_names(names: list[dict]) -> str:
    if not names:
        return '<span class="name-empty">No structured names recorded</span>'
    return "".join(
        f'<span class="name"><strong>{esc(name.get("english", ""))}</strong><b dir="rtl">{esc(name.get("arabic", ""))}</b><small>{esc(name.get("kind", "other"))}</small></span>'
        for name in names
    )


def render_unresolved(items: list[dict]) -> str:
    if not items:
        return ""
    rows = "".join(
        f'<li><strong>{esc(item.get("human_review_priority", "normal"))} · {esc(item.get("category", "uncertainty"))}</strong><span>{esc(item.get("explanation", ""))}</span></li>'
        for item in items
    )
    return f'<aside class="unresolved"><h3>Explicitly unresolved</h3><ul>{rows}</ul></aside>'


def render_witness_review(unit: dict) -> str:
    urdu = unit.get("urdu_cross_check") or {}
    collateral = unit.get("collateral_cross_check") or {}
    supplemental = unit.get("supplemental_cross_check") or {}
    evidence = list(collateral.get("evidence") or [])
    supplemental_evidence = list(supplemental.get("evidence") or [])
    candidates = list(urdu.get("candidates") or [])
    urdu_pages = [int(page) for page in (urdu.get("citation") or [])]
    if (
        urdu.get("state") == "not_required"
        and not evidence
        and not candidates
        and not supplemental_evidence
    ):
        return ""

    urdu_links = " ".join(
        f'<a href="{URDU_VOLUME_WITNESS_PDF}#page={page}" target="_blank" rel="noreferrer">Urdu scan {page}</a>'
        for page in urdu_pages
    ) or '<span>No Urdu scan citation recorded</span>'
    candidate_rows = []
    for candidate in candidates:
        page = int(candidate.get("scan_page") or 0)
        expected = candidate.get("expected_scan_page")
        distance = candidate.get("distance_from_expected")
        score = candidate.get("score")
        signals = ", ".join(
            str(signal).replace("_", " ") for signal in (candidate.get("selection_signals") or [])
        ) or "no selection signal recorded"
        alignment = (
            f"expected {expected}, distance {distance}" if expected is not None
            else "expected scan unavailable"
        )
        candidate_rows.append(
            '<li>'
            f'<a href="{URDU_VOLUME_WITNESS_PDF}#page={page}" target="_blank" rel="noreferrer">Urdu scan {page}</a>'
            f'<small>score {esc(score)} · {esc(alignment)} · {esc(signals)}</small>'
            '</li>'
        )
    candidate_block = (
        '<div class="witness-candidates"><strong>Urdu retrieval candidates</strong>'
        f'<ul>{"".join(candidate_rows)}</ul></div>'
        if candidate_rows else ""
    )
    records = []
    for item in evidence:
        state = str(item.get("retrieval_state") or "unknown")
        title = esc(item.get("title") or item.get("work_id") or "Collateral witness")
        query = esc(item.get("query") or "")
        source_url = esc(item.get("facsimile_url") or "")
        source_link = (
            f'<a href="{source_url}" target="_blank" rel="noreferrer">Open witness facsimile</a>'
            if source_url else ""
        )
        hit_rows = []
        for hit in item.get("hits") or []:
            pages = (hit.get("metadata") or {}).get("pages") or []
            citation = ", ".join(
                f"vol. {page.get('volume')}, p. {page.get('page')} (index {page.get('index')})"
                for page in pages
            ) or "Page metadata unavailable"
            clipped = " · retrieved excerpt clipped" if hit.get("text_truncated") else ""
            hit_rows.append(
                f'<div class="witness-hit"><small>{esc(citation + clipped)}</small>'
                f'<blockquote lang="ar" dir="rtl">{esc(hit.get("text") or "")}</blockquote></div>'
            )
        if state == "error":
            body = f'<p class="witness-error">Unavailable: {esc(item.get("error") or "provider error")}</p>'
        elif not hit_rows:
            body = '<p class="witness-empty">No exact keyword match returned.</p>'
        else:
            body = "".join(hit_rows)
        records.append(
            f'<section class="witness-record" data-state="{esc(state)}">'
            f'<header><div><strong>{title}</strong><small>Exact query: {query}</small></div>'
            f'<span>{esc(state.replace("_", " "))}</span>{source_link}</header>{body}</section>'
        )

    supplemental_records = []
    for item in supplemental_evidence:
        title = esc(item.get("title") or "Supplemental witness")
        kind = esc(str(item.get("kind") or "outside evidence").replace("_", " "))
        citation = esc(item.get("citation") or "Citation not recorded")
        evidence_id = esc(item.get("evidence_id") or "unidentified")
        source_url = esc(item.get("source_url") or "")
        source_link = (
            f'<a href="{source_url}" target="_blank" rel="noreferrer">Open cited source</a>'
            if source_url else ""
        )
        note = esc(item.get("acquisition_note") or "")
        note_block = f'<p class="witness-note">{note}</p>' if note else ""
        language, direction = language_markup(item.get("language"))
        supplemental_records.append(
            '<section class="witness-record" data-state="supplemental">'
            f'<header><div><strong>{title}</strong><small>{kind} &middot; {citation} &middot; {evidence_id}</small></div>'
            f'<span>hash-bound</span>{source_link}</header>'
            f'<div class="witness-hit"><small>Excerpt SHA-256: {esc(item.get("excerpt_sha256") or "not recorded")}</small>'
            f'<blockquote lang="{language}" dir="{direction}">{esc(item.get("excerpt") or "")}</blockquote>'
            f'{note_block}</div></section>'
        )

    summary = esc(urdu.get("notes") or collateral.get("notes") or "No model summary recorded.")
    return (
        '<details class="witness-audit"><summary>Witness evidence and decision</summary>'
        f'<div class="witness-summary"><p>{summary}</p><div>{urdu_links}</div>{candidate_block}</div>'
        f'{"".join(records)}{"".join(supplemental_records)}</details>'
    )


def render_unit(unit: dict) -> str:
    source = unit["source"]
    target = unit["target"]
    review = unit.get("review", {})
    scan_page = int(source["scan_page"])
    printed_page = target.get("printed_page")
    printed_label = "not recorded" if printed_page is None else str(printed_page)
    state = review.get("state", "unreviewed")
    flags = list(target.get("flags") or [])
    names = list(target.get("names") or [])
    unresolved = list(target.get("unresolved") or [])
    arabic = source.get("text") or "Arabic source text is not embedded in this unit."
    return f"""
      <article class="page" id="scan-{scan_page:04d}">
        <header class="page-header">
          <div>
            <span class="eyebrow">Volume 8 - scan {scan_page}</span>
            <h2>Printed page {esc(printed_label)}</h2>
          </div>
          <div class="page-state" data-state="{esc(state)}">
            <span>Review</span><strong>{esc(state.replace('_', ' '))}</strong>
          </div>
        </header>
        <div class="page-columns">
          <section class="text-panel english-panel"><h3>English</h3><div class="translation" lang="en">{esc(target["text"])}</div></section>
          <section class="text-panel arabic-panel"><h3>Canonical Arabic</h3><div class="source-arabic" lang="ar" dir="rtl">{esc(arabic)}</div></section>
        </div>
        {render_witness_review(unit)}
        {render_unresolved(unresolved)}
        <footer class="page-footer">
          <div class="flags" aria-label="Review flags">{render_flags(flags)}</div>
          <div class="names" aria-label="Structured names">{render_names(names)}</div>
          <div class="provenance">
            <span>{esc(unit['unit_id'])}</span>
            <a href="{ALIGNED_VOLUME_SOURCE_PDF}#page={scan_page}" target="_blank" rel="noreferrer">Open aligned Arabic scan</a>
          </div>
        </footer>
      </article>"""


def render_document(units: list[dict], source_path: Path) -> str:
    if not units:
        raise ValueError(f"No translated units found in {source_path}")
    flag_count = sum(len(unit.get("target", {}).get("flags") or []) for unit in units)
    approved_count = sum(
        unit.get("review", {}).get("state") == "approved" for unit in units
    )
    unresolved_count = sum(len(unit.get("target", {}).get("unresolved") or []) for unit in units)
    name_count = sum(len(unit.get("target", {}).get("names") or []) for unit in units)
    witness_count = sum(
        (unit.get("urdu_cross_check") or {}).get("state") != "not_required"
        for unit in units
    )
    first_scan = units[0]["source"]["scan_page"]
    last_scan = units[-1]["source"]["scan_page"]
    source_sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()
    articles = "\n".join(render_unit(unit) for unit in units)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="firstlight-source-sha256" content="{source_sha256}">
  <title>al-Isabah - Volume 8 English review draft</title>
  <style>
    :root {{ color-scheme: dark; --ink:#f4eadf; --muted:#bba895; --paper:#1b1714; --panel:#261d18; --line:#5e432f; --gold:#e49a42; --cyan:#69c7c3; --warn:#ef786f; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:#100e0d; color:var(--ink); font:16px/1.65 Georgia, 'Times New Roman', serif; }}
    a {{ color:#8bdad6; }}
    .masthead {{ border-bottom:1px solid var(--line); background:linear-gradient(145deg,#2c1f18,#171311); padding:clamp(2rem,6vw,5rem) max(1.25rem,calc((100vw - 920px)/2)); }}
    .eyebrow {{ color:var(--gold); font:700 .72rem/1.2 system-ui,sans-serif; letter-spacing:.14em; text-transform:uppercase; }}
    h1 {{ max-width:15ch; margin:.35rem 0 .75rem; font-size:clamp(2.5rem,6vw,5rem); line-height:.98; font-weight:500; }}
    .masthead p {{ max-width:70ch; color:var(--muted); }}
    .warning {{ max-width:70ch; padding:.85rem 1rem; border-left:3px solid var(--warn); background:#311d1b; color:#ffd7d2; }}
    .stats {{ display:flex; flex-wrap:wrap; gap:.75rem; margin-top:1.5rem; }}
    .stats span {{ padding:.5rem .7rem; border:1px solid var(--line); background:#171311; font:600 .78rem/1.2 system-ui,sans-serif; }}
    .controls {{ position:sticky; top:0; z-index:10; display:flex; gap:.75rem; padding:.85rem max(1.25rem,calc((100vw - 920px)/2)); background:rgba(16,14,13,.96); border-bottom:1px solid var(--line); backdrop-filter:blur(10px); }}
    .controls input {{ min-width:0; flex:1; padding:.75rem .9rem; border:1px solid var(--line); border-radius:4px; background:#1b1714; color:var(--ink); font:inherit; }}
    .controls button {{ border:1px solid #9a6130; border-radius:4px; background:#5d3216; color:#fff3e2; padding:.75rem 1rem; cursor:pointer; }}
    main {{ width:min(920px,calc(100% - 2rem)); margin:2rem auto 8rem; }}
    .page {{ margin:0 0 1.5rem; border:1px solid var(--line); border-radius:6px; background:var(--paper); box-shadow:0 18px 50px rgba(0,0,0,.16); overflow:hidden; }}
    .page[hidden] {{ display:none; }}
    .page-header {{ display:flex; justify-content:space-between; gap:1rem; align-items:start; padding:1rem 1.25rem; background:var(--panel); border-bottom:1px solid var(--line); }}
    .page-header h2 {{ margin:.2rem 0 0; font:600 1rem/1.2 system-ui,sans-serif; }}
    .page-state {{ text-align:right; font:600 .7rem/1.2 system-ui,sans-serif; text-transform:uppercase; color:var(--muted); }}
    .page-state strong {{ display:block; margin-top:.2rem; color:var(--warn); }}
    .page-state[data-state='approved'] strong {{ color:var(--cyan); }}
    .page-columns {{ display:grid;grid-template-columns:minmax(0,1.12fr) minmax(0,.88fr); }}
    .text-panel {{ min-width:0; }}
    .text-panel + .text-panel {{ border-left:1px solid var(--line); }}
    .text-panel h3 {{ margin:0;padding:.65rem 1rem;border-bottom:1px solid var(--line);color:var(--muted);background:#171311;font:700 .68rem/1.2 system-ui,sans-serif;letter-spacing:.1em;text-transform:uppercase; }}
    .translation,.source-arabic {{ padding:clamp(1.25rem,3vw,2.25rem);white-space:pre-wrap;font-size:1.02rem; }}
    .source-arabic {{ text-align:right;font-family:'Noto Naskh Arabic','Segoe UI',serif;font-size:1.15rem;line-height:1.9; }}
    .unresolved {{ margin:0;padding:1rem 1.25rem;border-top:1px solid #8c4a43;background:#311d1b; }}
    .unresolved h3 {{ margin:0 0 .6rem;color:#ffb4aa;font:700 .75rem/1.2 system-ui,sans-serif;text-transform:uppercase;letter-spacing:.08em; }}
    .unresolved ul {{ display:grid;gap:.55rem;margin:0;padding:0;list-style:none; }}
    .unresolved li {{ display:grid;gap:.2rem; }}
    .unresolved li strong {{ color:#f0a097;font:700 .7rem/1.2 system-ui,sans-serif;text-transform:uppercase; }}
    .unresolved li span {{ color:#f5d6d2; }}
    .witness-audit {{ border-top:1px solid #3b6561;background:#10211f; }}
    .witness-audit > summary {{ cursor:pointer;padding:.9rem 1.25rem;color:#a9e3de;font:700 .75rem/1.2 system-ui,sans-serif;letter-spacing:.08em;text-transform:uppercase; }}
    .witness-summary {{ padding:0 1.25rem 1rem;color:#bad3d0; }}
    .witness-summary p {{ margin:.3rem 0 .65rem; }}
    .witness-summary a {{ margin-right:.75rem; }}
    .witness-candidates {{ margin-top:.9rem;padding:.75rem;border:1px solid #315551;background:#132a27; }}
    .witness-candidates > strong {{ color:#a9e3de;font:700 .7rem/1.2 system-ui,sans-serif;text-transform:uppercase;letter-spacing:.06em; }}
    .witness-candidates ul {{ display:grid;gap:.5rem;margin:.6rem 0 0;padding:0;list-style:none; }}
    .witness-candidates li {{ display:grid;gap:.15rem; }}
    .witness-candidates small {{ color:#84aaa6;font:500 .68rem/1.3 system-ui,sans-serif; }}
    .witness-record {{ margin:0 1.25rem 1rem;border:1px solid #315551;background:#132a27; }}
    .witness-record > header {{ display:flex;flex-wrap:wrap;gap:.5rem 1rem;align-items:center;padding:.65rem .8rem;border-bottom:1px solid #315551;font:600 .7rem/1.3 system-ui,sans-serif; }}
    .witness-record > header div {{ display:grid;flex:1;min-width:14rem; }}
    .witness-record > header small {{ color:#84aaa6;font-weight:500; }}
    .witness-record > header span {{ color:#92d0ca;text-transform:uppercase; }}
    .witness-hit {{ padding:.8rem; }}
    .witness-hit + .witness-hit {{ border-top:1px solid #315551; }}
    .witness-hit small {{ color:#8fb1ad;font:600 .68rem/1.3 system-ui,sans-serif; }}
    .witness-hit blockquote {{ margin:.45rem 0 0;padding:.8rem;border-right:3px solid #518e88;background:#0f1c1a;white-space:pre-wrap;text-align:right;font-family:'Noto Naskh Arabic','Segoe UI',serif;font-size:1.05rem;line-height:1.85; }}
    .witness-error,.witness-empty {{ margin:0;padding:.8rem;color:#e7b0aa; }}
    .witness-note {{ margin:.65rem 0 0;color:#9fc2be;font:500 .75rem/1.45 system-ui,sans-serif; }}
    .page-footer {{ padding:1rem 1.25rem; border-top:1px solid var(--line); background:#161311; }}
    .flags {{ display:flex; flex-wrap:wrap; gap:.4rem; }}
    .flag {{ border:1px solid #78483e; border-radius:99px; padding:.25rem .55rem; color:#f4b6ae; font:600 .68rem/1.2 system-ui,sans-serif; }}
    .flag.is-clear {{ border-color:#386864; color:#8bdad6; }}
    .names {{ display:flex;flex-wrap:wrap;gap:.45rem;margin-top:.85rem; }}
    .name {{ display:grid;grid-template-columns:auto auto;gap:.1rem .55rem;align-items:baseline;padding:.38rem .55rem;border:1px solid #3c625f;border-radius:5px;background:#132422; }}
    .name strong {{ color:#bce9e5;font:600 .75rem/1.2 system-ui,sans-serif; }}
    .name b {{ color:#d8c5ad;font-weight:500; }}
    .name small {{ grid-column:1/-1;color:#759b98;font:600 .58rem/1 system-ui,sans-serif;text-transform:uppercase; }}
    .name-empty {{ color:#806f62;font:italic .72rem/1.2 system-ui,sans-serif; }}
    .provenance {{ display:flex; justify-content:space-between; gap:1rem; margin-top:.9rem; color:#806f62; font:.68rem/1.4 ui-monospace,monospace; }}
    .result-count {{ color:var(--muted); white-space:nowrap; align-self:center; font:600 .75rem/1 system-ui,sans-serif; }}
    @media (max-width:760px) {{ .page-columns {{ grid-template-columns:1fr; }} .text-panel + .text-panel {{ border-left:0;border-top:1px solid var(--line); }} .provenance,.page-header {{ flex-direction:column; }} .page-state {{ text-align:left; }} }}
    @media print {{ :root {{ color-scheme:light; }} body,.page {{ background:#fff; color:#111; }} .masthead {{ background:#fff; color:#111; padding:1cm; }} .controls {{ display:none; }} main {{ width:auto; margin:0; }} .page {{ border:0; border-radius:0; box-shadow:none; break-after:page; }} .page-header,.page-footer,.text-panel h3 {{ background:#fff; }} .translation,.source-arabic {{ padding:1cm; }} a {{ color:#111; }} }}
  </style>
</head>
<body>
  <header class="masthead">
    <span class="eyebrow">FirstLight source bundle - Volume 8</span>
    <h1>al-Isabah English review draft</h1>
    <p>A human-readable presentation generated from the page-addressable structured English artifact. Scan and printed-page boundaries, review state, flags, unit identity, and canonical Arabic access remain visible.</p>
    <p class="warning"><strong>Unapproved research translation.</strong> Readability is not evidence of accuracy. Corrections belong in the JSONL source and this page must then be regenerated.</p>
    <div class="stats">
      <span>{len(units)} translated substantive pages</span>
      <span>scans {first_scan}-{last_scan}</span>
      <span>{approved_count} operator-approved</span>
      <span>{flag_count} review flags</span>
      <span>{unresolved_count} unresolved items</span>
      <span>{witness_count} witness-reviewed pages</span>
      <span>{name_count} structured name mentions</span>
    </div>
  </header>
  <div class="controls">
    <input id="search" type="search" placeholder="Search English text, page, or review flag" aria-label="Search this review draft">
    <span class="result-count" id="result-count">{len(units)} pages</span>
    <button id="clear" type="button">Clear</button>
  </div>
  <main>{articles}
  </main>
  <script>
    const pages = [...document.querySelectorAll('.page')];
    const search = document.querySelector('#search');
    const count = document.querySelector('#result-count');
    function filter() {{
      const query = search.value.trim().toLocaleLowerCase();
      let visible = 0;
      pages.forEach((page) => {{
        const match = !query || page.textContent.toLocaleLowerCase().includes(query);
        page.hidden = !match;
        if (match) visible += 1;
      }});
      count.textContent = `${{visible}} page${{visible === 1 ? '' : 's'}}`;
    }}
    search.addEventListener('input', filter);
    document.querySelector('#clear').addEventListener('click', () => {{ search.value = ''; filter(); search.focus(); }});
  </script>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Translation-unit JSONL")
    parser.add_argument("--output", required=True, type=Path, help="Generated HTML path")
    args = parser.parse_args()
    units = read_units(args.input)
    document = render_document(units, args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(document, encoding="utf-8", newline="\n")
    print(f"Rendered {len(units)} translated units to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

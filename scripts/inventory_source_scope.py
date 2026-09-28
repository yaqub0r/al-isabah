#!/usr/bin/env python3
"""Inventory a pinned source range without exporting source expression or eligibility."""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
from pathlib import Path

import translation_workflow as workflow


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode()


def digest(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def build_inventory(source: Path, manifest: dict, start: int, end: int) -> dict:
    errors = workflow.validate_source_manifest(manifest) + workflow.verify_source(source, manifest)
    if errors:
        raise ValueError("source-binding-invalid")
    entries = workflow.parse_openiti_entries(source)
    if workflow.validate_source_inventory(entries, manifest):
        raise ValueError("whole-source-inventory-invalid")
    if type(start) is not int or type(end) is not int or not 1 <= start <= end <= len(entries):
        raise ValueError("scope-range-invalid")
    selected = entries[start - 1:end]
    structures = [s for e in selected for s in e["precedingSegments"]]
    fragments = selected + structures
    lines = source.read_text(encoding="utf-8").splitlines()
    first_line = min(f["lineStart"] for f in fragments)
    # Include everything to the next owned segment/entry, or EOF. This catches
    # trailing structural text that the existing entry parser does not attach.
    if end < len(entries):
        next_entry = entries[end]
        stop_line = min(f["lineStart"] for f in [next_entry] + next_entry["precedingSegments"]) - 1
    else:
        stop_line = len(lines)
    covered: set[int] = set()
    for fragment in fragments:
        raw = fragment["rawOpeniti"]
        if hashlib.sha256(raw.encode()).hexdigest() != fragment["rawSha256"]:
            raise ValueError("fragment-binding-invalid")
        covered.update(range(fragment["lineStart"], fragment["lineStart"] + len(raw.splitlines())))
    exclusions = []
    for exclusion in workflow.source_scope_exclusions(source):
        a, b = exclusion["lineStart"], exclusion["lineEnd"]
        if b >= first_line and a <= stop_line:
            covered.update(range(a, b + 1))
            exclusions.append({"kind": exclusion["kind"], "rawSha256": exclusion["rawSha256"]})
    gaps = [i for i in range(first_line, stop_line + 1)
            if i not in covered and workflow.PAGE_RE.sub("", lines[i - 1]).strip()]
    if gaps:
        raise ValueError("unrepresented-source-material")

    records = [{"id": e["sourceUnitId"], "ordinal": e["sourceOrdinal"],
                "printedEntryNumber": e["sourceEntryNumber"], "rawSha256": e["rawSha256"],
                "locations": e["locations"],
                "precedingSegmentIds": [s["segmentId"] for s in e["precedingSegments"]]}
               for e in selected]
    segments = [{"id": s["segmentId"], "ownerUnitId": e["sourceUnitId"],
                 "kind": s["kind"], "rawSha256": s["rawSha256"],
                 "locations": s["locations"], "headingLevel": s["headingLevel"]}
                for e in selected for s in e["precedingSegments"]]
    active = []
    for entry in entries[:start]:
        for segment in entry["precedingSegments"]:
            if segment["kind"] == "structural_heading":
                active = [s for s in active if s["headingLevel"] < segment["headingLevel"]]
                active.append(segment)
    owned_ids = {s["id"] for s in segments}
    inherited = [{"id": s["segmentId"], "rawSha256": s["rawSha256"],
                  "headingLevel": s["headingLevel"], "locations": s["locations"]}
                 for s in active if s["segmentId"] not in owned_ids]
    printed = collections.Counter(e["sourceEntryNumber"] for e in selected)
    first_volumes = collections.Counter(e["locations"][0]["volume"] for e in selected if e["locations"])
    touching_volumes = collections.Counter(v for e in selected for v in {l["volume"] for l in e["locations"]})
    output = {
        "schema": "al-isabah.source-scope-inventory.v1",
        "purpose": "candidate-scope-metadata-only-not-extraction-or-admission",
        "authority": {"sourceId": manifest["sourceId"], "revision": manifest["sourceRevision"],
                      "artifactSha256": manifest["download"]["sha256"], "artifactBytes": manifest["download"]["bytes"]},
        "sourceManifestSha256": digest(manifest),
        "parserLfSha256": workflow.canonical_text_sha256(Path(workflow.__file__)),
        "scope": {"firstOrdinal": start, "lastOrdinal": end, "selection": "explicit-contiguous-source-ordinals"},
        "counts": {"entries": len(records), "structuralSegments": len(segments),
                   "substantiveUnits": len(records) + len(segments),
                   "firstLocationVolumes": {str(v): n for v, n in sorted(first_volumes.items())},
                   "touchingVolumes": {str(v): n for v, n in sorted(touching_volumes.items())},
                   "structuralKinds": dict(sorted(collections.Counter(s["kind"] for s in segments).items())),
                   "unrepresentedSubstantiveLines": 0},
        "duplicatePrintedNumbers": sorted(n for n, c in printed.items() if c > 1),
        "absentPrintedNumbersWithinRange": sorted(set(range(min(printed), max(printed) + 1)) - printed.keys()),
        "crossVolumeUnitIds": [e["id"] for e in records if len({l["volume"] for l in e["locations"]}) > 1],
        "entries": records, "structuralSegments": segments,
        "inheritedContextDependencies": inherited, "exclusions": exclusions,
    }
    output["inventorySha256"] = digest(output)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--manifest", type=Path, default=workflow.ROOT / "profiles/translation-source.v1.json")
    parser.add_argument("--start-unit", type=int, required=True)
    parser.add_argument("--end-unit", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        manifest = workflow.load_json(args.manifest)
        value = build_inventory(args.source or workflow.default_source_path(manifest), manifest, args.start_unit, args.end_unit)
        encoded = canonical_bytes(value)
        if args.check:
            if args.output.read_bytes() != encoded:
                raise ValueError("inventory-byte-mismatch")
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("xb") as stream:
                stream.write(encoded)
        print(json.dumps({"inventorySha256": value["inventorySha256"], "fileSha256": hashlib.sha256(encoded).hexdigest(), "counts": value["counts"]}, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, workflow.WorkflowError):
        print("source-scope-inventory-failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

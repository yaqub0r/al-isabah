#!/usr/bin/env python3
"""Reconcile disjoint Codex adjudication shards with exact prompt provenance."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from run_codex_volume_revision import (
    atomic_json,
    index_by_scan,
    read_jsonl,
    sha256_file,
    sha256_text,
)
from run_codex_volume_adjudication import (
    build_prompt,
    expected_provenance,
    validate_existing_page,
)


STATE_SCHEMA = "firstlight.codex-adjudication-state.v1"
REPORT_SCHEMA = "firstlight.codex-adjudication-reconciliation.v1"


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def atomic_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + ".tmp")
    with pending.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    pending.replace(path)


def load_shard(shard: Path) -> tuple[dict[int, Path], dict]:
    state_path = shard / "state.json"
    page_dir = shard / "pages"
    if not state_path.is_file() or not page_dir.is_dir():
        raise RuntimeError(f"Adjudication shard lacks state.json or pages/: {shard}")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if state.get("schema") != STATE_SCHEMA:
        raise RuntimeError(f"Adjudication shard has unsupported state schema: {shard}")
    if state.get("failed"):
        raise RuntimeError(f"Adjudication shard has failed pages: {shard}")
    if state.get("stale"):
        raise RuntimeError(f"Adjudication shard has stale pages: {shard}")
    completed = state.get("completed") or {}
    paths = {
        int(path.stem): path
        for path in sorted(page_dir.glob("[0-9][0-9][0-9][0-9].json"))
    }
    completed_scans = {int(scan) for scan in completed}
    if set(paths) != completed_scans:
        raise RuntimeError(
            f"Adjudication shard state/page mismatch in {shard}: "
            f"missing={sorted(completed_scans - set(paths))}, "
            f"extra={sorted(set(paths) - completed_scans)}"
        )
    for scan, path in paths.items():
        checkpoint = (completed.get(str(scan)) or {}).get("result_sha256")
        if not checkpoint or sha256_file(path) != checkpoint:
            raise RuntimeError(
                f"Adjudication shard checkpoint hash mismatch at scan {scan}: {shard}"
            )
        record = json.loads(path.read_text(encoding="utf-8"))
        if int(record.get("scan_page", -1)) != scan:
            raise RuntimeError(
                f"Adjudication shard filename/record mismatch at scan {scan}: {shard}"
            )
    return paths, {
        "path": str(shard.resolve()),
        "state_sha256": sha256_file(state_path),
        "completed_pages": len(paths),
    }


def reconcile(
    *,
    source_path: Path,
    translations_path: Path,
    criticisms_path: Path,
    witness_path: Path,
    shards: list[Path],
    output_path: Path,
    report_path: Path,
    schema_path: Path,
    expected_model: str,
    expected_reasoning_effort: str,
    override_shards: list[Path] | None = None,
) -> dict:
    source_by_scan = index_by_scan(read_jsonl(source_path), "Aligned source")
    scans = sorted(source_by_scan)
    translation_by_scan = index_by_scan(read_jsonl(translations_path), "Translations")
    critique_by_scan = index_by_scan(read_jsonl(criticisms_path), "Criticisms")
    witness_by_scan = index_by_scan(read_jsonl(witness_path), "Witness resolutions")
    expected_scans = set(source_by_scan)
    combined: dict[int, Path] = {}
    shard_reports = []
    for shard in shards:
        paths, shard_report = load_shard(shard.resolve())
        overlap = sorted(set(combined) & set(paths))
        if overlap:
            raise RuntimeError(f"Adjudication shards overlap at scan pages: {overlap}")
        combined.update(paths)
        shard_reports.append(shard_report)
    replacement_reports = []
    replaced_scans: set[int] = set()
    for shard in override_shards or []:
        paths, shard_report = load_shard(shard.resolve())
        duplicate_replacements = sorted(replaced_scans & set(paths))
        if duplicate_replacements:
            raise RuntimeError(
                "Adjudication override shards overlap at scan pages: "
                f"{duplicate_replacements}"
            )
        unknown = sorted(set(paths) - set(combined))
        if unknown:
            raise RuntimeError(
                "Adjudication override shard does not replace base pages: "
                f"{unknown}"
            )
        replacements = []
        for scan, path in paths.items():
            prior_record = json.loads(combined[scan].read_text(encoding="utf-8"))
            replacement_record = json.loads(path.read_text(encoding="utf-8"))
            replacements.append({
                "scan_page": scan,
                "prior_record_sha256": sha256_text(json.dumps(
                    prior_record,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )),
                "replacement_record_sha256": sha256_text(json.dumps(
                    replacement_record,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )),
            })
            combined[scan] = path
        replaced_scans.update(paths)
        replacement_reports.append({
            **shard_report,
            "replacements": sorted(replacements, key=lambda item: item["scan_page"]),
        })
    if set(combined) != expected_scans:
        raise RuntimeError(
            "Adjudication reconciliation coverage mismatch: "
            f"missing={sorted(expected_scans - set(combined))}, "
            f"extra={sorted(set(combined) - expected_scans)}"
        )
    schema_sha256 = sha256_file(schema_path)
    records = []
    for scan in sorted(combined):
        index = scans.index(scan)
        prompt = build_prompt(
            source_by_scan[scan],
            translation_by_scan[scan],
            critique_by_scan[scan],
            witness_by_scan.get(scan),
            source_by_scan[scans[index - 1]] if index > 0 else None,
            source_by_scan[scans[index + 1]] if index + 1 < len(scans) else None,
        )
        expected = expected_provenance(
            prompt=prompt,
            source=source_by_scan[scan],
            translation=translation_by_scan[scan],
            critique=critique_by_scan[scan],
            witness=witness_by_scan.get(scan),
            model=expected_model,
            reasoning_effort=expected_reasoning_effort,
            schema_sha256=schema_sha256,
        )
        valid, reason = validate_existing_page(combined[scan], expected)
        if not valid:
            raise RuntimeError(f"Adjudication provenance mismatch at scan {scan}: {reason}")
        records.append(json.loads(combined[scan].read_text(encoding="utf-8")))
    atomic_jsonl(output_path, records)
    report = {
        "schema": REPORT_SCHEMA,
        "generated_at": now(),
        "inputs": {
            "aligned_source_sha256": sha256_file(source_path),
            "translations_sha256": sha256_file(translations_path),
            "criticisms_sha256": sha256_file(criticisms_path),
            "witness_resolutions_sha256": sha256_file(witness_path),
            "output_schema_sha256": schema_sha256,
        },
        "expected_model": expected_model,
        "expected_reasoning_effort": expected_reasoning_effort,
        "shards": shard_reports,
        "override_shards": replacement_reports,
        "replaced_pages": sorted(replaced_scans),
        "expected_pages": len(expected_scans),
        "reconciled_pages": len(records),
        "first_scan": min(expected_scans) if expected_scans else None,
        "last_scan": max(expected_scans) if expected_scans else None,
        "output": str(output_path.resolve()),
        "output_sha256": sha256_file(output_path),
        "pass": True,
    }
    atomic_json(report_path, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aligned-source", required=True, type=Path)
    parser.add_argument("--translations", required=True, type=Path)
    parser.add_argument("--criticisms", required=True, type=Path)
    parser.add_argument("--witness-resolutions", required=True, type=Path)
    parser.add_argument("--shard", required=True, action="append", type=Path)
    parser.add_argument("--override-shard", action="append", default=[], type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument(
        "--schema",
        type=Path,
        default=Path(__file__).with_name("schemas") / "codex-page-adjudication.schema.json",
    )
    parser.add_argument("--expected-model", default="gpt-5.6-sol")
    parser.add_argument("--expected-reasoning-effort", default="xhigh")
    args = parser.parse_args()
    report = reconcile(
        source_path=args.aligned_source.resolve(),
        translations_path=args.translations.resolve(),
        criticisms_path=args.criticisms.resolve(),
        witness_path=args.witness_resolutions.resolve(),
        shards=args.shard,
        output_path=args.output.resolve(),
        report_path=args.report.resolve(),
        schema_path=args.schema.resolve(),
        expected_model=args.expected_model,
        expected_reasoning_effort=args.expected_reasoning_effort,
        override_shards=args.override_shard,
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

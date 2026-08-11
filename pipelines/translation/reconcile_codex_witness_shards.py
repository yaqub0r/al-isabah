#!/usr/bin/env python3
"""Reconcile completed Codex witness shards into one provenance-checked JSONL."""
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
from run_codex_volume_critic import record_sha256
from run_codex_witness_resolution import validate_witness_provenance, witness_concerns


STATE_SCHEMA = "firstlight.codex-witness-state.v1"
REPORT_SCHEMA = "firstlight.codex-witness-reconciliation.v1"


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def atomic_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + ".tmp")
    with pending.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    pending.replace(path)


def load_carried_prior_witnesses(shard: Path) -> dict[int, dict]:
    """Validate and load the prior aggregate used by a text-only refresh shard."""
    manifest_path = shard / "run-manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError(f"Carried witness images require a run manifest: {shard}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    declared_sha = manifest.get("prior_witness_resolutions_sha256")
    original_value = manifest.get("prior_witness_resolutions_path")
    snapshot = (manifest.get("input_snapshots") or {}).get(
        "prior_witness_resolutions"
    ) or {}
    snapshot_value = snapshot.get("path")
    if not declared_sha or not original_value or not snapshot_value:
        raise RuntimeError(f"Carried witness manifest is incomplete: {shard}")
    original_path = Path(str(original_value)).resolve()
    snapshot_path = Path(str(snapshot_value)).resolve()
    if (
        not original_path.is_file()
        or not snapshot_path.is_file()
        or sha256_file(original_path) != declared_sha
        or sha256_file(snapshot_path) != declared_sha
        or snapshot.get("sha256") != declared_sha
    ):
        raise RuntimeError(f"Carried prior witness aggregate hash mismatch: {shard}")
    report_candidates = (
        original_path.with_name("reconciliation-report.json"),
        original_path.with_name("reconciliation.json"),
    )
    report_path = next((path for path in report_candidates if path.is_file()), None)
    if report_path is None:
        raise RuntimeError(
            f"Carried prior witness lacks its reconciliation report: {original_path}"
        )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if (
        report.get("schema") != REPORT_SCHEMA
        or not report.get("pass")
        or report.get("output_sha256") != declared_sha
    ):
        raise RuntimeError(
            f"Carried prior witness reconciliation is invalid: {report_path}"
        )
    return index_by_scan(read_jsonl(snapshot_path), "Carried prior witnesses")


def load_shard(shard: Path) -> tuple[dict[int, dict], dict]:
    state_path = shard / "state.json"
    page_dir = shard / "pages"
    if not state_path.is_file() or not page_dir.is_dir():
        raise RuntimeError(f"Witness shard lacks state.json or pages/: {shard}")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if state.get("schema") != STATE_SCHEMA:
        raise RuntimeError(f"Witness shard has unsupported state schema: {shard}")
    if state.get("failed"):
        raise RuntimeError(f"Witness shard has failed pages: {shard}")
    if state.get("stale"):
        raise RuntimeError(f"Witness shard has stale pages: {shard}")
    completed = state.get("completed") or {}
    page_paths = sorted(page_dir.glob("[0-9][0-9][0-9][0-9].json"))
    page_scans = {int(path.stem) for path in page_paths}
    completed_scans = {int(scan) for scan in completed}
    if page_scans != completed_scans:
        missing = sorted(completed_scans - page_scans)
        extra = sorted(page_scans - completed_scans)
        raise RuntimeError(
            f"Witness shard state/page mismatch in {shard}: missing={missing}, extra={extra}"
        )
    records: dict[int, dict] = {}
    carried_prior_by_scan: dict[int, dict] | None = None
    carried_prior_scans = []
    for path in page_paths:
        scan = int(path.stem)
        expected_sha = (completed.get(str(scan)) or {}).get("result_sha256")
        observed_sha = sha256_file(path)
        if not expected_sha or observed_sha != expected_sha:
            raise RuntimeError(f"Witness shard checkpoint hash mismatch at scan {scan}: {shard}")
        record = json.loads(path.read_text(encoding="utf-8"))
        if int(record.get("scan_page", -1)) != scan:
            raise RuntimeError(f"Witness shard filename/record mismatch at scan {scan}: {shard}")
        image_hashes = record.get("witness_image_sha256") or []
        candidates = record.get("urdu_witness_candidates") or []
        if len(image_hashes) != len(candidates):
            raise RuntimeError(f"Witness image/candidate count mismatch at scan {scan}: {shard}")
        for index, candidate in enumerate(candidates):
            image_path = shard / "witness-images" / (
                f"arabic-{scan:04d}-urdu-{int(candidate['scan_page']):04d}.png"
            )
            if image_path.is_file() and sha256_file(image_path) == image_hashes[index]:
                continue
            if not record.get("prior_witness_resolution_sha256"):
                raise RuntimeError(f"Witness image hash mismatch at scan {scan}: {image_path}")
            if carried_prior_by_scan is None:
                carried_prior_by_scan = load_carried_prior_witnesses(shard)
            prior = carried_prior_by_scan.get(scan)
            if prior is None or record_sha256(prior) != record[
                "prior_witness_resolution_sha256"
            ]:
                raise RuntimeError(
                    f"Carried prior witness record hash mismatch at scan {scan}: {shard}"
                )
            if (
                prior.get("urdu_witness_candidates") != candidates
                or prior.get("candidate_evidence_sha256")
                != record.get("candidate_evidence_sha256")
                or prior.get("witness_image_sha256") != image_hashes
            ):
                raise RuntimeError(
                    f"Carried prior witness evidence mismatch at scan {scan}: {shard}"
                )
            carried_prior_scans.append(scan)
            break
        records[scan] = record
    return records, {
        "path": str(shard.resolve()),
        "state_sha256": sha256_file(state_path),
        "completed_pages": len(records),
        "carried_prior_image_pages": sorted(set(carried_prior_scans)),
    }


def reconcile(
    *,
    source_path: Path,
    translations_path: Path,
    criticisms_path: Path,
    shards: list[Path],
    override_shards: list[Path] | None,
    output_path: Path,
    report_path: Path,
    expected_model: str,
    expected_reasoning_effort: str,
) -> dict:
    source_by_scan = index_by_scan(read_jsonl(source_path), "Aligned source")
    translation_by_scan = index_by_scan(read_jsonl(translations_path), "Translations")
    critique_by_scan = index_by_scan(read_jsonl(criticisms_path), "Criticisms")
    expected_scans = {
        scan
        for scan, translation in translation_by_scan.items()
        if witness_concerns(translation, critique_by_scan.get(scan))
    }
    combined: dict[int, dict] = {}
    shard_reports = []
    for shard in shards:
        records, shard_report = load_shard(shard.resolve())
        duplicates = sorted(set(combined) & set(records))
        if duplicates:
            raise RuntimeError(f"Witness shards overlap at scan pages: {duplicates}")
        combined.update(records)
        shard_reports.append(shard_report)
    replacement_reports = []
    replaced_scans: set[int] = set()
    for shard in override_shards or []:
        records, shard_report = load_shard(shard.resolve())
        duplicate_replacements = sorted(replaced_scans & set(records))
        if duplicate_replacements:
            raise RuntimeError(
                f"Witness override shards overlap at scan pages: {duplicate_replacements}"
            )
        unknown = sorted(set(records) - set(combined))
        if unknown:
            raise RuntimeError(
                f"Witness override shard does not replace base pages: {unknown}"
            )
        replacements = []
        for scan, record in records.items():
            replacements.append({
                "scan_page": scan,
                "prior_record_sha256": sha256_text(
                    json.dumps(combined[scan], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                ),
                "replacement_record_sha256": sha256_text(
                    json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                ),
            })
            combined[scan] = record
        replaced_scans.update(records)
        replacement_reports.append({**shard_report, "replacements": sorted(replacements, key=lambda item: item["scan_page"])})
    observed_scans = set(combined)
    if observed_scans != expected_scans:
        missing = sorted(expected_scans - observed_scans)
        extra = sorted(observed_scans - expected_scans)
        raise RuntimeError(
            f"Witness reconciliation coverage mismatch: missing={missing}, extra={extra}"
        )
    incomplete_evidence = []
    for scan in sorted(combined):
        if scan not in source_by_scan or scan not in critique_by_scan:
            raise RuntimeError(f"Witness scan {scan} lacks source or critique input")
        record = combined[scan]
        current, reason = validate_witness_provenance(
            source_by_scan[scan],
            translation_by_scan[scan],
            critique_by_scan[scan],
            record,
        )
        if not current:
            raise RuntimeError(f"Witness provenance mismatch at scan {scan}: {reason}")
        if record.get("model") != expected_model:
            raise RuntimeError(f"Unexpected witness model at scan {scan}: {record.get('model')}")
        if record.get("reasoning_effort") != expected_reasoning_effort:
            raise RuntimeError(
                f"Unexpected witness reasoning effort at scan {scan}: {record.get('reasoning_effort')}"
            )
        incomplete = [
            item
            for item in record.get("secondary_witness_evidence") or []
            if item.get("retrieval_state") not in {"hit", "no_match"}
        ]
        if incomplete:
            incomplete_evidence.append({
                "scan_page": scan,
                "states": sorted({str(item.get("retrieval_state")) for item in incomplete}),
                "works": sorted({str(item.get("work_id")) for item in incomplete}),
            })
    if incomplete_evidence:
        raise RuntimeError(
            "Incomplete collateral witness evidence: "
            + json.dumps(incomplete_evidence, ensure_ascii=False, separators=(",", ":"))
        )
    ordered = [combined[scan] for scan in sorted(combined)]
    atomic_jsonl(output_path, ordered)
    report = {
        "schema": REPORT_SCHEMA,
        "generated_at": now(),
        "inputs": {
            "aligned_source_sha256": sha256_file(source_path),
            "translations_sha256": sha256_file(translations_path),
            "criticisms_sha256": sha256_file(criticisms_path),
        },
        "expected_model": expected_model,
        "expected_reasoning_effort": expected_reasoning_effort,
        "shards": shard_reports,
        "override_shards": replacement_reports,
        "replaced_pages": sorted(replaced_scans),
        "expected_flagged_pages": len(expected_scans),
        "reconciled_pages": len(ordered),
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
    parser.add_argument("--shard", required=True, action="append", type=Path)
    parser.add_argument("--override-shard", action="append", default=[], type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--expected-model", default="gpt-5.6-sol")
    parser.add_argument("--expected-reasoning-effort", default="xhigh")
    args = parser.parse_args()
    report = reconcile(
        source_path=args.aligned_source.resolve(),
        translations_path=args.translations.resolve(),
        criticisms_path=args.criticisms.resolve(),
        shards=args.shard,
        override_shards=args.override_shard,
        output_path=args.output.resolve(),
        report_path=args.report.resolve(),
        expected_model=args.expected_model,
        expected_reasoning_effort=args.expected_reasoning_effort,
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

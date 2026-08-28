#!/usr/bin/env python3
"""Build the v2 public-working distribution from the strict public proposal."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from public_boundary import boundary_errors, canonical_json, sha256_bytes, sha256_file, summarize
from validate_current_release_closure import (
    CURRENT_CLOSURE,
    output_review_path,
    public_review_path,
    validate as validate_closure,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "2.0.0"
WORK_ID = "ibn-hajar-al-isabah"
REPOSITORY = "https://github.com/yaqub0r/al-isabah"
RIGHTS_MATRIX = ROOT / "compliance" / "rights-matrix.al-isabah.v1.json"


class DistributionError(RuntimeError):
    """Raised when a public distribution cannot be built safely."""


def utc_timestamp(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise DistributionError("generated timestamp must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def git_value(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def build(output: Path, repository_commit: str, generated_at: str) -> dict[str, Any]:
    closure_errors = validate_closure(CURRENT_CLOSURE)
    if closure_errors:
        raise DistributionError(summarize(closure_errors))
    if output.exists() and any(path.is_file() for path in output.rglob("*")):
        raise DistributionError("output directory must be empty")
    closure = json.loads(CURRENT_CLOSURE.read_text(encoding="utf-8"))
    proposals = [
        (
            ROOT / item["publicProposal"]["path"],
            json.loads((ROOT / item["publicProposal"]["path"]).read_text(encoding="utf-8")),
        )
        for item in closure["proposals"]
    ]
    inventory = {item["path"]: item for item in closure["outputInventory"]}
    output.mkdir(parents=True, exist_ok=True)
    records_dir = output / "records"
    records_dir.mkdir(exist_ok=True)
    reviews_dir = output / "reviews"
    reviews_dir.mkdir(exist_ok=True)
    records_by_volume: dict[int, list[dict[str, Any]]] = defaultdict(list)
    all_records: list[dict[str, Any]] = []
    for proposal_path, proposal in proposals:
        for record in proposal["records"]:
            records_by_volume[record["volume"]].append(record)
            all_records.append(record)
        review_source = public_review_path(proposal_path)
        review_output = output / output_review_path(proposal)
        review_output.write_bytes(review_source.read_bytes())
    files: list[dict[str, Any]] = []
    for volume, records in sorted(records_by_volume.items()):
        records.sort(key=lambda item: (item["sourceOrdinal"], item["id"]))
        record_bytes = b"".join(canonical_json(record) for record in records)
        relative = f"records/volume-{volume:02}.jsonl"
        expected_record = inventory[relative]
        if (
            sha256_bytes(record_bytes) != expected_record["sha256"]
            or len(record_bytes) != expected_record["bytes"]
            or len(records) != expected_record["recordCount"]
        ):
            raise DistributionError("release closure rejected the record projection")
        (output / relative).write_bytes(record_bytes)
        files.append(
            {
                "path": relative,
                "sha256": sha256_bytes(record_bytes),
                "bytes": len(record_bytes),
                "recordCount": len(records),
                "volume": volume,
            }
        )
    for relative, expected_output in inventory.items():
        path = output / relative
        if (
            not path.is_file()
            or sha256_file(path) != expected_output["sha256"]
            or path.stat().st_size != expected_output["bytes"]
        ):
            raise DistributionError("release closure rejected the output inventory")
    (output / "release-closure.json").write_bytes(CURRENT_CLOSURE.read_bytes())
    printed: dict[int, list[str]] = defaultdict(list)
    for record in all_records:
        printed[record["printedEntryNumber"]].append(record["id"])
    duplicate_printed = [
        {"printedEntryNumber": number, "recordIds": ids}
        for number, ids in sorted(printed.items()) if len(ids) > 1
    ]
    rights_matrix = json.loads(RIGHTS_MATRIX.read_text(encoding="utf-8"))
    license_record = rights_matrix["public_content_license"]
    authorities = {
        proposal["sourceAuthority"]["sourceId"]: proposal["sourceAuthority"]
        for _, proposal in proposals
    }
    manifest = {
        "schemaVersion": SCHEMA_VERSION,
        "distributionId": f"al-isabah-public-working-{repository_commit[:12]}",
        "publicationStatus": "public-working",
        "canonicalPromotion": "blocked",
        "work": {"id": WORK_ID, "titleArabic": "الإصابة في تمييز الصحابة", "titleEnglish": "Al-Isabah fi Tamyiz al-Sahabah"},
        "repository": {"url": REPOSITORY, "commit": repository_commit},
        "generatedAt": generated_at,
        "rights": {
            "matrixId": rights_matrix["matrix_id"],
            "license": {"spdx": license_record["spdx"], "url": license_record["url"]},
            "softwareLicenseGranted": license_record["software_license_granted"],
            "attribution": rights_matrix["attribution"],
            "excludedMaterial": rights_matrix["exclusions"],
        },
        "packets": [
            {
                "packetId": proposal["proposalId"],
                "sha256": sha256_file(path),
                "entryCount": len(proposal["records"]),
            }
            for path, proposal in proposals
        ],
        "authorities": [authorities[key] for key in sorted(authorities)],
        "counts": {
            "entries": len(all_records),
            "machinePassed": sum(
                proposal["review"]["machinePassed"] for _, proposal in proposals
            ),
            "needsAttention": sum(
                proposal["review"]["needsAttention"] for _, proposal in proposals
            ),
            "humanReviewed": sum(
                proposal["review"]["humanReviewed"] for _, proposal in proposals
            ),
        },
        "duplicatePrintedEntryNumbers": duplicate_printed,
        "files": files,
        "releaseClosure": {
            "closureId": closure["closureId"],
            "sha256": sha256_file(CURRENT_CLOSURE),
        },
    }
    errors = boundary_errors(manifest, "manifest") + boundary_errors(all_records, "records")
    if errors:
        raise DistributionError(summarize(errors))
    (output / "manifest.json").write_bytes(canonical_json(manifest))
    expected_paths = set(inventory) | {"manifest.json", "release-closure.json"}
    actual_paths = {
        path.relative_to(output).as_posix()
        for path in output.rglob("*")
        if path.is_file()
    }
    if actual_paths != expected_paths:
        raise DistributionError("release closure rejected the output inventory")
    return manifest


def package(output: Path, archive: Path) -> None:
    from validate_public_distribution import validate as validate_distribution

    errors = validate_distribution(output)
    if errors:
        raise DistributionError(summarize(errors))
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in sorted(output.rglob("*")):
            if path.is_file():
                info = zipfile.ZipInfo(path.relative_to(output).as_posix())
                info.date_time = (1980, 1, 1, 0, 0, 0)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                bundle.writestr(info, path.read_bytes())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--repository-commit")
    parser.add_argument("--generated-at")
    args = parser.parse_args()
    commit = args.repository_commit or git_value("rev-parse", "HEAD")
    generated_at = args.generated_at or git_value("show", "-s", "--format=%cI", commit)
    if not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise DistributionError("repository commit must be a full lowercase SHA-1")
    manifest = build(args.output.resolve(), commit, utc_timestamp(generated_at))
    if args.archive:
        package(args.output.resolve(), args.archive.resolve())
    print(f"Built {manifest['distributionId']} with {manifest['counts']['entries']} public-working entries and exact release closure.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

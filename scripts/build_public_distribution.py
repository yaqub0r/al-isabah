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
from validate_release_closure import CLOSURE, PROPOSAL, PUBLIC_REVIEW, validate as validate_closure


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
    closure_errors = validate_closure(CLOSURE)
    if closure_errors:
        raise DistributionError(summarize(closure_errors))
    proposal = json.loads(PROPOSAL.read_text(encoding="utf-8"))
    records = proposal["records"]
    record_bytes = b"".join(canonical_json(record) for record in records)
    closure = json.loads(CLOSURE.read_text(encoding="utf-8"))
    inventory = {item["path"]: item for item in closure["outputInventory"]}
    expected_record = inventory["records/volume-01.jsonl"]
    if sha256_bytes(record_bytes) != expected_record["sha256"] or len(record_bytes) != expected_record["bytes"]:
        raise DistributionError("release closure rejected the record projection")
    output.mkdir(parents=True, exist_ok=True)
    records_dir = output / "records"
    records_dir.mkdir(exist_ok=True)
    (records_dir / "volume-01.jsonl").write_bytes(record_bytes)
    (output / "review.json").write_bytes(PUBLIC_REVIEW.read_bytes())
    (output / "release-closure.json").write_bytes(CLOSURE.read_bytes())
    printed: dict[int, list[str]] = defaultdict(list)
    for record in records:
        printed[record["printedEntryNumber"]].append(record["id"])
    duplicate_printed = [
        {"printedEntryNumber": number, "recordIds": ids}
        for number, ids in sorted(printed.items()) if len(ids) > 1
    ]
    rights_matrix = json.loads(RIGHTS_MATRIX.read_text(encoding="utf-8"))
    license_record = rights_matrix["public_content_license"]
    authority = proposal["sourceAuthority"]
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
        "packets": [{"packetId": proposal["proposalId"], "sha256": sha256_file(PROPOSAL), "entryCount": len(records)}],
        "authorities": [authority],
        "counts": {
            "entries": len(records),
            "machinePassed": proposal["review"]["machinePassed"],
            "needsAttention": proposal["review"]["needsAttention"],
            "humanReviewed": proposal["review"]["humanReviewed"],
        },
        "duplicatePrintedEntryNumbers": duplicate_printed,
        "files": [{"path": "records/volume-01.jsonl", "sha256": sha256_bytes(record_bytes), "bytes": len(record_bytes), "recordCount": len(records), "volume": 1}],
        "releaseClosure": {"closureId": closure["closureId"], "sha256": sha256_file(CLOSURE)},
    }
    errors = boundary_errors(manifest, "manifest") + boundary_errors(records, "records")
    if errors:
        raise DistributionError(summarize(errors))
    (output / "manifest.json").write_bytes(canonical_json(manifest))
    return manifest


def package(output: Path, archive: Path) -> None:
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

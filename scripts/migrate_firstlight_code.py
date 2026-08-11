#!/usr/bin/env python3
"""Copy hash-verified FirstLight pipeline files into their standalone homes."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path, PurePosixPath


MAPPINGS = {
    "canonical_schema": (
        PurePosixPath("docs/narrative/sources/schemas"),
        PurePosixPath("evidence/schemas"),
    ),
    "candidate_translation_pipeline": (
        PurePosixPath("firstlight-research/scripts/translation"),
        PurePosixPath("pipelines/translation"),
    ),
    "candidate_acquisition_pipeline": (
        PurePosixPath("tools/source-acquisition"),
        PurePosixPath("pipelines/acquisition"),
    ),
}

EXACT_MAPPINGS = {
    "docs/narrative/sources/T1_primaries/ibn_hajar_isabah_v1/README.md":
        "evidence/firstlight/source/README.md",
    "docs/narrative/sources/T1_primaries/ibn_hajar_isabah_v1/edition-lock.json":
        "evidence/firstlight/source/edition-lock.json",
    "docs/narrative/sources/T1_primaries/ibn_hajar_isabah_v1/source-bundle.v1.json":
        "evidence/firstlight/source/source-bundle.v1.json",
    "docs/narrative/sources/T1_primaries/ibn_hajar_isabah_v1/urdu_witness_v1/README.md":
        "evidence/firstlight/source/urdu-witness.README.md",
    "docs/narrative/sources/T1_primaries/ibn_hajar_isabah_v1/urdu_witness_v1/witness-lock.json":
        "evidence/firstlight/source/urdu-witness-lock.json",
    "firstlight-research/data/translated/ibn_hajar_isabah/arabic_v1/README.md":
        "evidence/firstlight/volume-08/README.md",
    "firstlight-research/data/translated/ibn_hajar_isabah/arabic_v1/volume_08.machine-readiness.json":
        "evidence/firstlight/volume-08/machine-readiness.json",
    "firstlight-research/data/translated/ibn_hajar_isabah/arabic_v1/volume_08.source-repairs.json":
        "evidence/firstlight/volume-08/source-repairs.json",
    "firstlight-research/data/translated/ibn_hajar_isabah/arabic_v1/volume_08.supplemental-witness-evidence.jsonl":
        "evidence/firstlight/volume-08/supplemental-witness-evidence.jsonl",
    "firstlight-research/data/translated/ibn_hajar_isabah/arabic_v1/volume_08.translation-plan.json":
        "evidence/firstlight/volume-08/translation-plan.json",
    "firstlight-research/data/translated/ibn_hajar_isabah/arabic_v1/volume_08.usul-alignment-report.json":
        "evidence/firstlight/volume-08/usul-alignment-report.json",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def mapped_destination(record: dict) -> PurePosixPath | None:
    source_path = str(record.get("path") or "")
    exact = EXACT_MAPPINGS.get(source_path)
    if exact:
        return PurePosixPath(exact)
    role = record.get("role")
    if role not in MAPPINGS:
        return None
    source_prefix, destination_prefix = MAPPINGS[role]
    path = PurePosixPath(source_path)
    try:
        relative = path.relative_to(source_prefix)
    except ValueError as error:
        raise RuntimeError(f"{role} path is outside its allowed prefix: {path}") from error
    return destination_prefix / relative


def migrate(
    source_root: Path, destination_root: Path, inventory: dict, *,
    preserve_adapted: bool = False,
) -> dict:
    copied = reused = adapted = 0
    destinations: set[PurePosixPath] = set()
    for record in inventory.get("files") or []:
        destination_rel = mapped_destination(record)
        if destination_rel is None:
            continue
        if destination_rel in destinations:
            raise RuntimeError(f"Duplicate destination: {destination_rel}")
        destinations.add(destination_rel)
        source_rel = PurePosixPath(record["path"])
        source = source_root.joinpath(*source_rel.parts)
        destination = destination_root.joinpath(*destination_rel.parts)
        expected = record["sha256"]
        if not source.is_file() or source.stat().st_size != record["byte_size"]:
            raise RuntimeError(f"Missing or size-mismatched source: {source_rel}")
        if sha256_file(source) != expected:
            raise RuntimeError(f"Hash-mismatched source: {source_rel}")
        if destination.exists():
            if destination.is_file() and sha256_file(destination) == expected:
                reused += 1
                continue
            if preserve_adapted and destination.is_file():
                adapted += 1
                continue
            raise RuntimeError(f"Refusing to overwrite divergent destination: {destination_rel}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            dir=destination.parent, prefix=f".{destination.name}.",
            suffix=".partial", delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
        try:
            shutil.copyfile(source, temporary_path)
            if sha256_file(temporary_path) != expected:
                raise RuntimeError(f"Copied bytes failed verification: {destination_rel}")
            os.replace(temporary_path, destination)
        finally:
            temporary_path.unlink(missing_ok=True)
        copied += 1
    return {
        "selected": len(destinations), "copied": copied,
        "reused": reused, "preserved_adapted": adapted,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--destination-root", default=Path.cwd(), type=Path)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument(
        "--preserve-adapted", action="store_true",
        help="Keep existing divergent files and report them instead of overwriting",
    )
    args = parser.parse_args()
    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    result = migrate(
        args.source_root.resolve(), args.destination_root.resolve(), inventory,
        preserve_adapted=args.preserve_adapted,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

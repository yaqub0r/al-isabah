#!/usr/bin/env python3
"""Build, stage, verify, publish, and hydrate immutable research artifacts."""
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath


MANIFEST_SCHEMA = "al-isabah.artifact-manifest.v1"
INVENTORY_SCHEMA = "al-isabah.firstlight-migration-inventory.v1"
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
VOLUME_RE = re.compile(r"(?:^|/)volume_(\d{2})(?:\.|/)")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def object_key(digest: str) -> str:
    if not SHA_RE.fullmatch(digest):
        raise ValueError(f"Invalid SHA-256 digest: {digest!r}")
    return f"sha256/{digest[:2]}/{digest}"


def safe_repository_path(value: str) -> PurePosixPath:
    if not value or "\\" in value:
        raise ValueError(f"Expected a normalized repository path: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"Repository path escapes its root: {value!r}")
    return path


def infer_volume(path: str) -> int | None:
    match = VOLUME_RE.search(path)
    return int(match.group(1)) if match else None


def infer_language(path: str) -> str:
    lowered = path.lower()
    if "urdu" in lowered:
        return "ur"
    if "arabic" in lowered or "ibn_hajar_isabah_v1" in lowered:
        return "ar" if "translation" not in lowered and "review" not in lowered else "mul"
    return "mul"


def infer_format(path: str) -> str:
    if path.endswith(".jsonl"):
        return "application/x-ndjson"
    if path.endswith(".ocr.xml.gz"):
        return "application/gzip+alto-xml"
    if path.endswith(".txt.gz") or path.endswith(".json.gz"):
        return "application/gzip"
    return mimetypes.guess_type(path)[0] or "application/octet-stream"


def build_manifest(inventory: dict, *, work_id: str) -> dict:
    if inventory.get("schema") != INVENTORY_SCHEMA:
        raise RuntimeError(f"Unsupported inventory schema: {inventory.get('schema')}")
    artifacts = []
    seen_ids: set[str] = set()
    for record in inventory.get("files") or []:
        path = safe_repository_path(str(record.get("path") or "")).as_posix()
        digest = str(record.get("sha256") or "")
        size = int(record.get("byte_size", -1))
        if size < 0 or not SHA_RE.fullmatch(digest):
            raise RuntimeError(f"Invalid inventory record: {path}")
        artifact_id = f"firstlight:{path}"
        if artifact_id in seen_ids:
            raise RuntimeError(f"Duplicate artifact id: {artifact_id}")
        seen_ids.add(artifact_id)
        artifacts.append({
            "artifact_id": artifact_id,
            "role": str(record.get("role") or "unclassified"),
            "language": infer_language(path),
            "format": infer_format(path),
            "volume": infer_volume(path),
            "byte_size": size,
            "sha256": digest,
            "object_key": object_key(digest),
            "rights": "private",
            "origin": {"repository_path": path, "source_url": None},
            "derived_from": [],
        })
    return {
        "schema": MANIFEST_SCHEMA,
        "work_id": work_id,
        "generated_from": {
            "repository": str(inventory.get("source_repository") or ""),
            "revision": str(inventory.get("source_revision") or ""),
            "inventory_sha256": str(inventory.get("inventory_sha256") or ""),
        },
        "artifacts": sorted(artifacts, key=lambda item: item["artifact_id"]),
    }


def validate_manifest(manifest: dict) -> None:
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise RuntimeError(f"Unsupported manifest schema: {manifest.get('schema')}")
    if not str(manifest.get("work_id") or "").strip():
        raise RuntimeError("Manifest requires work_id")
    generated = manifest.get("generated_from") or {}
    if not SHA_RE.fullmatch(str(generated.get("inventory_sha256") or "")):
        raise RuntimeError("Manifest has invalid inventory_sha256")
    ids: set[str] = set()
    keys: dict[str, tuple[int, str]] = {}
    for item in manifest.get("artifacts") or []:
        artifact_id = str(item.get("artifact_id") or "")
        digest = str(item.get("sha256") or "")
        size = int(item.get("byte_size", -1))
        if not artifact_id or artifact_id in ids:
            raise RuntimeError(f"Duplicate or empty artifact_id: {artifact_id!r}")
        ids.add(artifact_id)
        if item.get("object_key") != object_key(digest) or size < 0:
            raise RuntimeError(f"Invalid content identity for {artifact_id}")
        identity = (size, digest)
        prior = keys.setdefault(item["object_key"], identity)
        if prior != identity:
            raise RuntimeError(f"Conflicting object identity: {item['object_key']}")
        safe_repository_path(str((item.get("origin") or {}).get("repository_path") or ""))


def select_artifacts(
    manifest: dict, *, volume: int | None = None, role: str | None = None,
    artifact_id: str | None = None,
) -> list[dict]:
    validate_manifest(manifest)
    selected = []
    for item in manifest["artifacts"]:
        if volume is not None and item.get("volume") != volume:
            continue
        if role is not None and item.get("role") != role:
            continue
        if artifact_id is not None and item.get("artifact_id") != artifact_id:
            continue
        selected.append(item)
    if not selected:
        raise RuntimeError("Artifact selection is empty")
    return selected


def cached_path(cache: Path, item: dict) -> Path:
    return cache.joinpath(*PurePosixPath(item["object_key"]).parts)


def verify_file(path: Path, item: dict) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"Artifact is not hydrated: {item['artifact_id']}")
    actual_size = path.stat().st_size
    if actual_size != item["byte_size"]:
        raise RuntimeError(
            f"Size mismatch for {item['artifact_id']}: {actual_size} != {item['byte_size']}"
        )
    actual_sha = sha256_file(path)
    if actual_sha != item["sha256"]:
        raise RuntimeError(
            f"SHA-256 mismatch for {item['artifact_id']}: {actual_sha} != {item['sha256']}"
        )


def atomic_copy(source: Path, destination: Path, item: dict) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=f".{destination.name}.", suffix=".partial", dir=destination.parent, delete=False
    ) as temporary:
        temporary_path = Path(temporary.name)
    try:
        shutil.copyfile(source, temporary_path)
        verify_file(temporary_path, item)
        os.replace(temporary_path, destination)
    finally:
        temporary_path.unlink(missing_ok=True)


def stage(source_root: Path, cache: Path, items: list[dict]) -> dict:
    source_root = source_root.resolve()
    staged = reused = 0
    for item in items:
        source_rel = safe_repository_path(item["origin"]["repository_path"])
        source = source_root.joinpath(*source_rel.parts)
        destination = cached_path(cache, item)
        if destination.exists():
            verify_file(destination, item)
            reused += 1
            continue
        verify_file(source, item)
        atomic_copy(source, destination, item)
        staged += 1
    return {"selected": len(items), "staged": staged, "reused": reused}


def verify(cache: Path, items: list[dict]) -> dict:
    for item in items:
        verify_file(cached_path(cache, item), item)
    return {"selected": len(items), "verified": len(items)}


def aws_command(
    operation: str, *, endpoint_url: str, bucket: str, item: dict,
    local_path: Path, profile: str | None,
) -> list[str]:
    command = ["aws"]
    if profile:
        command.extend(["--profile", profile])
    command.extend(["--endpoint-url", endpoint_url, "s3", operation])
    remote = f"s3://{bucket}/{item['object_key']}"
    if operation == "cp":
        command.extend([str(local_path), remote, "--only-show-errors"])
    elif operation == "download":
        command[command.index("download")] = "cp"
        command.extend([remote, str(local_path), "--only-show-errors"])
    else:
        raise ValueError(f"Unsupported AWS operation: {operation}")
    return command


def publish(
    cache: Path, items: list[dict], *, endpoint_url: str, bucket: str,
    profile: str | None,
) -> dict:
    for item in items:
        source = cached_path(cache, item)
        verify_file(source, item)
        subprocess.run(
            aws_command("cp", endpoint_url=endpoint_url, bucket=bucket, item=item,
                        local_path=source, profile=profile),
            check=True,
        )
    return {"selected": len(items), "published": len(items)}


def hydrate(
    cache: Path, items: list[dict], *, endpoint_url: str, bucket: str,
    profile: str | None,
) -> dict:
    hydrated = reused = 0
    for item in items:
        destination = cached_path(cache, item)
        if destination.exists():
            verify_file(destination, item)
            reused += 1
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            prefix=f".{destination.name}.", suffix=".partial",
            dir=destination.parent, delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
        try:
            subprocess.run(
                aws_command("download", endpoint_url=endpoint_url, bucket=bucket,
                            item=item, local_path=temporary_path, profile=profile),
                check=True,
            )
            verify_file(temporary_path, item)
            os.replace(temporary_path, destination)
            hydrated += 1
        finally:
            temporary_path.unlink(missing_ok=True)
    return {"selected": len(items), "hydrated": hydrated, "reused": reused}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n",
    )


def add_selection_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--volume", type=int)
    parser.add_argument("--role")
    parser.add_argument("--artifact-id")


def require_remote(args: argparse.Namespace) -> tuple[str, str, str | None]:
    endpoint = args.endpoint_url or os.environ.get("AL_ISABAH_S3_ENDPOINT")
    bucket = args.bucket or os.environ.get("AL_ISABAH_S3_BUCKET")
    profile = args.profile or os.environ.get("AL_ISABAH_AWS_PROFILE")
    if not endpoint or not bucket:
        raise RuntimeError(
            "Remote access requires --endpoint-url/AL_ISABAH_S3_ENDPOINT and "
            "--bucket/AL_ISABAH_S3_BUCKET"
        )
    return endpoint, bucket, profile


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build-manifest")
    build.add_argument("--inventory", required=True, type=Path)
    build.add_argument("--work-id", default="ibn-hajar-al-isabah")
    build.add_argument("--output", required=True, type=Path)
    for name in ("stage", "verify", "publish", "hydrate"):
        command = subparsers.add_parser(name)
        command.add_argument("--manifest", required=True, type=Path)
        command.add_argument("--cache", required=True, type=Path)
        add_selection_arguments(command)
        if name == "stage":
            command.add_argument("--source-root", required=True, type=Path)
        if name in {"publish", "hydrate"}:
            command.add_argument("--endpoint-url")
            command.add_argument("--bucket")
            command.add_argument("--profile")
    args = parser.parse_args()
    if args.command == "build-manifest":
        manifest = build_manifest(load_json(args.inventory), work_id=args.work_id)
        validate_manifest(manifest)
        write_json(args.output, manifest)
        result = {"artifacts": len(manifest["artifacts"]), "output": str(args.output)}
    else:
        manifest = load_json(args.manifest)
        items = select_artifacts(
            manifest, volume=args.volume, role=args.role, artifact_id=args.artifact_id
        )
        if args.command == "stage":
            result = stage(args.source_root, args.cache, items)
        elif args.command == "verify":
            result = verify(args.cache, items)
        else:
            endpoint, bucket, profile = require_remote(args)
            if args.command == "publish":
                result = publish(args.cache, items, endpoint_url=endpoint,
                                 bucket=bucket, profile=profile)
            else:
                result = hydrate(args.cache, items, endpoint_url=endpoint,
                                 bucket=bucket, profile=profile)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, RuntimeError, ValueError, subprocess.CalledProcessError) as error:
        print(f"artifact-store: {error}", file=sys.stderr)
        raise SystemExit(1)


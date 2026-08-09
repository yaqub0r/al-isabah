#!/usr/bin/env python3
"""Create a deterministic SHA-256 inventory for the FirstLight migration.

The source tree is read-only. Paths are repository-relative, symlinks are
rejected, and duplicate inclusion is an error so the inventory has one clear
role for every artifact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path, PurePosixPath


SCOPE_SCHEMA = "al-isabah.firstlight-migration-scope.v1"
INVENTORY_SCHEMA = "al-isabah.firstlight-migration-inventory.v1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_relative_path(value: str) -> PurePosixPath:
    if not value or "\\" in value:
        raise ValueError(f"Migration paths must be non-empty POSIX paths: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"Migration path escapes or is not normalized: {value!r}")
    return path


def files_for_include(source_root: Path, item: dict) -> list[Path]:
    relative = validate_relative_path(str(item.get("path") or ""))
    path = source_root.joinpath(*relative.parts)
    kind = item.get("kind")
    if not path.exists():
        raise FileNotFoundError(f"Migration input is missing: {relative.as_posix()}")
    if path.is_symlink():
        raise RuntimeError(f"Migration inputs may not be symlinks: {relative.as_posix()}")
    if kind == "file":
        if not path.is_file():
            raise RuntimeError(f"Expected migration file: {relative.as_posix()}")
        return [path]
    if kind != "tree" or not path.is_dir():
        raise RuntimeError(f"Expected migration tree: {relative.as_posix()}")
    descendants = sorted(path.rglob("*"), key=lambda value: value.as_posix())
    links = [value for value in descendants if value.is_symlink()]
    if links:
        relative_link = links[0].relative_to(source_root).as_posix()
        raise RuntimeError(f"Migration trees may not contain symlinks: {relative_link}")
    return [value for value in descendants if value.is_file()]


def build_inventory(
    *,
    source_root: Path,
    scope_path: Path,
    source_repository: str,
    source_revision: str,
    source_state: str,
) -> dict:
    source_root = source_root.resolve()
    scope_path = scope_path.resolve()
    scope = json.loads(scope_path.read_text(encoding="utf-8"))
    if scope.get("schema") != SCOPE_SCHEMA:
        raise RuntimeError(f"Unsupported migration scope schema: {scope.get('schema')}")
    includes = scope.get("includes")
    if not isinstance(includes, list) or not includes:
        raise RuntimeError("Migration scope must contain at least one include")

    records = []
    observed: dict[str, str] = {}
    for item in includes:
        role = str(item.get("role") or "").strip()
        if not role:
            raise RuntimeError("Every migration include requires a role")
        for path in files_for_include(source_root, item):
            relative = path.relative_to(source_root).as_posix()
            if relative in observed:
                raise RuntimeError(
                    f"Migration path is included twice: {relative} "
                    f"({observed[relative]} and {role})"
                )
            observed[relative] = role
            records.append({
                "path": relative,
                "role": role,
                "byte_size": path.stat().st_size,
                "sha256": sha256_file(path),
            })
    records.sort(key=lambda item: item["path"])

    counts: dict[str, int] = defaultdict(int)
    sizes: dict[str, int] = defaultdict(int)
    for record in records:
        counts[record["role"]] += 1
        sizes[record["role"]] += int(record["byte_size"])
    by_role = {
        role: {"file_count": counts[role], "byte_size": sizes[role]}
        for role in sorted(counts)
    }
    return {
        "schema": INVENTORY_SCHEMA,
        "source_repository": source_repository,
        "source_revision": source_revision,
        "source_worktree_state": source_state,
        "scope_sha256": sha256_file(scope_path),
        "inventory_sha256": canonical_sha256(records),
        "summary": {
            "file_count": len(records),
            "byte_size": sum(int(record["byte_size"]) for record in records),
            "by_role": by_role,
        },
        "files": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--scope", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source-repository", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument(
        "--source-state", choices=("clean", "dirty"), required=True
    )
    args = parser.parse_args()
    inventory = build_inventory(
        source_root=args.source_root,
        scope_path=args.scope,
        source_repository=args.source_repository,
        source_revision=args.source_revision,
        source_state=args.source_state,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(inventory["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

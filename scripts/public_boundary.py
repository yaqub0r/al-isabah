#!/usr/bin/env python3
"""Shared fail-closed public-boundary checks with value-safe diagnostics."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable


SAFE_URLS = {
    "https://creativecommons.org/licenses/by-nc-sa/4.0/",
    "https://github.com/yaqub0r/al-isabah",
    "https://github.com/yaqub0r/al-isabah/issues/35",
    "https://github.com/yaqub0r/al-isabah/issues/53",
    "https://github.com/yaqub0r/al-isabah/issues/70",
}
PROHIBITED_KEY_FRAGMENTS = {
    "blindtranslation",
    "independentcritique",
    "witnessresolution",
    "model",
    "reasoning",
    "prompt",
    "response",
    "rawfinding",
    "reconstructive",
    "repairoperation",
    "credential",
    "token",
    "secret",
    "password",
    "privatepath",
    "internalpath",
    "sourcepath",
    "schemapath",
    "objectkey",
    "storagelocation",
    "apiurl",
    "endpoint",
    "linestart",
    "lineend",
    "sourcecoordinate",
}
PROHIBITED_MARKERS = (
    "sabiqah",
    "firstlight",
    "elixir",
    "usul.ai",
    "lastpass",
    "cloudflarestorage.com",
    "aws_access_key_id",
    "aws_secret_access_key",
    "/api/",
    "content/translation-proposals/",
    "issue-0026.packet.json",
    "issue-0026.review.md",
)
WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:[\\/]")
UNC_PATH = re.compile(r"^(?:\\\\|//)[^/\\]+[/\\]")
RELATIVE_PATH = re.compile(r"^(?:\.\.?[/\\])")
POSIX_ABSOLUTE = re.compile(r"^/(?!/)")
TOKEN_SHAPES = (
    re.compile(r"\bgh[oprsu]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\b(?:sk|pk)_(?:live|test)_[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~-]{16,}\b", re.IGNORECASE),
)
INTERNAL_ARTIFACT = re.compile(
    r"(?:^|[/\\])issue-[0-9]{4}\.(?:packet\.json|review\.md)$",
    re.IGNORECASE,
)


def canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_text_bytes(path: Path) -> bytes:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return text.encode("utf-8")


def sha256_text_file(path: Path) -> str:
    return sha256_bytes(canonical_text_bytes(path))


def value_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalized_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", key.casefold())


def safe_error(path: str, category: str, value: str | None = None) -> str:
    suffix = f" sha256={value_hash(value)}" if value is not None else ""
    return f"{path}: category={category}{suffix}"


def boundary_errors(value: Any, path: str = "$") -> list[str]:
    """Reject prohibited structures and values without returning rejected values."""
    errors: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            normalized = normalized_key(str(key))
            if any(fragment in normalized for fragment in PROHIBITED_KEY_FRAGMENTS):
                errors.append(safe_error(child_path, "prohibited-field"))
            errors.extend(boundary_errors(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            errors.extend(boundary_errors(child, f"{path}[{index}]"))
    elif isinstance(value, str):
        folded = value.casefold()
        if any(marker in folded for marker in PROHIBITED_MARKERS):
            errors.append(safe_error(path, "internal-marker", value))
        if INTERNAL_ARTIFACT.search(value):
            errors.append(safe_error(path, "internal-marker", value))
        if WINDOWS_ABSOLUTE.match(value) or UNC_PATH.match(value) or POSIX_ABSOLUTE.match(value):
            errors.append(safe_error(path, "absolute-path", value))
        elif RELATIVE_PATH.match(value) or "\\" in value:
            errors.append(safe_error(path, "relative-or-internal-path", value))
        if re.match(r"^https?://", value, re.IGNORECASE) and value not in SAFE_URLS:
            errors.append(safe_error(path, "non-allowlisted-uri", value))
        if any(pattern.search(value) for pattern in TOKEN_SHAPES):
            errors.append(safe_error(path, "token-shaped-secret", value))
    return errors


def exact_keys(value: Any, allowed: Iterable[str], path: str) -> list[str]:
    if not isinstance(value, dict):
        return [safe_error(path, "expected-object")]
    allowed_set = set(allowed)
    errors: list[str] = []
    for key in sorted(set(value) - allowed_set):
        errors.append(safe_error(f"{path}.{key}", "unknown-field"))
    for key in sorted(allowed_set - set(value)):
        errors.append(safe_error(f"{path}.{key}", "missing-field"))
    return errors


def summarize(errors: list[str]) -> str:
    """Return category counts and a digest only; never rejected values."""
    categories: dict[str, int] = {}
    for error in errors:
        match = re.search(r"category=([a-z-]+)", error)
        category = match.group(1) if match else "validation"
        categories[category] = categories.get(category, 0) + 1
    digest = sha256_bytes("\n".join(sorted(errors)).encode("utf-8"))
    counts = ", ".join(f"{key}={categories[key]}" for key in sorted(categories))
    return f"public-boundary errors: {counts}; diagnostics-sha256={digest}"

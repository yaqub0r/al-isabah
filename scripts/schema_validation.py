"""Dependency-free JSON-Schema subset shared by repository validators."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any
from urllib.parse import urlparse


def validate_schema_instance(
    value: Any,
    schema: dict[str, Any],
    root_schema: dict[str, Any] | None = None,
    path: str = "$",
) -> list[str]:
    """Validate the JSON-Schema subset used by the translation packet.

    The workflow intentionally has no third-party runtime dependency. Keeping
    this small validator beside the declared schema prevents the CLI from
    accepting additional properties or shapes that its own schema rejects.
    """
    root = root_schema or schema
    if "$ref" in schema:
        reference = schema["$ref"]
        if not isinstance(reference, str) or not reference.startswith("#/"):
            return [f"{path}: unsupported schema reference {reference!r}"]
        target: Any = root
        for token in reference[2:].split("/"):
            target = target[token.replace("~1", "/").replace("~0", "~")]
        return validate_schema_instance(value, target, root, path)

    if "anyOf" in schema:
        alternatives = [
            validate_schema_instance(value, branch, root, path)
            for branch in schema["anyOf"]
        ]
        if not any(not errors for errors in alternatives):
            return [f"{path}: value does not match any allowed schema"]

    errors: list[str] = []
    expected_type = schema.get("type")
    if expected_type:
        expected_types = (
            expected_type if isinstance(expected_type, list) else [expected_type]
        )
        matches = any(
            (
                kind == "object"
                and isinstance(value, dict)
                or kind == "array"
                and isinstance(value, list)
                or kind == "string"
                and isinstance(value, str)
                or kind == "integer"
                and isinstance(value, int)
                and not isinstance(value, bool)
                or kind == "number"
                and isinstance(value, (int, float))
                and not isinstance(value, bool)
                or kind == "boolean"
                and isinstance(value, bool)
                or kind == "null"
                and value is None
            )
            for kind in expected_types
        )
        if not matches:
            return [f"{path}: expected schema type {expected_type!r}"]

    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: value must equal {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: value is outside the declared enum")

    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            errors.append(f"{path}: string is shorter than minLength")
        pattern = schema.get("pattern")
        if pattern and re.search(pattern, value) is None:
            errors.append(f"{path}: string does not match the declared pattern")
        format_name = schema.get("format")
        if format_name == "date-time":
            if not re.fullmatch(
                r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})",
                value,
            ):
                errors.append(f"{path}: value is not an ISO date-time")
            else:
                try:
                    datetime.fromisoformat(value.replace("Z", "+00:00"))
                except ValueError:
                    errors.append(f"{path}: value is not an ISO date-time")
        elif format_name == "uri":
            parsed = urlparse(value)
            if not parsed.scheme or not (
                parsed.netloc or parsed.scheme.lower() in {"mailto", "urn"}
            ):
                errors.append(f"{path}: value is not an absolute URI")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: number is below the declared minimum")

    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errors.append(f"{path}: array is shorter than minItems")
        if schema.get("uniqueItems"):
            encoded = [
                json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                for item in value
            ]
            if len(encoded) != len(set(encoded)):
                errors.append(f"{path}: array items must be unique")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                errors.extend(
                    validate_schema_instance(item, item_schema, root, f"{path}[{index}]")
                )

    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for required in schema.get("required", []):
            if required not in value:
                errors.append(f"{path}: missing required property {required!r}")
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in properties:
                    errors.append(f"{path}: unexpected property {key!r}")
        for key, child_schema in properties.items():
            if key in value:
                errors.extend(
                    validate_schema_instance(
                        value[key], child_schema, root, f"{path}.{key}"
                    )
                )
    return errors

#!/usr/bin/env python3
"""Proposed synthetic-only, closed knowledge export. No source text extraction."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from pathlib import Path

from public_boundary import boundary_errors

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas/al-isabah-knowledge-export.v1.schema.json"
SCHEMA_ID = "al-isabah.knowledge-export.v1"
COLLECTIONS = ("sourceRecords", "entities", "claims", "ambiguityGroups", "lifecycleEvents")


class Rejection(ValueError):
    """Only fixed codes may leave the validation boundary."""


def reject(code):
    raise Rejection(code)


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def read(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                reject("duplicate-key")
            result[key] = value
        return result
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=pairs,
                          parse_constant=lambda _: reject("invalid-json"))
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError):
        reject("invalid-json")


def schema_vocabulary(schema):
    """Reject schema constraints this dependency-free validator cannot execute."""
    supported = {"$schema", "$id", "$defs", "$ref", "type", "const", "enum",
                 "properties", "additionalProperties", "required", "items",
                 "uniqueItems", "minItems", "maxItems", "pattern", "maxLength",
                 "minimum", "maximum"}
    if not isinstance(schema, dict) or set(schema) - supported:
        reject("unsupported-schema")
    kind = schema.get("type")
    if kind not in {None, "object", "array", "string", "integer", "boolean"}:
        reject("unsupported-schema")
    common = {"$schema", "$id", "$defs", "$ref", "type", "const", "enum"}
    by_type = {"object": {"properties", "additionalProperties", "required"},
               "array": {"items", "uniqueItems", "minItems", "maxItems"},
               "string": {"pattern", "maxLength"},
               "integer": {"minimum", "maximum"}, "boolean": set(), None: set()}
    if set(schema) - common - by_type[kind]:
        reject("unsupported-schema")
    if "$ref" in schema and (set(schema) != {"$ref"} or not schema["$ref"].startswith("#/$defs/")):
        reject("unsupported-schema")
    if kind == "object" and (schema.get("additionalProperties") is not False
                             or set(schema.get("required", [])) != set(schema.get("properties", {}))):
        reject("unsupported-schema")
    if kind == "array" and "items" not in schema:
        reject("unsupported-schema")
    for key in ("$defs", "properties"):
        for child in schema.get(key, {}).values():
            schema_vocabulary(child)
    if "items" in schema:
        schema_vocabulary(schema["items"])


def shape(value, schema, root=None):
    """Validate the deliberately small JSON Schema vocabulary used here."""
    if root is None:
        schema_vocabulary(schema)
    root = root or schema
    if "$ref" in schema:
        name = schema["$ref"].split("/")[-1]
        if name not in root.get("$defs", {}):
            reject("unsupported-schema")
        return shape(value, root["$defs"][name], root)
    if "const" in schema and (type(value) is not type(schema["const"]) or value != schema["const"]):
        reject("schema-mismatch")
    if "enum" in schema and value not in schema["enum"]:
        reject("schema-mismatch")
    kind = schema.get("type")
    if kind == "object":
        if not isinstance(value, dict):
            reject("schema-mismatch")
        if set(value) - set(schema["properties"]):
            reject("prohibited-payload")
        if set(schema["required"]) - set(value):
            reject("schema-mismatch")
        for key, child in value.items():
            shape(child, schema["properties"][key], root)
    elif kind == "array":
        if not isinstance(value, list):
            reject("schema-mismatch")
        if not schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", 100000):
            reject("schema-mismatch")
        if schema.get("uniqueItems") and len({canonical(x) for x in value}) != len(value):
            reject("duplicate-item")
        for child in value:
            shape(child, schema["items"], root)
    elif kind == "string":
        if not isinstance(value, str) or len(value) > schema.get("maxLength", 256):
            reject("schema-mismatch")
        if "pattern" in schema and not re.fullmatch(schema["pattern"], value, flags=re.ASCII):
            reject("prohibited-payload")
    elif kind == "integer":
        if type(value) is not int or not schema.get("minimum", 0) <= value <= schema.get("maximum", 2147483647):
            reject("schema-mismatch")
    elif kind == "boolean" and type(value) is not bool:
        reject("schema-mismatch")


def index(items):
    result = {item["id"]: item for item in items}
    if len(result) != len(items):
        reject("immutable-id-conflict")
    return result


def pins(snapshot, schema):
    return {"schemaSha256": digest(schema), "policySha256": digest(snapshot["policy"]),
            "admissionSha256": digest(snapshot["admission"]),
            "rightsSha256": digest(snapshot["rights"]),
            "sourceReleaseSha256": digest(snapshot["sourceRelease"])}


def validate_snapshot(snapshot, expected_snapshot_sha256, expected_pins):
    schema = read(SCHEMA_PATH)
    schema_vocabulary(schema)
    shape(snapshot, schema["$defs"]["snapshot"], schema)
    if boundary_errors(snapshot):
        reject("prohibited-payload")
    if digest(snapshot) != expected_snapshot_sha256:
        reject("snapshot-digest-mismatch")
    if pins(snapshot, schema) != expected_pins:
        reject("policy-digest-mismatch")
    if snapshot["admission"]["approvedCollectionsSha256"] != digest({key: snapshot[key] for key in COLLECTIONS}):
        reject("admission-digest-mismatch")
    maps = {key: index(snapshot[key]) for key in COLLECTIONS}
    records, entities, claims, groups, events = (maps[key] for key in COLLECTIONS)
    all_ids = [item["id"] for key in COLLECTIONS for item in snapshot[key]]
    if len(all_ids) != len(set(all_ids)):
        reject("immutable-id-conflict")
    scope = {item["volume"]: item["recordCount"] for item in snapshot["sourceScope"]}
    if len(scope) != len(snapshot["sourceScope"]):
        reject("coverage-mismatch")
    for volume, count in scope.items():
        if sum(r["volume"] == volume for r in records.values()) > count:
            reject("coverage-mismatch")
    for record in records.values():
        if record["volume"] not in scope or record["sourceReleaseId"] != snapshot["sourceRelease"]["id"]:
            reject("source-identity-mismatch")
    if snapshot["sourceRelease"]["releaseTag"] != "synthetic-" + snapshot["sourceRelease"]["repositoryCommit"]:
        reject("source-identity-mismatch")
    for entity in entities.values():
        if not set(entity["sourceRecordIds"]) <= records.keys():
            reject("missing-reference")
    for claim in claims.values():
        if not set(claim["sourceRecordIds"]) <= records.keys() or not set(claim["ambiguityGroupIds"]) <= groups.keys():
            reject("missing-reference")
        if claim["subjectId"] not in entities or claim["objectId"] not in entities:
            reject("missing-reference")
        if claim["predicateId"] not in snapshot["policy"]["predicateIds"]:
            reject("unapproved-predicate")
        if any(records[r]["extractionStatus"] == "not_started" for r in claim["sourceRecordIds"]):
            reject("coverage-mismatch")
        if claim["storyUseTier"] == "factual_spine" and (
            claim["sourceCriticalStatus"] != "unqualified" or claim["ambiguityGroupIds"]
            or claim["assertionClass"] != "source_attested"
            or claim["evidentiaryStrength"] != "source_supported"
        ):
            reject("qualification-loss")
        if (claim["ambiguityGroupIds"] or claim["sourceCriticalStatus"] != "unqualified") and not claim["attributionRequired"]:
            reject("qualification-loss")
    for group in groups.values():
        members = set(group["memberClaimIds"])
        if not members <= claims.keys():
            reject("missing-reference")
        if members != {c["id"] for c in claims.values() if group["id"] in c["ambiguityGroupIds"]}:
            reject("ambiguity-incomplete")
    targets = set()
    edges = {}
    for event in events.values():
        target = event["targetClaimId"]
        replacements = event["replacementClaimIds"]
        if target not in claims or not set(replacements) <= claims.keys():
            reject("missing-reference")
        if target in targets or target in replacements:
            reject("lifecycle-conflict")
        targets.add(target)
        if (event["kind"] == "withdraws") != (len(replacements) == 0):
            reject("lifecycle-conflict")
        edges[target] = replacements
    def visit(node, ancestors):
        if node in ancestors:
            reject("lifecycle-conflict")
        for child in edges.get(node, []):
            visit(child, ancestors | {node})
    for target in edges:
        visit(target, set())
    batches = index(snapshot["batches"])
    for batch in batches.values():
        if not set(batch["recordIds"]) <= records.keys():
            reject("missing-reference")
        if set(batch["volumes"]) != {records[r]["volume"] for r in batch["recordIds"]}:
            reject("coverage-mismatch")
    return schema, maps, batches


def build(snapshot, batch_id, expected_snapshot_sha256, expected_pins):
    schema, maps, batches = validate_snapshot(snapshot, expected_snapshot_sha256, expected_pins)
    if batch_id not in batches:
        reject("undeclared-batch")
    records, entities, claims, groups, events = (maps[key] for key in COLLECTIONS)
    requested_records = set(batches[batch_id]["recordIds"])
    requested_claims = {c["id"] for c in claims.values() if requested_records & set(c["sourceRecordIds"])}
    selected = {key: set() for key in COLLECTIONS}
    selected["sourceRecords"] = requested_records.copy()
    selected["claims"] = requested_claims.copy()
    while True:
        before = copy.deepcopy(selected)
        for cid in list(selected["claims"]):
            claim = claims[cid]
            selected["sourceRecords"].update(claim["sourceRecordIds"])
            selected["entities"].update((claim["subjectId"], claim["objectId"]))
            selected["ambiguityGroups"].update(claim["ambiguityGroupIds"])
        for gid in list(selected["ambiguityGroups"]):
            selected["claims"].update(groups[gid]["memberClaimIds"])
        for eid in list(selected["entities"]):
            selected["sourceRecords"].update(entities[eid]["sourceRecordIds"])
        for event in events.values():
            involved = {event["targetClaimId"], *event["replacementClaimIds"]}
            if involved & selected["claims"]:
                selected["lifecycleEvents"].add(event["id"])
                selected["claims"].update(involved)
        if selected == before:
            break
    selection = {"requestedRecordIds": sorted(requested_records),
                 "dependencyRecordIds": sorted(selected["sourceRecords"] - requested_records),
                 "requestedClaimIds": sorted(requested_claims),
                 "dependencyClaimIds": sorted(selected["claims"] - requested_claims),
                 "volumes": sorted(batches[batch_id]["volumes"])}
    coverage = {"sourceScopeRecordCount": sum(s["recordCount"] for s in snapshot["sourceScope"]),
                "approvedSourceRecordCount": len(records),
                "semanticExtractedRecordCount": sum(r["extractionStatus"] != "not_started" for r in records.values()),
                "semanticCompleteRecordCount": sum(r["extractionStatus"] == "complete" for r in records.values()),
                "approvedClaimCount": len(claims),
                "requestedRecordCount": len(requested_records),
                "dependencyRecordCount": len(selection["dependencyRecordIds"]),
                "totalRecordCount": len(selected["sourceRecords"]),
                "requestedClaimCount": len(requested_claims),
                "dependencyClaimCount": len(selection["dependencyClaimIds"]),
                "totalClaimCount": len(selected["claims"])}
    output = {"schemaId": SCHEMA_ID, "schemaVersion": "1.0.0", "mode": "synthetic",
              "batchId": batch_id, "snapshotSha256": expected_snapshot_sha256,
              "pins": copy.deepcopy(expected_pins), "selection": selection, "coverage": coverage}
    for key in ("authority", "sourceRelease", "rights", "sourceScope"):
        output[key] = copy.deepcopy(snapshot[key])
    for key in COLLECTIONS:
        output[key] = [copy.deepcopy(maps[key][identifier]) for identifier in sorted(selected[key])]
    output["payloadSha256"] = digest(output)
    shape(output, schema)
    return output


def validate_batch(batch, snapshot, expected_snapshot_sha256, expected_pins):
    schema = read(SCHEMA_PATH)
    shape(batch, schema)
    if batch["pins"] != expected_pins:
        reject("policy-digest-mismatch")
    payload = {k: v for k, v in batch.items() if k != "payloadSha256"}
    if digest(payload) != batch["payloadSha256"]:
        reject("payload-digest-mismatch")
    expected = build(snapshot, batch["batchId"], expected_snapshot_sha256, expected_pins)
    if batch != expected:
        reject("batch-content-mismatch")


def replay(admissions):
    """Revalidate the entire trusted history atomically; return a derived ledger.

    Each tuple is (batch, snapshot, independently trusted snapshot digest, pins).
    Different approved snapshots may extend history, never mutate old IDs.
    """
    ledger = {key: {} for key in COLLECTIONS}
    batch_ids = {}
    releases = {}
    approvals = {}
    authority = None
    for batch, snapshot, expected_sha, expected_pins in admissions:
        validate_batch(batch, snapshot, expected_sha, expected_pins)
        if authority is not None and authority != batch["authority"]:
            reject("source-identity-mismatch")
        authority = batch["authority"]
        for key in ("policy", "admission"):
            identifier = (key, snapshot[key]["id"])
            binding = digest(snapshot[key])
            if identifier in approvals and approvals[identifier] != binding:
                reject("immutable-id-conflict")
            approvals[identifier] = binding
        release = batch["sourceRelease"]
        release_binding = {"release": release, "policySha256": batch["pins"]["policySha256"],
                           "rightsSha256": batch["pins"]["rightsSha256"]}
        for alias in (("id", release["id"]),
                      ("commit", release["repository"], release["repositoryCommit"]),
                      ("tag", release["repository"], release["releaseTag"])):
            if alias in releases and releases[alias] != release_binding:
                reject("immutable-id-conflict")
            releases[alias] = release_binding
        retired_before = {e["targetClaimId"] for e in ledger["lifecycleEvents"].values()}
        for event in batch["lifecycleEvents"]:
            if event["id"] not in ledger["lifecycleEvents"]:
                if event["targetClaimId"] in retired_before or set(event["replacementClaimIds"]) & ledger["claims"].keys():
                    reject("lifecycle-conflict")
        bid = batch["batchId"]
        if bid in batch_ids and batch_ids[bid] != digest(batch):
            reject("immutable-id-conflict")
        batch_ids[bid] = digest(batch)
        for key in COLLECTIONS:
            for item in batch[key]:
                old = ledger[key].get(item["id"])
                if old is not None and old != item:
                    reject("immutable-id-conflict")
                ledger[key][item["id"]] = copy.deepcopy(item)
    retired = {}
    for event in ledger["lifecycleEvents"].values():
        target = event["targetClaimId"]
        if target in retired and retired[target] != event:
            reject("lifecycle-conflict")
        retired[target] = event
    edges = {target: e["replacementClaimIds"] for target, e in retired.items()}
    def visit(node, ancestors):
        if node in ancestors:
            reject("lifecycle-conflict")
        for child in edges.get(node, []):
            visit(child, ancestors | {node})
    for target in edges:
        visit(target, set())
    return {"batchCount": len(batch_ids),
            "uniqueRecordCount": len(ledger["sourceRecords"]),
            "uniqueClaimCount": len(ledger["claims"]),
            "activeClaimIds": sorted(set(ledger["claims"]) - retired.keys()),
            "retiredClaimIds": sorted(retired),
            "ledger": {key: [values[k] for k in sorted(values)] for key, values in ledger.items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--trust", type=Path, required=True)
    parser.add_argument("--batch", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        trust = read(args.trust)
        schema = read(SCHEMA_PATH)
        shape(trust, schema["$defs"]["trust"], schema)
        output = canonical(build(read(args.snapshot), args.batch, trust["snapshotSha256"], trust["pins"]))
        if args.check:
            if args.output.read_bytes() != output:
                reject("noncanonical-output")
        else:
            args.output.write_bytes(output)
    except Rejection as error:
        print(str(error))
        return 1
    except (OSError, RecursionError):
        print("input-output-error")
        return 1
    print("synthetic-export-verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

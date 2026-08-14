"""Deterministically integrate audited issue #26 runtime repair artifacts.

Dry-run is the default. This script never changes source fields and verifies the
base packet hash plus every hash-addressed textual/name input before mutation.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import translation_workflow as workflow


PACKET = ROOT / ".runtime/translation/packets/issue-0026.json"
TEXTUAL = ROOT / ".runtime/translation/repairs/issue-0026-textual.json"
NAMES = ROOT / ".runtime/translation/repairs/issue-0026-names.json"
PROVENANCE_RANGES = (
    ROOT
    / ".runtime/translation/repairs/issue-0026-provenance-range-0001-0512-plus-structural.json",
    ROOT
    / ".runtime/translation/repairs/issue-0026-provenance-range-0513-1024.json",
    ROOT
    / ".runtime/translation/repairs/issue-0026-provenance-range-1025-1537.json",
)
PATH_TOKEN = re.compile(r"([A-Za-z][A-Za-z0-9_]*)|\[(\d+)\]")


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"{path}: top level must be an object")
    return value


def js_object_sha256(value: object) -> str:
    """Match SHA-256(JSON.stringify(value) UTF-8), preserving key order."""
    encoded = json.dumps(
        value, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def path_tokens(value: str) -> list[str | int]:
    if not value.startswith("$."):
        raise RuntimeError(f"unsupported field path: {value}")
    tokens: list[str | int] = []
    for name, index in PATH_TOKEN.findall(value[2:]):
        tokens.append(name if name else int(index))
    if not tokens:
        raise RuntimeError(f"empty field path: {value}")
    return tokens


def get_path(root: object, tokens: list[str | int]) -> object:
    current = root
    for token in tokens:
        current = current[token]  # type: ignore[index]
    return current


def set_path(root: object, tokens: list[str | int], value: object) -> None:
    parent = get_path(root, tokens[:-1])
    parent[tokens[-1]] = value  # type: ignore[index]


def normalize_names(names: dict, record_id: str) -> dict:
    normalized = copy.deepcopy(names)
    for mention in normalized.get("mentions", []):
        mention.pop("sourceUnitId", None)
        mention.pop("sourceSegmentId", None)
        mention["recordId"] = record_id
        for span in mention.get("sourceSpans", []):
            span["sourceField"] = str(span["sourceField"]).removeprefix("source.")
    return normalized


def protected_fingerprint(packet: dict) -> str:
    protected = {
        "assignment": packet["assignment"],
        "authority": packet["authority"],
        "policy": packet["policy"],
        "scope": packet["scope"],
        "sources": [entry["source"] for entry in packet["entries"]],
    }
    return workflow.bytes_sha256(workflow.json_bytes(protected))


def verify_source_hashes(record: dict, source: dict) -> None:
    for field, expected in record.get("sourceFieldSha256", {}).items():
        local_field = str(field).removeprefix("source.")
        actual = workflow.text_sha256(str(source.get(local_field) or ""))
        if actual != expected:
            raise RuntimeError(f"{record['recordId']}: stale {field} source hash")


def apply_textual(packet: dict, artifact: dict) -> int:
    if artifact.get("packetSha256") != file_sha256(PACKET):
        raise RuntimeError("textual artifact targets a different packet hash")
    if artifact.get("unresolvedCases"):
        raise RuntimeError("textual artifact still contains unresolved cases")
    seen: set[str] = set()
    for repair in artifact.get("repairs", []):
        repair_id = repair["repairId"]
        if repair_id in seen:
            raise RuntimeError(f"duplicate textual repair ID: {repair_id}")
        seen.add(repair_id)
        tokens = path_tokens(repair["fieldPath"])
        current = get_path(packet, tokens)
        if not isinstance(current, str):
            raise RuntimeError(f"{repair_id}: target is not text")
        if workflow.text_sha256(current) != repair["oldTextSha256"]:
            raise RuntimeError(f"{repair_id}: old text hash mismatch")
        set_path(packet, tokens, repair["replacementText"])
    for repair in artifact.get("phraseRepairs", []):
        repair_id = repair["repairId"]
        if repair_id in seen:
            raise RuntimeError(f"duplicate textual repair ID: {repair_id}")
        seen.add(repair_id)
        tokens = path_tokens(repair["fieldPath"])
        current = get_path(packet, tokens)
        if not isinstance(current, str):
            raise RuntimeError(f"{repair_id}: target is not text")
        if workflow.text_sha256(current) != repair["oldTextSha256"]:
            raise RuntimeError(f"{repair_id}: old text hash mismatch")
        if current.count(repair["oldPhrase"]) != 1:
            raise RuntimeError(f"{repair_id}: old phrase is not unique in target")
        replacement = current.replace(repair["oldPhrase"], repair["newPhrase"])
        if workflow.text_sha256(replacement) != repair["newTextSha256"]:
            raise RuntimeError(f"{repair_id}: new text hash mismatch")
        set_path(packet, tokens, replacement)
    return len(seen)


def textual_repair_audit(artifact: dict) -> dict:
    operations = []
    for repair in artifact.get("repairs", []):
        path = repair["fieldPath"]
        if ".blindTranslation." in path:
            target_stage = "blind_translation"
        elif ".adjudication." in path:
            target_stage = "adjudication"
        else:
            raise RuntimeError(f"unsupported textual repair stage: {path}")
        operations.append(
            {
                "repairId": repair["repairId"],
                "sourceUnitId": repair["sourceUnitId"],
                "segmentId": repair.get("segmentId"),
                "recordKind": workflow.normalized_repair_record_kind(
                    repair["recordKind"]
                ),
                "targetStage": target_stage,
                "fieldPath": path,
                "oldTextSha256": repair["oldTextSha256"],
                "newTextSha256": workflow.text_sha256(repair["replacementText"]),
                "reasons": copy.deepcopy(repair["reasons"]),
            }
        )
    for repair in artifact.get("phraseRepairs", []):
        path = repair["fieldPath"]
        if ".blindTranslation." in path:
            target_stage = "blind_translation"
        elif ".adjudication." in path:
            target_stage = "adjudication"
        else:
            raise RuntimeError(f"unsupported textual repair stage: {path}")
        operations.append(
            {
                "repairId": repair["repairId"],
                "sourceUnitId": repair["sourceUnitId"],
                "segmentId": repair.get("segmentId"),
                "recordKind": workflow.normalized_repair_record_kind(
                    repair["recordKind"]
                ),
                "targetStage": target_stage,
                "fieldPath": path,
                "oldTextSha256": repair["oldTextSha256"],
                "newTextSha256": repair["newTextSha256"],
                "reasons": copy.deepcopy(repair["reasons"]),
            }
        )
    artifact_sha = file_sha256(TEXTUAL)
    return {
        "status": "complete",
        "basePacketSha256": file_sha256(PACKET),
        "artifactSha256": artifact_sha,
        "runId": f"translation-repair-run-{artifact_sha[:16]}",
        "operations": operations,
    }


def apply_names(packet: dict, artifact: dict) -> tuple[int, int]:
    if artifact.get("sourcePacket", {}).get("sha256") != file_sha256(PACKET):
        raise RuntimeError("names artifact targets a different packet hash")
    entries = {entry["sourceUnitId"]: entry for entry in packet["entries"]}
    segments: dict[str, tuple[dict, dict]] = {}
    for entry in packet["entries"]:
        for source, translation in zip(
            entry["source"].get("precedingSegments", []),
            entry.get("precedingTranslations", []),
        ):
            segments[source["segmentId"]] = (source, translation)
    seen: set[str] = set()
    candidates = 0
    for record in artifact.get("records", []):
        record_id = record["recordId"]
        if record_id in seen:
            raise RuntimeError(f"duplicate name record: {record_id}")
        seen.add(record_id)
        if record["recordType"] == "entry":
            target = entries[record_id]
            source = target["source"]
        elif record["recordType"] == "structural_segment":
            source, target = segments[record_id]
        else:
            raise RuntimeError(f"{record_id}: unknown name record type")
        verify_source_hashes(record, source)
        target["names"] = normalize_names(record["names"], record_id)
        candidates += len(target["names"]["candidates"])
    expected = len(packet["entries"]) + len(segments)
    if len(seen) != expected:
        raise RuntimeError(f"name artifact covers {len(seen)} of {expected} records")
    return len(seen), candidates


def owner_indexes(packet: dict) -> tuple[dict[int, dict], dict[str, dict]]:
    entries: dict[int, dict] = {}
    segments: dict[str, dict] = {}
    for entry in packet["entries"]:
        ordinal = entry["sourceOrdinal"]
        if ordinal in entries:
            raise RuntimeError(f"duplicate source ordinal in packet: {ordinal}")
        entries[ordinal] = entry
        for translation in entry.get("precedingTranslations", []):
            segment_id = translation["segmentId"]
            if segment_id in segments:
                raise RuntimeError(f"duplicate structural segment in packet: {segment_id}")
            segments[segment_id] = translation
    return entries, segments


def owner_for_target(
    target: dict, entries: dict[int, dict], segments: dict[str, dict]
) -> dict:
    owner_type = target.get("ownerType")
    if owner_type == "entry":
        ordinal = target.get("sourceOrdinal")
        owner = entries.get(ordinal)
        if owner is None:
            raise RuntimeError(f"provenance target has unknown entry ordinal: {ordinal}")
        if owner.get("sourceUnitId") != target.get("sourceUnitId"):
            raise RuntimeError(f"provenance entry target ID mismatch at ordinal {ordinal}")
        return owner
    if owner_type == "preceding_segment":
        segment_id = target.get("segmentId")
        owner = segments.get(segment_id)
        if owner is None:
            raise RuntimeError(f"provenance target has unknown segment: {segment_id}")
        return owner
    raise RuntimeError(f"unsupported provenance owner type: {owner_type}")


def target_key(kind: str, target: dict) -> tuple[object, ...]:
    index_name = "resultIndex" if kind == "witness" else "unresolvedIndex"
    return (
        kind,
        target.get("ownerType"),
        target.get("sourceOrdinal"),
        target.get("sourceUnitId"),
        target.get("segmentId"),
        target.get(index_name),
    )


def verify_old_object(operation: dict, current: object, label: str) -> None:
    snapshot = operation.get("oldObjectSnapshot")
    expected_hash = operation.get("oldObjectSha256")
    if snapshot != current:
        raise RuntimeError(f"{label}: old object snapshot does not match packet")
    if js_object_sha256(snapshot) != expected_hash:
        raise RuntimeError(f"{label}: old object hash is invalid")


def blocker_count(artifact: dict) -> int:
    def visit(value: object, key_name: str = "") -> int:
        if isinstance(value, dict):
            return sum(visit(child, str(key)) for key, child in value.items())
        if isinstance(value, list):
            if key_name.lower() == "blockers":
                return len(value)
            return sum(visit(child) for child in value)
        lowered = key_name.lower()
        if (
            "blocker" in lowered
            and ("after" in lowered or "remaining" in lowered or lowered == "blockers")
            and isinstance(value, int)
        ):
            return value
        return 0

    return visit(artifact)


def apply_structural_mutation(
    mutation: dict, entries: dict[int, dict], segments: dict[str, dict]
) -> None:
    if not mutation:
        return
    target = mutation["target"]
    owner = owner_for_target(target, entries, segments)
    label = f"structural mutation {target['segmentId']}"

    old_witness = mutation["oldWitnessResolutionSnapshot"]
    if owner.get("witnessResolution") != old_witness:
        raise RuntimeError(f"{label}: old witness resolution does not match packet")
    if js_object_sha256(old_witness) != mutation["oldWitnessResolutionSha256"]:
        raise RuntimeError(f"{label}: old witness resolution hash is invalid")
    owner["witnessResolution"] = copy.deepcopy(
        mutation["witnessResolutionReplacement"]
    )

    finding_change = mutation["critiqueFindingReplacement"]
    finding_index = finding_change["findingIndex"]
    finding = owner["independentCritique"]["findings"][finding_index]
    verify_old_object(finding_change, finding, f"{label} critique finding")
    owner["independentCritique"]["findings"][finding_index] = copy.deepcopy(
        finding_change["replacement"]
    )

    decision_change = mutation["adjudicationDecisionReplacement"]
    decision_index = decision_change["decisionIndex"]
    decision = owner["adjudication"]["decisions"][decision_index]
    verify_old_object(decision_change, decision, f"{label} adjudication decision")
    owner["adjudication"]["decisions"][decision_index] = copy.deepcopy(
        decision_change["replacement"]
    )

    english_change = mutation["adjudicationEnglishReplacement"]
    current_english = owner["adjudication"]["english"]
    replacement = english_change["replacement"]
    if current_english == english_change["oldValue"]:
        if workflow.text_sha256(current_english) != english_change["oldValueSha256"]:
            raise RuntimeError(f"{label}: old adjudication English hash is invalid")
        owner["adjudication"]["english"] = replacement
    elif current_english != replacement:
        raise RuntimeError(f"{label}: adjudication English is neither old nor repaired")


def apply_provenance(packet: dict, artifacts: list[dict]) -> dict[str, int]:
    entries, segments = owner_indexes(packet)
    base_sha = file_sha256(PACKET)
    seen: set[tuple[object, ...]] = set()
    counts = {"witness": 0, "unresolved": 0, "alignments": 0, "structural": 0}

    for artifact in artifacts:
        if artifact.get("sourcePacket", {}).get("sha256") != base_sha:
            raise RuntimeError("provenance artifact targets a different packet hash")
        if blocker_count(artifact):
            raise RuntimeError(
                f"provenance artifact still reports blockers: {artifact.get('ownedScope')}"
            )

        alignments = [
            *artifact.get("ownerWitnessResolutionAlignments", []),
            *artifact.get("witnessResolutionReplacements", []),
            *artifact.get("witnessResolutionMutations", []),
        ]
        whole_witness_replacements = {
            (
                item["target"].get("ownerType"),
                item["target"].get("sourceOrdinal"),
                item["target"].get("sourceUnitId"),
                item["target"].get("segmentId"),
            ): item
            for item in alignments
        }
        structural_mutation = artifact.get("structuralOwnerMutation")
        if structural_mutation:
            structural_target = structural_mutation["target"]
            structural_key = (
                structural_target.get("ownerType"),
                structural_target.get("sourceOrdinal"),
                structural_target.get("sourceUnitId"),
                structural_target.get("segmentId"),
            )
            if structural_key in whole_witness_replacements:
                raise RuntimeError(
                    f"duplicate whole-owner witness replacement: {structural_key}"
                )
            whole_witness_replacements[structural_key] = {
                "target": structural_target,
                "replacement": structural_mutation["witnessResolutionReplacement"],
            }

        for kind, collection, index_name, field_name in (
            (
                "witness",
                [
                    *artifact.get("witnessNormalizations", []),
                    *artifact.get("witnessResultMutations", []),
                ],
                "resultIndex",
                "witnessResolution",
            ),
            (
                "unresolved",
                [
                    *artifact.get("unresolvedNormalizations", []),
                    *artifact.get("unresolvedItemMutations", []),
                ],
                "unresolvedIndex",
                "unresolved",
            ),
        ):
            for operation in collection:
                target = operation["target"]
                key = target_key(kind, target)
                if key in seen:
                    raise RuntimeError(f"duplicate provenance target: {key}")
                seen.add(key)
                owner = owner_for_target(target, entries, segments)
                index = target[index_name]
                if field_name == "witnessResolution":
                    owner_key = (
                        target.get("ownerType"),
                        target.get("sourceOrdinal"),
                        target.get("sourceUnitId"),
                        target.get("segmentId"),
                    )
                    whole_replacement = whole_witness_replacements.get(owner_key)
                    if operation.get("operation") == "add":
                        current_results = owner[field_name]["results"]
                        replacement_results = whole_replacement["replacement"][
                            "results"
                        ] if whole_replacement else []
                        if (
                            index != len(current_results)
                            or index >= len(replacement_results)
                            or replacement_results[index] != operation["normalized"]
                        ):
                            raise RuntimeError(
                                f"{key}: additive result is not covered by an exact "
                                "whole-owner replacement"
                            )
                        counts[kind] += 1
                        continue
                    current = owner[field_name]["results"][index]
                else:
                    current = owner[field_name][index]
                verify_old_object(operation, current, str(key))
                replacement = copy.deepcopy(operation["normalized"])
                if field_name == "witnessResolution":
                    if whole_replacement:
                        replacement_results = whole_replacement["replacement"][
                            "results"
                        ]
                        if (
                            index >= len(replacement_results)
                            or replacement_results[index] != replacement
                        ):
                            raise RuntimeError(
                                f"{key}: result normalization disagrees with owner replacement"
                            )
                    else:
                        owner[field_name]["results"][index] = replacement
                else:
                    owner[field_name][index] = replacement
                counts[kind] += 1

        for alignment in alignments:
            target = alignment["target"]
            key = (
                "alignment",
                target.get("ownerType"),
                target.get("sourceOrdinal"),
                target.get("sourceUnitId"),
                target.get("segmentId"),
            )
            if key in seen:
                raise RuntimeError(f"duplicate provenance target: {key}")
            seen.add(key)
            owner = owner_for_target(target, entries, segments)
            current = owner["witnessResolution"]
            verify_old_object(alignment, current, str(key))
            replacement = copy.deepcopy(alignment["replacement"])
            expected_replacement_hash = alignment.get("replacementObjectSha256")
            if (
                expected_replacement_hash
                and js_object_sha256(replacement) != expected_replacement_hash
            ):
                raise RuntimeError(f"{key}: replacement object hash is invalid")
            owner["witnessResolution"] = replacement
            counts["alignments"] += 1

        if structural_mutation:
            apply_structural_mutation(structural_mutation, entries, segments)
            counts["structural"] += 1

    return counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    packet = load(PACKET)
    protected_before = protected_fingerprint(packet)
    textual_artifact = load(TEXTUAL)
    textual_count = apply_textual(packet, textual_artifact)
    packet["postRunRepairAudit"] = textual_repair_audit(textual_artifact)
    name_records, candidate_count = apply_names(packet, load(NAMES))
    missing_ranges = [path for path in PROVENANCE_RANGES if not path.is_file()]
    if missing_ranges:
        raise RuntimeError(
            "missing provenance range artifacts: "
            + ", ".join(str(path) for path in missing_ranges)
        )
    provenance_counts = apply_provenance(packet, [load(path) for path in PROVENANCE_RANGES])
    packet["schemaVersion"] = "1.2.0"
    packet["toolVersion"] = workflow.TOOL_VERSION
    packet["formulaInventory"], formula_errors = workflow.formula_inventory(packet)
    packet["reviewPresentation"] = {"status": "pending", "path": None, "sha256": None}
    packet["machineReadiness"] = {
        "status": "pending",
        "validatedAt": None,
        "validatorVersion": workflow.TOOL_VERSION,
    }
    protected_after = protected_fingerprint(packet)
    if protected_after != protected_before:
        raise RuntimeError("protected assignment, source, authority, policy, or scope changed")

    name_errors = []
    for entry in packet["entries"]:
        name_errors.extend(
            workflow.validate_names(
                entry["names"],
                entry["source"],
                entry["sourceUnitId"],
                f"source unit {entry['sourceOrdinal']}",
                require_spans=True,
            )
        )
        for source, translation in zip(
            entry["source"].get("precedingSegments", []),
            entry.get("precedingTranslations", []),
        ):
            name_errors.extend(
                workflow.validate_names(
                    translation["names"],
                    source,
                    source["segmentId"],
                    source["segmentId"],
                    require_spans=True,
                )
            )
    packet_errors = workflow.validate_packet(packet, machine_ready=False)
    readiness_candidate = copy.deepcopy(packet)
    readiness_candidate["reviewPresentation"] = {
        "status": "ready",
        "path": "issue-0026.review.md",
        "sha256": "0" * 64,
    }
    readiness_candidate["machineReadiness"] = {
        "status": "ready",
        "validatedAt": "2026-08-14T00:00:00Z",
        "validatorVersion": workflow.TOOL_VERSION,
    }
    machine_errors = workflow.validate_packet(readiness_candidate, machine_ready=True)
    errors = formula_errors + name_errors + packet_errors + machine_errors
    report = {
        "basePacketSha256": file_sha256(PACKET),
        "protectedFingerprint": protected_after,
        "textualRepairs": textual_count,
        "nameRecords": name_records,
        "nameCandidates": candidate_count,
        "formulaOccurrences": len(packet["formulaInventory"]["occurrences"]),
        "provenance": provenance_counts,
        "serializedBytesIntegrated": len(workflow.json_bytes(packet)),
        "formulaErrors": formula_errors,
        "nameErrors": name_errors,
        "packetErrors": packet_errors,
        "machineReadyErrors": machine_errors,
    }
    print(json.dumps(report, ensure_ascii=True, indent=2))
    if errors:
        return 1
    if args.output:
        workflow.atomic_write(args.output, workflow.json_bytes(packet))
        print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

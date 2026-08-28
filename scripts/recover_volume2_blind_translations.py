#!/usr/bin/env python3
"""Recover source-bound Volume 2 blind records into a fresh issue-70 packet.

The legacy packets are read-only inputs.  This utility copies no critique,
witness, adjudication, name, readiness, presentation, or completion result.
"""

from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import translation_workflow as workflow


TARGET_ISSUE = 70
TARGET_RANGE = (1538, 3034)
LEGACY_SCHEMA_VERSION = "1.3.0"
LEGACY_SCHEMA_COMMIT = "55364d1decb5503f7fd96e5fb17243c49203414e"
LEGACY_SCHEMA_PATH = "schemas/translation-work-packet.v1.schema.json"
LEGACY_SCHEMA_SHA256 = "cb01ab5189d613321d6c39820b68ba6d632eccb0f7a7041758109edae069429e"
LEGACY_RANGES = {
    issue: (1538 + ((issue - 54) * 100), 1637 + ((issue - 54) * 100))
    for issue in range(54, 68)
}
LEGACY_RANGES[68] = (2938, 3034)

ENTRY_BLIND_FIELDS = {
    "status",
    "runId",
    "model",
    "reasoning",
    "policySha256",
    "english",
}
STRUCTURAL_BLIND_FIELDS = ENTRY_BLIND_FIELDS | {"headingEnglish"}


class RecoveryError(RuntimeError):
    """The requested recovery cannot prove a safe, source-bound migration."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RecoveryError(message)


def _pending_critique() -> dict[str, Any]:
    return {
        "status": "pending",
        "runId": None,
        "model": None,
        "findings": [],
        "semanticAudit": workflow.pending_semantic_audit(),
        "independentContext": workflow.pending_independent_context(),
        "provenance": workflow.pending_stage_provenance("independent_critique"),
    }


def _pending_witness() -> dict[str, Any]:
    return {
        "status": "pending",
        "results": [],
        "notRequiredRationale": None,
        "provenance": workflow.pending_stage_provenance("witness_resolution"),
    }


def _pending_adjudication(structural: bool) -> dict[str, Any]:
    result = {
        "status": "pending",
        "english": None,
        "decisions": [],
        "provenance": workflow.pending_stage_provenance("adjudication"),
    }
    if structural:
        result["headingEnglish"] = None
    return result


def _pending_names() -> dict[str, Any]:
    return {
        "status": "pending",
        "candidates": [],
        "mentions": [],
        "inventoryAudit": workflow.pending_name_inventory_audit(),
        "independentContext": workflow.pending_independent_context(),
        "provenance": workflow.pending_stage_provenance("name_inventory"),
    }


def _clear_later_stage_claims(owner: dict[str, Any], *, structural: bool) -> None:
    owner["independentCritique"] = _pending_critique()
    owner["witnessResolution"] = _pending_witness()
    owner["adjudication"] = _pending_adjudication(structural)
    owner["names"] = _pending_names()
    owner["unresolved"] = []
    owner["humanReview"] = {"status": "unreviewed"}


def _validate_fresh_target(
    packet: dict[str, Any],
    *,
    expected_issue: int,
    expected_range: tuple[int, int],
) -> None:
    assignment = packet.get("assignment", {})
    _require(
        packet.get("schemaVersion") == workflow.PACKET_SCHEMA_VERSION,
        "target packet does not use the current packet schema",
    )
    _require(
        packet.get("toolVersion") == workflow.TOOL_VERSION,
        "target packet does not use the current workflow version",
    )
    _require(
        packet.get("packetId") == f"isabah-translation-issue-{expected_issue}",
        f"target packet must belong to issue {expected_issue}",
    )
    _require(
        assignment.get("issueNumber") == expected_issue,
        f"target assignment must belong to issue {expected_issue}",
    )
    _require(
        (assignment.get("startUnit"), assignment.get("endUnit")) == expected_range,
        f"target assignment must cover source units {expected_range[0]}-{expected_range[1]}",
    )
    _require(
        packet.get("formulaInventory", {}).get("status") == "pending",
        "target formula inventory must still be pending",
    )
    _require(
        packet.get("postRunRepairAudits") == [],
        "target post-run repair state is not freshly prepared",
    )
    _require(
        packet.get("reviewPresentation")
        == {"status": "pending", "path": None, "sha256": None},
        "target review presentation is not freshly prepared",
    )
    readiness = packet.get("machineReadiness", {})
    _require(
        readiness.get("status") == "pending"
        and readiness.get("validatedAt") is None,
        "target machine-readiness state is not freshly prepared",
    )

    entries = packet.get("entries")
    _require(
        isinstance(entries, list) and all(isinstance(entry, dict) for entry in entries),
        "target entries must be an array of objects",
    )
    for entry in entries:
        owners = [entry, *entry.get("precedingTranslations", [])]
        _require(
            all(isinstance(owner, dict) for owner in owners),
            "target output owners must be objects",
        )
        for owner in owners:
            _require(
                owner.get("blindTranslation", {}).get("status") == "pending",
                "target already contains blind work; refusing to overwrite it",
            )
            for field in (
                "independentCritique",
                "witnessResolution",
                "adjudication",
                "names",
            ):
                _require(
                    owner.get(field, {}).get("status") == "pending",
                    f"target contains a non-pending {field} claim",
                )
            _require(
                owner.get("unresolved") == []
                and owner.get("humanReview") == {"status": "unreviewed"},
                "target contains later-stage unresolved or human-review state",
            )

    errors = workflow.validate_packet(packet, machine_ready=False)
    if errors:
        raise RecoveryError("target packet is invalid:\n- " + "\n- ".join(errors))


def _validate_legacy_packet(
    packet: dict[str, Any],
    target: dict[str, Any],
    *,
    issue: int,
    expected_range: tuple[int, int],
) -> None:
    assignment = packet.get("assignment", {})
    _require(
        packet.get("schemaVersion") == LEGACY_SCHEMA_VERSION,
        f"legacy issue {issue} packet must use schema {LEGACY_SCHEMA_VERSION}",
    )
    _require(
        packet.get("packetId") == f"isabah-translation-issue-{issue}"
        and assignment.get("issueNumber") == issue,
        f"legacy packet identity does not match issue {issue}",
    )
    _require(
        (assignment.get("startUnit"), assignment.get("endUnit")) == expected_range,
        f"legacy issue {issue} range does not match {expected_range[0]}-{expected_range[1]}",
    )
    _require(
        packet.get("workId") == target.get("workId"),
        f"legacy issue {issue} belongs to a different work",
    )
    _require(
        packet.get("authority") == target.get("authority"),
        f"legacy issue {issue} authority does not exactly match the target",
    )
    _require(
        packet.get("policy") == target.get("policy"),
        f"legacy issue {issue} policy snapshot does not exactly match the target",
    )
    entries = packet.get("entries")
    _require(
        isinstance(entries, list) and all(isinstance(entry, dict) for entry in entries),
        f"legacy issue {issue} entries must be an array of objects",
    )
    actual_ordinals = [entry.get("sourceOrdinal") for entry in entries]
    _require(
        actual_ordinals == list(range(expected_range[0], expected_range[1] + 1)),
        f"legacy issue {issue} does not exactly cover its source range in order",
    )
    legacy_audit = packet.get("postRunRepairAudit", {})
    if legacy_audit.get("status") == "not_required":
        repair_errors = [] if legacy_audit == {
            "status": "not_required",
            "basePacketSha256": None,
            "artifactSha256": None,
            "runId": None,
            "operations": [],
        } else ["legacy not-required repair audit must be empty"]
    else:
        modernized = copy.deepcopy(packet)
        modernized.pop("postRunRepairAudit", None)
        migrated_audit = copy.deepcopy(legacy_audit)
        for operation in migrated_audit.get("operations", []):
            if isinstance(operation, dict):
                operation["valueKind"] = "text"
        modernized["postRunRepairAudits"] = [
            {**migrated_audit, "previousAuditSha256": None}
        ]
        repair_errors = workflow.validate_post_run_repair_audits(modernized)
    if repair_errors:
        raise RecoveryError(
            f"legacy issue {issue} repair evidence is invalid:\n- "
            + "\n- ".join(repair_errors)
        )


def _repair_evidence(
    packet: dict[str, Any],
    *,
    source_unit_id: str,
    segment_id: str | None,
) -> list[dict[str, Any]]:
    audit = packet.get("postRunRepairAudit", {})
    if audit.get("status") != "complete":
        return []
    relevant = [
        operation
        for operation in audit.get("operations", [])
        if operation.get("targetStage") == "blind_translation"
        and operation.get("sourceUnitId") == source_unit_id
        and operation.get("segmentId") == segment_id
    ]
    return [
        {
            "evidenceId": f"legacy-blind-repair:{operation['repairId']}",
            "role": "legacy_post_run_repair_operation",
            "sha256": workflow.content_sha256(operation),
        }
        for operation in relevant
    ]


def _recover_blind_record(
    legacy: dict[str, Any],
    source: dict[str, Any],
    packet: dict[str, Any],
    *,
    source_unit_id: str,
    segment_id: str | None,
    legacy_packet_blob_sha256: str,
) -> dict[str, Any]:
    structural = segment_id is not None
    allowed = STRUCTURAL_BLIND_FIELDS if structural else ENTRY_BLIND_FIELDS
    _require(
        isinstance(legacy, dict),
        f"{segment_id or source_unit_id}: legacy blind record must be an object",
    )
    _require(
        set(legacy) == allowed,
        f"{segment_id or source_unit_id}: legacy blind record has unexpected fields",
    )
    _require(
        legacy.get("status") == "complete",
        f"{segment_id or source_unit_id}: legacy blind record is incomplete",
    )
    for field in ("runId", "model", "reasoning"):
        _require(
            isinstance(legacy.get(field), str) and bool(legacy[field].strip()),
            f"{segment_id or source_unit_id}: legacy blind {field} is missing",
        )
    _require(
        legacy.get("policySha256") == packet["policy"]["bindingSha256"],
        f"{segment_id or source_unit_id}: legacy blind record uses a stale policy",
    )
    if structural:
        for source_field, english_field in (
            ("headingArabic", "headingEnglish"),
            ("arabic", "english"),
        ):
            expected_text = bool(source.get(source_field))
            actual = legacy.get(english_field)
            _require(
                (isinstance(actual, str) and bool(actual.strip()))
                if expected_text
                else actual is None,
                f"{segment_id}: legacy blind {english_field} does not match the source shape",
            )
    else:
        _require(
            isinstance(legacy.get("english"), str)
            and bool(legacy["english"].strip()),
            f"{source_unit_id}: legacy blind English is missing",
        )

    recovered = copy.deepcopy(legacy)
    record_evidence = {
        "legacyPacketId": packet["packetId"],
        "sourceUnitId": source_unit_id,
        "segmentId": segment_id,
        "blindTranslation": legacy,
    }
    evidence = [
        {
            "evidenceId": f"legacy-packet-blob:{packet['packetId']}",
            "role": "legacy_packet_blob",
            "sha256": legacy_packet_blob_sha256,
        },
        {
            "evidenceId": (
                f"git:{LEGACY_SCHEMA_COMMIT}:{LEGACY_SCHEMA_PATH}"
            ),
            "role": "legacy_packet_schema",
            "sha256": LEGACY_SCHEMA_SHA256,
        },
        {
            "evidenceId": (
                f"legacy-blind-record:{packet['packetId']}:"
                f"{segment_id or source_unit_id}"
            ),
            "role": "legacy_blind_translation_record",
            "sha256": workflow.content_sha256(record_evidence),
        },
        *_repair_evidence(
            packet,
            source_unit_id=source_unit_id,
            segment_id=segment_id,
        ),
    ]
    recovered["provenance"] = workflow.completed_stage_provenance(
        recovered,
        "blind_translation",
        source,
        [],
        recovered["policySha256"],
        recovered["model"],
        recovered["reasoning"],
        evidence,
        origin="legacy_migration",
    )
    provenance_errors = workflow.validate_stage_provenance(
        recovered,
        "blind_translation",
        source,
        [],
        recovered["policySha256"],
        segment_id or source_unit_id,
    )
    if provenance_errors:
        raise RecoveryError(
            f"{segment_id or source_unit_id}: recovered blind provenance is invalid:\n- "
            + "\n- ".join(provenance_errors)
        )
    return recovered


def recover_blind_translations(
    target: dict[str, Any],
    legacy_packets: Mapping[int, dict[str, Any]],
    *,
    expected_target_issue: int = TARGET_ISSUE,
    expected_target_range: tuple[int, int] = TARGET_RANGE,
    expected_legacy_ranges: Mapping[int, tuple[int, int]] = LEGACY_RANGES,
    legacy_packet_blob_sha256s: Mapping[int, str],
) -> tuple[dict[str, Any], dict[str, int]]:
    """Return a recovered copy; neither the target nor legacy inputs are mutated."""
    _validate_fresh_target(
        target,
        expected_issue=expected_target_issue,
        expected_range=expected_target_range,
    )
    _require(
        set(legacy_packets) == set(expected_legacy_ranges),
        "legacy packet set must exactly match the authorized issue set",
    )
    _require(
        set(legacy_packet_blob_sha256s) == set(expected_legacy_ranges)
        and all(
            workflow.SHA256_RE.fullmatch(str(value))
            for value in legacy_packet_blob_sha256s.values()
        ),
        "exact legacy packet blob hashes are required for every authorized issue",
    )
    recovered = copy.deepcopy(target)
    target_entries = {entry["sourceOrdinal"]: entry for entry in recovered["entries"]}
    seen_run_ids: set[str] = set()
    entry_count = 0
    structural_count = 0
    repaired_blind_count = 0

    for issue in sorted(expected_legacy_ranges):
        legacy_packet = legacy_packets[issue]
        expected_range = expected_legacy_ranges[issue]
        _validate_legacy_packet(
            legacy_packet,
            recovered,
            issue=issue,
            expected_range=expected_range,
        )
        for legacy_entry in legacy_packet["entries"]:
            ordinal = legacy_entry["sourceOrdinal"]
            target_entry = target_entries.get(ordinal)
            _require(
                target_entry is not None,
                f"legacy source unit {ordinal} is outside the target assignment",
            )
            _require(
                legacy_entry.get("sourceEntryNumber")
                == target_entry.get("sourceEntryNumber")
                and legacy_entry.get("sourceUnitId")
                == target_entry.get("sourceUnitId")
                and legacy_entry.get("source") == target_entry.get("source"),
                f"source unit {ordinal} does not exactly match the fresh target source",
            )
            legacy_structural = legacy_entry.get("precedingTranslations")
            target_structural = target_entry.get("precedingTranslations")
            _require(
                isinstance(legacy_structural, list)
                and isinstance(target_structural, list)
                and all(isinstance(item, dict) for item in legacy_structural)
                and all(isinstance(item, dict) for item in target_structural)
                and [item.get("segmentId") for item in legacy_structural]
                == [item.get("segmentId") for item in target_structural],
                f"source unit {ordinal} structural coverage does not match the target",
            )

            blind = _recover_blind_record(
                legacy_entry.get("blindTranslation", {}),
                target_entry["source"],
                legacy_packet,
                source_unit_id=target_entry["sourceUnitId"],
                segment_id=None,
                legacy_packet_blob_sha256=legacy_packet_blob_sha256s[issue],
            )
            _require(
                blind["runId"] not in seen_run_ids,
                f"duplicate legacy blind run ID: {blind['runId']}",
            )
            seen_run_ids.add(blind["runId"])
            target_entry["blindTranslation"] = blind
            _clear_later_stage_claims(target_entry, structural=False)
            entry_count += 1
            repaired_blind_count += sum(
                item["role"] == "legacy_post_run_repair_operation"
                for item in blind["provenance"]["evidence"]
            )

            for index, (legacy_owner, target_owner, source_segment) in enumerate(
                zip(
                    legacy_structural,
                    target_structural,
                    target_entry["source"]["precedingSegments"],
                ),
                start=1,
            ):
                segment_id = target_owner["segmentId"]
                _require(
                    source_segment.get("segmentId") == segment_id,
                    f"source unit {ordinal} structural segment {index} is misbound",
                )
                blind = _recover_blind_record(
                    legacy_owner.get("blindTranslation", {}),
                    source_segment,
                    legacy_packet,
                    source_unit_id=target_entry["sourceUnitId"],
                    segment_id=segment_id,
                    legacy_packet_blob_sha256=legacy_packet_blob_sha256s[issue],
                )
                _require(
                    blind["runId"] not in seen_run_ids,
                    f"duplicate legacy blind run ID: {blind['runId']}",
                )
                seen_run_ids.add(blind["runId"])
                target_owner["blindTranslation"] = blind
                _clear_later_stage_claims(target_owner, structural=True)
                structural_count += 1
                repaired_blind_count += sum(
                    item["role"] == "legacy_post_run_repair_operation"
                    for item in blind["provenance"]["evidence"]
                )

    expected_ordinals = list(
        range(expected_target_range[0], expected_target_range[1] + 1)
    )
    _require(
        sorted(target_entries) == expected_ordinals and entry_count == len(expected_ordinals),
        "recovered entries do not exactly cover the target assignment",
    )
    recovered["formulaInventory"] = {
        "status": "pending",
        "registryVersion": workflow.FORMULA_REGISTRY_VERSION,
        "occurrences": [],
    }
    recovered["postRunRepairAudits"] = []
    recovered["reviewPresentation"] = {
        "status": "pending",
        "path": None,
        "sha256": None,
    }
    recovered["machineReadiness"] = {
        "status": "pending",
        "validatedAt": None,
        "validatorVersion": workflow.TOOL_VERSION,
    }
    errors = workflow.validate_packet(recovered, machine_ready=False)
    if errors:
        raise RecoveryError("recovered packet is invalid:\n- " + "\n- ".join(errors))
    return recovered, {
        "entries": entry_count,
        "structuralSegments": structural_count,
        "documentedBlindRepairs": repaired_blind_count,
    }


def recover_packet_file(
    target_path: Path,
    legacy_packet_directory: Path,
    *,
    dry_run: bool = False,
) -> dict[str, int]:
    target_path = target_path.resolve()
    legacy_packet_directory = legacy_packet_directory.resolve()
    _require(target_path.is_file(), f"target packet is missing: {target_path}")
    _require(not target_path.is_symlink(), "target packet may not be a symlink")
    _require(
        legacy_packet_directory.is_dir(),
        f"legacy packet directory is missing: {legacy_packet_directory}",
    )
    _require(
        not legacy_packet_directory.is_symlink(),
        "legacy packet directory may not be a symlink",
    )
    legacy_packets: dict[int, dict[str, Any]] = {}
    legacy_packet_blob_sha256s: dict[int, str] = {}
    for issue in sorted(LEGACY_RANGES):
        path = legacy_packet_directory / f"issue-{issue:04d}.json"
        _require(path.is_file(), f"legacy packet is missing: {path}")
        _require(not path.is_symlink(), f"legacy packet may not be a symlink: {path}")
        packet_blob = path.read_bytes()
        legacy_packet_blob_sha256s[issue] = workflow.bytes_sha256(packet_blob)
        legacy_packets[issue] = workflow.load_json(path)
    recovered, summary = recover_blind_translations(
        workflow.load_json(target_path),
        legacy_packets,
        legacy_packet_blob_sha256s=legacy_packet_blob_sha256s,
    )
    if not dry_run:
        workflow.atomic_write(target_path, workflow.json_bytes(recovered))
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-packet", required=True, type=Path)
    parser.add_argument("--legacy-packet-directory", required=True, type=Path)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate and report the recovery without writing the target packet",
    )
    args = parser.parse_args(argv)
    try:
        summary = recover_packet_file(
            args.target_packet,
            args.legacy_packet_directory,
            dry_run=args.dry_run,
        )
    except (RecoveryError, workflow.WorkflowError) as exc:
        parser.error(str(exc))
    mode = "Validated" if args.dry_run else "Recovered"
    print(
        f"{mode} {summary['entries']} entries and "
        f"{summary['structuralSegments']} structural segments; "
        f"bound {summary['documentedBlindRepairs']} documented blind repair(s)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

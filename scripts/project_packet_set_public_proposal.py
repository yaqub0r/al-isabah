#!/usr/bin/env python3
"""Project machine-ready translation packets into a strict public proposal.

The packet and review artifacts remain outside the public repository.  This
projection retains only the reader-facing bilingual record, normalized public
provenance, review state, formula identity, and aggregate evidence hashes.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from project_public_proposal import FORMULA_KEYS, NORMALIZED_SOURCE_ID, parity_projection
from public_boundary import canonical_json, sha256_bytes, sha256_file, sha256_text_file


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import translation_workflow as workflow  # noqa: E402


INLINE_SECTION = re.compile(r"\s*#~:section:\d*\s*(\([^\n]+\))\s*")


def public_arabic(value: str) -> str:
    """Render reader-safe Arabic without changing the locked source evidence."""
    visible = workflow.present_openiti_arabic(value.strip())
    return INLINE_SECTION.sub(r"\n\n\1\n\n", visible).strip()


def finding(value: dict[str, Any]) -> dict[str, str]:
    return {
        "category": str(value.get("category") or value.get("kind") or "other"),
        "priority": str(value.get("priority") or value.get("severity") or "review"),
    }


def public_name(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": value["candidateId"],
        "arabic": value["observedArabic"],
        "english": value["proposedEnglish"],
        "aliases": value.get("aliases", []),
        "kind": "person",
        "reviewState": value.get("reviewState", "unreviewed"),
    }


def public_context(segment: dict[str, Any], translation: dict[str, Any]) -> dict[str, Any]:
    adjudication = translation["adjudication"]
    unresolved = translation.get("unresolved", [])
    return {
        "id": segment["segmentId"],
        "kind": segment["kind"],
        "heading": {
            "arabic": segment.get("headingArabic"),
            "english": adjudication.get("headingEnglish"),
            "level": segment.get("headingLevel"),
        },
        "arabic": public_arabic(segment.get("arabic") or ""),
        "english": adjudication.get("english") or "",
        "pages": segment.get("locations", []),
        "humanReview": translation["humanReview"]["status"],
        "unresolved": [finding(item) for item in unresolved],
        "sourceSha256": segment["rawSha256"],
    }


def public_record(
    packet: dict[str, Any],
    entry: dict[str, Any],
    formulas: list[dict[str, Any]],
) -> dict[str, Any]:
    candidates = entry["names"]["candidates"]
    if not candidates:
        raise ValueError(f"source ordinal {entry['sourceOrdinal']} has no title candidate")
    primary = candidates[0]
    contexts = [
        public_context(segment, translation)
        for segment, translation in zip(
            entry["source"]["precedingSegments"],
            entry["precedingTranslations"],
            strict=True,
        )
    ]
    unresolved = entry.get("unresolved", [])
    needs_attention = bool(unresolved) or any(item["unresolved"] for item in contexts)
    authority = packet["authority"]
    return {
        "schemaVersion": "2.0.0",
        "id": entry["sourceUnitId"],
        "kind": "entry",
        "workId": packet["workId"],
        "packetId": packet["packetId"],
        "sourceOrdinal": entry["sourceOrdinal"],
        "printedEntryNumber": entry["sourceEntryNumber"],
        "canonicalEntryId": entry.get("canonicalEntryId"),
        "volume": entry["source"]["locations"][0]["volume"],
        "pages": entry["source"]["locations"],
        "title": {
            "arabic": entry["source"]["headingArabic"],
            "english": primary["proposedEnglish"],
            "state": "needs_attention" if needs_attention else "ready",
            "method": "primary-name-candidate",
        },
        "arabic": public_arabic(entry["source"]["arabic"]),
        "english": entry["adjudication"]["english"],
        "precedingMaterial": contexts,
        "names": [public_name(item) for item in candidates],
        "unresolved": [finding(item) for item in unresolved],
        "formulas": [
            {key: item[key] for key in FORMULA_KEYS}
            for item in formulas
        ],
        "machineAssessment": "needs_attention" if needs_attention else "passed",
        "humanReview": entry["humanReview"]["status"],
        "source": {
            "authorityId": NORMALIZED_SOURCE_ID,
            "commit": authority["commit"],
            "artifactSha256": authority["sha256"],
            "exactTextSha256": entry["source"]["rawSha256"],
            "license": authority["license"],
        },
        "policy": {"bindingSha256": packet["policy"]["bindingSha256"]},
    }


def packet_set_hash(values: list[dict[str, Any]], key: str) -> str:
    return sha256_bytes(
        canonical_json(
            [
                {
                    "issueNumber": item["issueNumber"],
                    key: item[key],
                }
                for item in values
            ]
        )
    )


def project(packet_paths: list[Path], proposal_id: str) -> dict[str, Any]:
    if not packet_paths:
        raise ValueError("at least one packet is required")
    packets: list[tuple[Path, dict[str, Any]]] = []
    evidence: list[dict[str, Any]] = []
    for path in packet_paths:
        packet = json.loads(path.read_text(encoding="utf-8"))
        errors = workflow.validate_packet(packet, machine_ready=True)
        if errors:
            raise ValueError(f"packet {packet.get('packetId', 'unknown')} is not machine-ready")
        presentation = path.parent / packet["reviewPresentation"]["path"]
        if not presentation.is_file():
            raise ValueError(f"packet {packet['packetId']} review presentation is missing")
        review_sha256 = sha256_file(presentation)
        if review_sha256 != packet["reviewPresentation"]["sha256"]:
            raise ValueError(f"packet {packet['packetId']} review presentation is stale")
        packets.append((path, packet))
        evidence.append(
            {
                "issueNumber": packet["assignment"]["issueNumber"],
                "packetSha256": sha256_file(path),
                "reviewSha256": review_sha256,
            }
        )

    packets.sort(key=lambda item: item[1]["assignment"]["startUnit"])
    evidence.sort(key=lambda item: item["issueNumber"])
    first = packets[0][1]
    authority = first["authority"]
    policy_sha256 = first["policy"]["bindingSha256"]
    previous_end: int | None = None
    records: list[dict[str, Any]] = []
    for _, packet in packets:
        if packet["authority"]["commit"] != authority["commit"] or packet["authority"]["sha256"] != authority["sha256"]:
            raise ValueError("packet authority mismatch")
        if packet["policy"]["bindingSha256"] != policy_sha256:
            raise ValueError("packet policy mismatch")
        start = packet["assignment"]["startUnit"]
        end = packet["assignment"]["endUnit"]
        if previous_end is not None and start != previous_end + 1:
            raise ValueError("packet set is not contiguous and non-overlapping")
        previous_end = end
        by_record: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for occurrence in packet["formulaInventory"]["occurrences"]:
            by_record[occurrence["recordId"]].append(occurrence)
        records.extend(
            public_record(packet, entry, by_record[entry["sourceUnitId"]])
            for entry in packet["entries"]
        )

    if records != sorted(records, key=lambda item: (item["sourceOrdinal"], item["id"])):
        raise ValueError("public records are not in stable source order")
    rights = json.loads(
        (ROOT / "compliance" / "rights-matrix.al-isabah.v1.json").read_text(
            encoding="utf-8"
        )
    )
    record_projection = sha256_bytes(b"".join(canonical_json(item) for item in records))
    proposal = {
        "schemaVersion": "1.1.0",
        "proposalId": proposal_id,
        "workId": first["workId"],
        "publicationStatus": "public-working",
        "canonicalPromotion": "blocked",
        "consumerSchemaVersion": "2.0.0",
        "sourceAuthority": {
            "sourceId": NORMALIZED_SOURCE_ID,
            "commit": authority["commit"],
            "sha256": authority["sha256"],
            "license": authority["license"],
        },
        "rights": {
            "matrixId": rights["matrix_id"],
            "allowedUseClassification": "approved-noncommercial-public-working",
            "statusCode": "public-working",
            "effectCode": "canonical-promotion-blocked",
        },
        "policy": {
            "bindingSha256": sha256_text_file(
                ROOT / "compliance" / "policy-binding.v2.json"
            )
        },
        "review": {
            "machinePassed": sum(item["machineAssessment"] == "passed" for item in records),
            "needsAttention": sum(item["machineAssessment"] == "needs_attention" for item in records),
            "humanReviewed": sum(item["humanReview"] in {"reviewed", "verified"} for item in records),
            "humanUnreviewed": sum(item["humanReview"] not in {"reviewed", "verified"} for item in records),
        },
        "evidenceBinding": {
            "kind": "machine-ready-packet-set",
            "packetCount": len(packets),
            "packetSetSha256": packet_set_hash(evidence, "packetSha256"),
            "reviewCount": len(packets),
            "reviewSetSha256": packet_set_hash(evidence, "reviewSha256"),
            "recordProjectionSha256": record_projection,
        },
        "baseline": {
            "distributionSchemaVersion": "2.0.0",
            "recordCount": len(records),
            "userFacingSha256": sha256_bytes(parity_projection(records)),
        },
        "records": records,
    }
    return proposal


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet", action="append", required=True, type=Path)
    parser.add_argument("--proposal-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    proposal = project([item.resolve() for item in args.packet], args.proposal_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json(proposal))
    print(
        f"Projected {len(proposal['records'])} records; "
        f"proposal-sha256={sha256_file(args.output)}; "
        f"user-facing-sha256={proposal['baseline']['userFacingSha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

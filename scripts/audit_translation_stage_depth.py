#!/usr/bin/env python3
"""Report translation-stage depth without treating status strings as evidence."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import translation_workflow as workflow


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def has_attached_context_self_attestation(owner: dict[str, Any]) -> bool:
    """Count internally consistent editable claims, never execution proof."""
    context = owner.get("independentContext", {})
    receipt = context.get("receipt", {})
    provenance = owner.get("provenance", {})
    evidence = provenance.get("evidence", [])
    return bool(
        context.get("status") == "complete"
        and context.get("freshContext") is True
        and context.get("priorStageContextExcluded") is True
        and isinstance(receipt, dict)
        and receipt.get("receiptId")
        and receipt.get("receiptSha256")
        and any(
            isinstance(item, dict)
            and item.get("evidenceId") == receipt.get("receiptId")
            and item.get("role") == "independent_context_receipt"
            and item.get("sha256") == receipt.get("receiptSha256")
            for item in evidence
        )
    )


def add_owner(
    metrics: Counter,
    owner: dict[str, Any],
    source: dict[str, Any],
    policy_sha256: str,
) -> None:
    blind = owner.get("blindTranslation", {})
    critique = owner.get("independentCritique", {})
    findings = critique.get("findings", [])
    witness = owner.get("witnessResolution", {})
    adjudication = owner.get("adjudication", {})
    names = owner.get("names", {})
    unresolved = owner.get("unresolved", [])
    heading = adjudication.get("headingEnglish") or ""
    english = adjudication.get("english") or ""
    metrics["records"] += 1
    metrics["readableArabicCharacters"] += len(source.get("headingArabic") or "")
    metrics["readableArabicCharacters"] += len(source.get("arabic") or "")
    metrics["adjudicatedEnglishCharacters"] += len(heading) + len(english)
    metrics["critiqueStatusComplete"] += critique.get("status") == "complete"
    metrics["contentAddressedStageChains"] += not workflow.validate_stage_chain(
        owner,
        source,
        policy_sha256,
        "stage-depth audit",
    )
    metrics[
        "critiqueIndependentContextSelfAttestations"
    ] += has_attached_context_self_attestation(critique)
    metrics["semanticAuditStatusComplete"] += (
        critique.get("semanticAudit", {}).get("status") == "complete"
    )
    metrics["findings"] += len(findings) if isinstance(findings, list) else 0
    metrics["recordsWithFindings"] += bool(findings)
    metrics["witnessStatusComplete"] += witness.get("status") == "complete"
    metrics["witnessStatusNotRequired"] += witness.get("status") == "not_required"
    results = witness.get("results", [])
    metrics["witnessResults"] += len(results) if isinstance(results, list) else 0
    metrics["adjudicationStatusComplete"] += adjudication.get("status") == "complete"
    decisions = adjudication.get("decisions", [])
    metrics["adjudicationDecisions"] += (
        len(decisions) if isinstance(decisions, list) else 0
    )
    metrics["nameInventoryStatusComplete"] += names.get("status") == "complete"
    metrics["nameInventoryAuditStatusComplete"] += (
        names.get("inventoryAudit", {}).get("status") == "complete"
    )
    metrics[
        "nameIndependentContextSelfAttestations"
    ] += has_attached_context_self_attestation(names)
    candidates = names.get("candidates", [])
    mentions = names.get("mentions", [])
    metrics["nameCandidates"] += len(candidates) if isinstance(candidates, list) else 0
    metrics["nameMentions"] += len(mentions) if isinstance(mentions, list) else 0
    metrics["unresolvedItems"] += len(unresolved) if isinstance(unresolved, list) else 0
    metrics["recordsWithUnresolved"] += bool(unresolved)


def audit_packets(paths: list[Path]) -> dict[str, Any]:
    metrics: Counter = Counter()
    issue_numbers = []
    for path in paths:
        packet = load(path)
        issue_numbers.append(packet.get("assignment", {}).get("issueNumber"))
        policy_sha256 = str(packet.get("policy", {}).get("bindingSha256", ""))
        for entry in packet.get("entries", []):
            metrics["biographies"] += 1
            add_owner(metrics, entry, entry.get("source", {}), policy_sha256)
            candidates = entry.get("names", {}).get("candidates", [])
            metrics["biographiesWithMultipleNames"] += (
                isinstance(candidates, list) and len(candidates) > 1
            )
            for source, owner in zip(
                entry.get("source", {}).get("precedingSegments", []),
                entry.get("precedingTranslations", []),
            ):
                metrics["structuralRecords"] += 1
                add_owner(metrics, owner, source, policy_sha256)
    metrics["recordsWithoutFindings"] = metrics["records"] - metrics["recordsWithFindings"]
    return {
        "kind": "private-packet-stage-depth",
        "packetCount": len(paths),
        "issueNumbers": issue_numbers,
        "evidenceSemantics": (
            "Status/checklist/context fields are editable self-attestations; "
            "contentAddressedStageChains means only recomputed internal consistency, "
            "not proof that semantic work or separate contexts occurred."
        ),
        "metrics": dict(sorted(metrics.items())),
    }


def audit_proposal(path: Path) -> dict[str, Any]:
    proposal = load(path)
    metrics: Counter = Counter()
    for record in proposal.get("records", []):
        names = record.get("names", [])
        unresolved = record.get("unresolved", [])
        metrics["records"] += 1
        metrics["arabicCharacters"] += len(record.get("arabic") or "")
        metrics["englishCharacters"] += len(record.get("english") or "")
        metrics["nameCandidates"] += len(names) if isinstance(names, list) else 0
        metrics["recordsWithMultipleNames"] += (
            isinstance(names, list) and len(names) > 1
        )
        metrics["unresolvedItems"] += (
            len(unresolved) if isinstance(unresolved, list) else 0
        )
        metrics["recordsWithUnresolved"] += bool(unresolved)
        metrics["machinePassed"] += record.get("machineAssessment") == "passed"
        metrics["needsAttention"] += record.get("machineAssessment") == "needs_attention"
        metrics["humanUnreviewed"] += record.get("humanReview") == "unreviewed"
    return {
        "kind": "public-proposal-depth",
        "proposalId": proposal.get("proposalId"),
        "metrics": dict(sorted(metrics.items())),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet", action="append", type=Path, default=[])
    parser.add_argument("--proposal", action="append", type=Path, default=[])
    args = parser.parse_args()
    if not args.packet and not args.proposal:
        parser.error("provide at least one --packet or --proposal")
    report = {
        "schemaVersion": "1.0.0",
        "audits": [
            *([audit_packets([path.resolve() for path in args.packet])] if args.packet else []),
            *(audit_proposal(path.resolve()) for path in args.proposal),
        ],
    }
    print(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

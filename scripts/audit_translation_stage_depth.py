#!/usr/bin/env python3
"""Report translation-stage depth without treating status strings as evidence."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def add_owner(metrics: Counter, owner: dict[str, Any], source: dict[str, Any]) -> None:
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
    metrics["critiqueComplete"] += critique.get("status") == "complete"
    metrics["semanticAuditComplete"] += (
        critique.get("semanticAudit", {}).get("status") == "complete"
    )
    metrics["findings"] += len(findings) if isinstance(findings, list) else 0
    metrics["recordsWithFindings"] += bool(findings)
    metrics["witnessComplete"] += witness.get("status") == "complete"
    metrics["witnessNotRequired"] += witness.get("status") == "not_required"
    results = witness.get("results", [])
    metrics["witnessResults"] += len(results) if isinstance(results, list) else 0
    metrics["adjudicationComplete"] += adjudication.get("status") == "complete"
    decisions = adjudication.get("decisions", [])
    metrics["adjudicationDecisions"] += (
        len(decisions) if isinstance(decisions, list) else 0
    )
    metrics["nameInventoryComplete"] += names.get("status") == "complete"
    metrics["nameInventoryAuditComplete"] += (
        names.get("inventoryAudit", {}).get("status") == "complete"
    )
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
        for entry in packet.get("entries", []):
            metrics["biographies"] += 1
            add_owner(metrics, entry, entry.get("source", {}))
            candidates = entry.get("names", {}).get("candidates", [])
            metrics["biographiesWithMultipleNames"] += (
                isinstance(candidates, list) and len(candidates) > 1
            )
            for source, owner in zip(
                entry.get("source", {}).get("precedingSegments", []),
                entry.get("precedingTranslations", []),
            ):
                metrics["structuralRecords"] += 1
                add_owner(metrics, owner, source)
    metrics["recordsWithoutFindings"] = metrics["records"] - metrics["recordsWithFindings"]
    return {
        "kind": "private-packet-stage-depth",
        "packetCount": len(paths),
        "issueNumbers": issue_numbers,
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

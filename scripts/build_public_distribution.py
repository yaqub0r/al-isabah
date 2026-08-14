#!/usr/bin/env python3
"""Build the application-neutral public-working Al-Isabah distribution."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import unicodedata
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
PACKETS = ROOT / "content" / "translation-proposals"
SCHEMA_VERSION = "1.0.0"
WORK_ID = "ibn-hajar-al-isabah"
REPOSITORY = "https://github.com/yaqub0r/al-isabah"
PRIVATE_MARKERS = (
    "usul.ai",
    "lastpass",
    "r2.cloudflarestorage.com",
    "aws_access_key_id",
    "aws_secret_access_key",
)


class DistributionError(RuntimeError):
    """Raised when a public distribution cannot be built safely."""


def canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def utc_timestamp(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise DistributionError("generated timestamp must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def git_value(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def normalized_words(value: str) -> list[str]:
    value = unicodedata.normalize("NFKD", value).casefold()
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", value).split()


def title_similarity(candidate: str, english: str) -> float:
    candidate_words = normalized_words(candidate)[:8]
    opening_words = normalized_words(english)[:20]
    if not candidate_words:
        return 0.0
    return sum(word in opening_words for word in candidate_words) / len(candidate_words)


def opening_sentence(value: str) -> str:
    match = re.search(r"(?<=[.!?])(?:[\"'’”)]*)\s", value.strip())
    return (value[: match.start() + 1] if match else value).strip().rstrip(".")


def opening_arabic_heading(source: dict[str, Any]) -> str:
    heading = str(source.get("headingArabic") or source.get("arabic") or "").strip()
    for marker in (" قال ", " روى ", " ذكره ", " أخرجه ", " وأخرج ", " وذكر "):
        if marker in heading:
            heading = heading.split(marker, 1)[0]
    return heading.strip(" ،؛.")


def title_for(entry: dict[str, Any]) -> dict[str, Any]:
    candidates = entry.get("names", {}).get("candidates", [])
    if not candidates:
        raise DistributionError(f"{entry['sourceUnitId']}: no title candidate")
    candidate = candidates[0]
    proposed = str(candidate.get("proposedEnglish") or "").strip()
    proposed = re.sub(r"\s*\([^)]*\)\s*$", "", proposed)
    observed = str(candidate.get("observedArabic") or "").strip()
    english = str(entry.get("adjudication", {}).get("english") or "").strip()
    source = entry.get("source", {})
    similarity = title_similarity(proposed, english)
    source_opening = str(source.get("arabic") or "").strip()
    candidate_is_opening = bool(observed) and source_opening.find(observed) <= 12
    if similarity < 0.6:
        proposed = opening_sentence(english)
        observed = opening_arabic_heading(source)
    state = "ready" if similarity >= 0.6 and candidate_is_opening else "needs_attention"
    if not proposed or not observed:
        raise DistributionError(f"{entry['sourceUnitId']}: empty bilingual title")
    return {
        "arabic": observed,
        "english": proposed,
        "state": state,
        "method": "primary-name-candidate" if similarity >= 0.6 else "opening-fallback",
    }


def pages_for(entry: dict[str, Any]) -> list[dict[str, int]]:
    result: list[dict[str, int]] = []
    seen: set[tuple[int, int]] = set()
    for location in entry.get("source", {}).get("locations", []):
        value = (int(location["volume"]), int(location["page"]))
        if value not in seen:
            seen.add(value)
            result.append({"volume": value[0], "page": value[1]})
    return result


def public_names(entry: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for candidate in entry.get("names", {}).get("candidates", []):
        result.append(
            {
                "id": candidate["candidateId"],
                "arabic": candidate["observedArabic"],
                "english": candidate["proposedEnglish"],
                "aliases": candidate.get("aliases", []),
                "kind": candidate.get("entityType", "person"),
                "reviewState": candidate.get("reviewState", "unreviewed"),
            }
        )
    return result


def public_unresolved(values: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    result = []
    for value in values:
        explanation = str(
            value.get("explanation")
            or value.get("detail")
            or value.get("question")
            or "Unresolved translation finding."
        ).strip()
        result.append(
            {
                "category": str(value.get("category") or value.get("kind") or "other"),
                "explanation": explanation,
                "priority": str(value.get("priority") or value.get("severity") or "review"),
            }
        )
    return result


def preceding_material(entry: dict[str, Any]) -> list[dict[str, Any]]:
    source_segments = entry.get("source", {}).get("precedingSegments", [])
    translations = entry.get("precedingTranslations", [])
    if len(source_segments) != len(translations):
        raise DistributionError(
            f"{entry['sourceUnitId']}: structural source/translation count differs"
        )
    result = []
    for source, translation in zip(source_segments, translations):
        adjudication = translation.get("adjudication", {})
        result.append(
            {
                "id": source["segmentId"],
                "kind": source["kind"],
                "heading": {
                    "arabic": source.get("headingArabic"),
                    "english": adjudication.get("headingEnglish"),
                    "level": source.get("headingLevel"),
                },
                "arabic": source.get("arabic") or "",
                "english": adjudication.get("english") or "",
                "pages": [
                    {"volume": int(item["volume"]), "page": int(item["page"])}
                    for item in source.get("locations", [])
                ],
                "humanReview": translation.get("humanReview", {}).get(
                    "status", "unreviewed"
                ),
                "unresolved": public_unresolved(translation.get("unresolved", [])),
                "sourceSha256": source["rawSha256"],
            }
        )
    return result


def formula_index(packet: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for occurrence in packet.get("formulaInventory", {}).get("occurrences", []):
        result[str(occurrence["recordId"])].append(occurrence)
    return result


def record_for(
    packet: dict[str, Any],
    entry: dict[str, Any],
    formulas: dict[str, list[dict[str, Any]]],
    volume: int,
) -> dict[str, Any]:
    if entry.get("adjudication", {}).get("status") != "complete":
        raise DistributionError(f"{entry['sourceUnitId']}: adjudication is incomplete")
    if entry.get("humanReview", {}).get("status") not in {
        "unreviewed",
        "in_review",
        "reviewed",
        "verified",
    }:
        raise DistributionError(f"{entry['sourceUnitId']}: invalid human review state")
    source = entry["source"]
    title = title_for(entry)
    unresolved = public_unresolved(entry.get("unresolved", []))
    machine_state = (
        "passed" if title["state"] == "ready" and not unresolved else "needs_attention"
    )
    record_formulas = list(formulas.get(entry["sourceUnitId"], []))
    for context in source.get("precedingSegments", []):
        record_formulas.extend(formulas.get(context["segmentId"], []))
    return {
        "schemaVersion": SCHEMA_VERSION,
        "id": entry["sourceUnitId"],
        "kind": "entry",
        "workId": packet["workId"],
        "packetId": packet["packetId"],
        "sourceOrdinal": int(entry["sourceOrdinal"]),
        "printedEntryNumber": int(entry["sourceEntryNumber"]),
        "canonicalEntryId": entry.get("canonicalEntryId"),
        "volume": volume,
        "pages": pages_for(entry),
        "title": title,
        "arabic": source["arabic"],
        "english": entry["adjudication"]["english"],
        "precedingMaterial": preceding_material(entry),
        "names": public_names(entry),
        "unresolved": unresolved,
        "formulas": record_formulas,
        "machineAssessment": machine_state,
        "humanReview": entry["humanReview"]["status"],
        "source": {
            "authorityId": packet["authority"]["sourceId"],
            "repository": packet["authority"]["repository"],
            "commit": packet["authority"]["commit"],
            "path": packet["authority"]["path"],
            "artifactSha256": packet["authority"]["sha256"],
            "exactTextSha256": source["rawSha256"],
            "lineStart": int(source["lineStart"]),
            "lineEnd": int(source["lineEnd"]),
            "license": packet["authority"]["license"],
        },
        "policy": {
            "bindingSha256": packet["policy"]["bindingSha256"],
            "contracts": packet["policy"]["contracts"],
        },
    }


def packet_volume(packet: dict[str, Any]) -> int:
    assigned = packet.get("assignment", {}).get("volume")
    if assigned is not None:
        return int(assigned)
    counts: dict[int, int] = defaultdict(int)
    for entry in packet.get("entries", []):
        for location in entry.get("source", {}).get("locations", []):
            counts[int(location["volume"])] += 1
    if not counts:
        raise DistributionError(f"{packet['packetId']}: cannot determine volume")
    highest = max(counts.values())
    winners = [volume for volume, count in counts.items() if count == highest]
    if len(winners) != 1:
        raise DistributionError(f"{packet['packetId']}: ambiguous packet volume")
    return winners[0]


def validate_no_private_markers(value: Any, label: str) -> None:
    serialized = json.dumps(value, ensure_ascii=False).casefold()
    found = [marker for marker in PRIVATE_MARKERS if marker in serialized]
    if found:
        raise DistributionError(f"{label}: private marker present: {', '.join(found)}")


def load_packets() -> list[tuple[Path, dict[str, Any]]]:
    result = []
    for path in sorted(PACKETS.glob("*.packet.json")):
        packet = json.loads(path.read_text(encoding="utf-8"))
        if packet.get("machineReadiness", {}).get("status") != "ready":
            continue
        if packet.get("reviewPresentation", {}).get("status") != "ready":
            raise DistributionError(f"{path.name}: review presentation is not ready")
        validate_no_private_markers(packet.get("authority", {}), path.name)
        result.append((path, packet))
    if not result:
        raise DistributionError("no machine-ready translation packets were found")
    return result


def build(output: Path, repository_commit: str, generated_at: str) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    records_dir = output / "records"
    records_dir.mkdir(exist_ok=True)
    records_by_volume: dict[int, list[dict[str, Any]]] = defaultdict(list)
    packet_records = []
    seen_ids: set[str] = set()
    printed_identity: dict[int, list[str]] = defaultdict(list)
    authorities: dict[str, dict[str, Any]] = {}
    for path, packet in load_packets():
        formulas = formula_index(packet)
        volume = packet_volume(packet)
        packet_records.append(
            {
                "packetId": packet["packetId"],
                "path": path.relative_to(ROOT).as_posix(),
                "sha256": sha256(path.read_bytes()),
                "entryCount": len(packet["entries"]),
            }
        )
        authority = packet["authority"]
        authorities[authority["sourceId"]] = authority
        for entry in packet["entries"]:
            record = record_for(packet, entry, formulas, volume)
            if record["id"] in seen_ids:
                raise DistributionError(f"duplicate stable record ID: {record['id']}")
            seen_ids.add(record["id"])
            printed_identity[record["printedEntryNumber"]].append(record["id"])
            records_by_volume[record["volume"]].append(record)
    files = []
    total = 0
    needs_attention = 0
    for volume, records in sorted(records_by_volume.items()):
        records.sort(key=lambda item: (item["sourceOrdinal"], item["id"]))
        data = b"".join(canonical_json(record) for record in records)
        relative = f"records/volume-{volume:02d}.jsonl"
        (output / relative).write_bytes(data)
        files.append(
            {
                "path": relative,
                "sha256": sha256(data),
                "bytes": len(data),
                "recordCount": len(records),
                "volume": volume,
            }
        )
        total += len(records)
        needs_attention += sum(
            record["machineAssessment"] == "needs_attention" for record in records
        )
    duplicate_printed = [
        {"printedEntryNumber": number, "recordIds": ids}
        for number, ids in sorted(printed_identity.items())
        if len(ids) > 1
    ]
    distribution_id = f"al-isabah-public-working-{repository_commit[:12]}"
    manifest = {
        "schemaVersion": SCHEMA_VERSION,
        "distributionId": distribution_id,
        "publicationStatus": "public-working",
        "canonicalPromotion": "blocked",
        "work": {
            "id": WORK_ID,
            "titleArabic": "الإصابة في تمييز الصحابة",
            "titleEnglish": "Al-Isabah fi Tamyiz al-Sahabah",
        },
        "repository": {"url": REPOSITORY, "commit": repository_commit},
        "generatedAt": generated_at,
        "packets": packet_records,
        "authorities": list(authorities.values()),
        "counts": {
            "entries": total,
            "machinePassed": total - needs_attention,
            "needsAttention": needs_attention,
            "humanReviewed": 0,
        },
        "duplicatePrintedEntryNumbers": duplicate_printed,
        "files": files,
    }
    validate_no_private_markers(manifest, "manifest")
    (output / "manifest.json").write_bytes(canonical_json(manifest))
    return manifest


def package(output: Path, archive: Path) -> None:
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in sorted(output.rglob("*")):
            if not path.is_file():
                continue
            info = zipfile.ZipInfo(path.relative_to(output).as_posix())
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            bundle.writestr(info, path.read_bytes())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--repository-commit")
    parser.add_argument("--generated-at")
    args = parser.parse_args()
    commit = args.repository_commit or git_value("rev-parse", "HEAD")
    generated_at = args.generated_at or git_value("show", "-s", "--format=%cI", commit)
    if len(commit) != 40 or not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise DistributionError("repository commit must be a full lowercase SHA-1")
    generated_at = utc_timestamp(generated_at)
    manifest = build(args.output.resolve(), commit, generated_at)
    if args.archive:
        package(args.output.resolve(), args.archive.resolve())
    print(
        f"Built {manifest['distributionId']} with "
        f"{manifest['counts']['entries']} public-working entries."
    )
    return 0



if __name__ == "__main__":
    raise SystemExit(main())

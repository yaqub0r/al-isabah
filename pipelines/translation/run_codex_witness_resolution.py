#!/usr/bin/env python3
"""Resolve flagged uncertainties against Urdu and collateral Arabic witnesses."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from isabah_entry_sequence import probable_entry_numbers
from run_codex_volume_revision import (
    atomic_json,
    index_by_scan,
    read_jsonl,
    read_retained_jsonl,
    require_volume8_scan_coverage,
    run_codex,
    sha256_file,
    sha256_text,
)
from run_codex_volume_critic import (
    record_sha256,
    validate_critique_provenance,
)
from urdu_witness_index import (
    UrduWitnessIndex,
    expected_urdu_scan_page,
    validate_volume8_witness_units,
)
from usul_secondary_witness import (
    DEFAULT_API_BASE,
    WITNESS_SOURCES,
    evidence_sha256,
    resolve_authenticated_api_key,
    retrieve_secondary_witnesses,
    verify_source_health,
)


PROMPT_VERSION = "isabah-v8-multilingual-witness-resolution-v4-edition-witnesses"
SUPPLEMENTAL_PROMPT_VERSION = "isabah-v8-multilingual-witness-resolution-v5-supplemental-edition-witnesses"
SUPPLEMENTAL_REFRESH_PROMPT_VERSION = "isabah-v8-supplemental-witness-refresh-v1"
PASS_NAME = "multilingual_witness_resolution"
SUPPLEMENTAL_EVIDENCE_SCHEMA = "firstlight.supplemental-witness-evidence.v1"
SUPPLEMENTAL_EVIDENCE_KINDS = {
    "alternative_edition",
    "parallel_transmission",
    "translation_witness",
    "lexical_reference",
}
ENTRY_HEADING_RE = re.compile(r"^\s*[0-9٠-٩۰-۹]{4,5}\s*[-–—.:،]*\s*")


def biography_heading_names(source: dict) -> list[str]:
    headings = []
    for value in source.get("heading_titles") or []:
        text = str(value or "").strip()
        if not ENTRY_HEADING_RE.match(text):
            continue
        cleaned = ENTRY_HEADING_RE.sub("", text).strip(" ،.:;-–—")
        if cleaned:
            headings.append(cleaned)
    return headings


def canonical_entry_numbers(source: dict) -> list[int]:
    return probable_entry_numbers(str(source.get("arabic_text") or ""))


def nearest_previous_heading_source(
    source_by_scan: dict[int, dict], scan_page: int
) -> dict | None:
    """Return the active biography source across arbitrarily long continuations."""
    for prior_scan in sorted(
        (value for value in source_by_scan if value < scan_page), reverse=True
    ):
        candidate = source_by_scan[prior_scan]
        if biography_heading_names(candidate):
            return candidate
    return None


def witness_concerns(translation: dict, critique: dict | None) -> list[dict]:
    concerns = []
    for index, uncertainty in enumerate(translation.get("uncertainties") or [], start=1):
        if uncertainty.get("witness_check_recommended"):
            concerns.append({"concern_id": f"translation-{index}", "origin": "translation", **uncertainty})
    for index, issue in enumerate((critique or {}).get("issues") or [], start=1):
        if issue.get("witness_check_recommended"):
            concerns.append({"concern_id": f"critic-{index}", "origin": "critic", **issue})
    return concerns


def incomplete_secondary_evidence(evidence: list[dict]) -> list[dict]:
    """Return collateral records that are not final positive/negative evidence."""
    return [
        item for item in evidence
        if item.get("retrieval_state") not in {"hit", "no_match"}
    ]


def load_supplemental_evidence(path: Path | None) -> dict[int, list[dict]]:
    """Load hash-bound evidence acquired outside the automated witnesses."""
    if path is None:
        return {}
    records = read_jsonl(path)
    by_scan: dict[int, list[dict]] = {}
    seen_ids: set[str] = set()
    for position, record in enumerate(records, start=1):
        if record.get("schema") != SUPPLEMENTAL_EVIDENCE_SCHEMA:
            raise RuntimeError(
                f"Supplemental evidence record {position} has an unsupported schema"
            )
        try:
            scan = int(record["scan_page"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError(
                f"Supplemental evidence record {position} has an invalid scan_page"
            ) from exc
        evidence_id = str(record.get("evidence_id") or "").strip()
        if not evidence_id or evidence_id in seen_ids:
            raise RuntimeError(
                f"Supplemental evidence record {position} has a missing or duplicate evidence_id"
            )
        seen_ids.add(evidence_id)
        if record.get("kind") not in SUPPLEMENTAL_EVIDENCE_KINDS:
            raise RuntimeError(
                f"Supplemental evidence {evidence_id} has an unsupported kind"
            )
        for field in ("title", "language", "source_url", "citation", "excerpt"):
            if not str(record.get(field) or "").strip():
                raise RuntimeError(
                    f"Supplemental evidence {evidence_id} is missing {field}"
                )
        concerns = record.get("concern_ids")
        if not isinstance(concerns, list) or not concerns or any(
            not isinstance(item, str) or not item.strip() for item in concerns
        ):
            raise RuntimeError(
                f"Supplemental evidence {evidence_id} must identify one or more concern_ids"
            )
        excerpt_sha = sha256_text(record["excerpt"])
        if record.get("excerpt_sha256") != excerpt_sha:
            raise RuntimeError(
                f"Supplemental evidence {evidence_id} excerpt_sha256 mismatch"
            )
        by_scan.setdefault(scan, []).append(record)
    return by_scan


def supplemental_evidence_blocks(evidence: list[dict]) -> str:
    blocks = []
    for item in evidence:
        edition = str(item.get("edition") or "not specified")
        blocks.append(
            f"{item['title']} [{item['kind']}; {item['language']}; edition={edition}]\n"
            f"Applies to: {', '.join(item['concern_ids'])}\n"
            f"Citation: {item['citation']}\n"
            f"Source URL: {item['source_url']}\n"
            f"Evidence ID: {item['evidence_id']}\n"
            f"Excerpt (SHA-256 {item['excerpt_sha256']}):\n{item['excerpt']}\n"
            f"Acquisition note: {item.get('acquisition_note', '')}"
        )
    return "\n\n---\n\n".join(blocks)


def scope_supplemental_evidence(
    evidence_by_scan: dict[int, list[dict]],
    requested_pages: list[int],
) -> dict[int, list[dict]]:
    """Keep global evidence strict for full runs and page-local for proof runs."""
    if not requested_pages:
        return evidence_by_scan
    requested = set(requested_pages)
    return {
        scan: records
        for scan, records in evidence_by_scan.items()
        if scan in requested
    }


def validate_cached_secondary_health(
    health: dict,
    *,
    max_age_hours: float,
    current_time: datetime | None = None,
) -> tuple[bool, str]:
    if health.get("schema") != "firstlight.usul-secondary-source-health.v1":
        return False, "schema mismatch"
    if not health.get("pass") or not health.get("live_queries"):
        return False, "not a passing live health check"
    checks = health.get("checks") or []
    expected_work_ids = {item["work_id"] for item in WITNESS_SOURCES}
    observed_work_ids = {
        item.get("work_id") for item in checks
        if item.get("retrieval_state") == "hit"
    }
    if observed_work_ids != expected_work_ids or len(checks) != len(expected_work_ids):
        return False, "collateral corpus coverage mismatch"
    try:
        checked_at = datetime.fromisoformat(str(health["checked_at"]).replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError):
        return False, "checked_at is missing or invalid"
    now = current_time or datetime.now(timezone.utc)
    age_seconds = (now - checked_at).total_seconds()
    if age_seconds < -300:
        return False, "checked_at is in the future"
    if age_seconds > max(0.0, max_age_hours) * 3600:
        return False, "live health check is stale"
    return True, "current"


def resolve_pdftoppm_executable(configured: Path) -> Path:
    """Resolve Codex runtime override shims to the bundled Poppler executable.

    Some Windows runtime builds expose ``bin/override/pdftoppm.cmd`` even though
    that shim points at a path that is not present in the bundle.  Prefer an
    adjacent executable when available, then the runtime's canonical Poppler
    location.  Unknown wrappers are preserved so their own diagnostics remain
    visible rather than silently selecting an unrelated executable.
    """
    configured = configured.resolve()
    if configured.suffix.lower() != ".cmd":
        return configured

    candidates = [configured.with_suffix(".exe")]
    if len(configured.parents) >= 3:
        dependencies_root = configured.parents[2]
        candidates.extend([
            dependencies_root / "native" / "poppler" / "Library" / "bin" / "pdftoppm.exe",
            dependencies_root / "native" / "poppler" / "bin" / "pdftoppm.exe",
        ])
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return configured


def render_pdf_page(
    pdftoppm: Path,
    pdf_path: Path,
    scan_page: int,
    output_path: Path,
    *,
    pdf_sha256: str | None = None,
) -> Path:
    """Render and content-bind one facsimile page for repeatable model review."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    source_sha256 = pdf_sha256 or sha256_file(pdf_path)
    metadata_path = output_path.with_suffix(output_path.suffix + ".render.json")
    expected_metadata = {
        "schema": "firstlight.witness-image-render.v1",
        "source_pdf_sha256": source_sha256,
        "scan_page": scan_page,
        "dpi": 200,
        "format": "png",
        "single_file": True,
    }
    if output_path.is_file() and metadata_path.is_file():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            metadata = {}
        if (
            all(metadata.get(key) == value for key, value in expected_metadata.items())
            and metadata.get("image_sha256") == sha256_file(output_path)
        ):
            return output_path

    pending_output = output_path.with_name(
        f"{output_path.stem}.rendering{output_path.suffix}"
    )
    pending_output.unlink(missing_ok=True)
    prefix = pending_output.with_suffix("")
    completed = subprocess.run(
        [
            str(pdftoppm), "-f", str(scan_page), "-l", str(scan_page),
            "-r", "200", "-png", "-singlefile", str(pdf_path), str(prefix),
        ],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=180,
    )
    if completed.returncode != 0 or not pending_output.exists():
        raise RuntimeError(f"Could not render Urdu witness page {scan_page}: {completed.stderr[-800:]}")
    pending_output.replace(output_path)
    atomic_json(metadata_path, {
        **expected_metadata,
        "image_sha256": sha256_file(output_path),
    })
    return output_path


def candidate_evidence(candidates: list[dict]) -> list[dict]:
    return [
        {
            "scan_page": item["scan_page"],
            "score": item["score"],
            "expected_scan_page": item.get("expected_scan_page"),
            "distance_from_expected": item.get("distance_from_expected"),
            "selection_signals": item.get("selection_signals", []),
            "matched_names": item["matched_names"],
            "matched_headings": item.get("matched_headings", []),
            "matched_entry_numbers": item["matched_entry_numbers"],
            "matched_tokens": item["matched_tokens"],
            "text_sha256": item["text_sha256"],
            "quality": item["quality"],
        }
        for item in candidates
    ]


def candidate_evidence_sha256(evidence: list[dict]) -> str:
    return sha256_text(json.dumps(evidence, sort_keys=True, separators=(",", ":")))


def validate_witness_provenance(
    source: dict,
    translation: dict,
    critique: dict,
    witness: dict,
) -> tuple[bool, str]:
    current, reason = validate_critique_provenance(source, translation, critique)
    if not current:
        return False, f"critique {reason}"
    expected = {
        "work_id": source.get("work_id"),
        "volume": source.get("volume"),
        "scan_page": source.get("scan_page"),
        "source_sha256": source.get("arabic_text_sha256"),
        "translation_sha256": record_sha256(translation),
        "critique_sha256": record_sha256(critique),
        "concern_ids": [
            item["concern_id"] for item in witness_concerns(translation, critique)
        ],
    }
    for field, value in expected.items():
        if witness.get(field) != value:
            return (
                False,
                f"{field} mismatch: expected {value!r}, found {witness.get(field)!r}",
            )
    observed_candidates_sha = candidate_evidence_sha256(
        witness.get("urdu_witness_candidates") or []
    )
    if witness.get("candidate_evidence_sha256") != observed_candidates_sha:
        return False, "urdu_witness_candidates content hash mismatch"
    observed_secondary_sha = evidence_sha256(
        witness.get("secondary_witness_evidence") or []
    )
    if witness.get("secondary_evidence_sha256") != observed_secondary_sha:
        return False, "secondary_witness_evidence content hash mismatch"
    observed_supplemental = witness.get("supplemental_witness_evidence") or []
    declared_supplemental_sha = witness.get("supplemental_evidence_sha256")
    if observed_supplemental or declared_supplemental_sha is not None:
        if declared_supplemental_sha != evidence_sha256(observed_supplemental):
            return False, "supplemental_witness_evidence content hash mismatch"
    findings = witness.get("findings") or []
    if [item.get("concern_id") for item in findings] != expected["concern_ids"]:
        return False, "witness findings do not cover the concerns in order"
    unresolved = witness.get("remaining_unresolved") or []
    if witness.get("overall_status") == "resolved" and (
        unresolved or any(item.get("conclusion") == "inconclusive" for item in findings)
    ):
        return False, "resolved status contains unresolved evidence"
    if witness.get("overall_status") == "unresolved" and not unresolved:
        return False, "unresolved status contains no remaining uncertainty"
    return True, "current"


def secondary_evidence_blocks(evidence: list[dict]) -> str:
    blocks = []
    for item in evidence:
        role = item.get("witness_role", "collateral_work")
        edition = item.get("edition") or "edition metadata unavailable"
        header = (
            f"{item['title']} ({item['author']}), role={role}, edition={edition}, "
            f"query {item['query']!r}, "
            f"state={item['retrieval_state']}, source={item['source_and_version']}"
        )
        if item.get("retrieval_state") == "error":
            blocks.append(f"{header}\nRetrieval error: {item.get('error', 'unknown')}")
            continue
        if item.get("retrieval_state") == "unavailable":
            blocks.append(
                f"{header}\nQuery unavailable after bounded retries: "
                f"{item.get('error', 'unknown provider error')}. This is not evidence "
                "that the work lacks a matching passage."
            )
            continue
        if not item.get("hits"):
            blocks.append(f"{header}\nNo exact keyword match returned.")
            continue
        hit_blocks = []
        for hit in item.get("hits") or []:
            pages = (hit.get("metadata") or {}).get("pages") or []
            citation = ", ".join(
                f"vol. {page.get('volume')}, p. {page.get('page')} (index {page.get('index')})"
                for page in pages
            ) or "page metadata unavailable"
            truncation = " [retrieved text clipped]" if hit.get("text_truncated") else ""
            hit_blocks.append(f"Citation: {citation}{truncation}\n{hit.get('text', '')}")
        blocks.append(f"{header}\n" + "\n\n".join(hit_blocks))
    return "\n\n---\n\n".join(blocks) if blocks else "[no collateral Arabic witness queries]"


def build_prompt(
    source: dict,
    translation: dict,
    critique: dict | None,
    concerns: list[dict],
    candidates: list[dict],
    secondary_evidence: list[dict] | None = None,
    supplemental_evidence: list[dict] | None = None,
) -> str:
    witness_blocks = []
    for position, candidate in enumerate(candidates, start=1):
        witness_blocks.append(
            f"URDU CANDIDATE {position} - attached image {position}, witness scan {candidate['scan_page']}, "
            f"OCR mean confidence {candidate['quality'].get('mean_word_confidence', 'unknown')}\n"
            f"{candidate['text']}"
        )
    prompt = f"""You are resolving material uncertainties in an Arabic-to-English translation of Ibn Hajar al-Asqalani's al-Isabah, Volume 8.

Canonical al-Isabah Arabic remains authoritative. The Urdu edition is a secondary translation witness. Usd al-Ghaba and al-Isti'ab are independent collateral Arabic works, not alternative manuscripts of al-Isabah; use them only when an exact matching entry clarifies a name, shared report, or damaged wording. Evidence labeled role=alternative_edition is a different machine-readable al-Isabah edition and may establish a textual variant. Never override clear canonical Arabic merely because another witness differs; when multiple independent editions agree that the canonical wording is mechanically corrupt, recommend a transparent, cited emendation rather than silently rewriting it. The attached images are the Urdu facsimile pages and outrank their noisy OCR transcriptions. All retrieval is heuristic, so explicitly say inconclusive if the relevant passage is absent, illegible, or only loosely related.

For every concern, determine whether the combined evidence supports the current English, supports a specific revision, or is inconclusive. Do not invent certainty. Audit only Arabic scan page {source['scan_page']}. In witness_pages, list only attached Urdu scan-page numbers. When collateral Arabic evidence matters, cite its work title and volume/page metadata in the explanation.

CANONICAL ARABIC:
{source['arabic_text']}

CURRENT ENGLISH:
{translation['english_text']}

FLAGGED CONCERNS:
{json.dumps(concerns, ensure_ascii=False, indent=2)}

FIDELITY CRITIQUE CONTEXT:
{json.dumps(critique or {}, ensure_ascii=False, indent=2)}

URDU WITNESS CANDIDATES (images attached in this order):
{chr(10).join(witness_blocks) if witness_blocks else '[none found]'}

COLLATERAL ARABIC WITNESSES (public Usul exact-keyword retrieval):
{secondary_evidence_blocks(secondary_evidence or [])}
"""
    if supplemental_evidence:
        prompt += f"""
SUPPLEMENTAL HASH-BOUND EVIDENCE (independently acquired editions, parallel transmissions, translations, or references):
Treat each item according to its stated kind. An alternative edition can establish whether a reading recurs, while a parallel transmission can clarify shared material but cannot silently replace the canonical al-Isabah wording. Cite the evidence ID when it affects a finding.
{supplemental_evidence_blocks(supplemental_evidence)}
"""
    return prompt


def build_supplemental_refresh_prompt(
    source: dict,
    translation: dict,
    critique: dict | None,
    concerns: list[dict],
    prior_witness: dict,
    secondary_evidence: list[dict] | None = None,
    supplemental_evidence: list[dict] | None = None,
) -> str:
    """Build a text-only update prompt from a hash-bound prior witness pass."""
    return f"""You are refreshing a completed multilingual witness resolution for Ibn Hajar al-Asqalani's al-Isabah, Volume 8.

Canonical al-Isabah Arabic remains authoritative. The prior witness resolution below was completed with its Urdu facsimile images attached; its record, Urdu candidate metadata, and image hashes are supplied as hash-bound prior evidence. Do not pretend to re-read absent images. Preserve prior findings that the new evidence does not affect. Reassess every concern in the original order using the newly supplied textual evidence, and return a complete replacement resolution rather than a delta.

Evidence labeled role=alternative_edition is another al-Isabah edition and may establish a textual variant. A parallel transmission or translation witness may clarify shared material but cannot silently replace clear canonical wording. Prefer a transparent, cited emendation when independent evidence establishes mechanical corruption. Cite supplemental evidence IDs whenever they affect a finding. In witness_pages, retain only Urdu scan pages already cited by the prior resolution.

CANONICAL ARABIC:
{source['arabic_text']}

CURRENT ENGLISH:
{translation['english_text']}

FLAGGED CONCERNS:
{json.dumps(concerns, ensure_ascii=False, indent=2)}

FIDELITY CRITIQUE CONTEXT:
{json.dumps(critique or {}, ensure_ascii=False, indent=2)}

PRIOR HASH-BOUND WITNESS RESOLUTION:
{json.dumps({key: prior_witness.get(key) for key in ('overall_status', 'summary', 'findings', 'remaining_unresolved', 'urdu_witness_candidates', 'witness_image_sha256')}, ensure_ascii=False, indent=2)}

NEW COLLATERAL ARABIC WITNESSES:
{secondary_evidence_blocks(secondary_evidence or [])}

NEW SUPPLEMENTAL HASH-BOUND EVIDENCE:
{supplemental_evidence_blocks(supplemental_evidence or [])}
"""


def expected_provenance(
    *,
    prompt: str,
    source: dict,
    translation: dict,
    critique: dict | None,
    candidates: list[dict],
    image_paths: list[Path],
    secondary_evidence: list[dict],
    supplemental_evidence: list[dict],
    concerns: list[dict],
    model: str,
    reasoning_effort: str,
    schema_sha256: str,
) -> dict[str, object]:
    expected = {
        "schema": "firstlight.codex-witness-resolution.v1",
        "scan_page": int(source["scan_page"]),
        "work_id": source["work_id"],
        "volume": source["volume"],
        "source_sha256": source["arabic_text_sha256"],
        "translation_sha256": record_sha256(translation),
        "critique_sha256": record_sha256(critique) if critique else None,
        "candidate_evidence_sha256": candidate_evidence_sha256(candidate_evidence(candidates)),
        "witness_image_sha256": [sha256_file(path) for path in image_paths],
        "secondary_evidence_sha256": evidence_sha256(secondary_evidence),
        "concern_ids": [item["concern_id"] for item in concerns],
        "model": model,
        "reasoning_effort": reasoning_effort,
        "pass": PASS_NAME,
        "prompt_version": (
            SUPPLEMENTAL_PROMPT_VERSION if supplemental_evidence else PROMPT_VERSION
        ),
        "prompt_sha256": sha256_text(prompt),
        "output_schema_sha256": schema_sha256,
    }
    if supplemental_evidence:
        expected["supplemental_evidence_sha256"] = evidence_sha256(
            supplemental_evidence
        )
    return expected


def validate_existing_page(
    path: Path,
    expected: dict[str, object],
    expected_result_sha256: str | None = None,
) -> tuple[bool, str]:
    if not path.exists():
        return False, "missing"
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"unreadable: {exc}"
    for key, value in expected.items():
        if record.get(key) != value:
            return False, f"{key} mismatch: expected {value!r}, found {record.get(key)!r}"
    if "candidate_evidence_sha256" in expected:
        observed_candidates_sha = candidate_evidence_sha256(record.get("urdu_witness_candidates") or [])
        if observed_candidates_sha != expected["candidate_evidence_sha256"]:
            return False, "urdu_witness_candidates content hash mismatch"
    if evidence_sha256(record.get("secondary_witness_evidence") or []) != expected.get("secondary_evidence_sha256"):
        return False, "secondary_witness_evidence content hash mismatch"
    observed_supplemental = record.get("supplemental_witness_evidence") or []
    expected_supplemental_sha = expected.get("supplemental_evidence_sha256")
    if observed_supplemental or expected_supplemental_sha is not None:
        if evidence_sha256(observed_supplemental) != expected_supplemental_sha:
            return False, "supplemental_witness_evidence content hash mismatch"
    if expected_result_sha256 and sha256_file(path) != expected_result_sha256:
        return False, "result_sha256 mismatch with checkpoint state"
    findings = record.get("findings") or []
    if len(findings) == 0:
        return False, "no witness findings"
    if [item.get("concern_id") for item in findings] != expected.get("concern_ids"):
        return False, "witness findings do not cover the concerns in order"
    unresolved = record.get("remaining_unresolved") or []
    if record.get("overall_status") == "resolved" and (
        unresolved or any(item.get("conclusion") == "inconclusive" for item in findings)
    ):
        return False, "resolved status contains unresolved evidence"
    if record.get("overall_status") == "unresolved" and not unresolved:
        return False, "unresolved status contains no remaining uncertainty"
    return True, "current"


def aggregate(page_dir: Path, output_path: Path, scans: set[int]) -> int:
    pending = output_path.with_suffix(output_path.suffix + ".tmp")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pending.open("w", encoding="utf-8", newline="\n") as handle:
        for scan in sorted(scans):
            record = json.loads((page_dir / f"{scan:04d}.json").read_text(encoding="utf-8"))
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    pending.replace(output_path)
    return len(scans)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aligned-source", required=True)
    parser.add_argument("--translations", required=True)
    parser.add_argument("--criticisms", required=True)
    parser.add_argument("--urdu-units", required=True)
    parser.add_argument("--repository-root", default=".")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--schema", default=str(Path(__file__).with_name("schemas") / "codex-witness-resolution.schema.json"))
    parser.add_argument("--codex", required=True)
    parser.add_argument("--pdftoppm", required=True)
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--reasoning-effort", default="xhigh")
    parser.add_argument("--top-witness-pages", type=int, default=3)
    parser.add_argument("--secondary-witness-mode", choices=["api", "cache", "off"], default="api")
    parser.add_argument(
        "--supplemental-evidence",
        help=(
            "Optional hash-bound JSONL evidence. If omitted, a "
            "volume_08.supplemental-witness-evidence.jsonl file beside the aligned "
            "source is loaded automatically when present."
        ),
    )
    parser.add_argument(
        "--prior-witness-resolutions",
        help=(
            "Optional completed witness JSONL to refresh from without reattaching "
            "the already analyzed Urdu facsimile images."
        ),
    )
    parser.add_argument(
        "--prepare-evidence-only",
        action="store_true",
        help="Acquire and validate witness evidence without invoking Codex.",
    )
    parser.add_argument("--usul-api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--secondary-query-limit", type=int, default=4)
    parser.add_argument("--secondary-hit-limit", type=int, default=2)
    parser.add_argument("--secondary-max-text-chars", type=int, default=3500)
    parser.add_argument("--secondary-timeout-seconds", type=int, default=45)
    parser.add_argument("--secondary-retries", type=int, default=2)
    parser.add_argument("--cached-health-max-age-hours", type=float, default=24.0)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--page", type=int, action="append", default=[])
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--retry-backoff-seconds", type=float, default=8.0)
    parser.add_argument("--request-delay-seconds", type=float, default=1.0)
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    args = parser.parse_args()

    pdf_renderer = resolve_pdftoppm_executable(Path(args.pdftoppm))

    source_path = Path(args.aligned_source).resolve()
    translations_path = Path(args.translations).resolve()
    criticisms_path = Path(args.criticisms).resolve()
    urdu_units_path = Path(args.urdu_units).resolve()
    out_dir = Path(args.out_dir).resolve()
    page_dir = out_dir / "pages"
    log_dir = out_dir / "logs"
    image_dir = out_dir / "witness-images"
    secondary_cache_dir = out_dir / "usul-secondary-cache"
    work_dir = out_dir / "sandbox"
    for directory in (page_dir, log_dir, image_dir, secondary_cache_dir, work_dir):
        directory.mkdir(parents=True, exist_ok=True)
    translation_records, translations_snapshot = read_retained_jsonl(
        translations_path, out_dir / "input-snapshots", "translations"
    )
    critique_records, criticisms_snapshot = read_retained_jsonl(
        criticisms_path, out_dir / "input-snapshots", "criticisms"
    )
    witness_units, urdu_units_snapshot = read_retained_jsonl(
        urdu_units_path, out_dir / "input-snapshots", "urdu-units"
    )
    input_snapshots = {
        "translations": translations_snapshot,
        "criticisms": criticisms_snapshot,
        "urdu_units": urdu_units_snapshot,
    }
    source_by_scan = index_by_scan(read_jsonl(source_path), "Aligned source")
    translation_by_scan = index_by_scan(translation_records, "Blind translations")
    critique_by_scan = index_by_scan(critique_records, "Fidelity criticisms")
    inferred_supplemental_path = source_path.with_name(
        "volume_08.supplemental-witness-evidence.jsonl"
    )
    supplemental_path = (
        Path(args.supplemental_evidence).resolve()
        if args.supplemental_evidence
        else inferred_supplemental_path if inferred_supplemental_path.is_file() else None
    )
    if args.supplemental_evidence and not supplemental_path.is_file():
        raise RuntimeError(f"Supplemental evidence file does not exist: {supplemental_path}")
    if supplemental_path:
        _, supplemental_snapshot = read_retained_jsonl(
            supplemental_path,
            out_dir / "input-snapshots",
            "supplemental-evidence",
        )
        input_snapshots["supplemental_evidence"] = supplemental_snapshot
        supplemental_by_scan = load_supplemental_evidence(
            Path(str(supplemental_snapshot["path"]))
        )
    else:
        supplemental_by_scan = {}
    if args.prior_witness_resolutions:
        prior_witness_path = Path(args.prior_witness_resolutions).resolve()
        prior_witness_records, prior_witness_snapshot = read_retained_jsonl(
            prior_witness_path,
            out_dir / "input-snapshots",
            "prior-witness-resolutions",
        )
        input_snapshots["prior_witness_resolutions"] = prior_witness_snapshot
        prior_witness_by_scan = index_by_scan(
            prior_witness_records, "Prior witness resolutions"
        )
    else:
        prior_witness_path = None
        prior_witness_by_scan = {}
    if not args.page and args.limit <= 0:
        require_volume8_scan_coverage(source_by_scan, "Aligned source")
        require_volume8_scan_coverage(translation_by_scan, "Blind translations")
        require_volume8_scan_coverage(critique_by_scan, "Fidelity criticisms")
    missing_critique = sorted(set(translation_by_scan) - set(critique_by_scan))
    if missing_critique:
        raise RuntimeError(
            f"Critique is incomplete; {len(missing_critique)} translated pages lack criticism"
        )
    for scan, translation in translation_by_scan.items():
        source = source_by_scan.get(scan)
        if source is None:
            raise RuntimeError(f"Blind translation scan {scan} is absent from aligned source")
        current, reason = validate_critique_provenance(
            source, translation, critique_by_scan[scan]
        )
        if not current:
            raise RuntimeError(
                f"Critique provenance mismatch at scan {scan}: {reason}"
            )
    for scan, prior_witness in prior_witness_by_scan.items():
        source = source_by_scan.get(scan)
        translation = translation_by_scan.get(scan)
        critique = critique_by_scan.get(scan)
        if source is None or translation is None or critique is None:
            raise RuntimeError(
                f"Prior witness scan {scan} is absent from the current source chain"
            )
        current, reason = validate_witness_provenance(
            source, translation, critique, prior_witness
        )
        if not current:
            raise RuntimeError(
                f"Prior witness provenance mismatch at scan {scan}: {reason}"
            )
    validate_volume8_witness_units(witness_units)
    witness_index = UrduWitnessIndex(witness_units)
    repository_root = Path(args.repository_root).resolve()
    authenticated_api_key, authenticated_api_key_source = (
        resolve_authenticated_api_key(repository_root)
        if args.secondary_witness_mode == "api"
        else (None, "not-requested")
    )

    selected = []
    concerns_by_scan = {}
    for scan in sorted(source_by_scan):
        if scan not in translation_by_scan or (args.page and scan not in set(args.page)):
            continue
        concerns = witness_concerns(translation_by_scan[scan], critique_by_scan.get(scan))
        if concerns:
            selected.append(scan)
            concerns_by_scan[scan] = concerns

    selected_set = set(selected)
    if prior_witness_path:
        missing_prior = sorted(selected_set - set(prior_witness_by_scan))
        if missing_prior:
            raise RuntimeError(
                "Supplemental refresh requires prior witness records for scans: "
                + ", ".join(str(scan) for scan in missing_prior)
            )
    supplemental_by_scan = scope_supplemental_evidence(
        supplemental_by_scan,
        args.page,
    )
    dangling_supplemental = sorted(set(supplemental_by_scan) - selected_set)
    if dangling_supplemental:
        raise RuntimeError(
            "Supplemental evidence targets pages without flagged concerns: "
            + ", ".join(str(scan) for scan in dangling_supplemental)
        )
    for scan, items in supplemental_by_scan.items():
        concern_ids = {item["concern_id"] for item in concerns_by_scan[scan]}
        for item in items:
            unknown = sorted(set(item["concern_ids"]) - concern_ids)
            if unknown:
                raise RuntimeError(
                    f"Supplemental evidence {item['evidence_id']} targets unknown "
                    f"scan {scan} concerns: {', '.join(unknown)}"
                )

    schema_path = Path(args.schema).resolve()
    schema_sha256 = sha256_file(schema_path)

    state_path = out_dir / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    if state.get("schema") != "firstlight.codex-witness-state.v1":
        state = {"schema": "firstlight.codex-witness-state.v1", "completed": {}, "failed": {}, "stale": {}}

    secondary_health = {
        "schema": "firstlight.usul-secondary-source-health.v1",
        "api_base": args.usul_api_base,
        "checks": [],
        "pass": args.secondary_witness_mode == "off",
    }
    secondary_health_path = out_dir / "secondary-source-health.json"
    if selected and args.secondary_witness_mode == "api":
        secondary_health = verify_source_health(
            cache_root=secondary_cache_dir,
            api_base=args.usul_api_base,
            timeout_seconds=max(5, args.secondary_timeout_seconds),
            retries=max(1, args.secondary_retries + 1),
        )
        atomic_json(secondary_health_path, secondary_health)
        if not secondary_health["pass"]:
            failed = [item["work_id"] for item in secondary_health["checks"] if item["retrieval_state"] != "hit"]
            raise RuntimeError(f"Collateral witness source health check failed: {', '.join(failed)}")
    elif selected and args.secondary_witness_mode == "cache":
        if not secondary_health_path.is_file():
            raise RuntimeError("Cached collateral witness mode requires a prior live source health check")
        secondary_health = json.loads(secondary_health_path.read_text(encoding="utf-8"))
        current, reason = validate_cached_secondary_health(
            secondary_health,
            max_age_hours=args.cached_health_max_age_hours,
        )
        if not current:
            raise RuntimeError(f"Cached collateral witness source health check is invalid: {reason}")
    else:
        atomic_json(secondary_health_path, secondary_health)

    jobs = {}
    source_pdf_hashes: dict[Path, str] = {}
    pending_scans = []
    for scan in selected:
        translation = translation_by_scan[scan]
        prior_witness = prior_witness_by_scan.get(scan)
        candidates = [] if prior_witness else witness_index.rank(
            arabic_text=source_by_scan[scan]["arabic_text"],
            arabic_names=[
                item["arabic"] for item in translation.get("names") or []
                if item.get("kind") == "person"
            ],
            heading_names=biography_heading_names(source_by_scan[scan]),
            entry_numbers=canonical_entry_numbers(source_by_scan[scan]),
            top_k=args.top_witness_pages,
            expected_scan_page=expected_urdu_scan_page(scan),
        )
        image_paths = []
        for candidate in candidates:
            pdf_path = (repository_root / str(candidate["pdf"])).resolve()
            if pdf_path not in source_pdf_hashes:
                source_pdf_hashes[pdf_path] = sha256_file(pdf_path)
            image_path = image_dir / f"arabic-{scan:04d}-urdu-{candidate['scan_page']:04d}.png"
            render_pdf_page(
                pdf_renderer,
                pdf_path,
                int(candidate["scan_page"]),
                image_path,
                pdf_sha256=source_pdf_hashes[pdf_path],
            )
            image_paths.append(image_path)
        secondary_evidence = []
        if args.secondary_witness_mode in {"api", "cache"}:
            secondary_evidence = retrieve_secondary_witnesses(
                source=source_by_scan[scan],
                previous_source=nearest_previous_heading_source(source_by_scan, scan),
                translation=translation,
                concerns=concerns_by_scan[scan],
                cache_root=secondary_cache_dir,
                api_base=args.usul_api_base,
                query_limit=max(0, args.secondary_query_limit),
                hit_limit=max(1, args.secondary_hit_limit),
                max_text_chars=max(500, args.secondary_max_text_chars),
                timeout_seconds=max(5, args.secondary_timeout_seconds),
                retries=max(1, args.secondary_retries),
                cache_only=args.secondary_witness_mode == "cache",
                cache_unavailable_errors=(
                    args.secondary_witness_mode == "api"
                    and bool(secondary_health.get("pass"))
                ),
                unavailable_max_age_hours=args.cached_health_max_age_hours,
                authenticated_api_key=authenticated_api_key,
            )
            incomplete_evidence = incomplete_secondary_evidence(secondary_evidence)
            if incomplete_evidence and (
                args.secondary_witness_mode == "cache" or args.prepare_evidence_only
            ):
                if args.secondary_witness_mode == "cache":
                    description = "non-final cached records"
                else:
                    description = "non-final retrieval records"
                raise RuntimeError(
                    f"Collateral evidence is incomplete for scan {scan}: "
                    f"{len(incomplete_evidence)} {description}"
                )
        supplemental_evidence = supplemental_by_scan.get(scan, [])
        if prior_witness:
            prompt = build_supplemental_refresh_prompt(
                source_by_scan[scan], translation, critique_by_scan.get(scan),
                concerns_by_scan[scan], prior_witness, secondary_evidence,
                supplemental_evidence,
            )
        else:
            prompt = build_prompt(
                source_by_scan[scan], translation, critique_by_scan.get(scan),
                concerns_by_scan[scan], candidates, secondary_evidence,
                supplemental_evidence,
            )
        expected = expected_provenance(
            prompt=prompt,
            source=source_by_scan[scan],
            translation=translation,
            critique=critique_by_scan.get(scan),
            candidates=candidates,
            image_paths=image_paths,
            secondary_evidence=secondary_evidence,
            supplemental_evidence=supplemental_evidence,
            concerns=concerns_by_scan[scan],
            model=args.model,
            reasoning_effort=args.reasoning_effort,
            schema_sha256=schema_sha256,
        )
        if prior_witness:
            expected.update({
                "candidate_evidence_sha256": prior_witness["candidate_evidence_sha256"],
                "witness_image_sha256": prior_witness["witness_image_sha256"],
                "prior_witness_resolution_sha256": record_sha256(prior_witness),
                "prompt_version": SUPPLEMENTAL_REFRESH_PROMPT_VERSION,
            })
        jobs[scan] = {
            "prompt": prompt,
            "expected": expected,
            "images": image_paths,
            "candidate_evidence": (
                prior_witness["urdu_witness_candidates"]
                if prior_witness else candidate_evidence(candidates)
            ),
            "secondary_evidence": secondary_evidence,
            "supplemental_evidence": supplemental_evidence,
        }
        checkpoint_sha = (state.get("completed", {}).get(str(scan)) or {}).get("result_sha256")
        current, reason = validate_existing_page(page_dir / f"{scan:04d}.json", expected, checkpoint_sha)
        if current:
            state["completed"][str(scan)] = {"result_sha256": sha256_file(page_dir / f"{scan:04d}.json")}
            state["failed"].pop(str(scan), None)
            state["stale"].pop(str(scan), None)
        else:
            pending_scans.append(scan)
            state["completed"].pop(str(scan), None)
            if reason != "missing":
                state["stale"][str(scan)] = {"reason": reason}
    if args.limit > 0:
        pending_scans = pending_scans[:args.limit]
    atomic_json(state_path, state)
    atomic_json(out_dir / "run-manifest.json", {
        "schema": "firstlight.codex-witness-run.v1",
        "prompt_version": (
            SUPPLEMENTAL_REFRESH_PROMPT_VERSION
            if prior_witness_path else PROMPT_VERSION
        ),
        "prompt_versions": sorted({
            str(job["expected"]["prompt_version"]) for job in jobs.values()
        }),
        "aligned_source_sha256": sha256_file(source_path),
        "translations_sha256": translations_snapshot["sha256"],
        "criticisms_sha256": criticisms_snapshot["sha256"],
        "urdu_units_sha256": urdu_units_snapshot["sha256"],
        "input_snapshots": input_snapshots,
        "pdf_renderer": str(pdf_renderer),
        "secondary_witness_mode": args.secondary_witness_mode,
        "supplemental_evidence_path": str(supplemental_path) if supplemental_path else None,
        "supplemental_evidence_sha256": (
            input_snapshots["supplemental_evidence"]["sha256"]
            if supplemental_path else None
        ),
        "prior_witness_resolutions_path": (
            str(prior_witness_path) if prior_witness_path else None
        ),
        "prior_witness_resolutions_sha256": (
            input_snapshots["prior_witness_resolutions"]["sha256"]
            if prior_witness_path else None
        ),
        "cached_health_max_age_hours": args.cached_health_max_age_hours,
        "secondary_witness_sources": [
            {key: value for key, value in item.items() if key != "facsimile_url"}
            | {"facsimile_url": item["facsimile_url"]}
            for item in WITNESS_SOURCES
        ],
        "usul_api_base": args.usul_api_base,
        "authenticated_v1_fallback": {
            "configured": bool(authenticated_api_key),
            "credential_source": authenticated_api_key_source,
        },
        "secondary_source_health_sha256": sha256_file(secondary_health_path),
        "secondary_source_health": secondary_health,
        "output_schema_sha256": schema_sha256,
        "model": args.model,
        "reasoning_effort": args.reasoning_effort,
        "prepare_evidence_only": args.prepare_evidence_only,
        "flagged_pages": len(selected),
        "selected_scan_pages": selected,
        "pending_pages_at_start": len(pending_scans),
        "started_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    })

    if args.prepare_evidence_only:
        print(json.dumps({
            "prepared_pages": len(jobs),
            "secondary_witness_mode": args.secondary_witness_mode,
            "pending_model_pages": len(pending_scans),
        }, indent=2))
        return 0

    for scan in pending_scans:
        result_path = page_dir / f"{scan:04d}.json"
        candidate_path = page_dir / f".{scan:04d}.candidate.json"
        last_error = ""
        for attempt in range(1, args.max_retries + 1):
            try:
                candidate_path.unlink(missing_ok=True)
                completed = run_codex(
                    codex_path=Path(args.codex).resolve(),
                    work_dir=work_dir,
                    schema_path=schema_path,
                    prompt=jobs[scan]["prompt"],
                    result_path=candidate_path,
                    model=args.model,
                    reasoning_effort=args.reasoning_effort,
                    timeout_seconds=args.timeout_seconds,
                    image_paths=jobs[scan]["images"],
                )
                (log_dir / f"{scan:04d}.stdout.log").write_text(completed.stdout, encoding="utf-8")
                (log_dir / f"{scan:04d}.stderr.log").write_text(completed.stderr, encoding="utf-8")
                if completed.returncode != 0:
                    raise RuntimeError(f"Codex exited {completed.returncode}: {completed.stderr[-1200:]}")
                record = json.loads(candidate_path.read_text(encoding="utf-8"))
                if int(record.get("scan_page", -1)) != scan:
                    raise RuntimeError(f"Codex returned scan_page {record.get('scan_page')} for {scan}")
                record.update(jobs[scan]["expected"])
                record["urdu_witness_candidates"] = jobs[scan]["candidate_evidence"]
                record["secondary_witness_evidence"] = jobs[scan]["secondary_evidence"]
                if jobs[scan]["supplemental_evidence"]:
                    record["supplemental_witness_evidence"] = jobs[scan]["supplemental_evidence"]
                record["generated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
                atomic_json(result_path, record)
                candidate_path.unlink(missing_ok=True)
                valid, reason = validate_existing_page(result_path, jobs[scan]["expected"])
                if not valid:
                    raise RuntimeError(reason)
                state["completed"][str(scan)] = {"attempts": attempt, "result_sha256": sha256_file(result_path)}
                state["failed"].pop(str(scan), None)
                state["stale"].pop(str(scan), None)
                atomic_json(state_path, state)
                print(f"ok scan_page={scan} status={record['overall_status']} attempt={attempt}", flush=True)
                break
            except Exception as exc:
                last_error = str(exc)
                candidate_path.unlink(missing_ok=True)
                if attempt < args.max_retries:
                    time.sleep(args.retry_backoff_seconds * attempt)
        else:
            state["failed"][str(scan)] = {"error": last_error}
            atomic_json(state_path, state)
            print(f"fail scan_page={scan}: {last_error}", flush=True)
        time.sleep(max(0.0, args.request_delay_seconds))

    current_scans = {
        scan for scan in selected
        if str(scan) in state["completed"] and validate_existing_page(
            page_dir / f"{scan:04d}.json",
            jobs[scan]["expected"],
            (state.get("completed", {}).get(str(scan)) or {}).get("result_sha256"),
        )[0]
    }
    count = aggregate(page_dir, out_dir / "witness-resolutions.jsonl", current_scans)
    print(json.dumps({"flagged_pages": len(selected), "aggregated": count, "failed": len(state["failed"])}, indent=2))
    return 0 if not state["failed"] and count == len(selected) else 2


if __name__ == "__main__":
    raise SystemExit(main())

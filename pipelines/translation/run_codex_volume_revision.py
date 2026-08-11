#!/usr/bin/env python3
"""Run a resumable blind Codex translation pass over aligned Arabic pages."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


PROMPT_VERSION = "isabah-v8-blind-page-v2"
PASS_NAME = "blind_translation"
VOLUME8_EXPECTED_SCANS = frozenset(range(4, 495))


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def index_by_scan(records: list[dict], label: str) -> dict[int, dict]:
    indexed: dict[int, dict] = {}
    duplicates = []
    for record in records:
        scan = int(record["scan_page"])
        if scan in indexed:
            duplicates.append(scan)
        indexed[scan] = record
    if duplicates:
        raise RuntimeError(f"{label} contains duplicate scan pages: {sorted(set(duplicates))[:20]}")
    return indexed


def require_volume8_scan_coverage(indexed: dict[int, dict], label: str) -> None:
    observed = set(indexed)
    if observed != VOLUME8_EXPECTED_SCANS:
        missing = sorted(VOLUME8_EXPECTED_SCANS - observed)
        extra = sorted(observed - VOLUME8_EXPECTED_SCANS)
        raise RuntimeError(
            f"{label} does not cover Volume 8 scan pages 4-494 exactly; "
            f"missing={missing[:20]} ({len(missing)} total), extra={extra[:20]} ({len(extra)} total)"
        )


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + ".tmp")
    pending.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pending.replace(path)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_text(payload: str) -> str:
    return sha256_bytes(payload.encode("utf-8"))


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def retain_input_snapshot(source: Path, snapshot_dir: Path, label: str) -> dict[str, object]:
    """Retain an immutable, content-addressed copy of a model-stage input."""
    if not label or Path(label).name != label:
        raise ValueError(f"Unsafe input snapshot label: {label!r}")
    payload = source.read_bytes()
    digest = sha256_bytes(payload)
    suffix = source.suffix or ".bin"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    destination = snapshot_dir / f"{label}-{digest}{suffix}"
    if destination.exists():
        if sha256_file(destination) != digest:
            raise RuntimeError(f"Retained input snapshot was modified: {destination}")
    else:
        pending = destination.with_suffix(destination.suffix + ".tmp")
        pending.write_bytes(payload)
        pending.replace(destination)
    return {
        "path": str(destination.resolve()),
        "sha256": digest,
        "byte_size": len(payload),
    }


def read_retained_jsonl(
    source: Path,
    snapshot_dir: Path,
    label: str,
) -> tuple[list[dict], dict[str, object]]:
    """Snapshot a JSONL input first, then parse only the immutable copy."""
    snapshot = retain_input_snapshot(source, snapshot_dir, label)
    return read_jsonl(Path(str(snapshot["path"]))), snapshot


def build_prompt(current: dict, previous: dict | None, following: dict | None) -> str:
    context_before = str((previous or {}).get("arabic_text") or "")[-1800:]
    context_after = str((following or {}).get("arabic_text") or "")[:1800]
    return f"""You are performing the first blind scholarly translation pass for Ibn Hajar al-Asqalani's al-Isabah fi Tamyiz al-Sahabah, Volume 8.

Translate ONLY CURRENT PAGE from canonical Arabic into faithful, complete English. PREVIOUS and NEXT are context only and must not be translated into the answer.

Requirements:
- Translate every substantive element on CURRENT PAGE: headings, entry numbers, prose, isnads, quotations, poetry, cross-references, variant readings, parenthetical sigla, footnotes, and colophon material. Do not summarize or silently omit repetitive/devotional/editorial language.
- Preserve paragraph order and visible structural divisions.
- Do not invent missing text. Record genuine ambiguity in uncertainties while still giving the best supported translation.
- Use conventional English forms for widely established names. Otherwise use stable, search-friendly transliteration without scholarly diacritics; retain ibn, bint, Abu, Umm, and al-. Do not collapse different people merely because their names look similar.
- Render Allah as "Allah" and رسول الله as "the Messenger of Allah". Preserve honorific meaning without inserting doctrinal explanation.
- Treat Arabic as authoritative. Do not consult or infer from an earlier English draft; none is provided.
- Return only the JSON object required by the supplied schema. scan_page must equal {current['scan_page']}.

PREVIOUS PAGE CONTEXT (do not translate):
{context_before or '[none]'}

CURRENT PAGE (translate all of this):
{current['arabic_text']}

NEXT PAGE CONTEXT (do not translate):
{context_after or '[none]'}
"""


def expected_provenance(
    *,
    prompt: str,
    current: dict,
    model: str,
    reasoning_effort: str,
    schema_sha256: str,
) -> dict[str, object]:
    return {
        "schema": "firstlight.codex-page-translation.v1",
        "scan_page": int(current["scan_page"]),
        "work_id": current["work_id"],
        "volume": current["volume"],
        "reader_page": current["reader_page"],
        "source_sha256": current["arabic_text_sha256"],
        "model": model,
        "reasoning_effort": reasoning_effort,
        "pass": PASS_NAME,
        "prompt_version": PROMPT_VERSION,
        "prompt_sha256": sha256_text(prompt),
        "output_schema_sha256": schema_sha256,
    }


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
    if expected_result_sha256 and sha256_file(path) != expected_result_sha256:
        return False, "result_sha256 mismatch with checkpoint state"
    if not str(record.get("english_text") or "").strip():
        return False, "empty english_text"
    return True, "current"


def run_codex(
    *,
    codex_path: Path,
    work_dir: Path,
    schema_path: Path,
    prompt: str,
    result_path: Path,
    model: str,
    reasoning_effort: str,
    timeout_seconds: int,
    image_paths: list[Path] | None = None,
) -> subprocess.CompletedProcess[str]:
    command = [
        str(codex_path),
        "--ask-for-approval",
        "never",
        "exec",
        "--ephemeral",
        "--skip-git-repo-check",
        "--sandbox",
        "read-only",
        "--model",
        model,
        "--config",
        f'model_reasoning_effort="{reasoning_effort}"',
        "--output-schema",
        str(schema_path),
        "--output-last-message",
        str(result_path),
    ]
    for image_path in image_paths or []:
        command.extend(["--image", str(image_path)])
    command.append("-")
    return subprocess.run(
        command,
        input=prompt,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        cwd=work_dir,
        timeout=timeout_seconds,
        env=os.environ.copy(),
    )


def aggregate(page_dir: Path, output_path: Path, included_scans: set[int] | None = None) -> int:
    records = []
    for path in sorted(page_dir.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if included_scans is None or int(record["scan_page"]) in included_scans:
            records.append(record)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pending = output_path.with_suffix(output_path.suffix + ".tmp")
    with pending.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    pending.replace(output_path)
    return len(records)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aligned-source", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--schema", default=str(Path(__file__).with_name("schemas") / "codex-page-translation.schema.json"))
    parser.add_argument("--codex", required=True)
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--reasoning-effort", default="high")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--page", type=int, action="append", default=[])
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--retry-backoff-seconds", type=float, default=5.0)
    parser.add_argument("--request-delay-seconds", type=float, default=1.0)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    args = parser.parse_args()

    source_path = Path(args.aligned_source).resolve()
    source = read_jsonl(source_path)
    by_scan = index_by_scan(source, "Aligned source")
    if not args.page and args.limit <= 0:
        require_volume8_scan_coverage(by_scan, "Aligned source")
    scans = sorted(by_scan)
    selected = [scan for scan in scans if not args.page or scan in set(args.page)]
    out_dir = Path(args.out_dir).resolve()
    page_dir = out_dir / "pages"
    log_dir = out_dir / "logs"
    work_dir = out_dir / "sandbox"
    for directory in (page_dir, log_dir, work_dir):
        directory.mkdir(parents=True, exist_ok=True)
    state_path = out_dir / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {
        "schema": "firstlight.codex-translation-state.v2", "completed": {}, "failed": {}, "stale": {}
    }
    if state.get("schema") != "firstlight.codex-translation-state.v2":
        state = {
            "schema": "firstlight.codex-translation-state.v2",
            "completed": {},
            "failed": dict(state.get("failed") or {}),
            "stale": {},
        }
    state["schema"] = "firstlight.codex-translation-state.v2"
    state.setdefault("completed", {})
    state.setdefault("failed", {})
    state.setdefault("stale", {})

    schema_path = Path(args.schema).resolve()
    schema_sha256 = sha256_file(schema_path)
    expected_by_scan: dict[int, dict[str, object]] = {}
    prompt_by_scan: dict[int, str] = {}
    pending: list[int] = []
    for scan in selected:
        index = scans.index(scan)
        previous = by_scan[scans[index - 1]] if index > 0 else None
        following = by_scan[scans[index + 1]] if index + 1 < len(scans) else None
        prompt = build_prompt(by_scan[scan], previous, following)
        expected = expected_provenance(
            prompt=prompt,
            current=by_scan[scan],
            model=args.model,
            reasoning_effort=args.reasoning_effort,
            schema_sha256=schema_sha256,
        )
        prompt_by_scan[scan] = prompt
        expected_by_scan[scan] = expected
        result_path = page_dir / f"{scan:04d}.json"
        checkpoint_sha = (state.get("completed", {}).get(str(scan)) or {}).get("result_sha256")
        current, reason = validate_existing_page(result_path, expected, checkpoint_sha)
        if current:
            state["completed"][str(scan)] = {
                "source_sha256": expected["source_sha256"],
                "prompt_sha256": expected["prompt_sha256"],
                "output_schema_sha256": schema_sha256,
                "result_sha256": sha256_file(result_path),
            }
            state["failed"].pop(str(scan), None)
            state["stale"].pop(str(scan), None)
        else:
            pending.append(scan)
            state["completed"].pop(str(scan), None)
            if reason != "missing":
                state["stale"][str(scan)] = {"reason": reason}
    if args.limit > 0:
        pending = pending[:args.limit]

    atomic_json(state_path, state)
    output_path = out_dir / "translations.jsonl"
    current_scans = {
        scan for scan in selected
        if str(scan) in state["completed"] and validate_existing_page(
            page_dir / f"{scan:04d}.json",
            expected_by_scan[scan],
            (state.get("completed", {}).get(str(scan)) or {}).get("result_sha256"),
        )[0]
    }
    aggregate(page_dir, output_path, current_scans)
    atomic_json(out_dir / "run-manifest.json", {
        "schema": "firstlight.codex-translation-run.v1",
        "prompt_version": PROMPT_VERSION,
        "aligned_source": str(source_path),
        "aligned_source_sha256": sha256_file(source_path),
        "output_schema": str(schema_path),
        "output_schema_sha256": schema_sha256,
        "model": args.model,
        "reasoning_effort": args.reasoning_effort,
        "selected_pages": len(selected),
        "current_pages_at_start": len(selected) - len(pending),
        "pending_pages_at_start": len(pending),
        "started_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    })

    for scan in pending:
        prompt = prompt_by_scan[scan]
        expected = expected_by_scan[scan]
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
                    prompt=prompt,
                    result_path=candidate_path,
                    model=args.model,
                    reasoning_effort=args.reasoning_effort,
                    timeout_seconds=args.timeout_seconds,
                )
                (log_dir / f"{scan:04d}.stdout.log").write_text(completed.stdout, encoding="utf-8")
                (log_dir / f"{scan:04d}.stderr.log").write_text(completed.stderr, encoding="utf-8")
                if completed.returncode != 0:
                    raise RuntimeError(f"Codex exited {completed.returncode}: {completed.stderr[-1200:]}")
                record = json.loads(candidate_path.read_text(encoding="utf-8"))
                if int(record.get("scan_page", -1)) != scan:
                    raise RuntimeError(f"Codex returned scan_page {record.get('scan_page')} for {scan}")
                record.update(expected)
                record.update({
                    "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                })
                atomic_json(result_path, record)
                candidate_path.unlink(missing_ok=True)
                state["completed"][str(scan)] = {
                    "attempts": attempt,
                    "source_sha256": expected["source_sha256"],
                    "prompt_sha256": expected["prompt_sha256"],
                    "output_schema_sha256": schema_sha256,
                    "result_sha256": sha256_file(result_path),
                }
                state["failed"].pop(str(scan), None)
                state["stale"].pop(str(scan), None)
                atomic_json(state_path, state)
                current_scans.add(scan)
                aggregate(page_dir, output_path, current_scans)
                print(f"ok scan_page={scan} attempt={attempt}", flush=True)
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
            expected_by_scan[scan],
            (state.get("completed", {}).get(str(scan)) or {}).get("result_sha256"),
        )[0]
    }
    count = aggregate(page_dir, output_path, current_scans)
    print(json.dumps({
        "planned": len(selected),
        "aggregated": count,
        "completed": len(state["completed"]),
        "failed": len(state["failed"]),
        "output": str(output_path),
    }, indent=2))
    return 0 if not state["failed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

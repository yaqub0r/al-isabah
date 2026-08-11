#!/usr/bin/env python3
"""Supervise the complete resumable Codex translation-to-human-review pipeline."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from run_codex_volume_revision import atomic_json, sha256_file


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def state_counts(path: Path) -> tuple[int, int]:
    if not path.exists():
        return 0, 0
    state = json.loads(path.read_text(encoding="utf-8"))
    return len(state.get("completed") or {}), len(state.get("failed") or {})


def jsonl_count(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def update_status(path: Path, status: dict, **changes: object) -> None:
    status.update(changes)
    status["updated_at"] = now()
    atomic_json(path, status)


def invalidate_published_readiness(path: Path) -> None:
    """Close a previously published gate while a replacement pipeline is active."""
    if not path.exists():
        return
    readiness = json.loads(path.read_text(encoding="utf-8"))
    readiness["ready_for_human_review"] = False
    readiness["pipeline_complete"] = False
    readiness["gate_state"] = "autonomous_pipeline_in_progress"
    readiness["invalidated_at"] = now()
    atomic_json(path, readiness)


def run_stage(
    *,
    name: str,
    command: list[str],
    root: Path,
    log_dir: Path,
    status_path: Path,
    status: dict,
) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    update_status(status_path, status, state="running", stage=name, stage_started_at=now(), last_error=None)
    stdout_path = log_dir / f"{name}.stdout.log"
    stderr_path = log_dir / f"{name}.stderr.log"
    with stdout_path.open("w", encoding="utf-8", newline="\n") as stdout, stderr_path.open("w", encoding="utf-8", newline="\n") as stderr:
        completed = subprocess.run(command, cwd=root, stdout=stdout, stderr=stderr, text=True, encoding="utf-8", errors="replace")
    if completed.returncode != 0:
        error = stderr_path.read_text(encoding="utf-8", errors="replace")[-2000:]
        update_status(status_path, status, state="failed", stage=name, last_error=error, returncode=completed.returncode)
        raise RuntimeError(f"Stage {name} failed with exit {completed.returncode}: {error}")
    status.setdefault("completed_stages", [])
    if name not in status["completed_stages"]:
        status["completed_stages"].append(name)
    update_status(status_path, status, state="running", stage=name, stage_completed_at=now(), returncode=0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", default=".", type=Path)
    parser.add_argument("--codex", required=True, type=Path)
    parser.add_argument("--pdftoppm", required=True, type=Path)
    parser.add_argument("--poll-seconds", type=float, default=20.0)
    parser.add_argument(
        "--secondary-witness-mode",
        choices=["api", "cache", "off"],
        default="api",
        help="How the witness stage obtains collateral Usul evidence.",
    )
    parser.add_argument(
        "--external-blind-worker",
        action="store_true",
        help="Wait for a separately managed blind runner instead of starting/resuming it here.",
    )
    args = parser.parse_args()

    root = args.repository_root.resolve()
    scripts = root / "firstlight-research/scripts/translation"
    data = root / "firstlight-research/data/translated/ibn_hajar_isabah/arabic_v1"
    generated = root / "generated"
    blind_dir = generated / "isabah-v8-codex-pass1"
    critic_dir = generated / "isabah-v8-codex-critic"
    witness_dir = generated / "isabah-v8-codex-witness"
    adjudication_dir = generated / "isabah-v8-codex-adjudication"
    supervisor_dir = generated / "isabah-v8-pipeline"
    status_path = supervisor_dir / "pipeline-state.json"
    log_dir = supervisor_dir / "logs"
    supervisor_dir.mkdir(parents=True, exist_ok=True)
    published_readiness = data / "volume_08.machine-readiness.json"
    invalidate_published_readiness(published_readiness)
    status = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {
        "schema": "firstlight.isabah-v8-pipeline-state.v1",
        "state": "waiting",
        "stage": "blind_translation",
        "completed_stages": [],
        "created_at": now(),
    }

    blind_state = blind_dir / "state.json"
    blind_translations = blind_dir / "translations.jsonl"
    aligned_source = data / "volume_08.usul-aligned-source.jsonl"
    common = ["--codex", str(args.codex.resolve()), "--model", "gpt-5.6-sol"]
    if args.external_blind_worker:
        update_status(status_path, status, state="waiting", stage="blind_translation", expected_pages=491)
        while True:
            completed, failed = state_counts(blind_state)
            update_status(status_path, status, blind_completed=completed, blind_failed=failed)
            if failed:
                raise RuntimeError(f"Blind translation has {failed} failed pages")
            if completed == 491 and jsonl_count(blind_translations) == 491:
                break
            time.sleep(max(2.0, args.poll_seconds))
    else:
        run_stage(
            name="blind_translation",
            root=root,
            log_dir=log_dir,
            status_path=status_path,
            status=status,
            command=[
                sys.executable, str(scripts / "run_codex_volume_revision.py"),
                "--aligned-source", str(aligned_source),
                "--out-dir", str(blind_dir),
                *common, "--reasoning-effort", "high", "--max-retries", "2",
                "--retry-backoff-seconds", "8", "--request-delay-seconds", "1",
            ],
        )
        completed, failed = state_counts(blind_state)
        update_status(status_path, status, blind_completed=completed, blind_failed=failed)
        if completed != 491 or failed or jsonl_count(blind_translations) != 491:
            raise RuntimeError(
                f"Blind translation exited without complete coverage: state={completed}/491, "
                f"aggregate={jsonl_count(blind_translations)}/491, failed={failed}"
            )
    if "blind_translation" not in status["completed_stages"]:
        status["completed_stages"].append("blind_translation")
    update_status(
        status_path,
        status,
        state="running",
        stage="critic",
        blind_translations_sha256=sha256_file(blind_translations),
    )

    run_stage(
        name="critic",
        root=root,
        log_dir=log_dir,
        status_path=status_path,
        status=status,
        command=[
            sys.executable, str(scripts / "run_codex_volume_critic.py"),
            "--aligned-source", str(aligned_source),
            "--translations", str(blind_translations),
            "--out-dir", str(critic_dir),
            *common, "--reasoning-effort", "high", "--max-retries", "2",
            "--retry-backoff-seconds", "8", "--request-delay-seconds", "1",
        ],
    )

    criticisms = critic_dir / "criticisms.jsonl"
    run_stage(
        name="witness_resolution",
        root=root,
        log_dir=log_dir,
        status_path=status_path,
        status=status,
        command=[
            sys.executable, str(scripts / "run_codex_witness_resolution.py"),
            "--aligned-source", str(aligned_source),
            "--translations", str(blind_translations),
            "--criticisms", str(criticisms),
            "--urdu-units", str(data.parent / "urdu_witness_v1/volume_08.translation-units.jsonl"),
            "--repository-root", str(root),
            "--out-dir", str(witness_dir),
            "--pdftoppm", str(args.pdftoppm.resolve()),
            "--secondary-witness-mode", args.secondary_witness_mode,
            "--supplemental-evidence", str(data / "volume_08.supplemental-witness-evidence.jsonl"),
            *common, "--reasoning-effort", "xhigh", "--max-retries", "2",
            "--retry-backoff-seconds", "8", "--request-delay-seconds", "1",
        ],
    )

    witness_resolutions = supervisor_dir / "witness-resolutions.reconciled.jsonl"
    run_stage(
        name="witness_integrity_reconciliation",
        root=root,
        log_dir=log_dir,
        status_path=status_path,
        status=status,
        command=[
            sys.executable, str(scripts / "reconcile_codex_witness_shards.py"),
            "--aligned-source", str(aligned_source),
            "--translations", str(blind_translations),
            "--criticisms", str(criticisms),
            "--shard", str(witness_dir),
            "--output", str(witness_resolutions),
            "--report", str(supervisor_dir / "witness-reconciliation.json"),
            "--expected-model", "gpt-5.6-sol",
            "--expected-reasoning-effort", "xhigh",
        ],
    )
    run_stage(
        name="adjudication",
        root=root,
        log_dir=log_dir,
        status_path=status_path,
        status=status,
        command=[
            sys.executable, str(scripts / "run_codex_volume_adjudication.py"),
            "--aligned-source", str(aligned_source),
            "--translations", str(blind_translations),
            "--criticisms", str(criticisms),
            "--witness-resolutions", str(witness_resolutions),
            "--out-dir", str(adjudication_dir),
            "--all-pages",
            *common, "--reasoning-effort", "xhigh", "--max-retries", "2",
            "--retry-backoff-seconds", "8", "--request-delay-seconds", "1",
        ],
    )

    adjudications = supervisor_dir / "adjudications.reconciled.jsonl"
    run_stage(
        name="adjudication_integrity_reconciliation",
        root=root,
        log_dir=log_dir,
        status_path=status_path,
        status=status,
        command=[
            sys.executable, str(scripts / "reconcile_codex_adjudication_shards.py"),
            "--aligned-source", str(aligned_source),
            "--translations", str(blind_translations),
            "--criticisms", str(criticisms),
            "--witness-resolutions", str(witness_resolutions),
            "--shard", str(adjudication_dir),
            "--output", str(adjudications),
            "--report", str(supervisor_dir / "adjudication-reconciliation.json"),
            "--expected-model", "gpt-5.6-sol",
            "--expected-reasoning-effort", "xhigh",
        ],
    )

    final_units = data / "volume_08.translation-units.jsonl"
    readiness_candidate = supervisor_dir / "volume_08.machine-readiness.candidate.json"
    run_stage(
        name="deterministic_finalization",
        root=root,
        log_dir=log_dir,
        status_path=status_path,
        status=status,
        command=[
            sys.executable, str(scripts / "build_codex_volume_final.py"),
            "--aligned-source", str(aligned_source),
            "--translations", str(blind_translations),
            "--criticisms", str(criticisms),
            "--witness-resolutions", str(witness_resolutions),
            "--adjudications", str(adjudications),
            "--output", str(final_units),
            "--report", str(readiness_candidate),
        ],
    )

    run_stage(
        name="name_review_json",
        root=root,
        log_dir=log_dir,
        status_path=status_path,
        status=status,
        command=[
            sys.executable, str(scripts / "build_translation_name_review.py"),
            "--input", str(final_units),
            "--output", str(root / "docs/narrative/names/reviews/ibn_hajar_isabah_v1.name-review.v1.json"),
            "--index", str(root / "docs/narrative/names/review-index-v1.json"),
            "--work-id", "ibn_hajar_isabah_v1", "--issue", "971",
        ],
    )

    review_html = data / "volume_08.review.html"
    run_stage(
        name="review_presentation",
        root=root,
        log_dir=log_dir,
        status_path=status_path,
        status=status,
        command=[
            sys.executable, str(scripts / "render_english_review.py"),
            "--input", str(final_units), "--output", str(review_html),
        ],
    )

    run_stage(
        name="source_bundle_update",
        root=root,
        log_dir=log_dir,
        status_path=status_path,
        status=status,
        command=[
            sys.executable, str(scripts / "update_isabah_source_bundle.py"),
            "--bundle", "docs/narrative/sources/T1_primaries/ibn_hajar_isabah_v1/source-bundle.v1.json",
            "--alignment-report", "firstlight-research/data/translated/ibn_hajar_isabah/arabic_v1/volume_08.usul-alignment-report.json",
            "--aligned-source", "firstlight-research/data/translated/ibn_hajar_isabah/arabic_v1/volume_08.usul-aligned-source.jsonl",
            "--readiness", str(readiness_candidate),
            "--readiness-label", "firstlight-research/data/translated/ibn_hajar_isabah/arabic_v1/volume_08.machine-readiness.json",
            "--structured-english", "firstlight-research/data/translated/ibn_hajar_isabah/arabic_v1/volume_08.translation-units.jsonl",
            "--presentation", "firstlight-research/data/translated/ibn_hajar_isabah/arabic_v1/volume_08.review.html",
            "--name-review", "docs/narrative/names/reviews/ibn_hajar_isabah_v1.name-review.v1.json",
            "--supplemental-witness-evidence", "firstlight-research/data/translated/ibn_hajar_isabah/arabic_v1/volume_08.supplemental-witness-evidence.jsonl",
        ],
    )

    run_stage(
        name="publish_readiness",
        root=root,
        log_dir=log_dir,
        status_path=status_path,
        status=status,
        command=[
            sys.executable, str(scripts / "publish_isabah_readiness.py"),
            "--candidate", str(readiness_candidate),
            "--units", str(final_units),
            "--presentation", str(review_html),
            "--name-review", str(root / "docs/narrative/names/reviews/ibn_hajar_isabah_v1.name-review.v1.json"),
            "--name-index", str(root / "docs/narrative/names/review-index-v1.json"),
            "--bundle", str(root / "docs/narrative/sources/T1_primaries/ibn_hajar_isabah_v1/source-bundle.v1.json"),
            "--aligned-source", str(aligned_source),
            "--output", str(published_readiness),
        ],
    )

    update_status(
        status_path,
        status,
        state="complete",
        stage="complete",
        completed_at=now(),
        final_units_sha256=sha256_file(final_units),
        readiness_sha256=sha256_file(published_readiness),
        presentation_sha256=sha256_file(review_html),
    )
    print(json.dumps(status, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

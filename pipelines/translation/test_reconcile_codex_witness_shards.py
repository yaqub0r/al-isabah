from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("reconcile_codex_witness_shards.py")
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("reconcile_codex_witness_shards", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)

from run_codex_volume_revision import sha256_file  # noqa: E402
from run_codex_volume_critic import record_sha256  # noqa: E402
from run_codex_witness_resolution import candidate_evidence_sha256  # noqa: E402
from usul_secondary_witness import evidence_sha256  # noqa: E402


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")


def make_inputs(scan: int) -> tuple[dict, dict, dict, dict]:
    source = {
        "work_id": "work",
        "volume": 8,
        "scan_page": scan,
        "arabic_text_sha256": f"source-{scan}",
    }
    translation = {
        "work_id": "work",
        "volume": 8,
        "scan_page": scan,
        "source_sha256": f"source-{scan}",
        "uncertainties": [{"witness_check_recommended": True, "note": "check"}],
    }
    critique = {
        "work_id": "work",
        "volume": 8,
        "scan_page": scan,
        "source_sha256": f"source-{scan}",
        "translation_sha256": record_sha256(translation),
        "issues": [],
    }
    witness = {
        "work_id": "work",
        "volume": 8,
        "scan_page": scan,
        "source_sha256": f"source-{scan}",
        "translation_sha256": record_sha256(translation),
        "critique_sha256": record_sha256(critique),
        "concern_ids": ["translation-1"],
        "urdu_witness_candidates": [],
        "candidate_evidence_sha256": candidate_evidence_sha256([]),
        "witness_image_sha256": [],
        "secondary_witness_evidence": [],
        "secondary_evidence_sha256": evidence_sha256([]),
        "findings": [{"concern_id": "translation-1", "conclusion": "supports_current"}],
        "remaining_unresolved": [],
        "overall_status": "resolved",
        "model": "gpt-5.6-sol",
        "reasoning_effort": "xhigh",
    }
    return source, translation, critique, witness


def make_shard(root: Path, name: str, records: list[dict]) -> Path:
    shard = root / name
    pages = shard / "pages"
    pages.mkdir(parents=True)
    completed = {}
    for record in records:
        scan = int(record["scan_page"])
        path = pages / f"{scan:04d}.json"
        path.write_text(json.dumps(record), encoding="utf-8")
        completed[str(scan)] = {"result_sha256": sha256_file(path)}
    (shard / "state.json").write_text(json.dumps({
        "schema": MODULE.STATE_SCHEMA,
        "completed": completed,
        "failed": {},
        "stale": {},
    }), encoding="utf-8")
    return shard


def add_carried_prior_chain(
    root: Path, shard: Path, prior: dict, *, legacy_report_name: bool = False
) -> Path:
    """Attach the immutable aggregate/snapshot proof used by text-only refreshes."""
    prior_dir = root / "prior-final"
    prior_dir.mkdir()
    prior_path = prior_dir / "witness-resolutions.jsonl"
    write_jsonl(prior_path, [prior])
    prior_sha = sha256_file(prior_path)
    report_name = "reconciliation.json" if legacy_report_name else "reconciliation-report.json"
    (prior_dir / report_name).write_text(json.dumps({
        "schema": MODULE.REPORT_SCHEMA,
        "pass": True,
        "output_sha256": prior_sha,
    }), encoding="utf-8")
    snapshot_dir = shard / "input-snapshots"
    snapshot_dir.mkdir()
    snapshot_path = snapshot_dir / "prior-witness-resolutions.jsonl"
    write_jsonl(snapshot_path, [prior])
    (shard / "run-manifest.json").write_text(json.dumps({
        "prior_witness_resolutions_path": str(prior_path.resolve()),
        "prior_witness_resolutions_sha256": prior_sha,
        "input_snapshots": {
            "prior_witness_resolutions": {
                "path": str(snapshot_path.resolve()),
                "sha256": prior_sha,
            }
        },
    }), encoding="utf-8")
    return snapshot_path


class ReconcileCodexWitnessShardsTests(unittest.TestCase):
    def test_accepts_hash_chained_prior_images_for_text_only_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prior = make_inputs(4)[3]
            candidates = [{"scan_page": 50}]
            prior["urdu_witness_candidates"] = candidates
            prior["candidate_evidence_sha256"] = candidate_evidence_sha256(candidates)
            prior["witness_image_sha256"] = ["a" * 64]
            refreshed = {
                **prior,
                "prior_witness_resolution_sha256": record_sha256(prior),
                "overall_status": "partially_resolved",
            }
            shard = make_shard(root, "refresh", [refreshed])
            add_carried_prior_chain(root, shard, prior)

            records, report = MODULE.load_shard(shard)

            self.assertEqual(records[4]["overall_status"], "partially_resolved")
            self.assertEqual(report["carried_prior_image_pages"], [4])

    def test_accepts_legacy_reconciliation_report_name(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prior = make_inputs(4)[3]
            candidates = [{"scan_page": 50}]
            prior["urdu_witness_candidates"] = candidates
            prior["candidate_evidence_sha256"] = candidate_evidence_sha256(candidates)
            prior["witness_image_sha256"] = ["a" * 64]
            refreshed = {
                **prior,
                "prior_witness_resolution_sha256": record_sha256(prior),
            }
            shard = make_shard(root, "refresh", [refreshed])
            add_carried_prior_chain(root, shard, prior, legacy_report_name=True)

            _, report = MODULE.load_shard(shard)

            self.assertEqual(report["carried_prior_image_pages"], [4])

    def test_rejects_tampered_carried_prior_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prior = make_inputs(4)[3]
            candidates = [{"scan_page": 50}]
            prior["urdu_witness_candidates"] = candidates
            prior["candidate_evidence_sha256"] = candidate_evidence_sha256(candidates)
            prior["witness_image_sha256"] = ["a" * 64]
            refreshed = {
                **prior,
                "prior_witness_resolution_sha256": record_sha256(prior),
            }
            shard = make_shard(root, "refresh", [refreshed])
            snapshot = add_carried_prior_chain(root, shard, prior)
            snapshot.write_text("tampered\n", encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "aggregate hash mismatch"):
                MODULE.load_shard(shard)

    def test_rejects_changed_evidence_when_images_are_carried(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prior = make_inputs(4)[3]
            candidates = [{"scan_page": 50}]
            prior["urdu_witness_candidates"] = candidates
            prior["candidate_evidence_sha256"] = candidate_evidence_sha256(candidates)
            prior["witness_image_sha256"] = ["a" * 64]
            refreshed = {
                **prior,
                "prior_witness_resolution_sha256": record_sha256(prior),
                "witness_image_sha256": ["b" * 64],
            }
            shard = make_shard(root, "refresh", [refreshed])
            add_carried_prior_chain(root, shard, prior)

            with self.assertRaisesRegex(RuntimeError, "evidence mismatch"):
                MODULE.load_shard(shard)

    def test_reconciles_complete_disjoint_shards(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = make_inputs(4)
            second = make_inputs(5)
            source = root / "source.jsonl"
            translations = root / "translations.jsonl"
            criticisms = root / "criticisms.jsonl"
            write_jsonl(source, [first[0], second[0]])
            write_jsonl(translations, [first[1], second[1]])
            write_jsonl(criticisms, [first[2], second[2]])
            report = MODULE.reconcile(
                source_path=source,
                translations_path=translations,
                criticisms_path=criticisms,
                shards=[make_shard(root, "a", [first[3]]), make_shard(root, "b", [second[3]])],
                override_shards=[],
                output_path=root / "witness.jsonl",
                report_path=root / "report.json",
                expected_model="gpt-5.6-sol",
                expected_reasoning_effort="xhigh",
            )
            self.assertTrue(report["pass"])
            self.assertEqual(report["reconciled_pages"], 2)
            self.assertEqual([item["scan_page"] for item in MODULE.read_jsonl(root / "witness.jsonl")], [4, 5])

    def test_rejects_checkpoint_hash_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = make_inputs(4)
            shard = make_shard(root, "a", [inputs[3]])
            state_path = shard / "state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["completed"]["4"]["result_sha256"] = "stale"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "checkpoint hash mismatch"):
                MODULE.load_shard(shard)

    def test_rejects_overlapping_shards(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_record, translation, critique, witness = make_inputs(4)
            source = root / "source.jsonl"
            translations = root / "translations.jsonl"
            criticisms = root / "criticisms.jsonl"
            write_jsonl(source, [source_record])
            write_jsonl(translations, [translation])
            write_jsonl(criticisms, [critique])
            with self.assertRaisesRegex(RuntimeError, "overlap"):
                MODULE.reconcile(
                    source_path=source,
                    translations_path=translations,
                    criticisms_path=criticisms,
                    shards=[make_shard(root, "a", [witness]), make_shard(root, "b", [witness])],
                    override_shards=[],
                    output_path=root / "witness.jsonl",
                    report_path=root / "report.json",
                    expected_model="gpt-5.6-sol",
                    expected_reasoning_effort="xhigh",
                )

    def test_override_shard_replaces_without_mutating_base(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_record, translation, critique, witness = make_inputs(4)
            replacement = {**witness, "overall_status": "unresolved", "remaining_unresolved": ["still uncertain"]}
            source = root / "source.jsonl"
            translations = root / "translations.jsonl"
            criticisms = root / "criticisms.jsonl"
            write_jsonl(source, [source_record])
            write_jsonl(translations, [translation])
            write_jsonl(criticisms, [critique])
            base = make_shard(root, "base", [witness])
            override = make_shard(root, "override", [replacement])
            report = MODULE.reconcile(
                source_path=source,
                translations_path=translations,
                criticisms_path=criticisms,
                shards=[base],
                override_shards=[override],
                output_path=root / "witness.jsonl",
                report_path=root / "report.json",
                expected_model="gpt-5.6-sol",
                expected_reasoning_effort="xhigh",
            )
            output = MODULE.read_jsonl(root / "witness.jsonl")
            self.assertEqual(report["replaced_pages"], [4])
            self.assertEqual(output[0]["overall_status"], "unresolved")
            self.assertEqual(json.loads((base / "pages/0004.json").read_text())["overall_status"], "resolved")

    def test_rejects_unavailable_collateral_evidence_at_final_merge(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = list(make_inputs(4))
            second = list(make_inputs(5))
            for inputs, state in ((first, "unavailable"), (second, "error")):
                inputs[3]["secondary_witness_evidence"] = [{
                    "work_id": "collateral",
                    "retrieval_state": state,
                }]
                inputs[3]["secondary_evidence_sha256"] = evidence_sha256(
                    inputs[3]["secondary_witness_evidence"]
                )
            source = root / "source.jsonl"
            translations = root / "translations.jsonl"
            criticisms = root / "criticisms.jsonl"
            write_jsonl(source, [first[0], second[0]])
            write_jsonl(translations, [first[1], second[1]])
            write_jsonl(criticisms, [first[2], second[2]])
            with self.assertRaisesRegex(RuntimeError, "Incomplete collateral") as raised:
                MODULE.reconcile(
                    source_path=source,
                    translations_path=translations,
                    criticisms_path=criticisms,
                    shards=[make_shard(root, "base", [first[3], second[3]])],
                    override_shards=[],
                    output_path=root / "witness.jsonl",
                    report_path=root / "report.json",
                    expected_model="gpt-5.6-sol",
                    expected_reasoning_effort="xhigh",
                )
            self.assertIn('"scan_page":4', str(raised.exception))
            self.assertIn('"scan_page":5', str(raised.exception))


if __name__ == "__main__":
    unittest.main()

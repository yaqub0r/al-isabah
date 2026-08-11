from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("reconcile_codex_adjudication_shards.py")
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("reconcile_codex_adjudication_shards", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)

from run_codex_volume_adjudication import build_prompt, expected_provenance  # noqa: E402
from run_codex_volume_critic import record_sha256  # noqa: E402
from run_codex_volume_revision import sha256_file  # noqa: E402


SCHEMA = SCRIPT.with_name("schemas") / "codex-page-adjudication.schema.json"


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")


def make_inputs(scan: int) -> tuple[dict, dict, dict]:
    source = {
        "work_id": "work",
        "volume": 8,
        "scan_page": scan,
        "arabic_text": f"arabic {scan}",
        "arabic_text_sha256": f"source-{scan}",
    }
    translation = {
        "work_id": "work",
        "volume": 8,
        "scan_page": scan,
        "source_sha256": f"source-{scan}",
        "english_text": f"english {scan}",
        "names": [],
        "uncertainties": [],
        "fidelity": {},
    }
    critique = {
        "work_id": "work",
        "volume": 8,
        "scan_page": scan,
        "source_sha256": f"source-{scan}",
        "translation_sha256": record_sha256(translation),
        "verdict": "revise",
        "issues": [],
    }
    return source, translation, critique


def make_record(
    source: dict,
    translation: dict,
    critique: dict,
    previous: dict | None,
    following: dict | None,
) -> dict:
    prompt = build_prompt(source, translation, critique, None, previous, following)
    return {
        "scan_page": source["scan_page"],
        "decision": "accept",
        "final_english_text": translation["english_text"],
        "names": [],
        "changes": [],
        "unresolved": [],
        "fidelity": {"complete": True},
        **expected_provenance(
            prompt=prompt,
            source=source,
            translation=translation,
            critique=critique,
            witness=None,
            model="gpt-5.6-sol",
            reasoning_effort="xhigh",
            schema_sha256=sha256_file(SCHEMA),
        ),
    }


def make_shard(root: Path, name: str, records: list[dict]) -> Path:
    shard = root / name
    pages = shard / "pages"
    pages.mkdir(parents=True)
    completed = {}
    for record in records:
        path = pages / f"{record['scan_page']:04d}.json"
        path.write_text(json.dumps(record), encoding="utf-8")
        completed[str(record["scan_page"])] = {"result_sha256": sha256_file(path)}
    (shard / "state.json").write_text(json.dumps({
        "schema": MODULE.STATE_SCHEMA,
        "completed": completed,
        "failed": {},
        "stale": {},
    }), encoding="utf-8")
    return shard


class ReconcileCodexAdjudicationShardsTests(unittest.TestCase):
    def test_reconciles_exact_disjoint_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = make_inputs(4)
            second = make_inputs(5)
            second[2]["verdict"] = "pass"
            sources = [first[0], second[0]]
            translations = [first[1], second[1]]
            criticisms = [first[2], second[2]]
            source_path = root / "source.jsonl"
            translations_path = root / "translations.jsonl"
            criticisms_path = root / "criticisms.jsonl"
            witness_path = root / "witness.jsonl"
            write_jsonl(source_path, sources)
            write_jsonl(translations_path, translations)
            write_jsonl(criticisms_path, criticisms)
            write_jsonl(witness_path, [])
            records = [
                make_record(*first, None, second[0]),
                make_record(*second, first[0], None),
            ]
            report = MODULE.reconcile(
                source_path=source_path,
                translations_path=translations_path,
                criticisms_path=criticisms_path,
                witness_path=witness_path,
                shards=[make_shard(root, "a", [records[0]]), make_shard(root, "b", [records[1]])],
                output_path=root / "adjudications.jsonl",
                report_path=root / "report.json",
                schema_path=SCHEMA,
                expected_model="gpt-5.6-sol",
                expected_reasoning_effort="xhigh",
            )
            self.assertTrue(report["pass"])
            self.assertEqual(report["reconciled_pages"], 2)

    def test_override_shard_replaces_base_page_with_audited_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = make_inputs(4)
            second = make_inputs(5)
            sources = [first[0], second[0]]
            translations = [first[1], second[1]]
            criticisms = [first[2], second[2]]
            source_path = root / "source.jsonl"
            translations_path = root / "translations.jsonl"
            criticisms_path = root / "criticisms.jsonl"
            witness_path = root / "witness.jsonl"
            write_jsonl(source_path, sources)
            write_jsonl(translations_path, translations)
            write_jsonl(criticisms_path, criticisms)
            write_jsonl(witness_path, [])
            records = [
                make_record(*first, None, second[0]),
                make_record(*second, first[0], None),
            ]
            replacement = {**records[0], "final_english_text": "revised English 4"}
            output_path = root / "adjudications.jsonl"
            report = MODULE.reconcile(
                source_path=source_path,
                translations_path=translations_path,
                criticisms_path=criticisms_path,
                witness_path=witness_path,
                shards=[make_shard(root, "base", records)],
                override_shards=[make_shard(root, "override", [replacement])],
                output_path=output_path,
                report_path=root / "report.json",
                schema_path=SCHEMA,
                expected_model="gpt-5.6-sol",
                expected_reasoning_effort="xhigh",
            )
            reconciled = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(reconciled[0]["final_english_text"], "revised English 4")
            self.assertEqual(report["replaced_pages"], [4])
            self.assertNotEqual(
                report["override_shards"][0]["replacements"][0]["prior_record_sha256"],
                report["override_shards"][0]["replacements"][0]["replacement_record_sha256"],
            )

    def test_override_shard_rejects_page_absent_from_base_shards(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = make_inputs(4)
            unknown = make_inputs(6)
            source_path = root / "source.jsonl"
            translations_path = root / "translations.jsonl"
            criticisms_path = root / "criticisms.jsonl"
            witness_path = root / "witness.jsonl"
            write_jsonl(source_path, [first[0]])
            write_jsonl(translations_path, [first[1]])
            write_jsonl(criticisms_path, [first[2]])
            write_jsonl(witness_path, [])
            with self.assertRaisesRegex(RuntimeError, "does not replace base pages"):
                MODULE.reconcile(
                    source_path=source_path,
                    translations_path=translations_path,
                    criticisms_path=criticisms_path,
                    witness_path=witness_path,
                    shards=[make_shard(root, "base", [make_record(*first, None, None)])],
                    override_shards=[make_shard(root, "override", [make_record(*unknown, None, None)])],
                    output_path=root / "adjudications.jsonl",
                    report_path=root / "report.json",
                    schema_path=SCHEMA,
                    expected_model="gpt-5.6-sol",
                    expected_reasoning_effort="xhigh",
                )

    def test_load_shard_rejects_stale_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = make_inputs(4)
            shard = make_shard(root, "a", [make_record(*inputs, None, None)])
            state_path = shard / "state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["stale"] = {"4": {"reason": "prompt mismatch"}}
            state_path.write_text(json.dumps(state), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "stale pages"):
                MODULE.load_shard(shard)


if __name__ == "__main__":
    unittest.main()

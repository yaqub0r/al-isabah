from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).with_name("run_codex_volume_revision.py")
SPEC = importlib.util.spec_from_file_location("run_codex_volume_revision", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class CodexVolumeRevisionTests(unittest.TestCase):
    def test_retains_content_addressed_input_snapshots(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "translations.jsonl"
            source.write_text('{"scan_page":4}\n', encoding="utf-8")
            first = MODULE.retain_input_snapshot(source, root / "snapshots", "translations")
            first_path = Path(first["path"])
            self.assertTrue(first_path.is_file())
            self.assertEqual(MODULE.sha256_file(first_path), first["sha256"])

            source.write_text('{"scan_page":4}\n{"scan_page":5}\n', encoding="utf-8")
            second = MODULE.retain_input_snapshot(source, root / "snapshots", "translations")
            self.assertNotEqual(first["path"], second["path"])
            self.assertTrue(first_path.is_file())
            self.assertEqual(len(list((root / "snapshots").glob("translations-*.jsonl"))), 2)

    def test_rejects_unsafe_snapshot_label(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.jsonl"
            source.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Unsafe input snapshot label"):
                MODULE.retain_input_snapshot(source, Path(directory), "../outside")

    def test_reads_jsonl_from_retained_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "translations.jsonl"
            source.write_text('{"scan_page":4}\n', encoding="utf-8")

            rows, snapshot = MODULE.read_retained_jsonl(
                source, root / "snapshots", "translations"
            )
            source.write_text('{"scan_page":5}\n', encoding="utf-8")

            self.assertEqual(rows, [{"scan_page": 4}])
            self.assertEqual(
                MODULE.read_jsonl(Path(snapshot["path"])),
                [{"scan_page": 4}],
            )

    def test_volume_coverage_and_duplicate_scan_guards_fail_closed(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "duplicate scan pages"):
            MODULE.index_by_scan([{"scan_page": 4}, {"scan_page": 4}], "Translations")
        with self.assertRaisesRegex(RuntimeError, "does not cover Volume 8"):
            MODULE.require_volume8_scan_coverage({4: {"scan_page": 4}}, "Translations")
        complete = {scan: {"scan_page": scan} for scan in range(4, 495)}
        MODULE.require_volume8_scan_coverage(complete, "Translations")

    def test_prompt_translates_only_current_page(self) -> None:
        current = {"scan_page": 5, "arabic_text": "CURRENT"}
        prompt = MODULE.build_prompt(current, {"arabic_text": "BEFORE"}, {"arabic_text": "AFTER"})
        self.assertIn("scan_page must equal 5", prompt)
        self.assertIn("CURRENT PAGE (translate all of this):\nCURRENT", prompt)
        self.assertIn("PREVIOUS PAGE CONTEXT (do not translate):\nBEFORE", prompt)
        self.assertIn("NEXT PAGE CONTEXT (do not translate):\nAFTER", prompt)
        self.assertNotIn("earlier English", prompt.replace("earlier English draft", ""))
        self.assertIn("رسول الله", prompt)

    def test_aggregate_orders_page_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pages = root / "pages"
            pages.mkdir()
            (pages / "0005.json").write_text(json.dumps({"scan_page": 5}), encoding="utf-8")
            (pages / "0004.json").write_text(json.dumps({"scan_page": 4}), encoding="utf-8")
            output = root / "translations.jsonl"
            self.assertEqual(MODULE.aggregate(pages, output), 2)
            rows = MODULE.read_jsonl(output)
            self.assertEqual([row["scan_page"] for row in rows], [4, 5])

    def test_aggregate_includes_only_validated_scans(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pages = root / "pages"
            pages.mkdir()
            (pages / "0004.json").write_text(json.dumps({"scan_page": 4}), encoding="utf-8")
            (pages / "0005.json").write_text(json.dumps({"scan_page": 5}), encoding="utf-8")
            output = root / "translations.jsonl"
            self.assertEqual(MODULE.aggregate(pages, output, {5}), 1)
            self.assertEqual(MODULE.read_jsonl(output), [{"scan_page": 5}])

    def test_existing_page_requires_full_provenance(self) -> None:
        current = {
            "scan_page": 5,
            "work_id": "work",
            "volume": 8,
            "reader_page": 3917,
            "arabic_text_sha256": "source-hash",
            "arabic_text": "نص",
        }
        prompt = MODULE.build_prompt(current, None, None)
        expected = MODULE.expected_provenance(
            prompt=prompt,
            current=current,
            model="gpt-5.6-sol",
            reasoning_effort="high",
            schema_sha256="schema-hash",
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "0005.json"
            path.write_text(json.dumps({**expected, "english_text": "Translation"}), encoding="utf-8")
            self.assertEqual(MODULE.validate_existing_page(path, expected), (True, "current"))

            changed = {**expected, "model": "different-model"}
            valid, reason = MODULE.validate_existing_page(path, changed)
            self.assertFalse(valid)
            self.assertIn("model mismatch", reason)

            legacy = {**expected, "english_text": "Translation"}
            legacy.pop("prompt_sha256")
            path.write_text(json.dumps(legacy), encoding="utf-8")
            valid, reason = MODULE.validate_existing_page(path, expected)
            self.assertFalse(valid)
            self.assertIn("prompt_sha256 mismatch", reason)

    def test_existing_page_must_match_checkpointed_result_hash(self) -> None:
        expected = {"scan_page": 5, "prompt_sha256": "prompt"}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "0005.json"
            path.write_text(json.dumps({**expected, "english_text": "original"}), encoding="utf-8")
            checkpoint_sha = MODULE.sha256_file(path)
            self.assertEqual(MODULE.validate_existing_page(path, expected, checkpoint_sha), (True, "current"))
            path.write_text(json.dumps({**expected, "english_text": "edited"}), encoding="utf-8")
            valid, reason = MODULE.validate_existing_page(path, expected, checkpoint_sha)
            self.assertFalse(valid)
            self.assertEqual(reason, "result_sha256 mismatch with checkpoint state")

    @mock.patch.object(MODULE.subprocess, "run")
    def test_run_codex_attaches_witness_images(self, run: mock.Mock) -> None:
        run.return_value = MODULE.subprocess.CompletedProcess([], 0, "", "")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            MODULE.run_codex(
                codex_path=root / "codex.exe",
                work_dir=root,
                schema_path=root / "schema.json",
                prompt="prompt",
                result_path=root / "result.json",
                model="gpt-5.6-sol",
                reasoning_effort="high",
                timeout_seconds=10,
                image_paths=[root / "witness-1.png", root / "witness-2.png"],
            )
        command = run.call_args.args[0]
        self.assertEqual(command.count("--image"), 2)
        self.assertIn("witness-1.png", " ".join(command))


if __name__ == "__main__":
    unittest.main()

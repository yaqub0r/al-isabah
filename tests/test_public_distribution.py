import importlib.util
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


BUILD = load_module("build_public_distribution", ROOT / "scripts" / "build_public_distribution.py")
VALIDATE = load_module("validate_public_distribution", ROOT / "scripts" / "validate_public_distribution.py")
COMMIT = "abd81f7eab94158be9e957d4b6f80751f1cc19e8"
GENERATED_AT = "2026-08-14T16:22:30Z"


class PublicDistributionTests(unittest.TestCase):
    def test_generated_timestamp_is_normalized_to_utc_z_form(self):
        self.assertEqual(
            BUILD.utc_timestamp("2026-08-14T14:22:30-02:00"),
            "2026-08-14T16:22:30Z",
        )

    def test_packet_volume_uses_the_dominant_source_volume(self):
        packet = {
            "packetId": "volume-8-test",
            "assignment": {},
            "entries": [
                {"source": {"locations": [{"volume": 8, "page": 1}]}},
                {"source": {"locations": [{"volume": 8, "page": 2}]}},
                {"source": {"locations": [{"volume": 7, "page": 600}]}},
            ],
        }
        self.assertEqual(BUILD.packet_volume(packet), 8)

    def test_real_volume_one_packet_is_complete_and_preserves_duplicate_printed_number(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "distribution"
            manifest = BUILD.build(output, COMMIT, GENERATED_AT)
            self.assertEqual(manifest["counts"]["entries"], 1537)
            self.assertEqual(manifest["schemaVersion"], "2.0.0")
            self.assertEqual(
                manifest["rights"]["license"]["spdx"], "CC-BY-NC-SA-4.0"
            )
            self.assertIs(manifest["rights"]["softwareLicenseGranted"], False)
            self.assertTrue(manifest["rights"]["attribution"])
            self.assertTrue(manifest["rights"]["excludedMaterial"])
            self.assertTrue(all("path" not in packet for packet in manifest["packets"]))
            self.assertEqual(manifest["duplicatePrintedEntryNumbers"], [{
                "printedEntryNumber": 1311,
                "recordIds": ["openiti-5835c183-unit-001310", "openiti-5835c183-unit-001311"],
            }])
            self.assertEqual(VALIDATE.validate(output), [])

            first_record = json.loads(
                (output / "records" / "volume-01.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()[0]
            )
            self.assertEqual(set(first_record["policy"]), {"bindingSha256"})
            self.assertFalse(
                {"repository", "path", "lineStart", "lineEnd"}
                & set(first_record["source"])
            )

    def test_archive_is_deterministic(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "distribution"
            BUILD.build(output, COMMIT, GENERATED_AT)
            first = root / "first.zip"
            second = root / "second.zip"
            BUILD.package(output, first)
            BUILD.package(output, second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with zipfile.ZipFile(first) as archive:
                self.assertEqual(sorted(archive.namelist()), ["manifest.json", "records/volume-01.jsonl"])

    def test_validator_rejects_identity_collapse(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "distribution"
            BUILD.build(output, COMMIT, GENERATED_AT)
            shard = output / "records" / "volume-01.jsonl"
            records = shard.read_text(encoding="utf-8").splitlines()
            duplicate = json.loads(records[1310])
            duplicate["id"] = json.loads(records[1309])["id"]
            records[1310] = json.dumps(duplicate, ensure_ascii=False)
            shard.write_text("\n".join(records) + "\n", encoding="utf-8")
            errors = VALIDATE.validate(output)
            self.assertTrue(any("hash mismatch" in error for error in errors))
            self.assertTrue(any("duplicate stable record ID" in error for error in errors))

    def test_validator_rejects_a_noncanonical_timestamp(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "distribution"
            BUILD.build(output, COMMIT, GENERATED_AT)
            manifest_path = output / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["generatedAt"] = "2026-08-14T16:22:30+00:00"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            self.assertTrue(
                any("UTC Z form" in error for error in VALIDATE.validate(output))
            )

    def test_validator_rejects_private_operational_fields(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "distribution"
            BUILD.build(output, COMMIT, GENERATED_AT)
            manifest_path = output / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["rights"]["credential"] = "not-a-real-secret"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            self.assertTrue(
                any("private field" in error for error in VALIDATE.validate(output))
            )


if __name__ == "__main__":
    unittest.main()

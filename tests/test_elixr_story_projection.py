import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


sys.path.insert(0, str(ROOT / "scripts"))
BUILD = load_module("build_elixr_story_projection", ROOT / "scripts" / "build_elixr_story_projection.py")
VALIDATE = load_module("validate_elixr_story_projection", ROOT / "scripts" / "validate_elixr_story_projection.py")
ADMISSION_PATH = ROOT / "profiles" / "story-projections" / "khadijah.v1.json"
PROJECTION_PATH = ROOT / "content" / "story-projections" / "khadijah.elixr-approved-story-projection.v1.json"
ADMISSION_SCHEMA = ROOT / "schemas" / "elixr-story-source-admission.v1.schema.json"
PROJECTION_SCHEMA = ROOT / "schemas" / "elixr-approved-story-projection.v1.schema.json"


class ElixrStoryProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.admission = json.loads(ADMISSION_PATH.read_text(encoding="utf-8"))
        cls.projection = json.loads(PROJECTION_PATH.read_text(encoding="utf-8"))

    def write_projection(self, root: Path, value: dict) -> Path:
        path = root / "projection.json"
        path.write_bytes(BUILD.canonical_json(value))
        return path

    def assert_closed_objects(self, value):
        if isinstance(value, dict):
            if value.get("type") == "object":
                self.assertIs(value.get("additionalProperties"), False, value.get("title", value))
            for child in value.values():
                self.assert_closed_objects(child)
        elif isinstance(value, list):
            for child in value:
                self.assert_closed_objects(child)

    def test_current_admission_and_projection_are_exact_and_deterministic(self):
        self.assertEqual(BUILD.admission_errors(self.admission), [])
        self.assertEqual(VALIDATE.validate(PROJECTION_PATH), [])
        self.assertEqual(BUILD.canonical_json(BUILD.build()), PROJECTION_PATH.read_bytes())
        self.assertEqual(
            self.projection["integrity"]["ambiguitySetSha256"],
            BUILD.sha256_bytes(BUILD.canonical_json(self.projection["ambiguitySets"])),
        )

    def test_schemas_are_closed_at_every_object_layer(self):
        for schema in (ADMISSION_SCHEMA, PROJECTION_SCHEMA):
            parsed = json.loads(schema.read_text(encoding="utf-8"))
            self.assert_closed_objects(parsed)

    def test_all_four_public_reports_are_admitted_without_flattening_story_use(self):
        decisions = {item["recordId"]: item["decision"] for item in self.admission["candidateRecords"]}
        self.assertEqual(decisions, {record_id: "admitted" for record_id in BUILD.EXPECTED_CANDIDATES})
        self.assertEqual(
            [item["recordId"] for item in self.projection["sourceRecords"]],
            list(BUILD.EXPECTED_CANDIDATES),
        )
        self.assertEqual(self.projection["review"]["machinePassed"], 1)
        self.assertEqual(self.projection["review"]["needsAttention"], 3)
        self.assertEqual(self.projection["review"]["humanReviewEffect"], "per_record_metadata")
        self.assertEqual(self.projection["review"]["releaseClassEffect"], "none")

    def test_public_locators_and_source_status_are_preserved(self):
        records = {item["recordId"]: item for item in self.projection["sourceRecords"]}
        self.assertEqual((records["openiti-5835c183-unit-000097"]["volume"], records["openiti-5835c183-unit-000097"]["pages"]), (1, [50]))
        self.assertEqual((records["openiti-5835c183-unit-000171"]["volume"], records["openiti-5835c183-unit-000171"]["pages"]), (1, [76]))
        self.assertEqual((records["openiti-5835c183-unit-000399"]["volume"], records["openiti-5835c183-unit-000399"]["pages"]), (1, [175]))
        self.assertEqual((records["openiti-5835c183-unit-000795"]["volume"], records["openiti-5835c183-unit-000795"]["pages"]), (1, [351, 352, 353]))
        self.assertEqual(records["openiti-5835c183-unit-000171"]["machineAssessment"], "passed")
        self.assertEqual(records["openiti-5835c183-unit-000171"]["uncertaintyCodes"], [])
        self.assertTrue(all(records[record_id]["machineAssessment"] == "needs_attention" for record_id in records if record_id != "openiti-5835c183-unit-000171"))

    def test_claims_separate_report_existence_critical_status_strength_and_story_use(self):
        claims = {item["id"]: item for item in self.projection["claims"]["attested"]}
        self.assertEqual(set(claims), BUILD.EXPECTED_CLAIM_IDS)
        self.assertEqual(self.projection["claims"]["inferred"], [])
        self.assertTrue(all(item["sourceReportExistence"] == "attested_in_source" for item in claims.values()))

        factual = claims["isabah-claim-al-aswad-nephew-of-khadijah-v1"]
        self.assertEqual(factual["storyUseTier"], "factual_spine")
        self.assertEqual(factual["sourceCriticalStatus"], "unqualified")
        self.assertEqual(factual["transmissionStrength"], "source_supported")
        self.assertFalse(factual["storyAttributionRequired"])

        genealogy = claims["isabah-claim-asad-nephew-of-khadijah-v1"]
        self.assertEqual(genealogy["sourceCriticalStatus"], "disputed")
        self.assertEqual(genealogy["transmissionStrength"], "criticized")
        self.assertEqual(genealogy["storyUseTier"], "attributed_disputed_report")
        self.assertIn("genealogical-identity", genealogy["factualAmbiguityCodes"])

        rejected = claims["isabah-claim-khadijah-mother-of-ibrahim-v1"]
        self.assertEqual(rejected["sourceCriticalStatus"], "rejected")
        self.assertEqual(rejected["transmissionStrength"], "not_assessed")
        self.assertEqual(rejected["storyUseTier"], "attributed_disputed_report")
        self.assertTrue(rejected["storyAttributionRequired"])

    def test_weak_transmission_alone_does_not_block_story_use(self):
        admission = copy.deepcopy(self.admission)
        migration = next(item for item in admission["attestedClaims"] if item["id"] == "isabah-claim-al-aswad-migration-one-v1")
        migration["transmissionStrength"] = "weak"
        self.assertEqual(BUILD.admission_errors(admission), [])

        migration["storyUseTier"] = "not_suitable_for_story"
        migration["rationaleCodes"] = ["weak-transmission"]
        errors = BUILD.admission_errors(admission)
        self.assertTrue(any("category=unsupported-story-exclusion" in error for error in errors), errors)

    def test_competing_reports_remain_parallel_unresolved_assertions(self):
        ambiguities = {item["id"]: item for item in self.projection["ambiguitySets"]}
        maternal = ambiguities["isabah-ambiguity-ibrahim-maternal-attribution-v1"]
        self.assertEqual(maternal["presentationMode"], "parallel_attributed_reports")
        self.assertEqual(maternal["resolutionStatus"], "unresolved")
        self.assertEqual(set(maternal["memberClaimIds"]), {
            "isabah-claim-khadijah-mother-of-ibrahim-v1",
            "isabah-claim-mariya-mother-of-ibrahim-v1",
        })
        journeys = ambiguities["isabah-ambiguity-bahira-journey-context-v1"]
        self.assertEqual(journeys["presentationMode"], "parallel_attributed_reports")
        self.assertEqual(set(journeys["memberClaimIds"]), {
            "isabah-claim-abu-talib-commercial-journey-v1",
            "isabah-claim-khadijah-commercial-journey-v1",
        })
        genealogy = ambiguities["isabah-ambiguity-asad-genealogy-v1"]
        self.assertEqual(genealogy["presentationMode"], "qualified_ambiguity_context")

    def test_no_prose_dialogue_precise_chronology_or_normative_claims(self):
        governed_assertions = {
            key: self.projection[key]
            for key in ("persons", "events", "relationships", "claims", "ambiguitySets")
        }
        rendered = json.dumps(governed_assertions, sort_keys=True).casefold()
        for forbidden in ("dialogue", "quotation", "excerpt", "normative", "obligation", "legal_ruling", "fatwa"):
            self.assertNotIn(forbidden, rendered)
        for event in self.projection["events"]:
            self.assertIn(event["temporalStatus"], {"unstated", "relative_only"})
            self.assertNotIn("date", event)
            self.assertNotIn("location", event)
            self.assertNotIn("causalSequence", event)

    def test_recursive_boundary_rejects_prohibited_payloads_without_echoing_values(self):
        cases = [
            {"english": "synthetic body"},
            {"arabic": "synthetic body"},
            {"quote": "synthetic quotation"},
            {"excerpt": "synthetic excerpt"},
            {"dialogue": "synthetic dialogue"},
            {"draft": "synthetic draft"},
            {"critique": "synthetic critique"},
            {"modelTrace": "synthetic trace"},
            {"witnessMaterial": "synthetic witness"},
            {"privateNote": "synthetic note"},
            {"filesystemPath": "C:" + "\\" + "synthetic" + "\\" + "file"},
            {"credential": "synthetic-credential-value"},
        ]
        for payload in cases:
            value = copy.deepcopy(self.projection)
            value["claims"]["attested"][0]["synthetic"] = {"deeper": payload}
            errors = BUILD.projection_boundary_errors(value)
            rendered = "\n".join(errors)
            self.assertTrue(errors, payload)
            for rejected in payload.values():
                self.assertNotIn(rejected, rendered)

    def test_unknown_major_unknown_fields_and_hash_drift_fail_closed(self):
        mutations = [
            (lambda value: value.__setitem__("schemaVersion", "2.0.0"), "contract-mismatch"),
            (lambda value: value["claims"]["attested"][0].__setitem__("unexpected", "synthetic"), "unknown-field"),
            (lambda value: value["sourceRecords"][0].__setitem__("recordSha256", "0" * 64), "deterministic-projection-mismatch"),
            (lambda value: value["sourceRelease"].__setitem__("assetSha256", "0" * 64), "deterministic-projection-mismatch"),
        ]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for mutate, category in mutations:
                value = copy.deepcopy(self.projection)
                mutate(value)
                errors = VALIDATE.validate(self.write_projection(root, value))
                self.assertTrue(any(f"category={category}" in error for error in errors), errors)

    def test_mutable_release_unknown_sources_and_supersession_fail_closed(self):
        mutations = [
            (lambda value: value["sourceRelease"].__setitem__("immutable", False), "mutable-source-release"),
            (lambda value: value["claims"]["attested"][0].__setitem__("sourceRecordIds", ["openiti-5835c183-unit-999999"]), "unadmitted-source"),
            (lambda value: value["claims"]["attested"][0].__setitem__("status", "superseded"), "unavailable-or-superseded-assertion"),
            (lambda value: value["lifecycle"].__setitem__("status", "superseded"), "unavailable-or-superseded-projection"),
        ]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for mutate, category in mutations:
                value = copy.deepcopy(self.projection)
                mutate(value)
                errors = VALIDATE.validate(self.write_projection(root, value))
                self.assertTrue(any(f"category={category}" in error for error in errors), errors)

    def test_disputed_material_cannot_be_silently_promoted_or_deattributed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for mutate, category in (
                (
                    lambda value: value["claims"]["attested"][3].__setitem__("storyUseTier", "factual_spine"),
                    "invalid-factual-spine",
                ),
                (
                    lambda value: value["claims"]["attested"][3].__setitem__("storyAttributionRequired", False),
                    "invalid-attributed-disputed-report",
                ),
            ):
                value = copy.deepcopy(self.projection)
                mutate(value)
                errors = VALIDATE.validate(self.write_projection(root, value))
                self.assertTrue(any(f"category={category}" in error for error in errors), errors)

    def test_removing_an_alternative_or_resolving_an_ambiguity_fails_closed(self):
        admission = copy.deepcopy(self.admission)
        admission["attestedClaims"] = [
            claim for claim in admission["attestedClaims"]
            if claim["id"] != "isabah-claim-mariya-mother-of-ibrahim-v1"
        ]
        errors = BUILD.admission_errors(admission)
        self.assertTrue(any("category=claim-inventory-mismatch" in error for error in errors), errors)
        self.assertTrue(any("category=ambiguity-membership-mismatch" in error for error in errors), errors)

        projection = copy.deepcopy(self.projection)
        projection["ambiguitySets"][1]["resolutionStatus"] = "resolved"
        with tempfile.TemporaryDirectory() as temp:
            errors = VALIDATE.validate(self.write_projection(Path(temp), projection))
        self.assertTrue(any("category=ambiguity-presentation-mismatch" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()

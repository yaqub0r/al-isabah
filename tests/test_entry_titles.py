import copy
import hashlib
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_entry_titles", ROOT / "scripts" / "validate_entry_titles.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)
SCHEMA_SPEC = importlib.util.spec_from_file_location(
    "schema_validation", ROOT / "scripts" / "schema_validation.py"
)
SCHEMA_MODULE = importlib.util.module_from_spec(SCHEMA_SPEC)
assert SCHEMA_SPEC.loader is not None
SCHEMA_SPEC.loader.exec_module(SCHEMA_MODULE)


class EntryTitleContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = MODULE.load()

    def test_active_profile_is_valid(self) -> None:
        self.assertEqual(MODULE.validate(self.profile), [])

    def test_covers_reported_entries(self) -> None:
        numbers = {item["sourceEntryNumber"] for item in self.profile["decisions"]}
        historical = {
            11426, 11427, 11430, 11436, 11439, 11441, 11442, 11443,
            11445, 11446, 11449, 11451, 11454, 11458, 11459, 11473,
            11474, 11476,
        }
        expected = historical | set(range(1538, 9484))
        expected.remove(7052)
        self.assertEqual(numbers, expected)
        self.assertEqual(len(self.profile["decisions"]), 7965)

    def test_successor_preserves_all_previous_decisions(self) -> None:
        previous = MODULE.load(ROOT / "profiles" / "entry-title-decisions.v8.json")
        split = len(previous["decisions"])
        self.assertEqual(self.profile["decisions"][:split], previous["decisions"])
        added = self.profile["decisions"][split:]
        self.assertEqual(
            [item["sourceUnitId"] for item in added],
            [f"openiti-5835c183-unit-{ordinal:06d}" for ordinal in range(7763, 9485)],
        )
        self.assertTrue(all("editorialSupply" not in item for item in added))
        self.assertTrue(all("sourceRawSha256" in item for item in added))

    def test_volume4_title_only_decision_is_exact_and_schema_valid(self) -> None:
        title_only = MODULE.decision_for_entry(self.profile, 5041)
        self.assertEqual(
            title_only["title"],
            {"ar": "عبد الله الأنصاري", "en": "ʿAbd Allāh al-Anṣārī"},
        )
        self.assertEqual(title_only["bodyOpeningKind"], "none")
        self.assertEqual(title_only["bodyOpening"], {"ar": "", "en": ""})
        schema = json.loads(
            (ROOT / "schemas" / "entry-title-decisions.v3.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(SCHEMA_MODULE.validate_schema_instance(self.profile, schema), [])

    def test_literal_zay_prefixes_remain_visible_without_an_assigned_role(self) -> None:
        for number in (3908, 4021, 4076, 4162, 4247):
            with self.subTest(number=number):
                decision = MODULE.decision_for_entry(self.profile, number)
                self.assertTrue(decision["title"]["ar"].startswith("ز "))
                self.assertTrue(decision["title"]["en"].startswith("“ز” "))
                self.assertNotIn("editorialSupply", decision)

    def test_new_body_openings_preserve_attested_formula_in_arabic(self) -> None:
        formula = "صلى الله عليه وسلم"
        covered = 0
        for decision in self.profile["decisions"]:
            if not 3781 <= decision["sourceEntryNumber"] <= 4525:
                continue
            for field in ("title", "bodyOpening"):
                arabic = decision[field]["ar"]
                english = decision[field]["en"]
                self.assertEqual(english.count(formula), arabic.count(formula))
                self.assertNotIn("ﷺ", english)
                covered += arabic.count(formula)
        self.assertEqual(covered, 19)

    def test_literal_damaged_heads_keep_body_and_attention_state(self) -> None:
        cases = {
            3052: ("الم بن وابصة", "“الم” ibn Wābiṣah"),
            3317: ("سفين بن عبد الله", "“سفين” ibn ʿAbd Allāh"),
        }
        for number, (arabic_title, english_title) in cases.items():
            with self.subTest(number=number):
                decision = MODULE.decision_for_entry(self.profile, number)
                self.assertEqual(decision["title"], {"ar": arabic_title, "en": english_title})
                self.assertNotIn("editorialSupply", decision)
                arabic = arabic_title + " " + decision["bodyOpening"]["ar"]
                english = english_title + ". " + decision["bodyOpening"]["en"]
                entry = {
                    "sourceOrdinal": number,
                    "source": {"headingArabic": arabic, "arabic": arabic},
                    "adjudication": {"english": english},
                    "unresolved": [{"description": "Source spelling remains unresolved."}],
                }
                title, body_ar, body_en = MODULE.governed_title_and_body(
                    entry, decision, render_arabic=lambda value: value
                )
                self.assertEqual(title["state"], "needs_attention")
                self.assertEqual(body_ar, decision["bodyOpening"]["ar"])
                self.assertEqual(body_en, decision["bodyOpening"]["en"])

    def test_ordinary_decision_cannot_silently_repair_source_letters(self) -> None:
        for number, restored in ((3052, "سالم بن وابصة"), (3317, "سفيان بن عبد الله")):
            with self.subTest(number=number):
                decision = copy.deepcopy(MODULE.decision_for_entry(self.profile, number))
                literal = decision["title"]["ar"]
                decision["title"]["ar"] = restored
                source = literal + " " + decision["bodyOpening"]["ar"]
                entry = {
                    "sourceOrdinal": number,
                    "source": {"headingArabic": source, "arabic": source},
                    "adjudication": {"english": decision["title"]["en"]},
                }
                with self.assertRaisesRegex(ValueError, "pinned Arabic source prefix"):
                    MODULE.governed_title_and_body(
                        entry, decision, render_arabic=lambda value: value
                    )

    def test_positive_reference_matches_the_pinned_source_lineage(self) -> None:
        decision = next(
            item
            for item in self.profile["decisions"]
            if item["sourceEntryNumber"] == 11426
        )
        self.assertEqual(
            decision["bodyOpening"],
            {
                "ar": "بن قرط بن سلمة بن قشير بن كعب بن بيعة بن عامر بن صعصعة",
                "en": "ibn Qurt ibn Salama ibn Qushayr ibn Ka'b ibn Bi'a ibn Amir ibn Sa'sa'a",
            },
        )

    def test_rejects_duplicate_entry_decision(self) -> None:
        profile = copy.deepcopy(self.profile)
        profile["decisions"].append(copy.deepcopy(profile["decisions"][0]))
        errors = MODULE.validate(profile)
        self.assertTrue(any("duplicate sourceEntryNumber" in error for error in errors), errors)

    def test_rejects_relationship_prose_in_title(self) -> None:
        profile = copy.deepcopy(self.profile)
        profile["decisions"][0]["title"]["en"] = "Name, the wife of Person"
        errors = MODULE.validate(profile)
        self.assertTrue(any("belongs in the body" in error for error in errors), errors)

    def test_rejects_missing_bilingual_body_opening(self) -> None:
        profile = copy.deepcopy(self.profile)
        profile["decisions"][0]["bodyOpening"]["ar"] = ""
        errors = MODULE.validate(profile)
        self.assertTrue(any("bodyOpening.ar" in error for error in errors), errors)

    def test_exact_decided_title_is_removed_and_body_opening_is_retained(self) -> None:
        self.assertEqual(
            MODULE.body_after_decided_title(
                "Ḥāzim, without a lineage attribution.",
                "Ḥāzim",
                "without a lineage attribution",
                location="synthetic English body",
            ),
            "without a lineage attribution.",
        )

    def test_rejects_title_split_that_loses_the_decided_body_opening(self) -> None:
        with self.assertRaisesRegex(ValueError, "not retained"):
            MODULE.body_after_decided_title(
                "Ḥāzim, narrated a report.",
                "Ḥāzim",
                "without a lineage attribution",
                location="synthetic English body",
            )

    def test_openiti_milestones_are_removed_only_at_the_source_heading_boundary(self) -> None:
        self.assertEqual(
            MODULE.clean_source_heading_boundary(
                "ms0504 الحكم بن ms0542 مرة قال PageV03P210"
            ),
            "الحكم بن مرة قال",
        )
        self.assertEqual(
            MODULE.clean_source_heading_boundary(
                "اسم xms0542 msnote xPageV03P210 PageV03P210x"
            ),
            "اسم xms0542 msnote xPageV03P210 PageV03P210x",
        )

    def test_rejects_openiti_milestone_controls_in_display_fields(self) -> None:
        for language in ("ar", "en"):
            for control in ("ms1115", "PageV03P210"):
                with self.subTest(language=language, control=control):
                    profile = copy.deepcopy(self.profile)
                    profile["decisions"][-1]["bodyOpening"][language] += f" {control}"
                    errors = MODULE.validate(profile)
                    self.assertTrue(
                        any(
                            "milestone controls are not display text" in error
                            for error in errors
                        ),
                        errors,
                    )

    def test_governed_split_accepts_embedded_marker_without_losing_body_text(self) -> None:
        entry = {
            "sourceOrdinal": 1791,
            "source": {
                "headingArabic": "الحكم بن ms0542 مرة قال بن منده",
                "arabic": "الحكم بن مرة قال بن منده خبر",
            },
            "adjudication": {
                "english": "Al-Ḥakam ibn Murra. Ibn Mandah said: Report."
            },
            "unresolved": [],
        }
        decision = {
            "title": {"ar": "الحكم بن مرة", "en": "Al-Ḥakam ibn Murra"},
            "bodyOpening": {"ar": "قال بن منده", "en": "Ibn Mandah said"},
        }
        title, arabic, english = MODULE.governed_title_and_body(
            entry,
            decision,
            render_arabic=lambda value: value.strip(),
        )
        self.assertEqual(title["arabic"], "الحكم بن مرة")
        self.assertEqual(arabic, "قال بن منده خبر")
        self.assertEqual(english, "Ibn Mandah said: Report.")

    def test_witness_bound_supplies_are_transparent_and_scope_equal(self) -> None:
        expected = {
            2784: {
                "title": {
                    "ar": "[الزبرقان] بن بدر",
                    "en": "[Al-Zibriqān] ibn Badr",
                },
                "scope": {
                    "kind": "personal-name",
                    "equality": "reviewed-bilingual-equivalent-subject",
                    "ar": "الزبرقان بن بدر",
                    "en": "Al-Zibriqān ibn Badr",
                },
                "prefix": {"ar": "بن بدر", "en": "Ibn Badr"},
            },
            2880: {
                "title": {
                    "ar": "[زيد] بن أبي أوفى",
                    "en": "[Zayd] ibn Abī Awfā",
                },
                "scope": {
                    "kind": "personal-name",
                    "equality": "reviewed-bilingual-equivalent-subject",
                    "ar": "زيد بن أبي أوفى",
                    "en": "Zayd ibn Abī Awfā",
                },
                "prefix": {"ar": "بن أبي أوفى", "en": "Ibn Abī Awfā"},
            },
        }
        for number, values in expected.items():
            decision = MODULE.decision_for_entry(self.profile, number)
            self.assertEqual(decision["title"], values["title"])
            self.assertEqual(
                decision["editorialSupply"]["semanticScope"], values["scope"]
            )
            self.assertEqual(MODULE.source_prefixes(decision), values["prefix"])
            self.assertEqual(
                decision["editorialSupply"]["witness"]["relation"],
                "same-work-alternative-edition",
            )

    def test_rejects_drifted_editorial_supply_source_prefix(self) -> None:
        profile = copy.deepcopy(self.profile)
        decision = MODULE.decision_for_entry(profile, 2784)
        decision["editorialSupply"]["sourcePrefix"]["ar"]["text"] += " "
        errors = MODULE.validate(profile)
        self.assertTrue(any("sourcePrefix.ar" in error for error in errors), errors)

    def test_rejects_drifted_witness_passage(self) -> None:
        profile = copy.deepcopy(self.profile)
        decision = MODULE.decision_for_entry(profile, 2784)
        decision["editorialSupply"]["witness"]["passage"]["text"] += " مختلف"
        errors = MODULE.validate(profile)
        self.assertTrue(any("witness.passage" in error for error in errors), errors)

    def test_rejects_drifted_witness_evidence_hash(self) -> None:
        profile = copy.deepcopy(self.profile)
        decision = MODULE.decision_for_entry(profile, 2880)
        decision["editorialSupply"]["witness"]["evidence"]["sha256"] = "0" * 64
        errors = MODULE.validate(profile)
        self.assertTrue(any("witness.bindingSha256" in error for error in errors), errors)

    def test_rejects_unbracketed_editorial_supply(self) -> None:
        profile = copy.deepcopy(self.profile)
        decision = MODULE.decision_for_entry(profile, 2880)
        decision["title"]["en"] = "Zayd ibn Abī Awfā"
        errors = MODULE.validate(profile)
        self.assertTrue(any("transparently bracket" in error for error in errors), errors)

    def test_entry_outside_governed_ranges_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "lacks a governed bilingual"):
            MODULE.decision_for_entry(self.profile, 9484)

    def test_repeated_printed_numbers_resolve_only_by_source_unit(self) -> None:
        for number, ordinals in ((6986, (6986, 6987)), (7760, (7760, 7761))):
            with self.subTest(number=number):
                with self.assertRaisesRegex(ValueError, "lacks a governed bilingual"):
                    MODULE.decision_for_entry(self.profile, number)
                decisions = [
                    MODULE.decision_for_entry(
                        self.profile,
                        number,
                        f"openiti-5835c183-unit-{ordinal:06d}",
                    )
                    for ordinal in ordinals
                ]
                self.assertEqual([item["sourceEntryNumber"] for item in decisions], [number, number])
                self.assertEqual(len({item["sourceRawSha256"] for item in decisions}), 2)

    def test_volume5_title_only_decision_is_source_bound(self) -> None:
        decision = MODULE.decision_for_entry(
            self.profile, 7613, "openiti-5835c183-unit-007613"
        )
        self.assertEqual(decision["title"]["ar"], "مالك بن الجلاح")
        self.assertEqual(decision["bodyOpeningKind"], "none")
        self.assertEqual(decision["bodyOpening"], {"ar": "", "en": ""})
        self.assertEqual(
            decision["sourceRawSha256"],
            "fa3cc474d223425554535518331a8e9d7406089e64ea728453049bdf784c4c1b",
        )

    def test_volume6_title_only_decisions_are_source_bound(self) -> None:
        for ordinal in (8282, 8357, 9010):
            with self.subTest(ordinal=ordinal):
                decision = MODULE.decision_for_entry(
                    self.profile,
                    ordinal - 1,
                    f"openiti-5835c183-unit-{ordinal:06d}",
                )
                self.assertEqual(decision["bodyOpeningKind"], "none")
                self.assertEqual(decision["bodyOpening"], {"ar": "", "en": ""})


if __name__ == "__main__":
    unittest.main()

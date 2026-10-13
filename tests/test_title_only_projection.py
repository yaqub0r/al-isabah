import copy
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


PROJECT = load_module(
    "project_packet_set_public_proposal",
    ROOT / "scripts" / "project_packet_set_public_proposal.py",
)
VALIDATE = load_module("validate_public_proposal", ROOT / "scripts" / "validate_public_proposal.py")


class TitleOnlyProjectionTests(unittest.TestCase):
    def test_title_and_inherited_heading_formulas_are_declared(self) -> None:
        formula = "صلى الله عليه وسلم"
        record = {
            "id": "synthetic-unit-007274",
            "title": {
                "arabic": f"القاسم بن رسول الله {formula}",
                "english": f"al-Qāsim, son of the Messenger of God {formula}",
            },
            "arabic": "",
            "english": "",
            "precedingMaterial": [
                {
                    "id": (
                        "continued-before-unit-007274-from-"
                        "synthetic-structural-heading"
                    ),
                    "kind": "continued_structural_heading",
                    "heading": {
                        "arabic": f"من لم يره {formula}",
                        "english": f"Those who did not see him {formula}",
                    },
                    "arabic": "",
                    "english": "",
                }
            ],
        }
        packet_formulas = [
            {
                "observedArabic": formula,
                "semanticClass": "prophetic_blessing",
                "targetRealization": formula,
            }
        ]

        record["formulas"] = PROJECT.projected_formula_inventory(
            record, packet_formulas
        )

        self.assertEqual(
            [item["formulaId"] for item in record["formulas"]],
            [
                (
                    "continued-before-unit-007274-from-"
                    "synthetic-structural-heading-headingArabic-formula-001"
                ),
                "synthetic-unit-007274-titleArabic-formula-001",
            ],
        )
        self.assertEqual(
            VALIDATE.public_formula_errors(record, "$.record"),
            [],
        )
        title_formulas = VALIDATE.formulas_for_scope(
            record["formulas"], record["id"], "titleArabic"
        )
        self.assertEqual(
            VALIDATE.public_english_errors(
                record["title"]["english"],
                title_formulas,
                record["id"],
                "$.record.title.english",
            ),
            [],
        )

    def test_exact_title_only_record_and_public_binding(self) -> None:
        arabic = "عبد الله الأنصاري"
        english = "ʿAbd Allāh al-Anṣārī"
        source_hash = hashlib.sha256(arabic.encode("utf-8")).hexdigest()
        decision = {
            "sourceEntryNumber": 5041,
            "role": "positive-reference",
            "title": {"ar": arabic, "en": english},
            "bodyOpeningKind": "none",
            "bodyOpening": {"ar": "", "en": ""},
            "sourceUnitSha256": source_hash,
        }
        packet = {
            "packetId": "synthetic-title-only",
            "workId": "ibn-hajar-al-isabah",
            "authority": {
                "commit": "0" * 40,
                "sha256": "1" * 64,
                "license": {},
            },
            "policy": {"bindingSha256": "2" * 64},
        }
        entry = {
            "sourceOrdinal": 5041,
            "sourceEntryNumber": 5041,
            "sourceUnitId": "synthetic-unit-005041",
            "canonicalEntryId": None,
            "source": {
                "headingArabic": arabic,
                "arabic": arabic,
                "rawSha256": source_hash,
                "precedingSegments": [],
                "locations": [{"volume": 4, "page": 1}],
            },
            "precedingTranslations": [],
            "adjudication": {"english": english},
            "names": {
                "candidates": [
                    {"observedArabic": arabic, "proposedEnglish": english}
                ]
            },
            "unresolved": [],
            "humanReview": {"status": "unreviewed"},
        }
        record = PROJECT.public_record(packet, entry, [], decision)
        self.assertEqual(record["bodyState"], "title-only")
        self.assertEqual((record["arabic"], record["english"]), ("", ""))
        self.assertEqual(record["title"]["arabic"], arabic)

        profile = {
            "schemaVersion": "1.2.0",
            "contractId": "al-isabah-entry-title-structure",
            "workId": "ibn-hajar-al-isabah",
            "status": "active",
            "sourceAuthority": {
                "repository": "https://example.org/source",
                "commit": "0" * 40,
                "artifact": "source.txt",
                "license": "approved",
            },
            "decisions": [decision],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profiles = root / "profiles"
            profiles.mkdir()
            path = profiles / "entry-title-decisions.v999.json"
            path.write_text(json.dumps(profile, ensure_ascii=False), encoding="utf-8")
            proposal = {
                "schemaVersion": "1.3.0",
                "proposalId": "issue-9999-public-proposal-v1",
                "entryTitleDecisions": {
                    "profileId": "entry-title-decisions.v999",
                    "profileSha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "coveredRecordCount": 1,
                },
                "records": [copy.deepcopy(record)],
            }
            self.assertTrue(
                any(
                    "title-profile-mismatch" in error
                    for error in VALIDATE._title_decision_errors(proposal)
                )
            )
            with patch.object(VALIDATE, "ROOT", root), patch.dict(
                VALIDATE.PINNED_TITLE_PROFILE_BINDINGS,
                {
                    ("1.3.0", "issue-9999-public-proposal-v1"): {
                        "profileId": "entry-title-decisions.v999",
                        "profileSha256": proposal["entryTitleDecisions"]["profileSha256"],
                    }
                },
            ):
                self.assertEqual(VALIDATE._title_decision_errors(proposal), [])
                wrong_body = copy.deepcopy(proposal)
                wrong_body["records"][0]["english"] = "invented biography"
                self.assertTrue(
                    any("title-only-body-mismatch" in error for error in VALIDATE._title_decision_errors(wrong_body))
                )
                wrong_hash = copy.deepcopy(proposal)
                wrong_hash["records"][0]["source"]["exactTextSha256"] = "0" * 64
                self.assertTrue(
                    any("title-only-body-mismatch" in error for error in VALIDATE._title_decision_errors(wrong_hash))
                )
                missing_marker = copy.deepcopy(proposal)
                del missing_marker["records"][0]["bodyState"]
                self.assertTrue(
                    any("title-only-body-mismatch" in error for error in VALIDATE._title_decision_errors(missing_marker))
                )


if __name__ == "__main__":
    unittest.main()

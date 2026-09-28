"""Synthetic-only fixture construction shared by regression tests."""
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import knowledge_export as k


def uid(kind, number):
    return f"urn:al-isabah:synthetic:{kind}:{number}"


def seal(snapshot):
    snapshot["admission"]["approvedCollectionsSha256"] = k.digest({key: snapshot[key] for key in k.COLLECTIONS})
    return {"snapshotSha256": k.digest(snapshot), "pins": k.pins(snapshot, k.read(k.SCHEMA_PATH))}


def fixture():
    h = lambda value: k.digest(value)
    records = [{"id": uid("record", i), "logicalRecordId": uid("logical-record", i),
                "sourceReleaseId": uid("release", 1), "recordSha256": h(["record", i]),
                "authorityUnitSha256": h(["unit", i]), "volume": i, "pages": [10*i],
                "sourceOrdinal": i, "printedEntryNumber": i,
                "machineAssessment": "needs_attention" if i == 1 else "passed",
                "humanReview": "unreviewed", "canonicalPromotion": "blocked",
                "extractionStatus": "partial" if i < 3 else "not_started"}
               for i in range(1,4)]
    entities = [{"id": uid("entity", i), "sourceRecordIds": [uid("record", i)]} for i in (1,2)]
    claims = [{"id": uid("claim", i), "subjectId": uid("entity", i),
               "predicateId": uid("predicate", "related-to"), "objectId": uid("entity", 3-i),
               "assertionClass": "source_attested", "sourceRecordIds": [uid("record", i)],
               "sourceCriticalStatus": "disputed", "evidentiaryStrength": "unassessed",
               "transmissionStrength": "unassessed", "storyUseTier": "attributed_disputed_report",
               "attributionRequired": True, "ambiguityGroupIds": [uid("group", 1)]} for i in (1,2)]
    snapshot = {"schemaId": "al-isabah.knowledge-snapshot.v1", "schemaVersion": "1.0.0", "mode": "synthetic",
                "authority": {"authorityId": uid("authority", 1), "workId": uid("work", 1),
                              "editionId": uid("edition", 1), "revisionId": uid("revision", 1),
                              "sourceArtifactSha256": h("synthetic-authority")},
                "sourceRelease": {"id": uid("release", 1), "repository": "https://github.com/yaqub0r/al-isabah",
                                  "repositoryCommit": "0"*40, "releaseTag": "synthetic-"+"0"*40,
                                  "distributionSchemaVersion": "2.0.0", "assetSha256": h("synthetic-asset"),
                                  "proposalId": uid("proposal", 1), "proposalSha256": h("synthetic-proposal"),
                                  "closureId": uid("closure", 1), "closureSha256": h("synthetic-closure"),
                                  "publicationStatus": "synthetic"},
                "rights": {"licenseId": "synthetic-no-real-content-license", "useClassification": "synthetic-testing-only",
                           "attributionIds": [uid("attribution", 1)], "commercialUse": "not-granted",
                           "redistribution": "synthetic-fixtures-only", "softwareLicenseGranted": False},
                "sourceScope": [{"volume": i, "recordCount": 10} for i in (1,2,3)],
                "policy": {"id": uid("policy", 1), "predicateIds": [uid("predicate", "related-to")],
                           "humanReviewEffect": "metadata-only", "consumerPromotion": "separate-policy",
                           "predicateSemantics": "synthetic-directed-relation-no-historical-meaning"},
                "admission": {"id": uid("admission", 1), "decision": "synthetic-test-only", "approvedCollectionsSha256": "0"*64},
                "batches": [{"id": uid("batch", i), "recordIds": [uid("record", i)], "volumes": [i]} for i in (1,2,3)],
                "sourceRecords": records, "entities": entities, "claims": claims,
                "ambiguityGroups": [{"id": uid("group", 1), "memberClaimIds": [uid("claim", 1),uid("claim", 2)],
                                     "resolutionStatus": "unresolved", "presentationMode": "parallel_attributed_reports"}],
                "lifecycleEvents": []}
    return snapshot, seal(snapshot)


def successor(snapshot, kind="corrects"):
    result = copy.deepcopy(snapshot)
    result["admission"]["id"] = uid("admission", 2)
    result["batches"] = [{"id": uid("batch", 4), "recordIds": [uid("record", 1)], "volumes": [1]}]
    replacements = []
    if kind != "withdraws":
        claim = copy.deepcopy(snapshot["claims"][0])
        claim["id"] = uid("claim", 3)
        claim["ambiguityGroupIds"] = []
        claim["sourceCriticalStatus"] = "qualified"
        claim["storyUseTier"] = "qualified_context"
        result["claims"].append(claim)
        replacements = [claim["id"]]
    result["lifecycleEvents"] = [{"id": uid("event", 1), "kind": kind,
                                  "targetClaimId": uid("claim", 1), "replacementClaimIds": replacements}]
    return result, seal(result)


def export(snapshot, trust, number):
    return k.build(snapshot, uid("batch", number), trust["snapshotSha256"], trust["pins"])


def admission(batch, snapshot, trust):
    return batch, snapshot, trust["snapshotSha256"], trust["pins"]


if __name__ == "__main__":
    directory = ROOT / "tests/fixtures/knowledge-export-v1"
    directory.mkdir(exist_ok=True)
    snapshot, trust = fixture()
    values = {"snapshot.json": snapshot, "trust.json": trust,
              "batch-1.json": export(snapshot, trust, 1), "batch-2.json": export(snapshot, trust, 2),
              "batch-3.json": export(snapshot, trust, 3)}
    for kind in ("corrects", "supersedes", "withdraws"):
        next_snapshot, next_trust = successor(snapshot, kind)
        values.update({f"{kind}-snapshot.json": next_snapshot, f"{kind}-trust.json": next_trust,
                       f"{kind}-batch.json": export(next_snapshot, next_trust, 4)})
    for name, value in values.items():
        (directory/name).write_bytes(k.canonical(value))
    print(k.digest(k.read(k.SCHEMA_PATH)))
    print(trust["snapshotSha256"])

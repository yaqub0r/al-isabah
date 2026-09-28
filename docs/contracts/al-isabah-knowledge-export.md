# Proposed repeatable text-free knowledge export

Issue [#87](https://github.com/yaqub0r/al-isabah/issues/87). Schema ID
`al-isabah.knowledge-export.v1`, version `1.0.0`. Status: **proposed,
synthetic-only foundation**. This is not approval to export real volumes.

The [closed schema](../../schemas/al-isabah-knowledge-export.v1.schema.json)
defines the wire object and `$defs.snapshot`, `$defs.trust`, `$defs.policy`,
and `$defs.admission` inputs. The dependency-free
[producer](../../scripts/knowledge_export.py) validates an explicitly pinned
snapshot and exports one declared batch. It performs no semantic extraction.
The [synthetic bundle](../../tests/fixtures/knowledge-export-v1/) provides three
batches and separate correction, supersession, and withdrawal successors.

## Authority and admission boundary

Al-Isabah owns source identity, approved semantic assertions, rights,
qualifications, correction history, and upstream publication status. Elixr
owns its separate intake approval and promotion rules. A payload's approval
label or internally consistent hashes never authorize its admission. The
caller must supply an independently trusted snapshot digest and pin set;
Elixr additionally pins exact export bytes under its own reviewed approval.
Fixture `trust.json` is test configuration, not an authority or production
allowlist. Self-generated trust is acceptable only in synthetic tests.

This additive source-specific route is separate from general Elixr ingress v2
and the immutable Khadijah story-projection v1 adapter. The consumer coordinates
it under Elixr issue #27 and a proposed ADR. There is no conversion to a story
package, automatic historical assertion, renderer, or change to existing
consumer admission. Producer validity alone cannot promote an Elixr view.

`mode` and publication status are constrained to `synthetic`; rights grant no
real-content license. The only permitted predicate is
`urn:al-isabah:synthetic:predicate:related-to`, a directed artificial relation
without historical meaning. Unknown predicates reject the entire batch. A real
predicate registry, rights/attribution profile, source-specific approval,
exact immutable artifact pins, and corresponding consumer review are future
prerequisites. This implementation does not claim all biographies have been
semantically extracted.

## Identity and exact source binding

All IDs are opaque, case-sensitive, kind-namespaced ASCII identifiers. No suffix
stripping, display-name matching, transliteration, normalization, or uncertain
person merging is allowed. `logicalRecordId` identifies a logical source unit;
`sourceRecords[].id` identifies immutable record-version bytes. Entity IDs are
explicit approved identities, never inferred from record names. Revision
transitions cannot silently preserve or merge uncertain identities.

`authority` carries authority, work, edition, revision, and exact source artifact
digest. Each record carries its release ID, record and authority-unit digests,
volume, pages, source ordinal, and printed entry number. `sourceRelease` carries
repository, commit, tag, distribution schema version, asset digest, proposal
identity/digest, and closure identity/digest. These are safe references; no
archive or underlying source body is transported. Synthetic hashes identify
test values, not authentic scholarly evidence.

A ledger is deliberately scoped to **one exact authority revision**. A changed
edition, revision, or source artifact requires a future explicit transition
contract or separately approved ledger. Within this scope, immutable release
IDs, repository/commit, and repository/tag aliases bind the complete release
object, rights, and policy pins. Changing an asset, proposal, closure, rights, or policy beneath
an existing identity rejects with `immutable-id-conflict`. Claims, records,
entities, ambiguity groups, events, and batch IDs likewise cannot change bytes.
Policy and admission IDs also bind immutable object digests across snapshots.

## Coverage and closure

The trusted snapshot declares source scope per volume, approved source records,
approved claims, and explicit batch record IDs/volumes. Source scope is not an
assertion that every source record is released or extracted. Each approved
record has independent `extractionStatus`: `not_started`, `partial`, or
`complete`. Partial extraction may contain zero or more approved claims;
`not_started` cannot support claims. Completion means completion of the
explicitly approved extraction scope, not proof of historical completeness.

Batch selection starts with all approved claims referencing requested records.
The producer computes transitive closure over ambiguity members, claim/entity
source references, and lifecycle targets/replacements. It includes complete
ambiguity groups even when their members originate in another volume or batch.
Unavailable dependencies fail closed. A dependency record does not implicitly
select every other claim about that record. All dependencies are in the batch;
no prior local intake is required to resolve a reference.

`selection` lists requested and dependency record/claim IDs separately.
`coverage` reports whole-snapshot source scope, approved records, extracted
records, extraction-complete records, and approved claims, plus batch requested,
dependency, and total counts. These whole-snapshot counts must not be summed
across batches. Replay reports distinct IDs; overlapping dependencies and exact
replays do not increase corpus counts. Arrays are emitted in exact ID order.

## Qualifications and lifecycle

Machine assessment, ongoing human review, canonical-promotion state, semantic
extraction, projection approval, and consumer admission are separate states.
Zero human review never blocks upstream publication by itself. `needs_attention`
is retained, not converted to a favorable assessment or blanket exclusion.
Assertions preserve class, critical qualification, evidentiary/transmission
strength, story-use tier, mandatory attribution, and complete ambiguity IDs.
No strength field defaults to favorable evidence. Claims with unresolved factual
ambiguity cannot enter `factual_spine`; qualification cannot lose attribution.

Corrections and supersessions mint new claim IDs and append events; withdrawals
append events without replacement claims. Original claims remain immutable
historical evidence. Events cannot point to themselves, form cycles, or give
one target conflicting outcomes. A new incremental event cannot reuse a prior
claim as a replacement or act again on a retired target. Exact previously seen
events are safe overlap. A complete approved corrected/withdrawn snapshot can
bootstrap a fresh ledger: predecessor claims are evidence, never active output.

Replay revalidates all supplied history into a new in-memory ledger before
returning a result, so any failure rejects the whole operation without changing
the caller's state. Retired IDs remain retired after historical batch replay.
Unresolved alternatives remain intact for audit even when a lifecycle event
retires one member; consumers must not interpret that as selection of a winner.
Historical views are audit evidence, not permission to restore withdrawn
material to active use. This producer is a reference validator, not persistent
consumer storage or a mechanism to bypass Elixr admission.

## Hash domains and deterministic replay

All semantic digests use SHA-256 of sorted-key, compact UTF-8 JSON followed by
exactly one LF (`json.dumps(..., sort_keys=True, separators=(",", ":"),
ensure_ascii=False) + "\n"`). Arrays retain order; floats, non-finite values,
unknown fields, duplicate object keys, and unconstrained prose are excluded.
Strings in this contract are ASCII constrained. Duplicate array values and IDs
reject. No Unicode normalization is performed.

- `snapshotSha256` hashes the complete approved snapshot.
- `pins.schemaSha256` hashes the parsed complete schema, including `$defs`.
- Policy, admission, rights, and source-release pins hash their complete objects.
- `admission.approvedCollectionsSha256` hashes the object containing exactly
  `sourceRecords`, `entities`, `claims`, `ambiguityGroups`, and `lifecycleEvents`.
- `payloadSha256` hashes the entire export except that one field itself.
- Source record/artifact/proposal/closure/asset hashes refer to the separately
  declared immutable upstream byte domains; the synthetic fixtures use test
  values and never establish real source authenticity.

Exact file SHA-256 is a **separate** consumer pin. Formatting/CRLF changes may
preserve a parsed semantic digest but change the exact-file digest. Consumer
approval must bind both. The CLI emits only canonical bytes and `--check`
requires exact byte equality. No timestamps, network calls, model calls, or
environment-dependent values affect output.

The custom validator executes only the schema vocabulary used here and rejects
unsupported schema keywords. Diagnostics emit fixed reason codes without
untrusted field names, values, text, or paths. Codes include `prohibited-payload`,
`schema-mismatch`, `unsupported-schema`, `duplicate-key`, `duplicate-item`,
`missing-reference`, `ambiguity-incomplete`, `coverage-mismatch`,
`source-identity-mismatch`, `snapshot-digest-mismatch`, `policy-digest-mismatch`,
`admission-digest-mismatch`, `payload-digest-mismatch`, `batch-content-mismatch`,
`immutable-id-conflict`, `lifecycle-conflict`, `qualification-loss`,
`unapproved-predicate`, `undeclared-batch`, `invalid-json`, `noncanonical-output`,
and `input-output-error`. No rejected records are silently skipped.

## Reproduction

From the repository root with Python on PATH:

```sh
python scripts/knowledge_export.py --snapshot tests/fixtures/knowledge-export-v1/snapshot.json --trust tests/fixtures/knowledge-export-v1/trust.json --batch urn:al-isabah:synthetic:batch:1 --output tests/fixtures/knowledge-export-v1/batch-1.json --check
python -m unittest discover -s tests -p test_knowledge_export.py
python scripts/build_elixr_story_projection.py --check
python scripts/validate_elixr_story_projection.py
python -m unittest discover -s tests
```

The fixtures are authored by `tests/knowledge_export_support.py`; regeneration
is an explicit developer action, never automatic approval of real input.
See the [eligibility and delivery inventory](../research/knowledge-export-eligibility.md)
for real pilot prerequisites and publication coupling.

# Executable knowledge-export v2 draft

Issue [#89](https://github.com/yaqub0r/al-isabah/issues/89); coordinated with Elixr
#29. This is an executable **synthetic conformance draft**, version
`2.0.0-draft.1`. It does not activate real extraction, publication or admission.
Synthetic v1 and Khadijah v1 remain unchanged.

The closed schema is `schemas/al-isabah-knowledge-export.v2-draft.schema.json`.
Its `$defs.snapshot`, `$defs.inventory`, `$defs.profile` and `$defs.trust` describe
the four independently supplied producer inputs. The proposed real source/profile
is `profiles/knowledge/volume-08.v2-draft.json`; both real enablement flags are
false. The schema can express the proposed real shape for review, but the
producer rejects real mode, non-synthetic authority/rights/reconciliation and
any non-synthetic Al-Isabah identifier. A shape pass is never approval.

## Interface and reproducibility

`scripts/knowledge_export_v2.py` provides:

- `validate_snapshot(snapshot, inventory, profile, trust)`;
- `build(snapshot, inventory, profile, trust, batch_id)`;
- `validate_payload(payload, snapshot, inventory, profile, trust)`; and
- `replay_identity(payloads)`, an immutable-ID audit only, not admission or a
  current-eligibility ledger.

This bounded draft supports one explicitly declared **full-snapshot** batch.
The batch declares requested and dependency logical-record IDs separately. Every
inventory record, span, disposition and referenced collection is present; subset
or undeclared batch requests reject. Future incremental selection requires a
separate reviewed extension; no incomplete batching algorithm is implied.

Synthetic fixture generation is an explicit developer operation:

```sh
python tests/knowledge_export_v2_support.py
python scripts/knowledge_export_v2.py --snapshot tests/fixtures/knowledge-export-v2-draft/snapshot.json --inventory tests/fixtures/knowledge-export-v2-draft/inventory.json --profile tests/fixtures/knowledge-export-v2-draft/profile.json --trust tests/fixtures/knowledge-export-v2-draft/trust.json --batch urn:al-isabah:synthetic:batch:1 --output tests/fixtures/knowledge-export-v2-draft/batch.json --check
python -m unittest discover -s tests -p test_knowledge_export_v2.py
```

Ordinary exporter writes use exclusive creation; `--check` compares exact bytes.
No source reading, network access, model calls, timestamps or environment-derived
content occurs in export. Diagnostics are fixed reason codes and never echo
rejected content or paths. The schema uses the existing dependency-free closed
JSON Schema subset. Dates are closed objects with status, timestamp and reason;
an unknown date has an empty timestamp plus an explicit reason, not an invented
current time. Recorded timestamps must be valid UTC ISO dates.

## Hash domains and independent pins

All semantic digests use SHA-256 of sorted-key compact UTF-8 JSON,
`ensure_ascii=False`, `allow_nan=False`, followed by one LF. Arrays retain their
order. Duplicate keys, duplicate objects, unknown fields, floats and arbitrary
prose are excluded. Collections are ordered by immutable ID; transmission order
is separately checked against contiguous zero-based positions.

Inventory, profile, schema and snapshot pins hash complete parsed objects.
`payloadSha256` hashes the complete export except that field. Exact-file SHA-256
is a separate consumer pin; fixture/export files use the canonical bytes so the
two domains coincide only when the relevant complete object is identical.
`recordSha256` identifies **external immutable upstream record bytes**, not the
text-free metadata object. An assessment input pin hashes its complete referenced
metadata object, including that external digest. The actual upstream record and
source-fragment byte domains must be verified by the source owner before real
approval; the draft does not pretend to verify unavailable bytes.

Fixture trust is deliberately synthetic configuration. Real trust must be
independently installed by the consumer under the reviewed authority/current-head
decision; an export cannot supply or refresh its own approval. The draft trust
checks exact source inventory, profile, snapshot and schema pins before export.

## Reference and assessment rules

Every generic reference contains a closed collection kind and an immutable ID.
All collection targets resolve, including mentions, values, places, times,
qualifications, attributions, restrictions and findings. A claim names exact
`sourceRecordVersionIds`; coverage counts stable `logicalRecordId` values.
Each source unit belongs to exactly one logical record in this snapshot.
Structural units retain their owning entry; authority-unit sets cannot drift
between the inventory and record metadata. Per-span claims and reports agree
in both directions with their disposition and owning records.

Predicates constrain subject entity kinds, object collection kinds and object
entity kinds. Role and event-type vocabularies are closed. Negative assertions,
modality, source-critical qualifications, ordered transmission, unresolved
alternatives and mandatory attribution are preserved. A disputed/unassessed
assertion cannot be upgraded to factual use. These checks prove structural
faithfulness of the representation, not historical truth or completeness of
semantic extraction.

Assessments are immutable versions with exact targets/input digests, actor and
method references, genuine effective/observed time states and predecessor links.
A snapshot explicitly selects current extraction and human-review assessments
for each record. Kind/target changes, stale selected predecessors, cycles,
false completion and inferred human review reject. Selection never refreshes an
old timestamp. The consumer must additionally retain prior identities and current
assessment chains across snapshots so omitted newer history cannot cause rollback.

Lifecycle events retain original targets and full ambiguity groups. Targets
cannot retire twice or form replacement cycles; withdrawal has no replacement;
entity split/merge types and cardinalities are explicit. A producer identity
audit detects changed bytes under an existing export/batch/collection identity.
The consumer owns active/retired state, current trust-head checks, revocation,
restore semantics and atomic persistence; producer identity audit does not
implement or substitute for those controls.

## Coverage formulas

Coverage is derived from the independently pinned inventory:

- `requestedLogicalRecords` / `dependencyLogicalRecords`: logical records with
  `inScope` true / false; assessment versions never add logical coverage.
- `sourceUnits`, `entries`, `structuralUnits`: in-scope authority units, split by
  entry versus structural kind. Dependency units are excluded from these counts.
- `expectedSpans`: inventory spans owned by in-scope source units. Every span in
  the full snapshot, including dependencies, must have exactly one disposition.
- `representedSpans`: scoped spans with a nonblocking disposition;
  `uncertainSpans`: scoped `represented_uncertain` spans;
  `blockedSpans`: scoped unsupported, unprocessed or source/mapping-blocked spans.
- `extractionCompleteRecords`: in-scope logical records whose explicitly selected
  extraction assessment is complete. Complete assessments cannot contain a
  blocking disposition. A nonclaim/structural outcome requires positive evidence.
- `assessmentVersions` and `claims`: whole-snapshot counts, including dependencies;
  these must not be summed across repeated exports.
- `scopeExtractionComplete`: all requested logical records have complete selected
  extraction assessments and no scoped blocking span remains. This is synthetic
  arithmetic, not source eligibility, semantic truth or consumer import completion.

The fixture exercises three logical records (two requested, one dependency),
three scoped source units, a heading, ordered transmission, competing positive
and negative claims, qualified event roles/time/place/counts and one unsupported
gap. It intentionally does not claim scope completion.

## Explicit draft limits before real use

Hash-only name mentions do not satisfy final readable name/alias semantics.
Normalized readable names, more expressive time/value forms, direction/inverse
rules for the candidate predicates, complete real span partition evidence,
positive semantic-stage/runtime evidence and reviewed approval records remain
required real-profile work. Unsupported material cannot be shoehorned into the
current closed vocabulary; retain a blocking disposition and extend it through
review. There is no claim that these draft enums represent every source passage.

The concrete decision packet is
`docs/decisions/0002-volume08-real-extraction-admission-draft.md`. It keeps actual
approval, rights, authority/current validity and semantic execution separate from
this reversible draft implementation. Schema/profile paths can trigger the
existing publication workflow **after a merge to main**; this draft PR must not
be merged under an earlier synthetic-only publication approval.


The draft deliberately supports one source-record version per logical record in
a snapshot. It cannot yet carry historical v1 and current v2 source-record bytes
together for source-correction bootstrap. Such input rejects; do not claim full
production correction/repeatability support. Same-source assertion lifecycle and
separate assessment revisions are covered.

An active semantic object cannot point to a retired dependency. Reject such a
snapshot atomically; do not silently cascade deletions. Audit-only collections
(assessments, span dispositions, ambiguity groups, lifecycle events, findings and
qualifications) retain historical references, as do report claim indexes. Active
claim references to qualifications/assessments must still name live objects.
Explicit current source/assessment selection remains live; current selected
assessment actor, method and finding dependencies remain live while its input,
target and predecessor links retain audit history. Consumer activation also
evaluates lifecycle/assessment times against its independent current observation;
the producer has no authority to supply or advance that observation.

A `nonclaim_form` disposition requires a complete independent-review/adjudication
assessment targeting both the exact disposition and owning source-record version,
with both included among hash-bound inputs. Extraction status alone is not review
evidence. `absence_of_evidence` cannot enter `factual_spine`.

The shared `adversarial-cases.json` fixture applies 17 explicit synthetic mutation
vectors to freshly re-pinned inputs. Both producer and consumer independently
execute it; trust-pin consistency does not excuse inconsistent content.

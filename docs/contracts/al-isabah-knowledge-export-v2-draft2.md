# Knowledge export draft 2: corrections and scoped execution evidence

Issue: #89. This is executable synthetic conformance, version
`2.0.0-draft.2`. Draft 1 and its frozen artifacts remain unchanged. Real execution
and admission are disabled. This contract does not approve a real method,
semantic assertion, artifact, publication or rights expansion.

## Immutable history and explicit current state

`currentSourceSelection` selects exactly one source record version for every
inventory logical record, including declared dependencies. Historical versions
remain immutable and must have explicit retirement events. Current references
cannot use retired dependencies. Entity versions retain `logicalEntityId`;
there can be only one live version for each logical entity identity. Equal names
never imply identity or a merge.

`currentSpanDispositionSelection` contains closed rows with
`sourceRecordVersionId`, `sourceSpanId`, and `spanDispositionId`. It selects exactly
one disposition for every owned span of each current source version. Every
immutable disposition records its `sourceRecordVersionId`. Historical dispositions
can share a source/span pair. They are never rewritten to include later claims.
Every historical claim/report pair must occur in a matching disposition, and every
live claim/report pair must occur in the current selected disposition. Current
selected disposition references must be live, except `assessmentIds`, which retain
historical supporting provenance. Span coverage uses only explicitly selected rows. `claims` and
`assessmentVersions` count retained immutable versions, including history; they
are not current-use approval counts. Logical source and span counts remain current.

The selected extraction assessment hash-binds the exact current source and every
selected disposition through its typed targets and inputs. The reverse link from
an old disposition to a new assessment is deliberately unnecessary: a new
assessment may reaffirm exactly the same source and disposition bytes. Assessment
predecessors still require equal kind and target lists. When target lists change,
use explicit assessment lifecycle events. Dates and row order never select current
state. Old assessments and their timestamps remain immutable.

Five positive fixtures demonstrate initial state, source correction with dependent
successors, extraction correction against unchanged source, reaffirmation of
unchanged objects, and an independent cohort correction. None performs real
semantic work. Replay checks immutable identity; consumer current-state validation
remains a separate responsibility. Mixing draft 1 and draft 2 in one active ledger
requires an explicit migration and otherwise fails closed.

## Readable names and exact quantities

`names` carries bounded readable `form`, `language`, `formRole`, `derivation`,
entity/source/span bindings, source-surface hash, and assessment/ambiguity IDs.
Forms use Latin or Arabic letters and combining marks with spaces, apostrophes,
hyphens and the modifier letters for hamzah/ayn. They are at most 120 characters,
one line, and already NFC-normalized; the validator rejects instead of silently
normalizing. The declared language must agree with the letters. This syntax is a
boundary check, not proof that arbitrary prose is a name. Source evidence and
review establish that distinction. Never put source sentences into name fields.

Entity `nameIds` and mention `nameId` close reciprocally. A named mention matches
its name's entity, source version, span, role and source-surface hash. Only an
`unnamed_reference` has an empty name ID. Editorial supply requires a complete
independent review or adjudication targeting and hash-binding both name and source
record. Source spelling, transliteration and normalization remain distinct
provenance states; do not infer certainty from readable text.

Quantities use integer `amountNumerator` / positive integer `amountDenominator`.
This preserves fractions without binary floating-point rounding. The draft 1
`amount` field is prohibited in draft 2. Units and approximation remain explicit.

## Upstream receipts and cohort boundaries

`profiles/knowledge/execution-methods.v1-draft.json` proposes only extraction,
independent review and adjudication under the existing trusted-host pattern.
The exact requested and observed provider/model/reasoning settings, fresh worker
context, separate worker sessions, host task, stage input/output digests, and
checkpoint are bound in an upstream receipt. The checkpoint includes task/worker
metadata. The full receipt has its own canonical digest. Reuse of a worker session
for distinct receipts is rejected, including across separate cohort chains.
Synthetic test logs pass through the actual host metadata parser. No real host
session is sampled or model executed by fixture generation.

Each receipt chain pins the inventory, profile and exact source metadata together
with explicit `requestedSourceRecordVersionIds` and
`dependencySourceRecordVersionIds`. Their disjoint union equals the receipt's
source versions. Dependencies cannot implicitly receive extraction approval: a
selected record's extraction chain must list it as requested. Stage scope is
unchanged across extraction, review and adjudication, and each later input binds
the previous output digest.

The final output is the exact semantic object projection for that cohort and its
reference closure. Source ownership and dependency closure are checked against
actual object/source-span references; unused or missing declared dependencies
fail. Every output object binds an immutable typed identity and content digest.
The union of selected chains must cover the assembled current semantic objects,
with no foreign objects, omitted objects, inconsistent shared identities or
order-dependent choices. The complete selected inventory is pinned before cohort execution; not-yet-processed
records remain inventoried with unprocessed dispositions. Changing that inventory
requires a separately reviewed version transition, not silent receipt rebinding.
An independent cohort correction preserves the other
cohort's actual receipt bytes. Old receipts remain evidence of their original
outputs; they cannot approve corrected outputs merely by being retained.

A `not_started` record has no receipt chain and only unprocessed dispositions.
Its pinned source/disposition metadata and source-targeted findings can still be
counted as inventoried metadata. They do not count as completed semantic review
or justify claims. Unsupported material stays visible with incomplete extraction.

Full receipts and source expression stay upstream. Exported assessments contain
only `receiptArtifactIds`; the corresponding `knowledge_receipt` artifacts bind the
canonical full receipt digest. Snapshot, payload and independent trust configuration
pin `receiptBundleSha256`; the profile pins `methodRegistrySha256`. The consumer
checks those closed references and independently installed pins without receiving
host metadata. This draft's synthetic trust bundle is not a real approval.
Production requires the actual upstream and consumer owner decisions and current
trust-head observation described in decision 0002.

## Reproduction

Generate authored synthetic fixtures with
`python tests/knowledge_export_v2_draft2_support.py`. The five subdirectories under
`tests/fixtures/knowledge-export-v2-draft2/` contain snapshot, inventory, profile,
trust, batch, upstream synthetic receipts, and proposed registry. Shared rejection
vectors are in `adversarial-cases.json`. Test exact outputs and substantive
correction/receipt rejection with
`python -m unittest discover -s tests -p test_knowledge_export_v2_draft2.py`.

The producer API is `build(snapshot, inventory, profile, trust, batch_id,
receipt_bundle, registry)`. The CLI requires `--receipts` and `--registry` alongside
its other pinned inputs. Canonical hashes retain sorted compact UTF-8 JSON with
one LF, as in draft 1. The receipt artifact hash covers the full canonical receipt,
including its internal receipt digest; the internal digest excludes only itself.

The real pilot preparation is separately reproducible with
`python scripts/prepare_knowledge_pilot.py --check`. It selects source ordinals
10754–10763, 11424–11425 and 12303 with all owned structure and retained findings
from the independently pinned real inventories. It reads no candidate/source
bodies, creates no semantic claims, and leaves span partition, structural crosswalk,
identity/fidelity review and all knowledge execution stages explicitly unstarted.

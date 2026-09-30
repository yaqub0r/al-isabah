# Knowledge export draft 3: typed subjects and governed evidence

Issue #89; consumer coordination: Elixr #29. Version `2.0.0-draft.3` is
synthetic conformance only. Drafts 1 and 2, their profiles and fixture bytes, and
historical local-trial evidence remain immutable. This version does not approve
semantic execution, translation changes, source acquisition, publication, or real
consumer admission. The full legacy-volume objective remains 1,550 entries and
205 owned structural units; synthetic success is not that import.

## Wire shape and governed domains

`claims.subjectRef` is a closed `{kind: entities|events, id}` reference. It
replaces `subjectId`; neither the old field nor both fields are accepted. Entity
subjects derive their predicate kind from `entity.kind`; event subjects derive
kind `event`. Both subject and object references participate in dependency,
retirement, current-selection and receipt-projection closure.

Each predicate retains its existing typed object/subject domain and adds:

| Field | Rule |
| --- | --- |
| `subjectEventTypes` | Exact approved event IDs for event subjects. Empty means no event domain. |
| `objectEventTypes` | Exact approved target event IDs. To allow every governed type, list them explicitly; no wildcard. |
| `objectValueKinds`, `objectUnits` | Both constrain a resolved value object; empty means no value domain. |
| `epistemicPolicy` | Closed, required allowed assertion classes, polarities, modalities and use tiers. |
| `sourceEvidenceRule` | `none` or `exact_notice_source_author`. |

Event references retain source-record and report evidence. Claims still bind
exact source spans, reports, qualifications, attribution and restrictions, and
report/claim and claim/qualification links remain reciprocal. An event object
referenced as a requested outcome or condition is not thereby asserted to have
occurred. Semantic event relationships may carry conflicting attributed accounts;
only the existing lifecycle/assessment graphs use acyclicity checks.

`profile.valueUnits` is a closed list of `{id, valueKinds}` definitions. Unit
codes have bounded symbolic syntax; the validator also requires membership in
the independently pinned profile and compatibility with the value kind. Initial
units are `persons` for counts, `years`, `months`, and `days` for ages/durations,
`sequence` for ordinals, and `camels` for counts. Rational numerator/denominator
and approximation stay explicit. No free prose, conversion, unit inference,
external registry or implicit future profile acceptance is introduced. Future
units can use a reviewed profile revision rather than a new wire shape, but the
consumer must explicitly accept that profile and preserve earlier unit meanings.

A place object must resolve through `entityId` to a live `place` entity. A place
wrapper around a person does not satisfy that rule. Counted animals use values;
they are not coerced into persons, collectives, works or places. Individual
non-place assets and unspecified legal rights remain unsupported residuals.

## Bounded added terms

The predicate prefix below is `urn:al-isabah:predicate:`. All meanings are
source-attributed; no relation is inferred from record order or a similar name.

| Predicate suffix | Domain and meaning |
| --- | --- |
| `nursing-sibling-of` | Person to person; specifically nursing, not biological siblinghood. |
| `foster-parent-of` | Person to person; subject is foster parent of object. |
| `companion-status-inferred-from` | Person to notice version; the source author makes the status inference using that notice as basis. |
| `companion-status-evidence-in` | Person to notice version; this profile permits only the source's statement of absence of evidence in that notice. |
| `emigrant-status-attested-in` | Person to notice version; attributed attestation scoped to that notice. |
| `precedes` | Event to event; explicit relative order. |
| `conditioned-on` | Event to event; subject is contingent on target, asserting neither occurrence. |
| `requests-outcome` | Supplication/blessing event to event; a request, not fulfillment. |
| `pledged-quantity` | Oath event to value; count/camels only, not completed transfer. |
| `granted-place` | Grant event to place; identifies a site without inventing a property right. |
| `departed-from`, `arrived-at` | Journey event to place; independently sourced direction, never inferred from a place list. |

Added event-type suffixes under `urn:al-isabah:event-type:` are `pregnancy`,
`purification`, `grant`, `blessing`, `supplication`, `stoning`, `pilgrimage`,
`ablution`, and `oath`. Existing birth, journey, death, encounter, marriage,
conversion, participation and narration remain usable. No generic other-act,
asset entity kind or new participant role is added. Type names alone do not
certify that all material narrative content has been represented.

## Predicate posture is not an editable eligibility flag

All four `epistemicPolicy` arrays are required, nonempty, unique and closed.
Checks are conjunctive, and **every** referenced use tier must be allowed. The
older general qualification-loss guard remains independently enforced.

The three status-evidence predicates require `source_attested` and `asserted`:
this describes the source making the statement, not historical truth of its
conclusion. Evidence-in permits only `absence_of_evidence`; inferred-from and
attested-in permit only `positive`. They allow `qualified_context`,
`attributed_disputed_report`, or `not_for_narrative`, never `factual_spine`.
Agent-origin status inference is outside this addition.

`conditioned-on` requires source-attested, positive, conditional posture.
Requests and pledges require source-attested, positive, asserted posture for the
reported request/pledge, not its fulfillment. These terms use the same nonfactual
use-tier cap. Ordinary predicates retain their reviewed envelope and the general
qualification constraints. Tests cover actual combinations and mixed allowed/
forbidden tier lists, including simultaneously changing polarity, qualifications
and factual-use eligibility with freshly rebuilt synthetic pins and receipts.

## Exact notice and correlated source-author evidence

For `exact_notice_source_author`, the object is an immutable source-record
version, included in the claim's exact source/dependency closure. A logical
record ID or a corpus-wide source label is insufficient. `sourceSpanIds` are the
spans attesting the source author's statement. Their owning record can differ
from the notice being discussed; the target notice need not itself be an
attesting span. Dependency records do not thereby obtain requested extraction
approval.

For each attesting record and span, require a source-author attribution bound to
that record's `sourceArtifactId`, with nonempty person references. The same
people must appear in cited reports actually covering that record/span and in
qualifications for that record targeting the exact claim. An author/evaluator
present only in a distractor report or qualification cannot satisfy the rule.
Work/license attribution, an actor ID, and a machine assessment are insufficient.

These checks establish reference ownership and provenance structure. They do
not authenticate the truth of a private reading or detect every semantically
wrong but fully declared notice; independent semantic review and exact approval
remain necessary. No machine-inference assessment system is created.

## Explicit successor planning

`scripts/knowledge_successors.py` accepts a pinned current semantic projection,
explicit before-hash/replacement patches and a successor namespace. It checks
object shapes, resolved references and supported reciprocal links in the input,
patched graph and result. One-sided edits reject; the helper never invents a
matching semantic edit. Reverse dependency closure terminates across reciprocal
cycles. Only affected objects receive deterministic new IDs; unchanged objects,
logical entity IDs and array/transmission order remain intact. Literal text is
not globally searched/replaced.

The output is a candidate plan, not an activated snapshot or approval. It creates
no assessment, receipt, lifecycle decision or concern resolution. Callers retain
all original history and explicitly build governed successor decisions and
current selections before full producer validation. Source records are external
references, not editable objects. Entity split/merge decisions are outside this
helper. Dry-run is the default. `--apply --output` exclusively creates a NEW
private runtime file; existing files and public output locations reject.

```powershell
python scripts/knowledge_successors.py --input <current-projection-json> --base-sha256 <exact-digest> --patches <explicit-patches-json> --namespace urn:al-isabah:synthetic:successor:example
```

## Conformance and private-stage validation

The new producer is `scripts/knowledge_export_v2_draft3.py`. Its build/validate
API matches draft 2. The closed schema and independent trust pins select draft
3 explicitly. The consumer must add the reviewed schema/profile pair; a changed
profile is not self-approved by a fresh payload hash. An existing synthetic
ledger needs an explicit version transition. There is no real-data migration
because this draft has admitted none.

Seven positive fixture states include the original correction/reaffirmation
patterns, bounded capability examples, and an explicit helper correction that
preserves old objects, receipts and an unrelated cohort. Shared adversarial
vectors specify their base fixture and synthetic re-pinning mode. The test
helper rebuilds hashes without repairing invalid semantics; no real receipt is
fabricated. All examples use invented identities and quantities.

```powershell
python tests/knowledge_export_v2_draft3_support.py
python scripts/knowledge_profile_v3.py --check
python -m unittest discover -s tests
```

`schemas/knowledge-pilot-stage-output.v2.schema.json` and
`scripts/knowledge_pilot_validation_v2.py` provide a separate private validation
surface with the same domain checks and explicit schema/profile pins. It rejects
v1 relabeling and creates no launch, approval or receipt. The previous actual
trial remains partial under its original schema/approval. A later semantic run
requires a new exact request/capture binding to reviewed code, profile, schema,
source scope and immutable adjudicated baseline; the earlier three-worker
approval cannot be reused. No finer-span infrastructure is mandatory: several
reports and claims may share one exact source span.

The separately versioned local runner is documented in
[the remediation runbook](../translation/knowledge-pilot-remediation.md). It
prepares an unsigned request, validates an independently supplied new decision,
and captures sequential proposals and host receipts. Its proposal envelope
receipt-binds explicit outcomes for every baseline concern and immutable object
successors; the frozen private v2 output schema remains unchanged. No semantic
execution is authorized by this contract or by generating the request.

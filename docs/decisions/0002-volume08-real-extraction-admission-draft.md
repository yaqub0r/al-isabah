# Decision packet: selected Volume 8 extraction and admission

Issue [#89](https://github.com/yaqub0r/al-isabah/issues/89). Status: **concrete
engineering proposal for coordinator review; real semantic execution and new
publication/admission have not been approved or performed by this packet**.
This replaces the earlier open scope question. Do not ask the user to choose
scope again or reapprove reversible draft implementation.

## Settled scope and verified reuse evidence

The user selected the complete legacy Volume 8 collection: 1,550 entries,
including the associated source structure, mapped to the approved authority.
`evidence/inventories/issue-0089-selected-scope.v1.json` records that decision.
Its selected source inventory is the full women's-book inventory: exact file
SHA-256 `001ea04c30fe3e52dec2d38dd49bb087c74a909474715c07e5a41b19237b4062`,
1,550 entries and 205 structural units, source ordinals 10754–12303 across
OpenITI volumes 7–8. This is not a mandate to join records by numeric offset.

A distinct available successor, `al-isabah-public-openiti-5835c18-v8`, is now
verified as a **reuse candidate**, without substitution under historical v4 pins:

| Evidence | Verified result |
| --- | --- |
| Manifest | `8f2573d56c6bac3fce29345952d1e877e0f51cc34bbd329700524d116d7a4104`; all 1,607 member byte sizes/hashes match |
| Index | `adb1c05adaf7fed3cf202ac31d7a66ad58457b18e0fd46bcc30b586ea38e9123`; 1,565 entries overall |
| Selected legacy records | All IDs 10759–12308 present once; all 1,550 recorded source numbers uniquely cover the selected authority inventory |
| Authority binding | Exact OpenITI artifact `bc9db8134c8278973967c91c00324531833f643fc0fb2c8ebe318c9ed4469eea`; each candidate's historical exact-source hash independently reproduced |
| Candidate display integrity | Each displayed-Arabic hash agrees with its candidate record; this is self-integrity, not independent proof of display fidelity |
| Historical validation | Zero errors using owner main-ancestor revision `07a9adae7066bc86cebe121b92fbd334eea525bc` and its exact code, honorific registry and title-profile blobs |
| Candidate states | All 1,550 translated and candidate-labeled eligible; 1,278 machine passed, 272 needs attention, all unreviewed |
| Retained findings | 304: 208 legacy-review findings, 91 honorific semantic reviews, 5 source-text uncertainties; each retained with category and priority on its record |
| Missing structured products | Zero durable candidate name records; 11 `headingsBefore` occurrences versus 205 expected source structural units, with no complete structural crosswalk |

The independently pinned, text-free report is
`evidence/inventories/issue-0089-successor-v8.crosswalk-audit.v1.json`, exact file
SHA-256 `55448e20f1f8ce43a922c3da11f27cebc270a79bdbd4cee97e8d3ae38451b60b`.
The report checks its selected inventory's external byte pin and embedded
content digest, not merely a self-declared hash. Its per-record mappings come
from actual retained candidate records and source-byte verification, not an
invented offset table. Hash consistency still does not prove that a historical
identity choice or English translation is semantically correct.

`issue-0089-successor-v8.historical-validation.v1.json` records exact validator
and dependency pins. Running today's owner validator produced 2,195 diagnostics
under changed honorific/presentation rules; that is not a count of invalid
entries or proof that the original artifact failed. The original pinned validator
passes. New work still needs current substantive assessment where applicable.

Do not equate 11 projected headings with 11 fully mapped source segments or infer
exactly 194 missing translations: their segmentation differs. Establish the
complete 205-unit structural crosswalk explicitly. The 304 findings remain
positive work inputs, not blanket exclusions or evidence of absent human review.
No restricted corpus body, source text, translation, search index, private
locator, model trace or credential was copied into this repository or Elixr.

## Proposed execution choice

**Prefer the verified successor's eligible reusable work plus the pinned approved
source**, retaining its own immutable provenance. Read candidate English as
existing project work, not as a replacement authority. Carry the 304 findings
into per-span extraction/review; repair only demonstrated source/translation
or representation defects. No evidence here justifies retranslation of all
1,550 entries. Neither historical v4 recovery nor legacy raw translation
provenance is mandatory for a wholly fresh source-derived knowledge artifact.

Use issue #89 as the ledger for the selected extraction scope. Before bulk work,
run a bounded first cohort of source ordinals 10754–10763, 11424–11425 and 12303:
13 entries selected mechanically to include the opening, physical-volume boundary
and ending. Include all owned structural units and unresolved findings; choose
additional representative source-critical cases only from verified records as
needed to test vocabulary adequacy. This is a proposed execution cohort, not a
claim that these 13 records have passed semantic review. Expose unsupported
categories instead of fitting them into a convenient predicate.

Proposed exact method ID: `codex-sol-xhigh-knowledge-explicit-host-draft-1`,
execution host Codex, provider `openai` as in the existing registry and subject
to captured host verification, model `gpt-5.6-sol`, reasoning `xhigh`. Stage scope is exactly
`knowledge_extraction`, `knowledge_independent_review`, and
`knowledge_adjudication`. Use fresh first-turn workers with no inherited
conversation and explicit task/worker overrides. Capture actual host settings,
session/turn IDs, stage input/output and checkpoint hashes using the existing
trusted-host pattern. Independent review uses a distinct worker/session and sees
the source, candidate and contract, not extractor deliberation. No external API,
provider, signing service, benchmark or infrastructure is introduced.

The existing registry approves translation stages only. The coordinator can
review this minimal stage-scope decision and the implementing knowledge receipt
binding through repository governance; do not relabel translation receipts or
pretend this method has already been admitted. The current draft exports do not
satisfy production semantic provenance. Captured settings are operational
provenance under a trusted host, not protection against malicious host fabrication
or proof of correctness. Any actual translation remediation follows the existing
translation-stage workflow and its source/witness boundaries.

## Proposed rights and approval authority

Retain the established approved OpenITI authority, exact revision and
CC-BY-NC-SA-4.0 attribution/noncommercial/share-alike limits. Do not claim a new
commercial right, erase attribution, apply the software license to content, or
assume text-free form removes existing conditions. The current-source license
choice is already established; its exact intended structured reuse and consumer
use must be recorded with the admitted artifact, without an expanded grant.
The successor's historical public-working classification and passing validator
are evidence for reuse, not self-authorization of a new assertion export.

Use the existing repository owner `github:yaqub0r` as the named upstream decision
authority and consumer decision authority in their respective repositories.
Record decisions through the existing protected-PR workflow and immutable commit,
with exact source/profile/rights/inventory/schema/snapshot bindings and an actual
owner decision reference. Agent-generated actor labels and PR creation alone do
not prove approval. Existing owner authority is preferred over invented keys,
review organizations or services.

Keep a **separately installed reviewed local trust configuration** on the consumer.
It pins authority IDs, exact upstream and consumer decisions, the decision-chain
head and explicit approve/revoke/supersede state. Before current activation,
verify the head from the owning repository in that same trusted-host operation
and supply an independent `asOf` observation. Offline or stale-head use permits
historical inspection only, never current activation. Keep the observation
watermark monotonic; do not infer freshness from incoming exports. Recheck all
retained active material, not only the newest batch. A restore must revalidate
current trust and cannot revive withdrawn claims. No new database or signing
service is required. This is ordinary repository/operator trust, not a
cryptographic guarantee against a malicious host or a withdrawal after the
recorded check time.

## Ready draft versus remaining execution work

The executable v2 draft now closes all reference collections, pins independent
inputs, exports a declared full snapshot and rejects real mode unconditionally.
The proposed source profile is `profiles/knowledge/volume-08.v2-draft.json`.
Its enums cover the typed families but are not asserted to represent every
source passage. Source inventory, legacy crosswalk and actual historical reuse
are real evidence; every semantic fixture is synthetic.

Before real execution/admission, finish these concrete engineering prerequisites:

1. Admit the exact knowledge-stage method and implement/test its receipt binding;
   translation-stage approval is not silently extended.
2. Define readable normalized names/aliases and richer source-supported literals
   where needed. Hash-only name observations in the draft are insufficient for
   the final full import. Preserve ambiguous identities without forced merges.
3. Build the exact source span partition and all 205 structural dispositions;
   retain source expression upstream. Exhaust and record supported versus
   unsupported material through the bounded real cohort before bulk extraction.
4. Review the exact successor-use/source/rights decision and actual semantic
   snapshot. No real snapshot exists yet; these cannot be replaced with invented
   approval hashes or favorable defaults.
5. Implement explicit current-versus-historical source-version selection before
   production repeatable intake. This draft deliberately rejects multiple source
   versions for one logical record; it supports assessment revisions and
   same-source assertion lifecycle only. It does **not** claim source-correction
   bootstrap/replay readiness.
6. Install exact independently reviewed upstream/consumer decisions and current
   head checks; only then can an eligible real export be activated by Elixr.

Items 1–3 and 5 are reviewable engineering work within the authorized goal, not
reasons to ask the user again for ordinary design choices. A concrete user or
owner decision is needed only where governing instructions actually require it:
new rights/publication scope, a material execution cost/workflow change, or actual
release/admission approval. The root delegation explicitly reserves new real
publication/merge for review; AGENTS.md also requires an explicit rights/release
decision before publication. This draft changes schema/profile paths that can
trigger the active publication workflow on merge, so earlier synthetic-only
publication permission must not be reused. Prepare and review the exact artifact
and impact before requesting any such final decision.


## Frozen checkpoint verification

All 273 repository tests passed, including the 17 shared adversarial vectors and
synthetic audit regressions. Compliance, current public-tree validation, exact
draft export regeneration, selected inventory regeneration and candidate audit
reproduction passed. The historical candidate validator passed with its original
pins. Elixr independently validates the same frozen schema and shared fixtures;
its draft consumer remains synthetic-only. Exact freeze pins are recorded in
`evidence/inventories/issue-0089-knowledge-v2-draft-freeze.v1.json`. This evidence
does not establish real semantic extraction or complete import.

## Draft 2 engineering follow-through

The separate executable `2.0.0-draft.2` contract is documented in
`docs/contracts/al-isabah-knowledge-export-v2-draft2.md`. It adds readable names,
rational quantities, explicit current source/span selection with immutable
historical versions, and scoped extraction/review/adjudication receipt binding.
Its positive fixtures cover source correction, unchanged-source extraction
correction, unchanged-disposition reaffirmation, and an independent cohort
correction that retains the other cohort's original receipts. Draft 1 is unchanged.

The proposed method registry remains inactive, with owner decision not recorded.
`evidence/inventories/issue-0089-knowledge-pilot-preparation.v1.json` prepares the
13 selected real entries, seven owned structural units and four retained findings
as metadata only. Source partitioning and all semantic stages remain unstarted.
The real 1,550-entry import has not been performed. The exact real semantic
artifact and owner release/admission decisions remain required; these engineering
fixtures do not replace them. No merge, publication or model execution occurs.


## Concrete local trial preparation

The next deterministic checkpoint assembles the selected 13 entries and seven
owned structural units into 20 lossless OpenITI blocks, with two separately
identified inherited heading contexts and all four retained findings. Its ignored
input packet and public-safe partition metadata reproduce from the exact approved
source and verified successor record hashes. This is paragraph-marker partitioning,
not a claim that title, name, sentence or semantic boundaries were inferred.
English structural alignment and all semantic review stages remain unstarted.

`scripts/knowledge_pilot_trial.py` provides a separate local-only request,
authorization, stage preparation, host capture and final validation path. The
runbook is `docs/translation/knowledge-pilot-local-trial.md`. It checks the reviewed
immutable feature commit and critical working files, exact packet/partition,
method/profile/schema/runbook pins, source scope and explicit task/worker settings.
Only an actual user response to the concrete ready trial in the coordinating
conversation can authorize its three fresh semantic workers. The coordinator
records that response honestly under the trusted-operator model and separately
supplies its decision digest. This does not authenticate a GitHub identity from
chat or approve merge, publication, production method activation or consumer intake.
No actual approval receipt exists at preparation time.

The upstream-only stage schema and validator require exact source-span coverage,
source-bound names/mentions, typed reference closure, retained-finding dispositions,
positive independent nonclaim reviews, explicit per-record semantic checks, and
honest partial/unresolved states. Final reporting requires all three stage outputs
and actual host receipts. Source expression and mention positions remain in ignored
runtime workflow evidence. A successful local trial still leaves exact artifact
admission and public release to their separate owner decisions after review.

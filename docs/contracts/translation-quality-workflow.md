# Translation quality workflow contract

- **Contract ID:** `translation-quality-workflow`
- **Status:** Active
- **Issue:** [#22](https://github.com/yaqub0r/al-isabah/issues/22)

## Purpose

This contract governs how the Al-Isabah project turns a locked source edition
into an English candidate that is ready for human scholarly review. Its core
quality model is reusable, while the local Al-Isabah profile tightens the
requirements for this work and must not weaken them.

The workflow optimizes for traceable accuracy, not fluent output alone. The
project must exhaust the applicable autonomous checks and witnesses before
asking a reviewer to inspect the work. A reviewer receives a bounded evidence
package, not an unexplained text dump. Human review remains a scholarly and
canonical-promotion gate, but it is not part of the definition of whether the
agent has finished translating a locked scope.

## Ownership boundary

Al-Isabah owns its source decisions, translation policy, translation runs,
comparison decisions, pre-publication review, canonical records, public
provenance, stable identifiers, editorial history, validation, and versioned
releases. Restricted source expression and large immutable evidence may live
in access-controlled storage, but their identities, hashes, roles, and allowed
uses remain governed by this repository.

Downstream products may provide interfaces or consume
checksum-pinned releases. They do not define Al-Isabah's translation policy or
become the scholarly authority by storing or displaying project artifacts.

This contract works with the repository-local
[`source register`](../../compliance/source-register.v1.json),
[`promotion-readiness record`](../../compliance/promotions/available-data.v1.json),
and [canonical publication model](../architecture/canonical-publication-repository.md).
It does not authorize redistribution or declare a translation canonical.

## Public-output invariant

Al-Isabah produces durable translation work only when that work is suitable for
public consumption. Every structured Arabic and English record, name record,
public provenance record, and generated reading presentation must satisfy this
invariant from the moment it is written. Access restrictions are not a
substitute for publication eligibility.

For this contract, a **work product** is a durable, book-facing source,
translation, name, provenance, or presentation record. Translation attempts,
critiques, restricted witness excerpts, model traces, and rights evidence are
workflow evidence rather than work products; they remain private when required
and can never be promoted in place. The pipeline may retain that evidence for
reproducibility, but the only durable records it emits into the book-facing
corpus satisfy this invariant.

This invariant applies to expression, not merely file placement. A public work
product must:

- derive its displayed source text from an artifact classified
  `approved-for-publication` in the repository-local source register;
- contain project-authored English and independently written editorial notes;
- exclude modern introductions, annotations, critical apparatus, indexes, or
  other protected expression unless that exact material is independently
  approved for publication;
- expose no private object locator, restricted witness passage, credential,
  correspondence, or internal model trace; and
- retain honest machine, human-review, uncertainty, and promotion states so a
  public reader cannot mistake a working translation for an approved edition.

Restricted editions, scans, comparison passages, and other private witnesses
may remain controlled research evidence. They may identify a question or
support an independently reasoned decision, but their expression must not be
copied, closely paraphrased, or silently normalized into the public work
product. Facts learned from a witness require an independently written record
and, where applicable, verification against a publication-approved source.

Public consumability is not canonical status. A machine-ready or unreviewed
record may be publicly readable when it satisfies this invariant, while human
approval, compliance approval, book-repository acceptance, and versioned
canonical release remain separate later gates. Public consumability is a
property of the work product, independent of its human-review and canonical-
promotion state.

## Required source bundle

Every in-scope work must identify these roles, including pending roles:

1. a complete human-viewable source authority approved for public use. This is
   normally a facsimile, but may be an integrity-pinned, licensed transcription
   when no reusable same-edition facsimile is available;
2. machine-readable source text approved for publication and bound to that
   human-viewable authority. When the authority is the transcription itself,
   record that limitation explicitly and do not claim facsimile verification;
3. explicitly classified alternative editions, translation witnesses,
   collateral works, and lexical references used to resolve uncertainty;
4. page- or entry-addressable, publicly consumable structured Arabic and
   English with provenance and review state;
5. a human-viewable English presentation generated from the structured
   English, with the authoritative language beside it when useful; and
6. alignment and quality evidence binding all derived artifacts to their exact
   inputs.

Structured English is the editable English authority. HTML, PDF, EPUB, search
indexes, and reader pages are reproducible derivatives and must never be
edited as the source of truth.

## Workflow state machine

The stages run in this order. A stage may iterate, but it may not be skipped or
reported complete without the evidence defined by the work profile.

```text
source_locked
  -> public_source_eligible
  -> source_text_aligned
  -> translation_scope_locked
  -> blind_translation_complete
  -> independent_critique_complete
  -> witness_resolution_complete
  -> adjudication_complete
  -> machine_validation_complete
  -> review_presentation_ready
  -> agent_complete
```

After `agent_complete`, three independent lifecycle dimensions continue:

```text
human_review: ongoing per-record management and correction
compliance: blocked | eligible
canonical_promotion: blocked | promoted
```

### Agent completion

A locked volume or cohort is **done** at `agent_complete` when every applicable
autonomous stage has been exhausted, every substantive unit in the locked scope
has structured English, machine validation has passed or preserved a genuinely
human-only finding as `needs_attention`, and the bilingual review presentation
is ready. The aggregate completion record must report the locked, translated,
and remaining agent-unit counts and must keep human-review coverage in a
separate object.

`agent_complete` does not mean human-approved, canonically promoted, free of
recorded uncertainty, or legally cleared for a new use. Conversely, zero human
reviews does not make an agent-complete scope incomplete. Human review is an
ongoing management state that may correct an agent-complete work product through
the normal immutable correction and supersession cycle.

A human review edit or an increase in review coverage does not itself reopen
agent work. A new agent revision is required only when there is newly available
machine-actionable work: the locked scope expands, a bound source or policy
input becomes stale, or a substantive defect is identified that the autonomous
workflow can address. Earlier completion evidence remains in history while the
new revision is in progress.

### 1. Source lock

Record the work, edition, publisher, date, editor or investigator, volume plan,
extent, pagination, provider landing pages, local or private object IDs,
languages, hashes, rights classifications, and known witnesses. A matching
title is not proof that two artifacts represent the same edition.

The public source authority must be classified `approved-for-publication`
before durable translation work begins. If the best available machine text or
facsimile is restricted, it may be retained only as a private witness while a
publication-approved base is established. The workflow must not create a
translation corpus before establishing source and output eligibility, then
expect a later classification or presentation change to cure it.

Prefer a provider that pairs a complete facsimile and machine-readable text for
the same edition. If a compatible license affirmatively permits publishing an
exact machine-readable artifact but no reusable same-edition scan is available,
the artifact may be the public authority only when its edition, license,
revision, complete hash, and transformation boundary are recorded. Keep an
independent public-domain facsimile when it materially improves recovery or
verification, label it as a different edition, and never infer page identity or
silently borrow its readings. Source and witness acquisition must be recorded
and classified in `compliance/source-register.v1.json` before use.

### 2. Source-text alignment

Map machine text to the most precise stable locations supplied by its approved
authority and to meaningful units such as pages, entries, headings, isnads,
notes, or poetry. When a same-edition facsimile is approved, verify those
locations against it. Otherwise record the lack of facsimile verification as a
visible source limitation and do not substitute locations from another edition.
Measure missing, duplicated, reordered, truncated, and corrupt units. OCR or
text repairs require an append-only ledger containing the original reading,
replacement, evidence, reason, exact location, and hashes.

### 3. Translation-scope lock

Define every substantive unit that must receive English, and explicitly list
excluded front matter, indexes, repeated furniture, or unavailable passages.
Coverage is measured against this locked inventory. Topic-focused cohorts must
also record inclusion and exclusion decisions so later whole-book fills can
extend the corpus without changing existing identities.

The scope inventory must also identify and exclude unapproved modern
paratextual material. Exclusion is explicit and reproducible; deleting
footnotes after translation is not an acceptable substitute for starting from
the publication-approved source authority.

### 4. Blind translation

Produce English directly from the authoritative source without exposing a
modern English witness as an answer key. Bind every result to the source hash,
prompt or policy version, schema version, model identity, reasoning setting,
and run identity. Preserve names, isnads, negation, dates, numerals, entry
numbers, citations, notes, poetry, uncertainty, and cross-unit continuation.

Preserve the semantics of every honorific and devotional formula from the
authoritative source. Record its semantic class, referent scope, grammatical
agreement, observed source form, expanded Arabic form, and target realization.
A versioned language and book profile may use an established equivalent
formula or a supported compact Unicode character. Literal spelling and global
count equality are diagnostics, not proof of correctness.

Never change a formula's referent, grammatical number or gender, family
inclusion, or substantive meaning. If the words are quoted, defined,
contrasted, or analyzed, they are substantive text rather than replaceable
formulaic typography and must remain faithfully translated. An uncertain
classification is an explicit review finding.

Compact characters are presentation values, not the only semantic record.
Keep the exact observed form in provenance and retain expanded Arabic plus a
target-language accessible expansion for fallback, search, copy, and
assistive technology. Use the Al-Isabah translation profile's
[honorific language rules](../translation-profiles/al-isabah.md#honorific-language-profile)
and its versioned machine-readable registry.

### 5. Independent critique

Audit each translated unit independently for omissions, additions, reversals,
name or relationship errors, damaged syntax, structural loss, and unsupported
normalization, including honorific preservation errors. Criticism records exact
concerns and locations; it does not silently rewrite the candidate.

### 6. Witness resolution

Send only material uncertainties to the smallest useful set of witnesses.
Prefer another machine-readable edition of the same work when the locked text
is damaged. Use Urdu, Persian, Turkish, or other established scholarly
translations when they clarify language or context. Use collateral works only
for shared people, reports, citations, or terminology.

Every result records the query, witness role, edition or work identity,
passage, location, retrieval status, and hash. A provider failure is
`unavailable`, never `no_match`. Alternative editions and collateral works may
support a transparent emendation but may not silently replace clear canonical
wording.

### 7. Adjudication

Produce a complete final candidate from the source, blind translation,
critique, and witness findings. Record each material decision and its basis.
Anything not resolved remains explicit on the affected unit; fluency must not
hide uncertainty.

Adjudication also confirms that the resulting expression is independently
written and traceable to the publication-approved source authority. A private
witness may justify a recorded intervention but may not supply public wording.

### 8. Machine validation

Fail closed unless validation proves:

- exact locked-scope coverage and ordering;
- current hashes and complete provenance for every upstream stage;
- public-source eligibility and public-output provenance;
- no duplicated or missing substantive unit;
- preservation of material numbers, names, notes, citations, and boundaries;
- a complete semantic inventory for honorific and devotional formulas,
  including referent scope and grammatical agreement;
- no known meaning-changing, wrong-referent, wrong-number, or wrong-gender
  realization;
- consistent terminology and durable name identities;
- a complete unresolved-item inventory; and
- separation of machine assessment from human-review state.

Where appropriate, use reference-based or quality-estimation metrics such as
COMET or XCOMET, back-translation diagnostics, terminology checks, named-entity
consistency, and targeted entailment or omission tests. Such signals prioritize
investigation; none independently certifies historical or theological
accuracy.

Literal-form and global-count differences may create review findings, but they
do not by themselves make an independently written, rights-compliant working
translation ineligible for public reading. A genuine semantic or agreement
error fails translation readiness and blocks approval and canonical promotion;
the record remains visible with an honest `needs_attention` state unless a
separate public-output invariant fails.

### 9. Review presentation

Generate a readable English surface from the validated structured records. It
must preserve headings, entry numbers, page or entry boundaries, notes,
uncertainty signals, and links to the authoritative source. The presentation
records the structured-English hash so drift is detectable.

Source structure must remain intelligible when a reading surface exposes only
a volume, page range, search result, or other slice of the work. A slice that
begins after the source's governing letter, part, chapter, or numbered section
heading must restate the active hierarchy before its first displayed unit. The
restatement must be derived from the pinned source, explicitly marked as
continued context, and kept distinct from a newly occurring source heading. A
later numbered division must never appear without enough active context for a
reader to understand what preceded it.

Structural events remain in source order and must not be styled as biography or
entry content. Consecutive events are presented sequentially rather than as
competing peer cards. In a bilingual Arabic-English reader, each event pairs
English on the left with Arabic on the right at widths that support columns and
preserves that language order when stacked responsively. Empty divisions are
retained when the source records them, but their notices remain compact and
visually subordinate to populated divisions and entries.

Deterministic validation must cover inherited slice context, the distinction
between contextual restatement and source occurrence, numbered-division
continuity, empty-division preservation, and responsive bilingual presentation.
If the active hierarchy cannot be established from the pinned source, the
affected slice is not presentation-ready.

The ordinary reading presentation contains only public work products. Reviewer
evidence packages remain separate from the presentation and may contain
restricted evidence only in access-controlled storage governed by the local
source register and the restrictions recorded for each witness.

The reviewer handoff includes:

- the machine-readable English candidate and its generated presentation;
- authoritative source text and facsimile locations;
- all remaining uncertainties and interventions;
- stage, coverage, model, witness, and provenance summaries; and
- a searchable durable name and mention index when names are in scope.

Only this state opens human review. When it covers every unit in the locked
volume or cohort, the aggregate scope becomes `agent_complete`. Automation may
mark machine assessment complete or needing attention; it must never set
`reviewed` or `verified`.

### 10. Human review and promotion

Human review records reviewer identity, scope, date, decisions, and unresolved
flags as ongoing management of an already agent-complete work product. Approval
makes a record eligible for local compliance and canonical promotion; it does
not perform promotion itself and it does not determine agent completion.
Promotion follows the local promotion-readiness record, canonical publication
model, and independent repository validation.

Human review may improve or approve a publicly consumable working record, but
it must never be used to retroactively legalize restricted source expression.

## Confidence is evidence, not one percentage

Do not collapse confidence into a single model-generated score. Record a
vector of independently inspectable evidence:

- facsimile integrity and edition identity;
- source-text accuracy and alignment coverage;
- translation coverage, omissions, additions, and semantic findings;
- structural fidelity for names, isnads, numbers, notes, poetry, and citations;
- agreement or disagreement among classified witnesses;
- model and reasoning calibration evidence;
- unresolved-item severity and disposition; and
- human-review scope and state.

Thresholds belong in a versioned book profile or evaluation policy. Changing a
threshold never rewrites the measurements that supported an earlier decision.

## Names and identities

Names are durable JSON data even when a database projection exists. Store a
stable identity, observed forms, normalized English and Arabic forms when
available, aliases, mentions, exact source locations, confidence evidence,
review state, and merge or split history. Generated databases and search
indexes are rebuildable projections.

Names must remain reviewable without requiring application infrastructure.
Operator teaching examples may update a versioned recognition policy and
trigger reassessment, but must not silently rewrite approved identities.

## Reproducibility and resumability

Every autonomous stage must be content-addressed or fingerprinted by all inputs
that affect its result. A checkpoint is reusable only when source, upstream
records, prompt or policy, schema, model, reasoning setting, and attached
evidence still match. Writes are atomic, failures remain retryable, and parallel
shards merge only through a validator that rejects stale, missing, overlapping,
or incompatible results.

Credentials, private object keys, and restricted witness text must not appear
in prompts, public manifests, logs, or canonical content.

## Fail-closed conditions

The workflow does not open human review or promotion when any required input is
missing, stale, unclassified, misaligned, provider-indeterminate, structurally
incomplete, or unsupported by current hashes. The blocked state must state the
reason and the evidence needed to continue.

The workflow must also refuse to write a durable translation record or reading
presentation when the displayed source authority lacks
`approved-for-publication` status, when output contains unapproved modern
editorial expression, or when public-output provenance is incomplete. Existing
records produced under an earlier policy remain quarantined until a
reproducible audit either proves this invariant or rebuilds them from an
approved source bundle.

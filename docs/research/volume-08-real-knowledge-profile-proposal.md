# Proposed real Volume 8 knowledge profile

Issue [#89](https://github.com/yaqub0r/al-isabah/issues/89), coordinated with Elixr
[#29](https://github.com/yaqub0r/elixr/issues/29). Status: **decision proposal,
not active policy, assertion approval or source admission**. The later executable
synthetic draft is specified in `docs/contracts/al-isabah-knowledge-export-v2-draft.md`;
its actual schema is draft-only and real mode remains disabled.
The [eligibility checkpoint](volume-08-eligibility-checkpoint.md) describes the
actual source evidence and outstanding mapping. This proposal must not cause a
synthetic schema to accept real data or imply that extraction has occurred.

## Version and trust decision

Use a new producer-owned `al-isabah.knowledge-export.v2` with a separately
versioned real-source/predicate/rights profile. Keep synthetic v1 and the
Khadijah v1 artifact, validators, admissions and ledgers immutable. The existing
five Khadijah predicates (`nephew_of`, `mother_of`, `son_of`, `brother_of`,
`participated_in`) are useful historical semantics, not an adequate full-volume
vocabulary and not approval for any new occurrence.

An independent Al-Isabah review decision must pin the exact approved semantic
snapshot, source authority/revision, inventory, crosswalk, extraction scope,
vocabulary/profile, source register, current governing policy/schema and
qualification mapping. It must cite substantive machine findings and resolution
or retained qualification states. Hashes prove byte identity, not review or
permission; the snapshot cannot approve its own trust file. Elixr separately
reviews and pins those upstream decisions and exact export file bytes. Neither
producer validity nor a successful consumer coverage helper grants admission.

The current authority is the licensed OpenITI transcription identified in the
checkpoint. The rights decision must expressly address the intended structured
reuse, attribution, noncommercial and share-alike conditions and downstream
presentation, rather than claim that text-free form removes all conditions.
Carry source attribution, author/work/edition/revision identities, exact rights
record digest and mandatory claim attribution. No new legal conclusion or
blanket commercial permission is made here. A reviewed different authority
would need its own inventory, reconciliation and admission, not a changed label.

## Identity, scope and span accounting

Maintain separate opaque identities for authority source units, structural
segments, permanent canonical entries, immutable record revisions, observed
mentions, entities, reports, assertions, events and ambiguity groups. A reviewed
many-to-many source-to-legacy crosswalk records unchanged, split, joined,
unmatched and unresolved mappings. Printed numbers, normalized names and equal
counts never create identity or merge people. New entity resolution decisions
are explicit append-only proposals with their evidence and consequences.

Pin an expected source inventory independently of the semantic export. The
user’s final scope selects an explicitly reviewed inventory; “Volume 8” is
insufficient because the two editions use different boundaries. Separate source
occurrences from inherited heading context and external dependency records.
Approved record coverage, extraction coverage, approved assertions, exported
closure and consumer admission each need their own exact ID set and counts.

Inside Al-Isabah, partition every scoped entry and structural unit into stable,
content-bound semantic spans, accounting for the entire approved source text.
The span map and exact offsets remain upstream; export only opaque span IDs,
source-unit/segment references, input digests, disposition codes and linked
approved assertion/report/ambiguity IDs. The independently reviewed span
inventory and its digest cannot be generated from only successfully extracted
claims. A unit has exactly one accounted outcome for every expected span:

| Outcome | Required evidence | Full extraction effect |
| --- | --- | --- |
| represented | All supported propositions mapped to typed reports/assertions with roles, polarity and qualifiers | Can complete |
| represented_uncertain | All alternatives and unresolved source qualifications represented without selecting a winner | Can complete |
| structural_only | Heading/section/empty-division identity and hierarchy captured, no biographical claim asserted | Can complete |
| nonclaim_form | Reviewed reason such as formula-only occurrence or bibliographic formatting; substantive propositions must not be placed here | Can complete |
| unsupported_semantics | Exact gap category and source-span binding; no placeholder historical claim | Blocks full extraction |
| unprocessed | Work has not exhausted semantic analysis | Blocks full extraction |
| source_or_mapping_blocked | Specific source damage, missing mapping or eligibility defect | Blocks applicable scope |

Substantive poetry, names, isnads, citations, honorific referents and continuations
are not automatically nonclaims. Formula typography need not become a historical
assertion, but its occurrence and any discussed semantic content remain
accounted. Modern apparatus already outside approved source scope needs a
separately justified exclusion; exclusions cannot hide difficult book content.
An entry with no historical assertions may complete only with positively
reviewed nonclaim/structural dispositions, never an empty-array default.

## Required semantic coverage and proposed typed families

A source-grounded review must finalize exact predicates, permitted subject/object
kinds, role vocabulary, cardinality, inverse/direction semantics and limits.
These families are minimum representation requirements, not inferred facts:

| Family | Representation requirement |
| --- | --- |
| Subject identity and names | Preserve observed name/kunya/nisba/alias mentions and proposed identity links with ambiguity; an alias mention does not prove same-person identity. |
| Kinship and social relations | Directed, attributed relations including parent/child, sibling, spouse, lineage and affiliation when attested; preserve conflicting identification and gender/role distinctions. No inference by shared surname. |
| Events and actions | Event occurrences with typed participant roles, temporal/place qualifications and explicit attribution; do not flatten who did, reported, witnessed or was affected by an act into one relation. |
| Reports and transmission | Distinguish a report’s existence from endorsement of its content; preserve ordered transmitters, speaker/attributor, cited work/source and report alternatives without exporting quotations. |
| Source-critical evaluation | Bind the author’s doubt, rejection, correction, competing attribution and evidentiary assessments to their exact report/assertion/identity target and evaluator. Unknown strength stays unknown. |
| Polarity and modality | Positive/negative assertions, reported absence, possibility, conditional or disputed statements remain different values; never convert a negated relation into a positive edge or lack of evidence into negation. |
| Place, time and quantity | Explicit source-supported locations, intervals, approximate dates and material numerals, including uncertainty and competing values; calendar conversion and geographic identification require separate derivation provenance. |
| Structure and cross-references | Ordered book/letter/part/division boundaries, empty divisions, inherited context, continuations and source cross-references; unresolved referents retain candidate sets and closure gaps. |

An assertion records its class (`attested` versus explicitly justified
`inferred`), report/source attribution, polarity, modality, participants and
roles, critical qualification, transmission/evidence assessment, unresolved
alternatives and consumer-use restrictions. “Attested” means the source makes a
statement, not that its historical content is established. A disputed report
must not become an unqualified event. Do not default missing qualifications to
favorable strength or factual use. Source-critical wording that cannot yet be
represented becomes an explicit unsupported gap, not silent loss.

## Lifecycle and completion

Carry machine assessment, ongoing human review, source/public-working status,
canonical promotion, semantic extraction, upstream projection approval and
consumer admission separately. Human review remains unreviewed unless actual
append-only evidence says otherwise; absent review alone is not an upstream
blocker. Concrete defects block under their own reason codes.

Corrections, supersessions, withdrawals, entity splits/merges and affected
report/ambiguity dependencies require explicit immutable successor decisions.
Preserve predecessor evidence and the complete transitive dependency closure.
No retired assertion can return to active use through replay, and retiring an
alternative does not prove another alternative correct. Cross-volume dependency
records stay separate from in-scope coverage counts and do not authorize bulk
extraction of their source volume.

A full-import statement requires independently pinned exact inventory and span
closure, all units processed under the reviewed vocabulary, zero unaccounted or
unsupported gaps, actual upstream eligibility/approval for the semantic records,
complete ambiguity/lifecycle/dependency closure, byte-pinned consumer admission
and verified replay into the intended consumer state. Fully represented
historical uncertainty may remain indefinitely. Metadata inventory, translation
completion, source-page counts, an exporter pass and synthetic tests cannot
substitute for any of those claims.

## Bounded next execution decision

First recover and verify the remediated public-working crosswalk. Reuse eligible
existing structured English and evidence. Select a small source-bound extraction
cohort covering an ordinary biography, a boundary/continuation, explicit
uncertainty or source criticism, name ambiguity, transmission and structural
material; select concrete IDs from verified eligible records, not invented
examples. Review actual unsupported categories to finalize the v2 vocabulary
before scaling to the entire selected volume. Do not acquire new model services
or start translation rework to compensate for unavailable mapping.

The existing runtime registry approves five translation stages; it does not by
itself establish an approved knowledge-extraction stage. The reviewed real
profile must decide the exact extraction/independent-critique/adjudication method
and captured provenance. Any translation remediation follows the existing
explicit task/worker method unchanged. No semantic stage is claimed by this
inventory task. Elixr may test its independent set-coverage arithmetic with
synthetic data while this decision is pending; it must not activate real ingress
or choose a competing source/predicate envelope.

## Assessment revisions and admission currency

Keep the logical source record stable while giving each immutable source revision
and extraction/review/eligibility assessment its own ID. An assessment identifies
its actual reviewer or machine method, status, effective and observed times,
exact inputs, predecessor and correction links. Unknown dates remain explicitly
unknown; importing a subset does not create a new assessment time. Count logical
record coverage separately from assessment versions. Retain prior assessments
and do not silently mutate source-record bytes when review or extraction changes.

A protected PR and immutable commit provide review provenance, not sufficient
artifact eligibility. A separately supplied reviewed admission configuration
must bind the actual eligible artifacts and source/rights/profile decisions.
Before implementing real intake, decide who may approve, how correction,
revocation and expiry/current-validity are represented, which independently
pinned decision chain the consumer trusts, and how a retired or superseded
assessment affects dependent assertions. Never assume the newest subset import
refreshes eligibility for unchanged records. No signing service or database is
required by this proposal.

Missing historical v4 access blocks proof of reuse and the existing identity
crosswalk; it is not inherently a ban on fresh correctly attributed extraction
from the approved source. After the user selects scope, compare verified reuse
with independently deriving knowledge from that source under the reviewed real
profile. A new derivation must carry its own honest source, method, rights and
semantic review evidence; it must not inherit unverified legacy approvals or
be burdened with fictional legacy translation lineage.

## Concrete v2 interface fields for joint review

These are proposed field names and shapes, not an active JSON schema. Missing
required decisions below remain blockers; no wildcard predicates or open prose
bags are proposed. Exact enums and the eventual closed schema need joint review.

| Object | Proposed required fields |
| --- | --- |
| Envelope | `schema`, `schemaVersion`, `mode: real`, `exportId`, `batchId`, `snapshotRef`, `profileRef`, `authority`, `scopeRef`, `inventoryRefs`, `sourceReleases`, `rightsRef`, `policyRefs`, `sourceRecords`, `assessments`, `entities`, `reports`, `events`, `claims`, `ambiguityGroups`, `spanDispositions`, `lifecycleEvents`, `selection`, `coverage`, `payloadSha256` |
| Immutable reference | `id`, `version`, `sha256`, `hashDomain`; where repository-owned, `repository`, `commit`, `artifactId`; no private locator |
| Authority | `id`, `workId`, `editionId`, `revision`, `sourceArtifactSha256`, `sourceManifestSha256`, `verificationBasis` |
| Scope reference | `id`, `sha256`, `sourceInventoryId`, `reconciliationId`, `extractionScopeId`; labels such as Volume 8 are display metadata only |
| Inventory references | `sourceUnits`, `structuralSegments`, `inheritedContext`, `reconciliation`, `semanticSpans`, `supportedVocabulary`; each is an immutable reference |
| Source record | `logicalRecordId`, `recordVersionId`, `recordSha256`, `authorityUnitIds`, `structuralSegmentIds`, `sourceReleaseId`, `sourceLocations`; source locations allow multiple volume/page pairs, never one misleading volume label |
| Assessment | `id`, `kind`, `targetIds`, `inputRefs`, `status`, `actorRef`, `methodRef`, `effectiveAt`, `observedAt`, `predecessorIds`, `findingIds`; unavailable times are null with a reason code, never fabricated |
| Entity | `id`, `kind`, `sourceRecordVersionIds`, `mentionIds`, `identityAssessmentIds`, `ambiguityGroupIds`; observed name/alias representation needs a reviewed field-specific boundary, not arbitrary source snippets |
| Report | `id`, `sourceRecordVersionIds`, `sourceSpanIds`, `attributorEntityIds`, `transmission`, `claimIds`, `criticalAssessmentIds`, `ambiguityGroupIds`; `transmission` is an ordered array of role/entity references, with unresolved positions explicit |
| Event | `id`, `typeId`, `participantRoles`, `placeRefs`, `timeRefs`, `sourceRecordVersionIds`, `reportIds`, `ambiguityGroupIds`; every role is an allowlisted role/entity pair |
| Assertion | `id`, `reportIds`, `sourceRecordVersionIds`, `sourceSpanIds`, `subjectId`, `predicateId`, `objectRef`, `assertionClass`, `polarity`, `modality`, `qualificationRefs`, `assessmentIds`, `attributionRefs`, `ambiguityGroupIds`, `useRestrictionIds`; `objectRef` is a closed tagged entity/event/value reference |
| Span disposition | `spanId`, `sourceUnitId`, `sourceSpanSha256`, `status`, `reasonCode`, `reportIds`, `claimIds`, `ambiguityGroupIds`, `assessmentIds`; span text and offsets remain upstream |
| Ambiguity group | `id`, `kind`, `memberIds`, `sourceRecordVersionIds`, `assessmentIds`, `resolutionState`; full members and dependency closure travel together |
| Lifecycle event | `id`, `kind`, `targetIds`, `replacementIds`, `decisionRef`, `effectiveAt`, `dependencyIds`; no silent replacement, cycles or revival |
| External upstream approval | `approvalId`, `decisionRef`, `approvedSnapshotSha256`, `profileRef`, `authorityRef`, `inventoryRefs`, `rightsRef`, `policyRefs`, `schemaRef`, `assessmentRefs`, `supersedes`, `revokes`, `validity`; supplied through independently reviewed trust configuration |
| Consumer admission | `admissionId`, `decisionRef`, `upstreamApprovalRef`, `exportFileSha256`, `payloadSha256`, `allowedUseProfileRef`, `validity`; consumer-owned and separately supplied |

`selection` separates requested and dependency record/assertion/report/entity/
assessment IDs. `coverage` reports exact expected, represented, eligible,
approved, exported and admitted ID-set digests and counts with named scope;
producer counts cannot claim consumer admission. Assessment-version counts are
never added to logical-record coverage. `sourceReleases` may bind an existing
approved release only if actually used; a fresh source-derived assertion needs
its own approved upstream artifact revision instead of fictitious translation
release provenance. Unsettled policy, profile or admission references have no
usable value: null placeholders are not acceptable in a real admitted payload.

## Minimal semantic execution-method proposal

For review, propose a new knowledge-stage method using the already available
Codex execution host and registry provider `openai`, explicit `gpt-5.6-sol` / `xhigh` task and fresh-worker launches,
matching the current translation baseline operational settings. This is a new
stage-scope approval request, not a claim that the translation registry already
covers extraction or that this model has empirically proved optimal. No paid
API, new provider, infrastructure, benchmark or signing service is assumed.

1. `knowledge_extraction`: a fresh worker receives only the exact eligible
   source records, locked span inventory, approved vocabulary and policy. It
   creates candidate typed propositions, reports, roles, alternatives and one
   disposition per expected span. It cannot approve its own claims.
2. `knowledge_independent_review`: a separate first-turn worker receives the
   same source and vocabulary plus the candidate, but no extractor deliberation.
   It checks each span for omissions/additions, polarity, participant roles,
   attribution, transmission order, names, ambiguity, source criticism and
   unsupported categories. Findings bind exact source/output digests.
3. `knowledge_adjudication`: another distinct worker receives candidate and
   review findings, resolves machine-actionable issues with governed evidence,
   preserves remaining qualified alternatives or blocking gaps and records
   every intervention. Material source/translation repairs return to the
   existing translation workflow, not an implicit extraction-stage emendation.
4. Deterministic checks prove closed shapes, exact span disposition coverage,
   source and method pins, no unauthorized fields, positive review evidence,
   qualification preservation and full dependency/lifecycle closure. The
   separately reviewed upstream approval then admits the exact snapshot;
   successful semantic execution alone does not grant publication/admission.

Reuse the trusted-host provenance pattern only through a reviewed knowledge
stage binding: explicit launch request, host-captured actual provider/model/
reasoning/session/turn, fresh-context evidence, stage input/output and checkpoint
hashes. Independent review must use a session distinct from extraction and
adjudication. Do not relabel a translation-stage receipt or worker-written
model string as knowledge approval. Capture is operational provenance under a
trusted host, not protection against malicious fabrication or proof of semantic
accuracy. The review decision must approve the exact stage IDs, configuration,
evidence schema and artifact output boundary before any such real run begins.

Consumer review clarifications: `exportId` and `batchId` bind one declared
snapshot/batch selection and exact immutable bytes; an existing identity with
different content rejects. `snapshotRef` binds the externally approved semantic
snapshot. Assertion/report/entity source references use immutable
`sourceRecordVersionIds`, while coverage uses `logicalRecordId`. Every generic
`targetIds`/`inputRefs`/`objectRef` value is a typed reference into an explicitly
closed collection or independently pinned registry, not an untyped string.

Before v2 schema approval, define and include all referenced collections:
mentions, typed values, time/place descriptions, qualifications, attributions,
use restrictions and findings. Their shapes, exact source bindings and allowed
fields require review alongside their referring fields. No dangling reference,
unconstrained prose object, implicit favorable value or undeclared registry is
accepted. These collection definitions remain concrete schema work pending the
profile decision; the draft table is not represented as an executable interface.

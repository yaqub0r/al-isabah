# Local provisional knowledge export v2-local1

This companion prepares and verifies real-shaped local artifacts using the rich
frozen draft3 semantic model. It does not dispatch workers, install consumer
trust, publish content, or confer canonical status. The executable adapter
currently consumes the exact existing 13-entry remediation run. Complete Volume
8 extraction and import remains a separate deliverable covering all 1,550
entries and 205 owned structural units.

## Wire and semantic identity

The single producer-owned wire schema is
`schemas/al-isabah-knowledge-export.v2-local1.schema.json`, version
`2.0.0-local.1`. `scripts/knowledge_local_schema.py --check` reproduces it as an
explicit metadata overlay of frozen draft3. Entity, name, mention, report, event,
claim, value/unit, predicate/domain/epistemic, reference, lifecycle, assessment,
source, finding, and coverage definitions remain identical. The graph validator
body also remains identical apart from accepting real artifact metadata status
`proposed` or `approved` instead of `synthetic_only`.

The export and snapshot use `mode: real`, `fixtureClass: not-a-fixture`, and
`admissionClass: local_provisional`. Their schema identifiers, and the inventory
and profile identifiers, end in `v2-local1`. The exact profile comes from
`knowledge_local_projection.profile_value()`: frozen Volume 8 draft3 authority,
scope, method and vocabulary, with only the declared local metadata changes.
An arbitrary caller-supplied profile hash is insufficient. The authority must
remain the licensed transcription; inventory reconciliation may be verified or
explicitly `fresh_derivation_legacy_mapping_unverified`.

Profile `realAdmissionEnabled: true` describes this software capability. It
never grants permission. `realExecutionEnabled` remains false because this
exporter runs no semantic jobs. Rights retain attribution, noncommercial and
share-alike constraints, with `approvalStatus:
requires_exact_local_authorization`. Actual owner identity, scope, allowed uses,
use tiers, partial acceptance, validity and artifact selection must be supplied
through a separately reviewed authorization.

## Historical execution and deterministic projection

`knowledge_local_execution.py` verifies the actual preserved decision, packet,
partition, baseline, three ordered proposals and host receipts, and final report.
A fixed 34-file dependency manifest binds the historical verifier to reviewed
commit `e2a898553e41185098f5fbcc30ed60e8a8816231`. Replay may run at a later HEAD;
changing a historical dependency fails closed. Neither a hardcoded commit label
nor a newly approved export can repair a tampered historical execution.

The new receipt bundle contains the unchanged historical evidence and explicit
exporter-derived projection records. Each projection preserves original stage,
proposal, receipt and decision digests, requested/dependency source coverage,
projection implementation hash and exact input/output checkpoints. The records
say `derivedBy: exporter`; they never claim that workers emitted the canonical
export. Exported receipt artifacts identify these derived records. Full host
history remains upstream.

Every exporter-derived immutable version binds its projection implementation;
receipt versions additionally bind profile, inventory and requested scope.
Authority-derived unit and logical-record identities remain stable. Source
record hashes bind authority, ordinal, owned source-unit/span metadata and
inherited source context. English, candidate record hashes, editorial findings
and prior machine status remain separately bound by the preserved packet and
history; changing them cannot silently revise a source record. A changed source
binding under a reused immutable source ID is rejected on replay.

The projection preserves all three stages' object versions and records explicit
retirement for versions absent from the final adjudicated proposal. Retirement
records reference that exact proposal. For a correction, supply the previous
verified bundle: its immutable objects, receipt bindings and lifecycle events
retain exact IDs, bytes and original decision provenance. Only still-live
predecessors can receive new retirement events. Profile and inventory context
must remain exact; this is not an implicit migration. Historical effective dates remain
unknown when no supported date was captured. Consumer application of an exactly
approved provisional snapshot may use its explicit admission observation as the
operational activation point; this does not fill in the historical date. Known
future-effective changes remain ineligible. The actual admission decision must
disclose this operational policy.

Completion is calculated per record. Blocked spans, unresolved substantive or
coverage concerns, incomplete review axes, and unresolved blocking findings
remain explicit. The two previously reviewed opaque legacy notes have a narrow
source-free classification bound to original concern and marker hashes, IDs,
owning record and spans. Only unchanged classified concerns retain that
management-provenance distinction. New concerns, changed concerns, nonlegacy
links, or another concern on the same span gain no exemption. Missing or
retargeted classified bindings fail closed. This is separate from ongoing human
review; the exporter records unreviewed human state and invents no human act.

A proposed or unresolved nonclaim classification projects as unprocessed until
positively confirmed. A confirmed independent review retains that stage's role;
it is not labeled adjudication.

## External authorization and hash domains

All JSON digests use sorted compact UTF-8 JSON plus LF, preserving array order.
`exportFileSha256` hashes exact file bytes, including formatting. Those bytes
must decode to the same validated payload; reformatted equivalent JSON requires
a new exact file authorization. Duplicate keys and invalid JSON are rejected.

The independent trust object has schema
`al-isabah.knowledge-local-trust.v1`. Its subject binding consists of these exact
12 fields, selected in `knowledge_local_authorization.BINDINGS`:

- `snapshotSha256`, `inventorySha256`, `profileSha256`, `schemaSha256`;
- `receiptBundleSha256`, `exportFileSha256`, `payloadSha256`;
- `methodRegistrySha256`, `sourceRegisterSha256`, `rightsMatrixSha256`;
- `policyBindingSha256`, `selectedScopeSha256`.

The subject is the canonical digest of
`{domain: al-isabah.local-export-subject.v1, binding: <those fields>}`.
The authorization digest is the canonical digest of
`{domain: al-isabah.local-export-authorization.v1, authorization: <full object>}`.
Trust carries that digest in `upstreamAuthorizationSha256`. It never appears in
export, snapshot, profile, receipt bundle or their constituent artifacts. This
prevents direct and indirect authorization hash cycles.

Authorization schema `al-isabah.knowledge-local-authorization.v1` binds an
explicit authority, exact subject, requested and dependency logical records,
allowed uses/use tiers, partial acceptance, effective/observed times, validity,
and recorded actual-user-message origin. Origin fields are provenance claims,
not cryptographic authentication. The verifier requires an independently
supplied authorization digest and authority identity, explicit as-of time and
requested use, and external revocation context. No owner or date is inferred.

Validity is either `until_revoked` with empty `notAfter`, or `bounded` with a
strictly later `notAfter`; `notBefore` cannot precede `effectiveAt`. Expired,
future, revoked, wrong-owner, wrong-artifact, wrong-scope or disallowed-use
requests reject. Partial intake needs explicit `acceptPartial: true`; it cannot
satisfy the full-volume objective. The consumer owns its separately installed
approval/revocation/supersession chain, configuration pin and current head.
Producer trust cannot install that chain or approve its own downstream use.

## Local commands and synthetic conformance

First assemble captured files with `prepare_local_knowledge_history.py
--directory <completed-remediation-directory> --decision <execution-decision.json>
--decision-sha256 <independent-pin> --partition <partition.json>
--report-sha256 <independent-pin> --output <new-history.json>`. This verifies and
packages the unchanged files; it cannot write into the source trial directories
or invent missing evidence. The exporter then consumes that exact history.

`knowledge_export_local.py prepare --history <history.json> --requested-records
<record-ids.json> --directory <new-directory>` validates captured history and
writes immutable candidate snapshot, inventory, profile, receipt bundle, export,
bindings and unsigned authorization request. The directory must be new and
ignored under `.runtime/knowledge/issue-0089`. For a cumulative correction add
`--prior-bundle <previous-receipts.json>`; the prior bundle is independently
replayed before being carried forward. Preparation emits no approval.

`verify --directory <candidate-directory> --authorization <decision.json>
--authorization-sha256 <external-pin> --authority-id <external-owner>
--as-of <explicit-time> --requested-use <approved-use>` verifies exact files and
writes upstream trust plus a verification receipt. Supply each applicable
revocation using `--revoked-authorization-sha256`. This still performs no
consumer admission. Existing files are never replaced with conflicting bytes.

The shared `tests/fixtures/knowledge-export-v2-local1` corpus contains authored
synthetic initial/correction artifacts and authorization negatives. Its README
explicitly disclaims real source work, host execution and approval. Real wire
shapes in these tests do not activate any owner configuration. Producer tests
also cover changed historical evidence, derived projections, raw-byte bindings,
source identity, per-record completion and immutable replay/restore.

## Remaining full-volume execution deliverable

The current pilot request and packet verifier intentionally retain their 13
ordinals. This local exporter alone does not enable extraction of the remaining
corpus. Do not expand the frozen pilot or treat a working partial import as full
coverage.

The minimal later extension is a separately reviewed lossless full-scope
partition and request, covering the selected 1,550 entries and all 205 owned
structures, with explicit owner relationships and inherited context. Partition
cohorts using measured source/input and expected structured-output capacity,
including evidence and review overhead, rather than equal entry counts. One
bounded full-volume authorization should pin the entire partition, code,
method, total scope and accountable cohort IDs; each fresh three-stage cohort
must bind its exact requested records and necessary dependencies under that
authorization. This avoids asking for a new blanket permission per batch.

Each cohort needs exact outcomes, retained concerns and actual host receipts.
The deterministic projection must bind those unchanged receipts to the shared
full inventory/profile, preserve earlier cohort versions and explicit
successors, and distinguish dependency context from extracted coverage. Source,
rights, scope or method changes require an explicit updated decision. Final
reconciliation must prove exact entry/structure coverage and actual semantic
outcomes across all cohorts; counts alone, synthetic fixtures and provisional
partial admission cannot establish completion. No new workers or source
interpretation are authorized by this extension description.

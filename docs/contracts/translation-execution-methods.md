# Production semantic execution methods

- **Contract ID:** `translation-execution-methods`
- **Status:** Active
- **Issue:** [#76](https://github.com/yaqub0r/al-isabah/issues/76)

## Admission, not a model recommendation

Production semantic stages accept only an exact method ID active for that stage
in the integrity-bound execution-method registry discovered through the current
machine governance reference. A method includes provider, exact model identity,
reasoning setting, orchestration mode, and explicit configuration origin. A
family name, alias, default, inherited setting, or worker assertion is not an
approved method. This contract is provider-neutral; the registry owns the
concrete approvals. Deterministic parsing, hashing, rendering, and validation
are not semantic model stages and do not acquire a model requirement.

The governed semantic stages are blind translation, independent critique,
witness-resolution judgment (including the not-required rationale),
adjudication, and bilingual name inventory. Approval for one stage does not
authorize another. A future method can have a narrower stage scope.

## Effective runtime binding

Packet v2 and stage-provenance v2 require an `execution` envelope for every
completed semantic stage. Its requested configuration must be explicit and
exactly match the stage's active method. Its independent attestation binds the
effective configuration, method and registry hash, run and session identities,
input/output hashes, checkpoint fingerprint, telemetry digest, issuance time,
and context-separation observations. The checkpoint already binds source,
policy, schema, upstream output, and attached evidence. A changed checkpoint
requires a new attestation; old receipts cannot certify a repaired output.

The runtime attester must observe the effective settings from the execution
host or provider, not copy labels from the worker, task prompt, intended model
selection, or packet. It must bind the resulting output to the observed run
before signing. For critique and name inventory it must independently observe
fresh context and prior-stage exclusion. The existing context self-report is
still checked for consistency but is not an authentication mechanism.
An independent stage cannot reuse its upstream stage's attested session ID.

Attestations use OpenSSH Ed25519 signatures over canonical JSON: UTF-8,
sorted keys, compact separators, one terminal LF, and namespace
`al-isabah-runtime-v1`. Verification uses `ssh-keygen -Y verify` with a public
key selected only from the reviewed active registry. Worker-selected keys,
trust-store overrides, unsigned telemetry, self-report, missing configuration,
and signature or telemetry/provenance mismatches fail closed. Verification
failure or an unavailable verifier is never a successful run.
The signature transport follows the
[OpenSSH verification interface](https://man.openbsd.org/ssh-keygen#Y).

The signing key must be controlled by a trusted runtime service or operator
outside the translating worker's writable and credential boundary. This
repository contains no signer, private key, or claim that a host adapter has
already been deployed. The initial registry deliberately reports
`runtimeTrustStatus: unprovisioned` with no enrolled keys. It approves a method,
not an operational attester. Therefore new production semantic completion is
blocked until a separately reviewed registry version enrolls a real attester
and a decision record pins its authority ID and public-key digest. Synthetic
tests use ephemeral keys and are not production enrollment or quality evidence.

Signatures authenticate the enrolled authority's statement, not the truth of
arbitrary telemetry. Enrollment review must establish effective-setting
observation, output/run binding, context separation, key custody, and a
revocation procedure. Key rotation or revocation requires a new registry version;
old receipts remain evidence under their original pin but do not authorize new
production work. Raw telemetry and signing material remain outside public Git.

## Decisions and evaluation evidence

The public-safe append-only decision area records exact configuration, stage
scope, date, available prompt/policy/schema/source/cohort hashes, evaluation
design, blinded comparison details, substantive error categories, unresolved
and witness load, usage/cost/latency when measured, decision basis, limitations,
and supersession lineage. Missing measurements are null, not zero. A governance
approval is not empirical proof; a provenance-safety rejection is not a measured
translation-quality failure. Unevaluated and inconclusive are distinct states.

Do not publish Arabic or English samples, restricted witness passages, raw
traces, deliberation, credentials, or private locators in these records. Closed
schemas and value scans are required; they do not replace public-boundary review
of independently written summaries. The book proposal/distribution allowlist
is unchanged: permission to record model identifiers here does not expose them
in reader-facing artifacts.

To add or change a method:

1. Add a new immutable decision/evaluation record; never edit an earlier record.
   Link superseded records by identity, path, and hash. An explicit superseded
   decision or a successor's supersession edge retires an earlier approval.
2. Add the next versioned registry file. Pin its predecessor and retain every
   earlier evaluation reference unchanged. Active methods must match exact,
   unsuperseded approvals and stage scopes. Enrolling an attester also requires
   a decision binding its public-key digest.
3. Review the evidence limitations, runtime trust boundary, registry update,
   schemas, policy binding, and machine-reference pin together through a PR.
   No automation or evaluation score approves a method by itself.

Issue [#49](https://github.com/yaqub0r/al-isabah/issues/49) is a possible future
evidence producer. This contract neither expands nor completes that issue and
does not treat its proposed harness as an already controlled evaluation.

## Historical and consumer boundary

This is a breaking consumer-interpretation change: machine reference v3.0.0,
policy binding v4, and packet v2 apply to new work. Existing packet/schema v1,
policy bindings v1-v3, governance references v1-v2, decisions, source bytes,
and released products remain unchanged. Validate an old packet with the code
and governance at its original immutable commit; it is not a new v2 production
submission. Deterministic rebinding or relabeling cannot invent a past runtime
attestation. Existing public releases retain their pinned validation path and
are not reissued by this change.

Run the full tests, compliance validator, execution-governance validator, and
public-tree validator. New packet validation and shard merging must exercise
runtime admission, not merely parse the envelope. A downstream client must pin
the new machine reference at an immutable commit and verify all listed hashes
before executing new production work. Release creation remains separately
authorized; this contract changes no publication trigger or setting.

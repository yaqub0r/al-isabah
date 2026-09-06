# Production semantic execution methods

- **Contract ID:** `translation-execution-methods`
- **Status:** Active
- **Issues:** [#76](https://github.com/yaqub0r/al-isabah/issues/76), successor [#78](https://github.com/yaqub0r/al-isabah/issues/78)

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

Packet v3 and stage-provenance v3 require an `execution` envelope for every
completed semantic stage. Both the production task and each semantic worker
must be launched with explicit model and reasoning overrides matching the
stage's approved method. Neither parent settings, defaults, inherited context,
nor instructions in a prompt establish the effective settings.

The coordinator records the actual launch overrides and captures effective
provider, model, reasoning, session and turn identities from the selected
host-written metadata, separately from worker-authored output labels. The
minimal evidence binds those records to the method, registry hash, stage/run,
input/output hashes and checkpoint fingerprint. The checkpoint already binds
source, policy, schema, upstream output and attached evidence. New or changed
outputs/checkpoints require a new capture binding; old evidence cannot certify
repaired output. Historical rebinding never manufactures new execution.

Semantic workers start with explicitly excluded inherited conversation context.
Capture verifies first-turn metadata and rejects recorded forks. Independent
critique and name inventory must use sessions distinct from their prior stages
and from the coordinating production task. Existing context receipts must still
match their input/output/run hashes. Fresh-context metadata and launch controls
are operational evidence, not a semantic audit of the contents of a prompt.

This is **unsigned operational provenance under a trusted-local-host and
trusted-coordinator assumption**. It detects omissions, accidental setting
inheritance, stale bindings and inconsistent labels. It does not authenticate
the host or protect against a malicious host/editor consistently fabricating
metadata. A worker label alone is insufficient; a hash is not a signature.
No external attester, enrolled key, signing service, new benchmark, pilot
translation or additional semantic pass is required. Failure to capture actual
host settings remains fail-closed, never a reason to copy intended settings.

The local `host_runtime.py` request, capture-launch and bind commands implement
the current host adapter; the runbook specifies literal launch overrides and
the private-data boundary. Only caller-selected session metadata is read.
The adapter retains no prompts, responses, raw logs, private paths or secrets.
An unsupported or incomplete host metadata format fails closed and requires a
reviewed adapter update, not a speculative service dependency.

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
   unsuperseded approvals and stage scopes. Trust-semantics changes require an
   explicit successor decision, not silent reinterpretation of an old record.
3. Review the evidence limitations, runtime trust boundary, registry update,
   schemas, policy binding, and machine-reference pin together through a PR.
   No automation or evaluation score approves a method by itself.

Issue [#49](https://github.com/yaqub0r/al-isabah/issues/49) is a possible future
evidence producer. This contract neither expands nor completes that issue and
does not treat its proposed harness as an already controlled evaluation.

## Historical and consumer boundary

This is a breaking consumer-interpretation change: machine reference v4.0.0,
policy binding v5, registry v2 and packet/provenance v3 apply to new work.
Registry v1, packet schemas v1-v2, signed-attestation schema v1, policy bindings
v1-v4, governance references v1-v3, decisions, source bytes and releases remain
unchanged. Decision 0006 supersedes 0001's mandatory signing design without
claiming that the approved model needs requalification or failed a benchmark.
The former signed verifier remains available for historical regression tests;
validate old packets using code and governance at their original immutable
commit. Never reinterpret a historical signed receipt as unsigned new work or
relabel an old high run as the approved baseline.

Machine reference v5.0.0 and policy binding v6 succeed those discovery and
policy artifacts for Issue 82 so the next immutable title-decision profile can
be bound without changing Issue 80. The packet-schema document advances to v4
only to hard-pin the v6 policy path; packet, shard, stage-provenance and tool
data remain version 3.0.0, and registry v2 plus the approved execution method
remain unchanged. References v1–v4, bindings v1–v5, and packet schemas v1–v3
remain immutable historical provenance.

Run the full tests, compliance validator, execution-governance validator, and
public-tree validator. New packet validation and shard merging must exercise
runtime admission, not merely parse the envelope. A downstream client must pin
the new machine reference at an immutable commit and verify all listed hashes
before executing new production work. Release creation remains separately
authorized; this contract changes no publication trigger or setting.

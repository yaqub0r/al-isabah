# Bounded local knowledge pilot

Issue #89. This runbook prepares and validates local workflow evidence for the
13-entry trial. It does not enable a production exporter, public promotion,
consumer intake, merge, or release. The proposed method is approved for this
bounded local action only if the actual user explicitly authorizes the concrete
ready trial in the coordinating conversation.

## Ready inputs

Run `scripts/assemble_knowledge_pilot.py` with the exact existing approved source
and verified successor candidate root. These are local CLI inputs, not public
metadata. The assembler verifies the pinned authority, candidate manifest and
selected record hashes, approved-source unit hashes and parser version. It copies
only the selected existing English, retained findings, approved Arabic source
units and inherited heading context into ignored runtime workflow evidence.
Candidate English is reusable project work to be checked against the authority;
it never replaces the Arabic authority. No translation is altered or created.

The deterministic partition splits only at explicit OpenITI paragraph markers.
It preserves every byte of each parser-bound raw source unit in order, including
markers and whitespace. In this cohort the source exposes 20 such blocks: 13
entry units and seven owned structural units. Two inherited heading contexts are
provided separately. A raw entry-marker block is not a governed personal title;
its whole content must be assessed. No sentence, identity or title boundary is
inferred from typography. Finer semantic spans may be proposed later through an
explicit source-bound revision if the pilot shows they are needed.

The runtime packet and public-safe partition metadata are immutable outputs.
Re-running with `--check` verifies them. Counts and hashes do not claim semantic
coverage. All four retained findings must receive explicit output dispositions.
The pilot's structural source coverage is prepared; English structural alignment
still requires extraction and independent review.

## Actual operator decision

The coordinator first generates a decision request at the exact reviewed feature
commit using the packet, partition, method, profile, schema and policy hashes.
It presents the 13 source ordinals, the three stages, exact Codex task/worker
settings (`openai`, `gpt-5.6-sol`, `xhigh`, fresh non-forked workers), maximum three
workers, and local-only outputs. No automatic bulk run or publication follows.

Only after the actual user answers affirmatively does the coordinator record the
minimal decision receipt. Its origin refers to the coordinating conversation and
actual user turn/message when available. Agent delegations, tool outputs,
automatic continuations and the earlier scope-selection answer are not approval.
The gate requires a separately supplied expected decision digest and checks all
request pins and scope. The real decision file is absent before approval.

This is operator authorization under trusted local host/coordinator assumptions.
It is not cryptographic authentication of a GitHub identity from a chat, and it
is not an owner publication/admission decision. Do not invent authenticated fields,
signatures or an unavailable user message ID. A user-turn reference may be empty
when the host does not expose it; the conversation reference and coordinator's
honest record of the actual user authorization remain required. Synthetic test
receipts are explicitly labeled and cannot authorize real packet execution.

## Three stages

Prepare each stage only through the gate. Each immutable stage input binds the
packet, partition, approved decision, profile/schema, exact method and preceding
stage output/receipt. Worker launch requests must use explicit model and reasoning
settings and fresh context. The executing task uses the same explicit baseline.
Actual host session/turn metadata is captured after execution; self-written model
labels do not count. Distinct stages use distinct first-turn worker sessions.

1. `knowledge_extraction`: inspect every scoped source block and existing English.
   Produce typed entities, names, mentions, claims, reports, transmission, events,
   quantities, time/place, attributions, qualifications and uncertainty where
   supported. Mark unsupported material explicitly. Never invent facts to fit a
   predicate. Preserve the source author's evaluations as attributed judgments.
2. `knowledge_independent_review`: receive the locked input plus the extraction
   output, without extractor deliberation. Independently check source identity,
   English fidelity, span coverage, names/identity, negation, numbers, isnads,
   qualifications, structure and retained findings. Return a complete revised
   proposal plus explicit concerns; do not hide defects with smoother prose.
3. `knowledge_adjudication`: inspect the source, candidate and both structured
   outputs/concerns. Return the complete adjudicated proposal, retaining unresolved
   concerns and unsupported vocabulary. No witness acquisition, translation
   remediation or new corpus scope is implicitly authorized by this trial.

Use `schemas/knowledge-pilot-stage-output.v1.schema.json`. Stage output remains
private workflow evidence. Names are bounded readable forms. Private mention
positions bind exact source substrings and hashes; positions and source expression
never cross the consumer boundary. Changed semantic objects receive new stage-scoped IDs; unchanged objects may retain
their IDs only with identical content. Use the `urn:al-isabah:trial:` namespace for
new proposal identities. No synthetic identities or human-assessment IDs are
created in real trial output. Positive nonclaim dispositions receive an explicit
per-span rationale and separate confirmation at review/adjudication.
All references resolve, spans are exhaustively
accounted for, reciprocal claim/report links close, and positive completion cannot
coexist with unprocessed/unsupported spans or unresolved record checks/concerns.
A partial result is useful evidence for vocabulary or source work, not completion.

Record each stage only after deterministic validation and capture of its actual
host metadata. The receipt binds the immutable output, input, decision, method,
source scope and predecessor receipt. The local trial receipts are a separate
schema from production receipts and cannot be relabeled as approved production
execution. Reuse or later admission requires an explicit review of their exact
provenance and governing decision; earlier evidence is never rewritten.

The final local handoff contains the three outputs/receipts, deterministic
validation report and an honest list of remaining source, translation, vocabulary
or adjudication work. It is not a public reading product or an invitation to stop
autonomous work after a first draft. Actual artifact admission and public release
remain separate, exact repository decisions after the artifact exists.


## Commands for the reviewed feature commit

Generate the concrete request after committing the gate and its reviewed inputs:

```powershell
python scripts/knowledge_pilot_trial.py request
```

This creates an unsigned decision **request**, never an approval. After the actual
user response, the coordinator writes `decision.json` in the ignored trial
directory and independently supplies its canonical digest to subsequent commands.
For each stage, use the exact stage name from the request:

```powershell
python scripts/knowledge_pilot_trial.py prepare --stage knowledge_extraction --decision .runtime/knowledge/issue-0089/trial/decision.json --decision-sha256 <actual-approved-decision-digest>
```

The prepared input supplies the full private packet, output schema, profile,
instructions and exact launch request shapes. The coordinating task records the
actual explicit tool launch arguments as task/worker request files. It supplies
the existing host session log and exact session/turn IDs to `capture`; the capture
helper reads only the metadata needed to verify settings, never emits raw logs,
and never substitutes a worker's claimed model label:

```powershell
python scripts/knowledge_pilot_trial.py capture --stage knowledge_extraction --decision .runtime/knowledge/issue-0089/trial/decision.json --decision-sha256 <actual-approved-decision-digest> --task-request <actual-task-request-json> --worker-request <actual-worker-request-json> --task-log <local-task-session-log> --task-session <actual-task-session-id> --task-turn <actual-task-turn-id> --worker-log <local-worker-session-log> --worker-session <actual-worker-session-id> --worker-turn <actual-worker-turn-id>
```

Repeat prepare/capture for independent review and adjudication, then run `report`
with the same decision arguments. Reporting requires all three valid stage
outputs/receipts and keeps partial results, concerns and unreviewed human state
explicit. The CLI does not dispatch a model or send messages itself. Runtime
inputs, outputs and decisions must remain under ignored
`.runtime/knowledge/issue-0089/`; a public output directory is rejected. Use a new
`--directory` beneath that root for a newly reviewed commit; conflicting earlier
outputs are preserved rather than overwritten.

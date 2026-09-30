# Bounded local draft3 remediation

This is a separately authorized three-stage continuation of a completed local
trial. The old three workers are exhausted. An unsigned request is not approval.
This runner does not launch models, admit consumer data, or publish anything.
The full objective remains all 1,550 Volume 8 entries and 205 owned structure
units; this bounded pilot alone cannot establish that objective's completion.

Use `scripts/knowledge_pilot_remediation.py` with actions `request`, `prepare`,
`capture`, and `report`. Every action requires `--original-directory`,
`--recovery-directory`, a distinct ignored `--directory` under
`.runtime/knowledge/issue-0089`, and an independently reviewed
`--baseline-report-sha256`. Packet and partition default to the existing locked
pilot inputs. Historical input/output/receipt files are read only.

The request pins the committed code, draft3 profile, private output v2 schema,
this runbook, original three stages, report, final adjudication, and original
concern IDs. Prepare and capture require `--decision` and independently supplied
`--decision-sha256`. The decision has schema
`al-isabah.knowledge-remediation-decision.v1`, exact `request`, `approval:
approved`, and the same trusted coordinator's actual user-message origin fields
as the original gate. Never create an approval from agent messages. The new
origin uses a real user-turn reference when the host exposes one; an empty
reference preserves explicit unavailability and does not create an approval.
The new
decision must explicitly authorize three fresh sequential workers using the
pinned model/provider/reasoning settings. No old decision or worker is reusable.

Run the stages in order: knowledge extraction, independent review, adjudication.
Select the actual stage identifier printed in the request with `--stage`.
Prepare writes `<stage>.input.json`. Supply `<stage>.proposal.json`; capture
requires the actual `--task-log`, `--worker-log`, `--task-request`,
`--worker-request`, `--task-session`, `--worker-session`, `--task-turn`, and
`--worker-turn`. The task/worker observation and parent linkage must pass the
existing host verifier. Report replays all three stages and receipts. Files are
created exclusively; conflicting existing files are rejected.

## Worker output and preservation

Read the embedded locked packet, complete historical baseline, profile, output
schema, and prior remediation proposals. Use only this supplied evidence.
Do not acquire witnesses, reinterpret sources outside the authorized scope,
silently alter source bytes, translate new content, or infer agent-origin status.
Preserve supported knowledge, explicit uncertainty, devotional formulas, source
qualifications, names, report routes, event participants, and inherited findings.
An unresolved scholarly question is not automatically an extraction failure.
Describe source, provenance, fidelity, and representation residuals precisely.
The original generic legacy marker proves only inherited unresolved presence;
its lost locator is a provenance gap, not evidence of a particular omitted fact.

The proposal is a closed object with these five fields:

* `schema`: `al-isabah.knowledge-remediation-proposal.v1`.
* `output`: a complete private `al-isabah.knowledge-pilot-stage-output.v2` object
  for this stage and exact stage-input digest.
* `baselineSha256`: the input's exact baseline digest.
* `concernOutcomes`: exactly one row for every original concern, with
  `baselineConcernId`, `baselineConcernSha256`, `outcome` (`resolved` or
  `residual`), and a substantive `rationale`. Preserve its ID, category, and
  source-span scope in output concerns; set its status to resolved or open to
  match the outcome. New concerns may be added.
* `objectSuccessors`: exactly one row for each baseline object absent from the
  new output, with typed `before`, `beforeSha256`, typed `after`, and `rationale`.
  A successor has a new ID in the same collection; entity logical identity stays
  stable. Multiple original objects cannot collapse into one successor. Reused
  IDs must retain identical content. Do not silently delete baseline objects.

The receipt hashes the entire proposal, including both coverage ledgers.
Historical v1 claims are never relabeled as v2: their changed typed-subject shape
requires new immutable IDs and explicit successors, with all references updated.
Use the deterministic explicit-patch successor helper when appropriate; it is
not a semantic authority and cannot choose corrections or grant approval.

## Draft3 semantic constraints

Use only the closed embedded profile. Claim subjects are typed entity/event
references. Predicate domains and every epistemic policy dimension must pass,
including every use tier. Quantities use profile-owned short units, retain exact
rational amounts and approximation flags, and never invent animal participants.
Place wrappers refer to place entities. Ordered events require explicit source
order; conditions are conditional, requests are not fulfillment, and pledges are
not transfers. Granted place does not invent a legal right.

Status predicates retain source attribution and exact notice record versions.
Companionship absence of evidence is notice-scoped, never a categorical denial
or a factual-spine assertion. Cross-record attestation is allowed only with
matching attesting source spans, report author, source artifact, and evaluator
qualification for the exact claim. Preserve supported and disputed reports;
structural validation cannot prove semantic truth.

Run the existing source identity, English fidelity, structure, honorific, name,
negation/number/transmission, and qualification review axes. Every original
concern needs a concrete outcome even if the concern is a residual provenance
gap. A `partial` result is honest when strict completion checks remain unmet.
Human review remains separate, ongoing metadata. Global real execution and
consumer admission flags remain disabled; local authorization does not change
them or authorize the remaining full-volume import.

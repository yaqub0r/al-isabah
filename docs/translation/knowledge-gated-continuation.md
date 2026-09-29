# Capacity-blocked gated successor continuation

This issue-89 supplement preserves the approved a56 successor request, decision,
extraction proposal, ledger, Gate 1 and receipt. Extraction passed known-obligation
Gate 1 and is not rerun. The attempted independent-review worker reached a host
model-capacity error without a proposal or receipt. Its first-turn host metadata,
raw-log hash and exact failure status count as one launch. The original
three-worker authorization cannot cover replacement review plus adjudication.

The continuation has a separate request, current committed code identity and
exact user-origin decision. A preview is deliberately non-authorizable until
the new code has been reviewed and committed. Its exact request binds one
canonical absolute continuation directory; changing that directory requires a
new request and decision, so a failed slot cannot be reset by moving files.
The historical runner is checked
against a56 separately; its original authorization is never relabeled as
approval of the fourth launch. The new decision permits at most two additional
fresh nonforked GPT-6 Sol/high workers in order: replacement independent review,
then adjudication. Four total sessions include successful extraction and the
failed review. The same observed parent task must be used. Do not automatically
retry another failure, change model or effort, or reuse any earlier session.

For each remaining stage, prepare its input and persist exactly one `reserve`
record **before** dispatch. Wait for the host's terminal result, then `bind`
the actual first-turn session and terminal log to that reservation exactly once.
If the terminal result cannot be determined, bind it as `unknown` and stop.
A pending reservation, unknown or failed
attempt consumes the stage slot; it cannot be rebound or retried under this
decision. `capture` requires the bound attempt to have completed successfully,
with the same observed worker identity. Adjudication preparation requires the
replacement review's valid receipt, reservation and attempt. The final envelope
reconciles both slot records and all four launches. If replacement review fails,
stop and obtain a new decision instead of dispatching another worker. This
local mechanism cannot detect launches made outside the recorded workflow;
operators must not launch out of band.

Host terminal metadata may mark an assistant's final response as `final` or
`final_answer`; both require a matching successful `task_complete`. If an older
validator persisted `unknown` despite a successful terminal log, preserve that
attempt and use a separate linked correction preview. The preview binds the
original request, decision, reservation, unknown attempt, proposal and raw-log
hash. It does not rewrite the attempt, approve changed code, issue a new slot,
or authorize adjudication. Resolve the changed-code authorization boundary
before using the correction to capture a receipt or launch the remaining worker.

For the pinned issue-89 `final_answer` host log, the execution-repair path uses
the original exact user decision as its scope authority. After the classifier
fix and this runbook are reviewed and committed, generate `repair-preview`
outside the canonical continuation directory. It independently checks the
original committed code and current corrected code, the original decision,
the saved review input, proposal, reservation, `unknown` attempt, and raw host
log. A coordinator engineering review changes only the record's `status` from
`pending_review` to `reviewed` and pins the exact resulting JSON digest. The
record's origin is `trusted_coordinator_engineering_review`; it is not a new
user-message approval. Supply that record and digest with `--repair-record`
and `--repair-sha256` on later commands. The fixed review may then receive a
linked corrected receipt without another review launch. Its original attempt
remains `unknown` on disk and in the launch ledger. The corrected receipt and
subsequent adjudication input, receipt, and report bind the repair digest and
corrected commit. Only the already approved fourth slot, adjudication, can be
reserved and launched. The ordinary path still requires its exact committed
request and decision, with no repair override.

The replacement review receives the exact extraction ledger, Gate 1 and failed
attempt metadata. The adjudicator also receives the review proposal and receipt.
Each new receipt binds the continuation decision, failed attempt and prior launch
ledger. Adjudication must submit an exact final ledger and deterministic final
reconciliation. The final envelope distinguishes the extraction Gate 1 result
from retained final coverage and lists all four launch attempts. A valid review
rejection may leave final coverage `not_established`; extracted candidates alone
cannot be reported as retained reviewed progress. Human scholarly review remains
unreviewed. No export, consumer admission, public release or full-volume work is
authorized by this supplement.

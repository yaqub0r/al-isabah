# Execution decisions and evaluations

These closed, sample-free evidence summaries are governed by
[`translation-execution-methods`](../../docs/contracts/translation-execution-methods.md).
They contain configuration identifiers, independently written decision summaries,
aggregate measurements when available, and hashes—not translation samples or
runtime traces. Null measurements mean unavailable, not a successful zero-error
evaluation. All initial decisions are governance or incident records, not
controlled quality experiments.

Records are append-only. Add a successor record with exact supersession links
and a new versioned active registry; never edit or delete a prior record. The
registry's predecessor chain retains all historical evidence references. Its
initial approved method did not enroll a runtime signing authority. Decision
0006 and registry v2 supersede that signing prerequisite with explicit launches
and captured host settings under a trusted-host assumption. Earlier records
remain unchanged; no quality benchmark or signing service is required.

# Bounded successor coverage gate

This is a proposed Gate 1 check for issue 89's 13-record pilot. It does not
authorize another worker, accept a source interpretation, grant consumer
admission, or change publication state. The saved 20-row obligation index is a
draft, not an approved or exhaustive source-atom ledger. A later accountable
decision must independently pin a reviewed JSON seed before use.

The reviewed seed names every **known** obligation, its owned packet record and
coarse span, its origin digest, its kind (`semantic_gap`, `carry_forward`,
`provenance_gap`, or `candidate_only`), and any specific permitted unresolved
reasons. A semantic gap also names one or more expected approved predicate IDs,
event type IDs, value kind/unit pairs, or the explicit new-route requirement.
Only a new object matching a seed alternative counts for that obligation; an
unrelated new act on the same coarse span does not. The seed binds the source
artifact, packet, final baseline output, profile,
and originating report. The caller supplies each digest independently; a
worker's ledger or candidate output cannot authorize its own seed. Schema:
`schemas/knowledge-coverage-gate.v1.schema.json`.

An extraction worker may submit its candidate finer source anchors, complete
proposal graph, and expanded obligation ledger together. It need not wait for
an independently reviewed source-atom ledger or human scholarly review. Every
known obligation needs one outcome. `represented` and
`qualified_uncertainty` require existing candidate object IDs and source
anchors verified against exact packet bytes. `unresolved` requires one of the
seed's specific reason codes. A candidate-only English label cannot become a
source-backed object by changing its ledger status. A coarse anchor only proves
the packet contains those bytes; independent review must still assess whether
it supports the proposed act, route, relation, and completeness claim.

Gate 1 reuses the current private output and proposal validators, including
the baseline concern ledger, explicit object successors, immutable IDs, closed
profile, source ownership, and structural qualification checks. It counts
progress only when a known `semantic_gap` outcome links a new modeled claim,
event, report route, or value whose semantic core was absent from the saved
baseline. A copied graph, ID migration, or changed concern label contributes no
progress. Explicit successor mappings must preserve the semantic core and
claim qualifications. Qualified uncertainty is reported separately from an
unresolved extraction or provenance gap. Gate 1 always reports
`partial_progress`, never exhaustive truth, admission, or release. Human
scholarly review remains `unreviewed`; pending independent semantic review is a
separate state.

The CLI `scripts/knowledge_coverage_gate.py` takes the locked `--packet` and
`--partition`, exact `--profile`, saved `--baseline-input` and
`--baseline-proposal`, new `--candidate-input` and `--candidate-proposal`,
reviewed `--seed`, worker `--ledger`, six independently supplied SHA-256 pins
(`--source-artifact-sha256`, `--packet-sha256`,
`--baseline-output-sha256`, `--profile-sha256`, `--seed-sha256`,
`--origin-report-sha256`), and an ignored-runtime `--output` path. It writes
only a new metadata-only gate result. A failed check writes no result. The
private packet, proposals, and source passages remain outside this repository.

Independent review follows extraction and must check the source/ledger's
completeness and the semantic relevance of each candidate anchor and object.
Byte containment and a matching seed discriminator do not establish factual
entailment; independent source review must decide whether the passage actually
supports the proposed meaning.
Adjudication can follow only if the separately authorized conditional run
permits it. One future exact user decision may cover at most three fresh
GPT-6 Sol/High workers, with review and adjudication conditional on Gate 1;
this document itself grants no such decision.

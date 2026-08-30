# Al-Isabah contract index

This is the first stop for any agent changing source, translation, review, or
canonical content in this repository. Read every applicable local contract and
profile before changing governed records. External applications may mirror or
execute these rules, but they are not policy authorities.

## Translation entry point

For every Arabic-to-English translation task, read these documents in order:

1. [`translation-quality-workflow`](translation-quality-workflow.md) — the
   required source lock, autonomous translation, critique, witness,
   adjudication, validation, presentation, and human-review handoff;
2. [Al-Isabah translation profile](../translation-profiles/al-isabah.md) — the
   approved Arabic authority, witness roles, honorific rules, stable units,
   Volume 8 precedent, and book-specific quality targets; and
3. [`entry-title-structure`](entry-title-structure.md) — the bilingual title and
   body boundary that translated entry records must preserve.

After reading the policies, use the
[agent translation workflow](../translation/agent-workflow.md) for the
repository-local commands and distributed assignment protocol.

The translation workflow is not complete when English is fluent. It is ready
for human review only after the applicable autonomous stages are exhausted and
the evidence package, structured English, durable JSON names, and readable
bilingual presentation agree by hash. When every unit in a locked volume or
cohort reaches that point, the aggregate scope is `agent_complete`; human review
coverage is an independent, ongoing management state.

## Local supporting controls

- [`translation-governance-reference.v4.json`](translation-governance-reference.v4.json)
  is the versioned, integrity-bound discovery document for downstream
  consumers. The companion [compatibility guide](downstream-consumer-compatibility.md)
  defines pinning, release semantics, and the Sabiqah deprecation inventory.
- [`elixr-approved-story-projection`](elixr-approved-story-projection.md) is the
  closed, text-free consumer contract for the first partial Khadijah structured
  assertion projection. It pins one exact immutable public-working release and
  does not create a new release or canonical-promotion state.
- [`profiles/honorific-formulas.v1.json`](../../profiles/honorific-formulas.v1.json)
  is the machine-readable Al-Isabah formula registry implemented by the local
  translation workflow.
- [`compliance/source-register.v1.json`](../../compliance/source-register.v1.json)
  classifies authorities and witnesses and records publication eligibility.
- [`compliance/promotions/available-data.v2.json`](../../compliance/promotions/available-data.v2.json)
  records current public-working and canonical-promotion readiness.
- [`compliance/translation-coverage.v1.json`](../../compliance/translation-coverage.v1.json)
  records aggregate agent completion separately from human-review coverage and
  promotion state.
- [`canonical-publication-repository.md`](../architecture/canonical-publication-repository.md)
  defines the repository boundary and release responsibilities.
- [`compliance/policy-binding.v5.json`](../../compliance/policy-binding.v5.json)
  integrity-pins the local contracts, translation profile, and pinned-source
  profile used by new translation work. Versions 1 through 4 remain immutable
  provenance for releases created under their policy sets.

- [`translation-execution-methods`](translation-execution-methods.md) governs exact
  stage-specific admission and captured effective settings under trusted-host semantics.
- [`execution-methods.v2.json`](../../profiles/execution-methods.v2.json) pins
  active approvals and append-only public-safe evaluation records.

## Validation

Run the complete dependency-free validation suite from the repository root:

```sh
python -m unittest discover -s tests
python scripts/validate_compliance.py
python scripts/validate_content.py
python scripts/validate_entry_titles.py
python scripts/execution_governance.py
python scripts/validate_public_tree.py
```

A passing structural check does not create human approval or settle a rights
question. Human approval is disclosed, never inferred; release eligibility is
decided independently by the exact substantive controls in the active
promotion-readiness record.

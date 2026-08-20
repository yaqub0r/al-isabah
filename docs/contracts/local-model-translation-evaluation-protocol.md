# Local-model translation evaluation protocol

- **Protocol ID:** `local-model-translation-evaluation`
- **Status:** Active
- **Issue:** [#49](https://github.com/yaqub0r/al-isabah/issues/49)

## Purpose and authority

This is a non-governing evaluation protocol and supporting control for a local model in a narrow supporting role. It cannot make translation decisions and does not authorize canonical translation work, human approval, compliance approval, or promotion. The repository's translation-quality contract, Al-Isabah profile, source profile, honorific registry, and title/body contract remain authoritative. This protocol is separately integrity-bound by `evaluations/local-model/v1/cases.json`; it is intentionally not added to the global compliance policy binding.

Profile labels such as `low`, `high`, and `xhigh` are controller-defined resource budgets, not claims that a local model has Sol-style native effort levels. Every run records the effective context, output budget, sampling, runtime, model digest when disclosed, and whether native thinking was requested and observed. Private thinking text is never requested, retained, displayed, or committed.

## Public and private boundary

Tracked evaluation contracts may contain the approved public Arabic authority, the already-public working comparator, hashes, prompts, schemas, aggregate smoke evidence, thresholds, and decisions. Model attempts, model final outputs, anonymization keys, human review packets, reviewer worksheets, generated comparison reports, and raw scoring artifacts remain under ignored `.runtime/local-model-evaluation/`.

Every runner/scorer output path is resolved before any input is read, must remain under that exact ignored tree after symlink resolution, and must pass `git check-ignore`. Configurations disclose operational sampling temperature and `samplingSeed` (including an explicit `null` when no seed is available). Artifact IDs and SHA-256 bindings connect packets, runs, alias keys, worksheets, scores, rubrics, gates, and reports; missing or unrelated evidence fails closed.

Never commit credentials, restricted witnesses, private paths or object locators, raw controller logs, personal information, chain-of-thought, or private model deliberation. A generated report may display final model translations beside approved Arabic for an authorized reviewer, but it is workflow evidence and not a book-facing work product.

## Version 1 locked slice

`evaluations/local-model/v1/cases.json` locks three held-out public source units and their already-public working comparators:

- `openiti-5835c183-unit-000112` — textual identity and conditional attribution;
- `openiti-5835c183-unit-001129` — isnad, honorifics, and name variants; and
- `openiti-5835c183-unit-001467` — genealogy, delegation terminology, and a textual variant.

The blind packet strips every comparator field. Models receive only the approved Arabic, case/category identifiers, pinned policy/glossary hashes, and the versioned prompt. Earlier attempts are historical baseline evidence and are not relabeled as new runs.

## Execution separation

The runner and scorer are separate programs:

- `scripts/local_model_evaluation.py` validates contracts, prepares source-only packets, records frozen final outputs, and creates a seeded model-anonymous review packet plus a separate alias key.
- `scripts/score_local_model_evaluation.py` accepts a completed human-review worksheet, unblinds it with the alias key, applies predeclared role gates, and renders a bilingual human report.

The runner cannot set human approval. The scorer cannot perform model inference or alter source/run records.

## Reproducible commands

From the repository root:

```sh
python scripts/local_model_evaluation.py validate

python scripts/local_model_evaluation.py prepare \
  --config evaluations/local-model/v1/configs/gemma4-xhigh-v1.json \
  --output .runtime/local-model-evaluation/issue-49/gemma-packet.json

# An operator invokes the configured model outside the repository script and
# writes only its final JSON outputs to the ignored runtime directory.
python scripts/local_model_evaluation.py record \
  --packet .runtime/local-model-evaluation/issue-49/gemma-packet.json \
  --outputs .runtime/local-model-evaluation/issue-49/gemma-outputs.json \
  --generated-at <UTC-date-time> \
  --output .runtime/local-model-evaluation/issue-49/gemma-run.json

python scripts/local_model_evaluation.py anonymize \
  --runs .runtime/local-model-evaluation/issue-49/gemma-run.json \
         .runtime/local-model-evaluation/issue-49/sol-run.json \
  --seed <recorded-seed> \
  --packet-output .runtime/local-model-evaluation/issue-49/review-packet.json \
  --key-output .runtime/local-model-evaluation/issue-49/review-key.json

# An authorized human completes reviews.json while model identities remain hidden.
python scripts/score_local_model_evaluation.py score \
  --cases evaluations/local-model/v1/cases.json \
  --runs .runtime/local-model-evaluation/issue-49/gemma-run.json \
         .runtime/local-model-evaluation/issue-49/sol-run.json \
  --packet .runtime/local-model-evaluation/issue-49/review-packet.json \
  --key .runtime/local-model-evaluation/issue-49/review-key.json \
  --reviews .runtime/local-model-evaluation/issue-49/reviews.json \
  --output .runtime/local-model-evaluation/issue-49/score.json

python scripts/score_local_model_evaluation.py report \
  --cases evaluations/local-model/v1/cases.json \
  --runs .runtime/local-model-evaluation/issue-49/gemma-run.json \
         .runtime/local-model-evaluation/issue-49/sol-run.json \
  --packet .runtime/local-model-evaluation/issue-49/review-packet.json \
  --key .runtime/local-model-evaluation/issue-49/review-key.json \
  --reviews .runtime/local-model-evaluation/issue-49/reviews.json \
  --score .runtime/local-model-evaluation/issue-49/score.json \
  --output .runtime/local-model-evaluation/issue-49/report.md
```

## Smoke and GPU discipline

Before inference, inspect controller status and defer if another GPU workload is active. Run each profile's smoke probe only when the GPU is free, retain pass/fail and non-sensitive effective settings, and return the controller to `off` afterward. A deterministic smoke temperature is recorded separately from the operational profile temperature. Failed pre-fix probes remain evidence rather than being erased.

## Blind review and scoring

A human reviewer sees Arabic plus candidates labeled only `A`, `B`, and so on. Each candidate keeps `titleEnglish`, `bodyEnglish`, and `issues` separate. The reviewer scores fidelity, structure, uncertainty handling, and formula preservation from 0 to 2, records material errors, and adds notes. The alias key is withheld until the worksheet is frozen. Repeat counts are derived only from distinct, validated run artifacts grouped by comparable configuration; no caller supplies an eligibility count. Scoring accepts only the repository-tracked cases manifest and revalidates every run against its source, policy, packet, and configuration bindings. Reporting requires the original review packet, alias key, and frozen reviewer worksheet, then rederives the complete score before rendering.

Reference English is a working comparator, not an unquestioned gold standard. A disagreement must be adjudicated against Arabic and classified evidence. Local agreement or silence is never clearance.

## Role gates and decisions

The three-case slice is deliberately too small to grant a role. `role-gates.json` requires, at minimum, a larger held-out set and repeated runs for draft assistance; critique triage additionally requires a seeded-error recall set. Local semantic authority is prohibited. Passing a numerical gate makes a role eligible for a dated human decision; it never changes policy automatically.

Every decision is append-only in `decision-log.json`, states its evidence and limitations, and leaves promotion blocked unless the independent translation, human-review, compliance, and canonical gates are satisfied.

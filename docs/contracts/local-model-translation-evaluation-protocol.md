# Local-model translation evaluation protocol

- **Protocol ID:** `local-model-translation-evaluation`
- **Status:** Active
- **Issue:** [#49](https://github.com/yaqub0r/al-isabah/issues/49)
- **Requirement revision:** [public identified evidence](https://github.com/yaqub0r/al-isabah/issues/49#issuecomment-5357953603)

## Purpose and authority

This is a non-governing evaluation protocol for narrow local-model supporting roles. It cannot make translation decisions or authorize canonical translation, human approval, compliance approval, promotion, or semantic authority. The repository's translation-quality contract, Al-Isabah profile, source profile, honorific registry, and title/body contract remain authoritative. This protocol is separately integrity-bound by `evaluations/local-model/v1/cases.json` and is intentionally outside the global compliance policy binding.

Profile labels (`low`, `high`, `xhigh`) are controller resource budgets, not claims about native model effort. Runs disclose effective configuration, model/config identity, sampling, runtime, available digest, resource outcome, and limitations. Thought traces and raw controller/agent logs are never requested for public evidence and must not be retained here.

## Public evidence boundary

Sanitized final model outputs, source-only packets, run provenance and resource outcomes, identified review packets, consenting reviewer scores and notes, reports, and role decisions are tracked under `evaluations/local-model/v1/results/`. Every CLI output for an actual evaluation result is resolved beneath that root, may not escape through a symlink, and may not be Git-ignored. `results-manifest.json` is a closed admission ledger: repository validation enumerates every tracked file under the results root, rejects undeclared or unsupported files, schema-validates JSON, verifies artifact and trusted-dependency hashes, and regenerates declared reports byte-for-byte.

Credentials, private/internal paths or object locators, restricted/private witness evidence, private correspondence, living-person personal information, non-consenting reviewer personal information, thought traces, and raw controller/agent logs are prohibited. Field-name checks are case-insensitive and punctuation-insensitive, and every externally supplied public text value is recursively scanned fail-closed for machine-verifiable credential, path, trace, restricted-evidence, URL/autolink, email, phone, and government-identifier patterns. Model outputs and human review evidence carry explicit closed public-safety admission and provenance records.

## Locked public cases and admission

`evaluations/local-model/v1/cases.json` locks three held-out public source units. Every case has a closed `publicEligibility` decision recording:

- an approved public authority classification;
- explicit false decisions for restricted witness text, credentials, internal paths/object locators, private correspondence, and living-person personal information;
- a concise public rationale; and
- a stable public reviewer, date, and issue-comment evidence link.

Any missing, open, or disqualifying value fails admission. The Arabic, source anchors, working comparator, case order, prompt, policy binding, protocol, and glossary are versioned and hashed. Every model receives the exact same source-only case set and policy inputs. Reference English is withheld until each model's source-only translation pass is frozen; this is execution separation, not anonymous human review.

## Identified public review

Human review is identified, not blind. The review packet displays each run ID and full model/config identity with Arabic, `titleEnglish`, `bodyEnglish`, and declared `issues`. No anonymization or identity-mapping stage exists. Reviewers must provide a stable public reviewer ID, explicit publication consent, a date, and public consent evidence. Scores remain source-based: fidelity, structure, uncertainty handling, and formula preservation are each scored from 0 to 2, with concrete material errors and notes.

Unreviewed runs and packets are valid public pending evidence. They are always marked `unreviewed`, `no-role`, and promotion-blocked so current sanitized outputs can be committed before scoring. Completed scoring verifies exact case/run coverage and order, rederives packet/run/worksheet/score/report bindings, derives repeat counts from distinct comparable runs, and requires exact canonical equality with the tracked role gates. Preparing and validating later artifacts likewise reconstructs configuration identity from exact authorized files under the tracked configs directory; caller-supplied IDs, model names, hashes, or gates cannot create a new trust root. A run's resource profile must equal its authorized config's house profile.

The generated identified report is bilingual and shows Arabic; model/config identity; title, body, and issues; review status; scores and notes when present; role gates; and limitations. Dynamic text is HTML-escaped; bare URLs, URI schemes, `www.` forms, email/angle autolinks, inline/reference/nested links, and remote images are neutralized before GFM emission.

## Reproducible commands

From the repository root (example public result names only):

```sh
python scripts/local_model_evaluation.py validate

python scripts/local_model_evaluation.py prepare \
  --config evaluations/local-model/v1/configs/gemma4-xhigh-v1.json \
  --output evaluations/local-model/v1/results/issue-49/gemma-packet.json

# Invoke the identified config outside this script. Freeze only sanitized final
# JSON output (titleEnglish, bodyEnglish, issues, and a closed publicSafety
# admission with sanitized-final-model-output provenance) under the public results root.
python scripts/local_model_evaluation.py record \
  --packet evaluations/local-model/v1/results/issue-49/gemma-packet.json \
  --outputs evaluations/local-model/v1/results/issue-49/gemma-outputs.json \
  --generated-at <UTC-date-time> \
  --resource-status completed \
  --resource-profile xhigh \
  --output evaluations/local-model/v1/results/issue-49/gemma-run.json

python scripts/local_model_evaluation.py review-packet \
  --runs evaluations/local-model/v1/results/issue-49/gemma-run.json \
         evaluations/local-model/v1/results/issue-49/sol-run.json \
  --output evaluations/local-model/v1/results/issue-49/identified-review-packet.json

# A pending public report requires no human worksheet or score.
python scripts/score_local_model_evaluation.py report \
  --cases evaluations/local-model/v1/cases.json \
  --runs evaluations/local-model/v1/results/issue-49/gemma-run.json \
         evaluations/local-model/v1/results/issue-49/sol-run.json \
  --packet evaluations/local-model/v1/results/issue-49/identified-review-packet.json \
  --output evaluations/local-model/v1/results/issue-49/pending-report.md

# After an identified, consenting reviewer completes reviews.json:
python scripts/score_local_model_evaluation.py score \
  --cases evaluations/local-model/v1/cases.json \
  --runs evaluations/local-model/v1/results/issue-49/gemma-run.json \
         evaluations/local-model/v1/results/issue-49/sol-run.json \
  --packet evaluations/local-model/v1/results/issue-49/identified-review-packet.json \
  --reviews evaluations/local-model/v1/results/issue-49/reviews.json \
  --output evaluations/local-model/v1/results/issue-49/score.json

python scripts/score_local_model_evaluation.py report \
  --cases evaluations/local-model/v1/cases.json \
  --runs evaluations/local-model/v1/results/issue-49/gemma-run.json \
         evaluations/local-model/v1/results/issue-49/sol-run.json \
  --packet evaluations/local-model/v1/results/issue-49/identified-review-packet.json \
  --reviews evaluations/local-model/v1/results/issue-49/reviews.json \
  --score evaluations/local-model/v1/results/issue-49/score.json \
  --output evaluations/local-model/v1/results/issue-49/reviewed-report.md
```

## Smoke, gates, and decisions

Before inference, inspect controller status and defer if another GPU workload is active. Preserve low/high/xhigh pass/fail evidence and distinguish deterministic smoke temperature from operational profile temperature. Failed pre-fix xhigh probes remain evidence, and the controller returns to `off`.

The three-case slice is too small to grant a role. `role-gates.json` requires a larger held-out set and repeated runs for draft assistance; critique triage additionally requires a seeded-error recall set. Local semantic authority is prohibited. Numerical eligibility only permits a dated human role decision; it never changes policy automatically. `decision-log.json` remains append-only and hash-chained, and promotion stays blocked absent all independent gates.

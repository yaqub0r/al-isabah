# Repository workflow

## Realtime voice pronunciation

When conversation context indicates realtime voice, use the original-language
spelling and this project glossary. Preserve consonant distinctions and vowel
length, apply user corrections consistently, and keep ordinary project Latin
spellings in prose.

- Al-Isabah — الإِصَابَة — *al-iṣābah* — approximately /al.ʔi.sˤaː.ba/; use
  emphatic ṣād ص and the long ā, not sīn.

## Issue-first development

Every repository change must be associated with a GitHub issue before work
begins. Keep changes within the issue scope and reference the issue in pull
requests. Use a closing reference only when all acceptance criteria are met.

## Scholarly integrity

- Never silently modify canonical Arabic source bytes.
- Preserve source hashes, edition identity, witness evidence, unresolved
  readings, and editorial provenance.
- Keep immutable evidence, canonical editorial records, and generated products
  as distinct data layers.
- Treat machine validation and human scholarly review as separate states.
- Prefer reversible imports and derived projections over destructive rewrites.
- Follow `docs/architecture/canonical-publication-repository.md` for the
  repository's responsibilities and client/application boundary.
- Accept only publication-ready content promoted with exact, reviewable
  provenance and compliance metadata. Keep restricted research witnesses,
  reconstructive comparison output, and private storage details out of this
  repository.
- Treat human scholarly review as append-only, ongoing, nonterminal metadata.
  Its absence or incomplete coverage never blocks public-working publication,
  canonical promotion, or immutable release eligibility by itself. Concrete
  source, rights, provenance, public-boundary, deterministic-validation, or
  substantive defects remain fail-closed under their own reason codes.
- Preserve every honorific and devotional formula attested by the approved
  Arabic authority at the corresponding occurrence in the English record,
  using its Arabic written form. Do not translate, transliterate, omit, expand,
  substitute, or add a formula. Require the promotion manifest to attest that
  this check passed.
- Before adding or promoting content, update
  `compliance/source-register.v1.json` and the applicable manifest under
  `compliance/promotions/`, then run `python -m unittest discover -s tests`.
  A passing structural check does not override a blocked or unresolved rights
  classification.

## Translation workflow

This repository is the authority for translating Al-Isabah. Sabiqah and other
applications may execute or present the workflow, but their copies and runtime
behavior never replace the policies in this repository.

Before starting or modifying any translation, read in order:

1. `docs/contracts/INDEX.md`;
2. `docs/contracts/translation-quality-workflow.md`;
3. `docs/translation-profiles/al-isabah.md`; and
4. `docs/contracts/entry-title-structure.md`.

Then follow `docs/translation/agent-workflow.md` for the executable clone,
doctor, hydrate, claim, prepare, translate, validate, render, and submit path.
GitHub issues are the assignment ledger; do not translate an unclaimed or
overlapping entry range.

Do not hand work to a human merely because a first English draft exists. Before
opening ongoing human review, exhaust the applicable source
alignment, blind translation, independent critique, selective witness
resolution, adjudication, deterministic validation, name reconciliation, and
bilingual presentation stages first. Preserve unresolved findings rather than
hiding them with fluent wording.

All contracts needed to make Al-Isabah translation decisions must remain local
to this repository and integrity-bound by
`compliance/policy-binding.v6.json`. The v1-v5 bindings remain immutable
release provenance for earlier public-working artifacts. A translation change may use
restricted evidence in approved external storage, but it must not depend on
policy text in another repository. Run `python -m unittest discover -s tests` before delivery;
the suite fails when a required local policy file is missing or altered without
updating its reviewed binding.

## Architecture

- The domain model must not depend on Astro, React, Decap, Cloudflare, GitHub,
  or a future mobile framework.
- Preserve the validated Python translation/evidence pipeline; do not rewrite
  it solely for stack uniformity.
- Keep third-party workflow infrastructure at the edge and replaceable.
- Avoid new packages or services until a demonstrated dependency boundary
  justifies them.

## Delivery

Use feature branches and pull requests after the initial empty-repository
bootstrap. Run relevant validation and tests before merging. Do not publish the
repository or source binaries without an explicit rights and release decision.


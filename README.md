# Al-Isabah Scholarly Platform

A platform-neutral canonical publication repository for a scholarly edition
and English translation of *al-Isabah fi Tamyiz al-Sahabah* by Ibn Hajar
al-Asqalani.

The permanent product is the approved, versioned scholarly dataset: canonical
Arabic text, aligned English translation, editorial annotations, stable
identifiers, review state, book-specific provenance, and release history. Web
and future mobile applications are clients of that dataset.

Downstream applications maintain their own extraction, knowledge graphs,
admission, orchestration, and application-specific evaluations. They consume
approved, versioned book releases without adding application code here.

This repository governs Al-Isabah source decisions, translation quality,
review state, canonical promotion, and releases. Restricted research witnesses,
credentials, and private comparison expression stay in approved external
storage, while their non-sensitive identities, hashes, roles, and allowed uses
remain governed here. Reader and review applications are clients of this
repository's pinned contracts and releases rather than translation authorities.

See the [canonical publication repository
model](docs/architecture/canonical-publication-repository.md) for the complete
responsibility and trust-boundary model.

Downstream consumers discover and pin the versioned
[translation-governance reference](docs/contracts/translation-governance-reference.v13.json).
Its [compatibility guide](docs/contracts/downstream-consumer-compatibility.md)
documents immutable-commit pinning, the Al-Isabah-owned formula registry,
consumer responsibilities, and the downstream deprecation path. Human review
updates per-record metadata and confidence rather than release class;
incremental translations, corrections, and review coverage all use the same
immutable release cycle.

## Translating Al-Isabah

Start with the [local contract index](docs/contracts/INDEX.md). It directs an
agent through the required
[translation-quality workflow](docs/contracts/translation-quality-workflow.md),
the [Al-Isabah translation profile](docs/translation-profiles/al-isabah.md),
and the [entry-title structure contract](docs/contracts/entry-title-structure.md).
Together they specify the authoritative Arabic source, witness roles, stable
units and JSON names, autonomous quality stages, human-review handoff, and
promotion boundary.

Human review deliberately begins after the autonomous handoff; it is not a
terminal publication gate. A draft must first complete every applicable
autonomous alignment, blind translation, critique, witness, adjudication,
validation, and readable-presentation step. The local compliance validator
integrity-checks these policy files so a fresh clone cannot silently depend on
translation rules stored in another repository.

For project planning, a locked volume or cohort is **done** when those autonomous
stages are exhausted for every scoped unit and the aggregate status is
`agent_complete`. Human review is a separate, ongoing management state: zero
human reviews does not make a completed translation incomplete, and later
reviewer corrections use the immutable revision cycle. Aggregate completion and
review coverage are recorded in
[`compliance/translation-coverage.v1.json`](compliance/translation-coverage.v1.json).

The [agent translation runbook](docs/translation/agent-workflow.md) turns that
contract into one distributable path that requires no downstream application checkout or model
API key:

```sh
python scripts/translation_workflow.py doctor
python scripts/translation_workflow.py hydrate
python scripts/translation_workflow.py status
python scripts/translation_workflow.py locate --entry 11482
python scripts/translation_workflow.py claim --start-unit <first-unit> --end-unit <last-unit>
python scripts/translation_workflow.py prepare --issue <issue-number>
python scripts/translation_workflow.py merge-shard --packet <packet> --shard <entry-shard>
python scripts/translation_workflow.py merge-structure-shard --packet <packet> --shard <structure-shard>
```

The CLI uses GitHub issues to prevent overlapping claims, creates
source-and-policy-bound packets, validates every autonomous stage, and emits a
human-readable bilingual review artifact while preserving `unreviewed` as the
human state.

## Entry structure

The [entry-title structure
contract](docs/contracts/entry-title-structure.md) defines a title as the
shortest stable name or heading phrase identifying an entry's subject. Lineage,
relationships, narration, and biographical prose remain in ordered body blocks;
Arabic and English titles must cover the same semantic boundary. The versioned
[title-decision profile](profiles/entry-title-decisions.v11.json) records
governed decisions for entries whose printed heading line does not provide that
boundary reliably. Its witness-bound editorial supplies preserve damaged source
prefixes while displaying bracketed subject heads supported by same-work
evidence. Reader applications consume this structure and must not infer titles
from typography or body length.

The [source compliance register](compliance/source-register.v1.json) applies
the repository-local policy binding to the available evidence and exact public
proposals. The current [promotion-readiness
manifest](compliance/promotions/available-data.v3.json) approves the exact
Issue #100 full-book package for a controlled, immutable public-working release
after protected merge. Canonical promotion remains blocked by separate source,
rights, provenance, and substantive controls; human review remains ongoing and
nonterminal.

The repository is public, but public repository visibility is not a rights or
release decision for any source artifact. Eligible public scholarly content is
available under CC BY-NC-SA 4.0 only when the per-book rights matrix and an
applicable publication manifest approve it. See the [scholarly-content rights notice](SCHOLARLY_CONTENT_RIGHTS.md)
and [pilot rights matrix](compliance/rights-matrix.al-isabah.v1.json). Software,
schemas, workflows, tests, and other code are outside that grant; no software
license has been selected.

Repository-model documentation is tracked in [issue
#9](https://github.com/yaqub0r/al-isabah/issues/9). Initial repository work is
tracked in [issue #1](https://github.com/yaqub0r/al-isabah/issues/1).

Validate compliance metadata with:

```sh
python -m unittest discover -s tests
```

Validate the active title-decision profile directly with:

```sh
python scripts/validate_entry_titles.py
```

Canonical publication records are validated separately from private research
evidence. Run `python scripts/validate_content.py`; it fails closed when an
entry lacks an active stable identifier, exact substantive eligibility
attestations, disclosed ongoing human-review and unresolved states, compliance
approval, source hashes, or an explicit promotion manifest. Zero or incomplete
human-review coverage is not itself a blocker.

The legacy Volume 8 and Khadijah development work remains retained in approved
access-controlled research storage. Issue 98 supersedes the legacy Volume 8
completion claim with a normal-contract, source-bound public-safe proposal; it
does not expose or erase the historical private evidence. The non-sensitive
integrity and retirement record remains in
`compliance/research-retirement.v1.json`.

## Public-working boundary

Current public-working builds consume only strict
[`public-proposal.v2`](schemas/public-proposal.v2.schema.json) artifacts and their
exact release closure. Internal translation-work packets and detailed review
evidence are not public build inputs. The Issue #100 cumulative closure admits
exactly 12,303 ordered source units across Volumes 1–8 from ten accepted
proposal/review pairs. It preserves 1,382 owned structural segments and 23
inherited display contexts, emits the three Volume 3 cohorts as one cumulative
volume shard, and excludes the superseded Issue #53 proposal and legacy private
Volume 8 corpus. All 12,303 records remain human-unreviewed; that disclosure is
not a release blocker, while canonical promotion remains blocked.

Publication is controlled and manual. A merge does not create a release: a
maintainer must dispatch the publication workflow with the exact immutable
`main` commit after repository release immutability and all release gates are
verified. Earlier releases remain rollback and historical pins. See the
[public distribution contract](docs/architecture/public-distribution.md) for
the exact closure, asset, checksum, and supersession rules.


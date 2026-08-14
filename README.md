# Al-Isabah Scholarly Platform

A platform-neutral canonical publication repository for a scholarly edition
and English translation of *al-Isabah fi Tamyiz al-Sahabah* by Ibn Hajar
al-Asqalani.

The permanent product is the approved, versioned scholarly dataset: canonical
Arabic text, aligned English translation, editorial annotations, stable
identifiers, review state, book-specific provenance, and release history. Web
and future mobile applications are clients of that dataset.

This repository governs Al-Isabah source decisions, translation quality,
review state, canonical promotion, and releases. Restricted research witnesses,
credentials, and private comparison expression stay in approved external
storage, while their non-sensitive identities, hashes, roles, and allowed uses
remain governed here. [Sabiqah](https://github.com/yaqub0r/sabiqah) may provide
reader and review interfaces, but it is a client of this repository's pinned
contracts and releases rather than the translation authority.

See the [canonical publication repository
model](docs/architecture/canonical-publication-repository.md) for the complete
responsibility and trust-boundary model.

## Translating Al-Isabah

Start with the [local contract index](docs/contracts/INDEX.md). It directs an
agent through the required
[translation-quality workflow](docs/contracts/translation-quality-workflow.md),
the [Al-Isabah translation profile](docs/translation-profiles/al-isabah.md),
and the [entry-title structure contract](docs/contracts/entry-title-structure.md).
Together they specify the authoritative Arabic source, witness roles, stable
units and JSON names, autonomous quality stages, human-review handoff, and
promotion boundary.

Human review is deliberately last. A draft must first complete every applicable
autonomous alignment, blind translation, critique, witness, adjudication,
validation, and readable-presentation step. The local compliance validator
integrity-checks these policy files so a fresh clone cannot silently depend on
translation rules stored in another repository.

The [agent translation runbook](docs/translation/agent-workflow.md) turns that
contract into one distributable path that requires no Sabiqah checkout or model
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
[title-decision profile](profiles/entry-title-decisions.v2.json) records
reviewed decisions for entries whose printed heading line does not provide that
boundary reliably. Reader applications consume this structure and must not
infer titles from typography or body length.

The [source compliance register](compliance/source-register.v1.json) applies
the repository-local policy binding to the data currently available on the
Volume 8 and Khadijah development branches. The corresponding [promotion
readiness manifest](compliance/promotions/available-data.v1.json) is
**blocked**: the current Arabic and English records remain useful research and
review material, but they are not approved for a public release.

The repository is public, but public repository visibility is not a rights or
release decision for any source artifact. Only reviewed, publication-ready
content belongs in versioned public releases.

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
evidence. Run `python scripts/validate_content.py`; it fails closed when
an entry lacks an active stable identifier, reviewed Arabic and English,
compliance approval, source hashes, or an explicit promotion manifest.

The legacy Volume 8 and Khadijah development work was retained for authenticated
review in Sabiqah rather than promoted here. Its non-sensitive integrity and
retirement record is in `compliance/research-retirement.v1.json`.


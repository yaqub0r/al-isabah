# Al-Isabah Scholarly Platform

A platform-neutral canonical publication repository for a scholarly edition
and English translation of *al-Isabah fi Tamyiz al-Sahabah* by Ibn Hajar
al-Asqalani.

The permanent product is the approved, versioned scholarly dataset: canonical
Arabic text, aligned English translation, editorial annotations, stable
identifiers, review state, book-specific provenance, and release history. Web
and future mobile applications are clients of that dataset.

[Sabiqah](https://github.com/yaqub0r/sabiqah) governs source acquisition,
rights assessment and clearance, private research evidence, comparison,
translation and review workflows, promotion, and public presentation. This
repository receives publication-ready content through an explicit reviewed
promotion. Restricted research witnesses and private comparison evidence do
not belong here.

See the [canonical publication repository
model](docs/architecture/canonical-publication-repository.md) for the complete
responsibility and trust-boundary model.

## Entry structure

The [entry-title structure
contract](docs/contracts/entry-title-structure.md) defines a title as the
shortest stable name or heading phrase identifying an entry's subject. Lineage,
relationships, narration, and biographical prose remain in ordered body blocks;
Arabic and English titles must cover the same semantic boundary. The versioned
[title-decision profile](profiles/entry-title-decisions.v1.json) records
reviewed decisions for entries whose printed heading line does not provide that
boundary reliably. Reader applications consume this structure and must not
infer titles from typography or body length.

The [source compliance register](compliance/source-register.v1.json) applies
Sabiqah's pinned content contracts to the data currently available on the
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

Canonical publication records are validated separately from Sabiqah's private
research corpus. Run `python scripts/validate_content.py`; it fails closed when
an entry lacks an active stable identifier, reviewed Arabic and English,
compliance approval, source hashes, or an explicit promotion manifest.

The legacy Volume 8 and Khadijah development work was retained for authenticated
review in Sabiqah rather than promoted here. Its non-sensitive integrity and
retirement record is in `compliance/research-retirement.v1.json`.


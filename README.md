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


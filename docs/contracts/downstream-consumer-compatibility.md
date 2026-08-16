# Downstream translation-governance compatibility

- **Status:** Active
- **Issue:** [#45](https://github.com/yaqub0r/al-isabah/issues/45)
- **Machine reference:**
  [`translation-governance-reference.v1.json`](translation-governance-reference.v1.json)

## Authority and pinning

Al-Isabah is the sole authority for its translation-quality contract, book
profile, formula semantics, source and rights decisions, per-record scholarly
review metadata, promotion rules, and immutable releases. A downstream
consumer may execute a compatible client workflow or present the results, but
it must not copy these files and treat the copy as governing policy.

A consumer starts from the stable machine-reference path above, retrieved from
an immutable Al-Isabah repository commit. It then verifies every listed
artifact using SHA-256 over UTF-8 text normalized to LF line endings. A branch
name, latest release lookup, or mutable raw-file URL is a discovery mechanism,
not a durable pin.

The reference uses semantic versioning. A breaking change to consumer
interpretation increments the major version; a backward-compatible artifact
or field increments the minor version; a clarification that changes no
behavior increments the patch version. Artifact hashes still change whenever
their exact text changes, so consumers must validate both the reference
version and the pinned hashes.

The machine reference does not replace the immutable public-distribution
contract. Public distribution schema v2 remains the active ingestion format;
schema v1 remains rollback-only. This ownership cleanup changes neither
schema, release class, nor existing release bytes.

## Review, correction, and release semantics

Human scholarly review changes per-record review metadata and confidence. It
does not create or select a different release class. Additional translations,
accepted corrections, and increased review coverage all use the same
immutable release cycle: validate a new repository state, issue a new
checksum-addressed release when separately authorized, and retain explicit
supersession history. No consumer may mutate an already published release.

A consumer may retain its own reviewer accounts, access control, append-only
review events, private evidence, application state, storage, and presentation.
Those responsibilities do not make the consumer the scholarly authority.
Accepted review decisions return through an Al-Isabah-governed proposal and
release process before they become canonical book metadata.

## Sabiqah follow-up inventory

The following inventory is an implementation map for a separate Sabiqah issue.
Nothing in this Al-Isabah change edits or authorizes edits to Sabiqah.

| Sabiqah path | Follow-up action |
| --- | --- |
| `docs/contracts/translation-quality-workflow.md` | Delete the duplicate governing contract and replace local links with a pinned Al-Isabah reference. |
| `docs/translation-profiles/al-isabah.md` | Delete the duplicate book profile and replace local links with the pinned upstream profile. |
| `packages/release-model/src/honorifics.registry.json` | Stop using the local file as semantic authority. Replace its Al-Isabah semantics with a verified projection of `profiles/honorific-formulas.v1.json`; presentation-only font support may remain consumer-owned. |
| `packages/release-model/src/honorifics.ts` and `packages/release-model/tests/honorifics.test.ts` | Keep the renderer/adapter behavior, but load and test the pinned upstream semantic projection instead of a governing local registry. |
| `docs/contracts/contracts.registry.json` | Remove the `translation-quality-workflow` contract object and its translation-path mapping. Keep Sabiqah-owned contracts and the generic acknowledgement mechanism. |
| `tools/contracts/check-contract-ack.node-test.mjs` | Remove `translation-quality-workflow` expectations, including the release-fixture expectation and the translation-implementation-path test; add consumer compatibility coverage instead. |
| `.github/workflows/application-validate.yml` | Remove both `docs/translation-profiles/al-isabah.md` path filters. Keep application, distribution-ingestion, and private-evidence checks. |
| `package.json` | Remove `docs/translation-profiles/al-isabah.md` from `format` and `format:check`; keep local contract tooling for Sabiqah-owned policies. |
| `docs/contracts/INDEX.md` | Remove the local translation-quality row and Al-Isabah book-profile section; add the pinned upstream consumer reference. |
| `README.md` and `AGENTS.md` | Replace claims that Sabiqah governs Al-Isabah translation execution or authors its canonical translations. Retain Sabiqah ownership of private evidence handling, application state, storage, and presentation. |
| `docs/architecture/content-governance.md` | Recast translation and promotion-preparation claims as client execution under the canonical book repository's pinned policy. |
| `docs/architecture/honorific-presentation.md` | Keep presentation and font decisions consumer-owned while making Al-Isabah formula semantics upstream-owned. |
| `docs/architecture/application-platform.md` | Keep reader and append-only review interfaces; clarify that review events update proposals for upstream per-record metadata rather than release class. |
| `docs/architecture/book-release-contract.md` | Preserve verified ingestion and rollback behavior; align review coverage, corrections, and incremental translation with one immutable release cycle. |
| `evidence/source-authorities/al-isabah.v1.json` | Replace the note pointing to Sabiqah's local profile with the pinned Al-Isabah reference. Do not move or expose private evidence. |

The generic `.github/workflows/contract-ack.yml`,
`.github/pull_request_template.md`, and
`tools/contracts/check-contract-ack.mjs` are not themselves duplicate
translation policy. They should remain for Sabiqah-owned contracts after the
translation-specific registry entry and test expectations are removed.

Distribution verification and ingestion code, synthetic release fixtures,
review UI and append-only review storage, private-evidence controls, reader
presentation, and rollback pointers are also legitimate consumer surfaces.
They must not be deleted merely because they mention Al-Isabah.

# Public distribution contract

- **Status:** Accepted
- **Issue:** [#28](https://github.com/yaqub0r/al-isabah/issues/28)
- **Schema:** [`public-distribution.v2.schema.json`](../../schemas/public-distribution.v2.schema.json)

## Purpose

Al-Isabah is a self-contained scholarly-content repository and a producer of
application-neutral public-working distributions. Applications consume this
contract; they do not inspect translation packets, infer scholarly policy, or
depend on the repository's internal working layout.

Each strict `public-proposal.v1` artifact contributes its approved public-working
records to a deterministic distribution. Internal translation-work packets are
not build inputs. A distribution is immutable,
checksum-addressed, bound to the exact repository commit and source authority,
and explicitly distinct from a canonical or human-approved release.

Public-proposal v1.0 remains the exact historical-remediation shape for issue
0026. Public-proposal v1.1 is the additive shape for packet sets that never
entered Git: it replaces the issue-0026-only historical-blob fields with
aggregate packet-set, review-set, and public-record-projection hashes. Those
hashes attest that the public projection agreed with machine-ready evidence at
generation time; they do not publish the evidence or imply that it was ever a
Git artifact. The raw packets and detailed review presentations remain outside
the public repository under the submission rule.

## Stable identity

`sourceUnitId` is the record identity. `sourceOrdinal` is its ordering key.
Printed entry numbers are descriptive metadata and may repeat. Consumers must
not key, deduplicate, or join records by printed entry number. The manifest
lists repeated printed numbers so that loss through accidental map-key
collapse is testable.

## Public boundary

The compiler accepts only proposals that pass the recursive public boundary,
strict field allowlist, source/rights/policy checks, reader-facing parity check,
and their exact release closures. It carries the approved source authority, license,
exact public source hashes, repository-local policy binding, machine state,
human-review state, finding category codes, and the minimal formula identity
needed to audit the reader text. Restricted witnesses, raw findings, private
locators, credentials, model traces, internal critique evidence, and source or
stage coordinates are not proposal or distribution fields.

The distribution also excludes downstream application and private research
system names, private paths or storage locations, source-file paths and line
coordinates, API details, schema locations, and operational credentials. It
retains only the public scholarly provenance needed to identify and verify the
approved edition: authority identifier, immutable source revision, artifact and
record hashes, license, attribution, and human-readable page metadata. Internal
packet paths and policy file inventories are not part of the public contract.

Every distribution declares its book-level rights-matrix identifier, public
content license, required attribution, and excluded material. The current
eligible public scholarly content is CC BY-NC-SA 4.0. This is a content grant,
not a software license; code and repository infrastructure remain outside it.

An unreviewed record may be public-working. It is never represented as
canonical. Ambiguous title projection remains visibly `needs_attention` and
does not silently acquire human approval.

## Files

`manifest.json` is the entry point. `release-closure.json` binds every current
proposal, projection, public review, source authority, source register, rights
decision, policy binding, review count, and non-manifest output hash. The
historical issue-0026 closure remains immutable and is itself bound by the
current cumulative closure. Record shards are newline-delimited JSON,
split by volume and sorted by `(sourceOrdinal, id)`. The manifest records the
SHA-256 digest, byte length, record count, and volume for every shard. A
consumer rejects missing, extra, reordered, duplicated, or hash-mismatched
content and rejects unknown major schema versions.

Each proposal's deterministic review is emitted under `reviews/`, preserving
its separate human-review management state. The CI pipeline builds and
validates the cumulative distribution for every pull request. The publication
workflow remains manually disabled between controlled releases; merging does
not enable or dispatch it. A later, separately authorized immutable prerelease
must still pass the protected test, public-boundary, historical-closure, and
cumulative-closure checks. Any such release remains a transport for a
public-working distribution, not a declaration of canonical publication.

## Compatibility changes

Additive fields may be introduced in a backward-compatible minor version. The
2.0 contract adds explicit content-rights metadata and exact release closure.
The v1 assets are historical and superseded: they remain available only for
validating older immutable bundles and are not valid inputs for new builds.
Removing or changing a required field, identity rule, public-state meaning, or
checksum rule requires a new major version and coordinated consumer support.
Applications pin a distribution ID and retain the previous immutable version
for rollback.

## Release immutability and supersession

The public-working release for commit
`919b75cd314d6a3e340e6f4676715ef4a2bee46a` is a valid schema-v2 transport,
but GitHub reports it as mutable because repository release immutability was
disabled when it was created. It remains retained as historical evidence and a
content-equivalent transition pin; it must not be cited as proof that its tag or
asset is immutable.

Issue [#40](https://github.com/yaqub0r/al-isabah/issues/40) records the
non-destructive supersession decision. Repository release immutability must be
enabled before any later public-working release is created. The first verified
schema-v2 release created under that setting is the recommended pin when issue
#40 records its exact commit-addressed tag and asset digest. Its reader-facing
scholarly content must remain identical to the transition pin, and its manifest
must continue to declare `public-working` with `canonicalPromotion` blocked.

No predecessor is replaced by this supersession. Existing schema-v2 releases
remain rollback and historical pins. Legacy schema-v1 releases remain retained
for history but are superseded for new consumers because they contain the
already documented legacy operational metadata.

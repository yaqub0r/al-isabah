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

## Stable identity

`sourceUnitId` is the record identity. `sourceOrdinal` is its ordering key.
Printed entry numbers are descriptive metadata and may repeat. Consumers must
not key, deduplicate, or join records by printed entry number. The manifest
lists repeated printed numbers so that loss through accidental map-key
collapse is testable.

## Public boundary

The compiler accepts only a proposal that passes the recursive public boundary,
strict field allowlist, source/rights/policy checks, reader-facing parity check,
and exact release closure. It carries the approved source authority, license,
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

`manifest.json` is the entry point. `release-closure.json` binds the proposal,
projection, source authority, source register, rights decisions and exclusions,
policy binding, review counts, and every non-manifest output hash. Record shards are newline-delimited JSON,
split by volume and sorted by `(sourceOrdinal, id)`. The manifest records the
SHA-256 digest, byte length, record count, and volume for every shard. A
consumer rejects missing, extra, reordered, duplicated, or hash-mismatched
content and rejects unknown major schema versions.

The CI pipeline builds and validates the distribution for every pull request.
Automated publication is paused after the issue #35 public-boundary finding.
It may be deliberately re-enabled only after the current-tree remediation is
merged, boundary and closure validation pass on the merged commit, the
historical-exposure decision remains recorded, and repository review is
complete. Any future release remains a transport for a public-working
distribution, not a declaration of canonical publication.

## Compatibility changes

Additive fields may be introduced in a backward-compatible minor version. The
2.0 contract adds explicit content-rights metadata and exact release closure.
The v1 assets are historical and superseded: they remain available only for
validating older immutable bundles and are not valid inputs for new builds.
Removing or changing a required field, identity rule, public-state meaning, or
checksum rule requires a new major version and coordinated consumer support.
Applications pin a distribution ID and retain the previous immutable version
for rollback.

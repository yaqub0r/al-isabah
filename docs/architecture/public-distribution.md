# Public distribution contract

- **Status:** Accepted
- **Issue:** [#28](https://github.com/yaqub0r/al-isabah/issues/28)
- **Schema:** [`public-distribution.v1.schema.json`](../../schemas/public-distribution.v1.schema.json)

## Purpose

Al-Isabah is a self-contained scholarly-content repository and a producer of
application-neutral public-working distributions. Applications consume this
contract; they do not inspect translation packets, infer scholarly policy, or
depend on the repository's internal working layout.

Each machine-ready translation packet contributes its complete public-working
records to a deterministic distribution. A distribution is immutable,
checksum-addressed, bound to the exact repository commit and source authority,
and explicitly distinct from a canonical or human-approved release.

## Stable identity

`sourceUnitId` is the record identity. `sourceOrdinal` is its ordering key.
Printed entry numbers are descriptive metadata and may repeat. Consumers must
not key, deduplicate, or join records by printed entry number. The manifest
lists repeated printed numbers so that loss through accidental map-key
collapse is testable.

## Public boundary

The compiler accepts only packets whose machine-readiness and review
presentation states are `ready`. It carries the approved source authority,
license, exact source hashes, repository-local policy binding, machine state,
human-review state, unresolved findings, and formula inventory into the
distribution. Restricted witnesses, private locators, credentials, model
traces, and internal critique evidence are not distribution fields.

An unreviewed record may be public-working. It is never represented as
canonical. Ambiguous title projection remains visibly `needs_attention` and
does not silently acquire human approval.

## Files

`manifest.json` is the entry point. Record shards are newline-delimited JSON,
split by volume and sorted by `(sourceOrdinal, id)`. The manifest records the
SHA-256 digest, byte length, record count, and volume for every shard. A
consumer rejects missing, extra, reordered, duplicated, or hash-mismatched
content and rejects unknown major schema versions.

The CI pipeline builds and validates the distribution for every pull request.
After a qualifying merge to `main`, it publishes a commit-addressed GitHub
pre-release named `public-working-<commit>`. The release is a transport for a
public-working distribution, not a declaration of canonical publication.

## Compatibility changes

Additive fields may be introduced in a backward-compatible minor version.
Removing or changing a required field, identity rule, public-state meaning, or
checksum rule requires a new major version and coordinated consumer support.
Applications pin a distribution ID and retain the previous immutable version
for rollback.

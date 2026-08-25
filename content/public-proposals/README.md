# Public proposals

This directory contains strict, versioned public-working projections. A public
proposal preserves approved reader-facing Arabic and English, stable identity,
ordering, normalized public provenance, and aggregate review state. It excludes
internal translation stages, model or critique material, raw findings,
reconstructive operations, restricted witness wording, private or operational
locations, source coordinates, credentials, and unknown fields.

`issue-0026.public-proposal.json` validates against
`schemas/public-proposal.v1.schema.json`. Its deterministic public review is
`issue-0026.public-review.json`. Both are bound by the exact closure manifest in
`compliance/publication/issue-0026.release-closure.v1.json`.

`issue-0053.public-proposal.json` is the v1.1 strict projection for the 1,497
machine-ready Volume 2 records. Its aggregate packet-set and review-set hashes
bind the public projection to evidence that never entered Git; its deterministic
public review is `issue-0053.public-review.json`. Human review remains
`unreviewed` and independently ongoing for every record.

The cumulative distribution closure is
`compliance/publication/issue-0053.release-closure.v1.json`. It binds both
approved proposals and reviews, Volume 1 and Volume 2 record shards, the current
source register, and the preserved historical issue-0026 closure.

These artifacts are approved only for `public-working` distribution. Canonical
promotion remains blocked and requires its own human scholarly and compliance
decision.

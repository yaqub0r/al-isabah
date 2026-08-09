# Repository workflow

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


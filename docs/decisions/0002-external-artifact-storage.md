# ADR 0002: External content-addressed artifact storage

- Status: accepted
- Date: 2026-08-11
- Issues: https://github.com/yaqub0r/al-isabah/issues/1 and https://github.com/yaqub0r/firstlight/issues/998

## Context

The FirstLight migration inventory currently describes hundreds of megabytes of
facsimiles, OCR, multilingual witnesses, model checkpoints, and generated
review products. These bytes are necessary evidence, but ordinary Git blobs are
the wrong distribution mechanism for a growing eight-volume scholarly corpus.
Git LFS would keep them out of normal packfiles, but every revised object still
consumes another full stored version and routine clones or CI can consume LFS
bandwidth.

The canonical editorial dataset and operator decisions must remain readable
without a database. Licensed or redistribution-uncertain source files must not
become public merely because a reader application is published.

## Decision

Large immutable evidence and rebuildable products use content-addressed object
storage. Their object key is derived only from the SHA-256 digest:

```text
sha256/ab/<64-character-sha256>
```

Git contains the validated artifact manifest, canonical editorial JSON,
reviewer decisions, schemas, and pipelines. A repository-ignored local cache
contains hydrated objects. The initial remote is private S3-compatible storage;
Cloudflare R2 is the preferred operator deployment but is not part of the
domain model.

The manifest never records credentials or machine-specific absolute paths.
Remote publication is an explicit operation. Hydration verifies byte size and
SHA-256 before an object becomes visible in the cache. A failed or interrupted
transfer cannot replace a verified object.

Small immutable metadata may remain in Git when doing so materially improves
reviewability. Generated HTML, scans, bulk OCR, page images, raw model runs, and
large generated mention graphs remain artifacts even when each individual file
is below GitHub's hard file-size limit.

## Consequences

- A fresh clone is small and useful without the complete corpus.
- Reproducing a volume requires its manifest plus authorized artifact access.
- Licensed evidence remains private by default and can use signed access at the
  application edge.
- The object store needs an independent backup and lifecycle policy; Git alone
  is not the binary backup.
- FirstLight consumes versioned al-Isabah releases rather than duplicating the
  scholarly source library.


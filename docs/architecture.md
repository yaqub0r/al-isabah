# Architecture

## Product boundary

Al-Isabah is a platform-neutral scholarly dataset with multiple clients. The
public reader, web editor, import and validation tools, future workflow
integration, and future mobile application consume the same domain model.

The repository owns the scholarly truth. FirstLight is a downstream consumer
of explicit, versioned releases; it does not own the canonical al-Isabah data.

The product specification is guidance. Architecture should be added only when
it protects the dataset or enables a demonstrated user workflow.

## Decision hierarchy

1. Preserve the Arabic source and its edition identity.
2. Preserve provenance, portability, and human review decisions.
3. Keep the domain model independent of clients and workflow vendors.
4. Make bilingual reading and scholarly editing excellent.
5. Prefer small, replaceable infrastructure over speculative services.

## Three data layers

### 1. Immutable evidence

`evidence/` holds or describes acquired editions, facsimiles, OCR, witness
texts, page alignment, machine translation runs, criticism, adjudication, and
supplemental checks.

Evidence records are append-only. A correction creates a new record that cites
the superseded record. Canonical Arabic bytes are never normalized in place.
Every localized artifact has a SHA-256 digest and edition/witness identity.

Large source binaries may use Git LFS initially. They are excluded from normal
web deployment builds. A future object store may serve binaries, but the
repository retains hash-bound acquisition metadata sufficient to verify them.

### 2. Canonical editorial dataset

`content/entries/` contains one human-readable JSON record per biography. These
records contain stable identifiers, source spans, aligned Arabic/English
segments, notes, citations, cross-references, and explicit review decisions.

Canonical editorial records cite evidence; they do not embed the entire history
of every machine run. An evidence reference must be resolvable to the exact
source or QA artifact used for the decision.

### 3. Derived products

`derived/` contains reproducible reader pages, search indexes, exports, release
bundles, and downstream snapshots. Derived artifacts are never edited as the
source of truth and may be deleted and rebuilt.

## Initial repository shape

```text
apps/
  web/                    Astro reader with an interactive /admin route
packages/
  model/                  TypeScript types, Zod schemas, serialization, IDs
  editor/                 Decap-independent React editor
content/
  entries/                Canonical entry JSON
  identifiers.json        Permanent allocation and retirement ledger
evidence/
  manifests/              Hash-bound acquisition and migration manifests
  firstlight/             Preserved upstream translation/QA records
pipelines/
  translation/            Existing validated Python pipeline
  import/                 Evidence-to-canonical importers
  export/                 Versioned release builders
scripts/
docs/
  decisions/
```

Validation remains in `packages/model` at first. A separate validation package
is warranted only when it gains a genuinely independent release or dependency
boundary. The reader and admin route remain one Astro application initially;
the reusable editor is the meaningful UI boundary.

## Stable identifiers

Names, slugs, file paths, edition page numbers, and printed entry numbers are
mutable metadata and never serve as identity.

Entry identifiers use an allocated form such as:

```text
isabah-entry-00010759
```

The apparent number is an allocation token. Once assigned it never changes,
even if a printed entry number is corrected. `content/identifiers.json` records
the allocation source, current canonical record, aliases, and retirement state.
An identifier is never reused.

Segments use stable entry-scoped allocation tokens:

```text
isabah-entry-00010759-segment-0001
```

Splitting or merging segments creates new IDs and records which earlier IDs
were superseded; it does not renumber surviving segments.

## Source and edition model

An entry may cite multiple non-contiguous source spans and multiple editions.
A source span identifies:

- work and edition IDs,
- volume and printed page,
- facsimile scan or reader location,
- exact text digest,
- optional entry number as printed in that edition.

One locked edition may be the current editorial authority without pretending
that pagination or readings are universal. Urdu and collateral biographies are
witnesses, not silent replacements for the Arabic authority.

## Translation and review state

Machine assessment and human review are separate dimensions.

```text
translation: untranslated | draft | translated
machineAssessment: pending | passed | needs_attention
humanReview: unreviewed | in_review | reviewed | verified | disputed
```

Automation may set `machineAssessment`; it never sets `reviewed` or `verified`.
Unresolved readings live on the affected segment and remain visible to readers
or editors according to release policy.

Translator notes, editorial notes, and source text are distinct typed objects.
Rendering must not make commentary appear to be Ibn Hajar's text.

## Import policy

The completed FirstLight Volume 8 JSONL is preserved byte-for-byte as upstream
evidence. An importer derives candidate entry records from it and emits a
report. Importers are deterministic, validate before writing, and refuse to
overwrite existing canonical records unless an explicit reconciliation command
names both versions.

Page-level provenance may cover several entries or partial entries. The importer
therefore records source fragments first, then joins fragments into entry
candidates. It does not assume one page equals one biography.

The first validation set must include:

1. a normal single-page entry,
2. an entry spanning a page boundary,
3. an entry with an unresolved witness or name reading.

## Web and editor

The first client is a static-first Astro application. React is used for the
specialized segment editor and only where interaction requires it.

The public reader requires no CMS or runtime content API. `/admin` initially
mounts the same reusable editor package. Authentication and PR creation are
workflow adapters at the edge.

Decap is deferred until the model, importer, and editor vertical slice are
proven. If adopted, it may provide authentication and generic Git workflow, but
only through a thin adapter. No model or editor package may import Decap.

## Search

Search indexes are derived. Arabic normalization occurs only in search fields
and never rewrites canonical Arabic. The initial implementation may use
Pagefind or another static index after representative Arabic and English
queries are benchmarked.

## FirstLight integration

Al-Isabah publishes a versioned data bundle and manifest containing hashes,
schema versions, coverage, review state, and download locations. FirstLight
pins a specific release and checksum. Story-specific annotations remain in
FirstLight and refer to stable al-Isabah IDs.

No Git submodule is planned: a pinned release is easier to clone, validate,
upgrade, and roll back.

## Hosting and future API

Cloudflare Pages is a candidate deployment target, not part of the domain
architecture. The public reader remains statically deployable.

A backend or workflow service is introduced only when collaboration needs can
no longer be met safely with GitHub and a replaceable adapter. A future mobile
client consumes the same schemas or a generated API contract; the current web
UI is not abstracted into a cross-platform component system prematurely.

## Rights and publication

Repository visibility, source redistribution, and public deployment are
separate decisions. Each source artifact records its rights status. The
repository remains private and no source binary is published until an explicit
release decision confirms the intended rights posture.

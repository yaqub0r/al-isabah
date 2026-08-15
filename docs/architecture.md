# Architecture

## Product boundary

Al-Isabah is a platform-neutral scholarly dataset with multiple clients. Reader
and review applications, import and validation tools, and future clients consume
explicit book-owned contracts rather than importing a web application from this
repository.

The repository owns the scholarly truth. Downstream applications consume
explicit, versioned releases; they do not own the canonical Al-Isabah data.

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

Large source binaries live in versioned R2 object storage and are excluded from
Git. The repository retains hash-bound acquisition and rights metadata
sufficient to verify every object and determine whether it may be published.

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

## Repository shape

```text
content/
  entries/                Canonical entry JSON
  review-proposals/       Validated, non-canonical review workflow inputs
  identifiers.json        Permanent allocation and retirement ledger
evidence/
  manifests/              Non-sensitive publication and migration manifests
compliance/               Source classification and promotion decisions
scripts/                  Canonical validation and deterministic release tools
schemas/                  Interchange and workflow JSON Schemas
docs/
  decisions/
```

Al-Isabah governs acquisition decisions, translation runs, comparison roles,
and pre-publication review through its local contracts. Restricted source
expression, model traces, and large immutable evidence may live in approved
access-controlled storage; the repository retains their non-sensitive,
hash-bound provenance and every policy needed to interpret them. Canonical
content contains only approved records, their book-specific public provenance,
stable IDs, and deterministic publication validation.

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

## Promotion policy

Candidate records remain non-canonical until the repository-local
source-compliance and scholarly-review gates approve an explicit promotion
manifest. Repository validation refuses canonical content that lacks reviewed
Arabic and English, an active stable identifier, source hashes, and promotion
provenance. Import never silently overwrites canonical history.

## Reader and review workflow

A downstream application owns its reader and proposal editor, reviewer state,
and deployment. This repository owns the translation and canonical-content
contracts those interfaces consume; it does not contain or deploy a web
application.

A consumer may use a replaceable GitHub workflow shell that creates a
contributor-owned fork and pull request to this repository. Its editor emits a
validated proposal using the repository's review-proposal contract. A proposal
is not canonical scholarship and never silently changes Arabic. Repository
validation and maintainer review must approve the corresponding editorial
change.

## Search

Search indexes are derived. Arabic normalization occurs only in search fields
and never rewrites canonical Arabic. The initial implementation may use
Pagefind or another static index after representative Arabic and English
queries are benchmarked.

## Downstream integration

Al-Isabah publishes a versioned data bundle and manifest containing hashes,
contract versions, coverage, and review state. A downstream application pins a
specific release and checksum. Application-specific annotations remain outside
this repository and refer to stable Al-Isabah IDs.

No Git submodule is planned: a pinned release is easier to clone, validate,
upgrade, and roll back.

## Hosting and future interfaces

Hosting stays outside this book's domain model. A future mobile client consumes
the same book releases or a generated interface contract; this repository does
not abstract a web UI into a cross-platform component system.

## Rights and publication

Repository visibility, source redistribution, and public deployment are
separate decisions. The repository is public, while each source artifact still
records its rights status. No source binary is published until an explicit
release decision confirms the intended rights posture.

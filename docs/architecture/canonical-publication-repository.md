# Canonical publication repository model

- **Status:** Proposed
- **Issue:** [#9](https://github.com/yaqub0r/al-isabah/issues/9)

## Purpose

This repository is the canonical, publication-ready scholarly record for
*al-Isabah fi Tamyiz al-Sahabah*. Sabiqah prepares and approves content through
its governed workflow; this repository preserves the approved edition and
publishes reproducible, versioned releases.

This record defines repository responsibilities and trust boundaries. It does
not establish the rights status of a particular source or replace qualified
legal review.

## Repository responsibilities

The repository owns:

- approved canonical Arabic records and aligned English translations;
- stable work, entry, segment, and source identifiers;
- book-specific bibliographic provenance and rights basis for released content;
- independently written editorial decisions, annotations, uncertainty, and
  review state;
- schemas, validation, and deterministic derived products needed to reproduce
  a release; and
- immutable release identifiers, source commits, manifests, and change history.

The public record must distinguish the witness used as a translation or
transcription base from witnesses consulted only for comparison. It should
contain enough non-sensitive provenance to audit a released record without
reproducing restricted evidence.

## Responsibilities outside this repository

Sabiqah governs:

- acquisition and private storage of research witnesses;
- rights assessment and clearance workflow;
- detailed comparison material that is not approved for public release;
- translation, contributor, scholarly-review, and compliance workflow;
- accounts, invitations, reviewer reputation, and other application state; and
- reader/editor presentation and deployment infrastructure.

Restricted scans, OCR, translations, rights-holder correspondence, credentials,
private storage locations, and reconstructive comparison files must not be
committed here. A provider's public availability is provenance, not by itself a
reuse authorization.

## Promotion boundary

Content enters this repository through an explicit, reviewed promotion from
Sabiqah. Each promotion must identify:

- the content and provenance manifest;
- the Sabiqah compliance-policy version applied;
- the Sabiqah translation-quality policy version and passing attestations for
  source authority, public-output eligibility, Arabic-form honorific
  preservation, and translation lineage;
- the source commit or reproducible content hash;
- completed scholarly and compliance reviews; and
- unresolved limitations that must remain visible to readers and reviewers.

Repository validation and maintainer review are independent gates. Promotion
does not permit Sabiqah or an agent to silently overwrite canonical Arabic,
translation, provenance, or editorial history.

Sabiqah may expose a separately validated `public-working` corpus before this
promotion. Such a corpus must use approved public-source expression, carry its
license and attribution, exclude private evidence, and quarantine failed
records. Public readability is not an implicit promotion request: this
repository accepts only the subset that later completes human scholarly review,
compliance approval, and the manifest gates above.

## Release and consumption

Every public release is pinned to an immutable repository state and contains
only material approved for that release. Sabiqah and other consumers use the
versioned release contract rather than private evidence or a mutable working
branch. The repository remains platform-neutral: its domain model must not
depend on Sabiqah's current web framework, hosting provider, or editorial UI.

Corrections arrive as reviewable proposals with their rationale and evidence
references. Accepted corrections create new history; they do not erase the
provenance or review record of earlier releases.

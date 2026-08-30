# Canonical publication repository model

- **Status:** Proposed
- **Issue:** [#9](https://github.com/yaqub0r/al-isabah/issues/9)

## Purpose

This repository is the canonical scholarly authority for
_al-Isabah fi Tamyiz al-Sahabah_. It governs translation and review through its
local contracts, preserves the approved edition, and publishes reproducible,
versioned releases. A downstream application may execute or present those workflows as a client,
but it does not own the book's policy.

This record defines repository responsibilities and trust boundaries. It does
not establish the rights status of a particular source or replace qualified
legal review.

## Repository responsibilities

The repository owns:

- the translation-quality contract and Al-Isabah implementation profile;
- source classification, translation runs, review state, and promotion rules;
- approved canonical Arabic records and aligned English translations;
- stable work, entry, segment, and source identifiers;
- book-specific bibliographic provenance and rights basis for released content;
- independently written editorial decisions, annotations, uncertainty, and
  review state;
- schemas, validation, and deterministic derived products needed to reproduce
  a release; and
- immutable release identifiers, source commits, manifests, and change history.

Aggregate translation completion is distinct from scholarly management. A
locked volume or cohort is `agent_complete` after all applicable autonomous
translation stages are exhausted with zero remaining agent units. Human review
then continues per record and may produce corrections indefinitely; its
coverage does not determine or erase the completion state.

The public record must distinguish the witness used as a translation or
transcription base from witnesses consulted only for comparison. It should
contain enough non-sensitive provenance to audit a released record without
reproducing restricted evidence.

## Responsibilities outside public Git

Restricted scans, OCR, witness translations, rights-holder correspondence,
credentials, private storage locations, detailed comparison passages, and
reconstructive model traces must not be committed here. They may live in
project-approved access-controlled storage or be processed through a client
application, but this repository still governs their identity, hash, witness
role, allowed use, and effect on a translation decision. A provider's public
availability is provenance, not by itself a reuse authorization.

Each downstream application governs its own accounts, invitations, reviewer
reputation, application state, reader/editor presentation, and deployment infrastructure. Those are
application responsibilities, not translation-policy authority.

## Promotion boundary

Content becomes canonical through an explicit, locally validated promotion.
Each promotion must identify:

- the content and provenance manifest;
- the repository-local compliance-policy binding applied;
- the local translation-quality contract/profile versions and passing attestations for
  source authority, public-output eligibility, Arabic-form honorific
  preservation, and translation lineage;
- the source commit or reproducible content hash;
- passing rights, public-boundary, deterministic-validation, substantive, and
  compliance controls; and
- complete disclosure of unresolved limitations and ongoing human-review state.

Repository validation and maintainer review are independent gates. Promotion
does not permit an application or agent to silently overwrite canonical Arabic,
translation, provenance, or editorial history.

An application may expose a separately validated `public-working` corpus before
canonical promotion. Such a corpus must use approved public-source expression,
carry its license and attribution, exclude private evidence, and quarantine
failed records under the local translation contract. Public readability is not
an implicit promotion request: only the subset that passes the substantive
compliance and manifest gates becomes canonical. Human review remains
append-only, ongoing metadata; zero or incomplete coverage never blocks
promotion by itself.

## Release and consumption

Every public release is pinned to an immutable repository state and contains
only material approved for that release. Consumers use the
versioned release contract rather than private evidence or a mutable working
branch. The repository remains platform-neutral: its domain model must not
depend on a consumer's current web framework, hosting provider, or editorial UI.

The application-neutral handoff is defined by the
[public distribution contract](public-distribution.md). Consumers ingest that
immutable contract rather than inspecting translation packets or depending on
the repository's internal working layout.

Consumers discover the governing policy set and aggregate translation coverage
through the versioned
[translation-governance reference](../contracts/translation-governance-reference.v3.json)
and pin it at an immutable repository commit. That reference records the active
policy, formula-registry, and translation-coverage hashes without replacing the
public distribution schema. Human review remains per-record metadata and
confidence, not a release class or translation-completion test; incremental
translations, corrections, and review coverage use the same immutable release
and supersession cycle.

Public-working handoff now begins with a strict public proposal, not an internal
translation-work packet. The [issue 0026 boundary decision](public-boundary-remediation.md)
records the forward remediation and historical-exposure exception. This does
not change the separate canonical-promotion gates.

Corrections arrive as reviewable proposals with their rationale and evidence
references. Accepted corrections create new immutable superseding releases;
they do not erase the provenance or review record of earlier releases, imply
review completion, or select a different release class.

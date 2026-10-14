# Al-Isabah source compliance

This directory applies Al-Isabah's repository-local source, translation, and
canonical-promotion controls to the material presently available for research
and review.

It is a public operational record, not a source-specific legal opinion. Public
availability is recorded as provenance and is never treated by itself as
permission to reproduce, adapt, or redistribute an artifact.

## Governing contracts

The policy binding is repository-local. It integrity-pins:

- `translation-quality-workflow`;
- `al-isabah-translation-profile`; and
- `entry-title-structure`; and
- `translation-source-profile`.

The active binding, repository-relative paths, and canonical UTF-8/LF SHA-256
digests are recorded in [`policy-binding.v12.json`](policy-binding.v12.json).
Versions 1 through 11 remain byte-stable under their original governance pins.
Validation fails if a required policy file is missing, changed without review,
resolves outside the repository, or names another repository as its authority.

## Records

- [`source-register.v1.json`](source-register.v1.json) classifies source and
  derived-data classes without publishing restricted expression, private
  storage locations, or access credentials.
- [`promotions/available-data.v3.json`](promotions/available-data.v3.json)
  records the explicit Issue #100 controlled public-working release decision
  separately from the still-blocked canonical-promotion decision. Version 2 is
  retained as immutable historical evaluation evidence.
- [`translation-coverage.v1.json`](translation-coverage.v1.json) reports whether
  each locked volume or cohort is agent-complete while keeping human-review,
  current-policy, public-working, and canonical-promotion states independent.
- [`schemas/`](schemas/) defines the machine-readable record shapes.
- [`rights-matrix.al-isabah.v1.json`](rights-matrix.al-isabah.v1.json) is the
  pilot per-book decision record for source roles, allowed uses, public content
  licensing, attribution, exclusions, review date, and follow-up triggers.
- [`../scripts/validate_compliance.py`](../scripts/validate_compliance.py)
  rejects inconsistent or unsafe promotion claims.

## Current result

Public-working distribution and canonical promotion have separate decisions.
The Issue #100 closure admits exactly 12,303 ordered source units across Volumes
1–8 from ten strict proposal/review pairs. It binds 1,382 owned structural
segments, 23 inherited display contexts, eight cumulative volume outputs, and
explicit front/terminal completeness. All 12,303 records remain
human-unreviewed; that state is disclosed but is not itself a publication or
promotion blocker. The distribution uses the pinned licensed OpenITI authority,
required CC BY-NC-SA 4.0 attribution, and a public boundary that excludes
private apparatus and operational locators.

Canonical promotion into this repository remains blocked by concrete source,
rights, provenance, and substantive conditions. In particular:

- the 1995 DKI Arabic facsimile, reader text, OCR, and aligned transcription are
  private/reference-only research witnesses, not approved public source text;
- the modern Urdu translation is a private comparison witness, not a public
  translation base;
- the legacy English and entry projections lack current source/provenance
  binding and deterministic substantive eligibility evidence;
- the old projections still contain modern editorial apparatus and are not the
  public-working corpus;
- exact historical acquisition dates for retained research witnesses were not
  recorded, so the register states that gap instead of inventing dates.

The legacy data is preserved for remediation and scholarly review. The block
does not assert that the underlying medieval work is protected, and it does not
require deleting research evidence. The public-working determination permits
honest reading and review; it does not convert machine-remediated records into
the canonical scholarly edition. Promotion can be reconsidered after English
lineage and substantive findings are deterministically resolved or honestly
carried forward and every applicable repository gate passes. Human scholarly
review remains append-only, ongoing, nonterminal metadata; zero or incomplete
coverage is disclosed and never blocks publication or promotion by itself.

The release-bound v1 promotion record, v2 candidate evaluation, prior
source-register snapshots, policy bindings, and earlier publication closures
retain their historical wording and hashes. They are immutable evidence, not
the active Issue #100 decision. New consumers pin governance reference v13 at
an immutable repository commit and verify both
`promotions/available-data.v3.json` and
`publication/issue-0100.release-closure.v1.json`. The superseded Issue #53
proposal and legacy private 1,550-record Volume 8 corpus remain excluded.

## Public content license and boundary

Eligible public scholarly content is licensed under CC BY-NC-SA 4.0 with the
attribution in [`../SCHOLARLY_CONTENT_RIGHTS.md`](../SCHOLARLY_CONTENT_RIGHTS.md). This grant does
not apply to software, schemas, workflows, tests, or other code. It also does
not reclassify restricted source material.

Public distributions contain no downstream application or private research
system names, private evidence expression, OCR, credentials, operational
details, private paths, storage locations, API details, schema locations, or
source-file locations. Public scholarly provenance remains hash-bound through
edition identifiers, immutable revisions, record hashes, license and
attribution, without publishing those operational locators.

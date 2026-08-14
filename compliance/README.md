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

The binding, repository-relative paths, and canonical UTF-8/LF SHA-256 digests
are recorded in [`policy-binding.v1.json`](policy-binding.v1.json). Validation fails if a
required policy file is missing, changed without review, resolves outside the
repository, or names another repository as its authority.

## Records

- [`source-register.v1.json`](source-register.v1.json) classifies source and
  derived-data classes without publishing restricted expression, private
  storage locations, or access credentials.
- [`promotions/available-data.v1.json`](promotions/available-data.v1.json)
  evaluates the presently available Volume 8 and Khadijah data for promotion.
- [`schemas/`](schemas/) defines the machine-readable record shapes.
- [`../scripts/validate_compliance.py`](../scripts/validate_compliance.py)
  rejects inconsistent or unsafe promotion claims.

## Current result

Public working display and canonical promotion now have separate decisions.
Sabiqah may anonymously serve `al-isabah-public-openiti-5835c18-v1` because all
1,565 legacy book entries are rebuilt against the pinned licensed OpenITI
authority, attributed under CC BY-NC-SA 4.0, and stripped of private apparatus
and locators. The 1,496 translations that pass the public-output and Arabic-form
honorific checks retain English; the other 69 entries remain public in approved
Arabic while their legacy English is withheld. The 14 FirstLight contextual
passages are not book entries and remain named in the corpus quarantine ledger.

Canonical promotion into this repository remains blocked. In particular:

- the 1995 DKI Arabic facsimile, reader text, OCR, and aligned transcription are
  private/reference-only research witnesses, not approved public source text;
- the modern Urdu translation is a private comparison witness, not a public
  translation base;
- the legacy English and entry projections have not completed human and
  canonical-repository review;
- the old projections still contain modern editorial apparatus and are not the
  public-working corpus;
- exact historical acquisition dates for retained research witnesses were not
  recorded, so the register states that gap instead of inventing dates.

The legacy data is preserved for remediation and scholarly review. The block
does not assert that the underlying medieval work is protected, and it does not
require deleting research evidence. The public-working determination permits
honest reading and review; it does not convert machine-remediated records into
the canonical scholarly edition. Promotion can be reconsidered after English
lineage and scholarship are independently reviewed and every applicable
repository gate passes.

# Al-Isabah source compliance

This directory applies Sabiqah's content-source and canonical-promotion
contracts to the actual Al-Isabah material presently available for research
and review.

It is a public operational record, not a source-specific legal opinion. Public
availability is recorded as provenance and is never treated by itself as
permission to reproduce, adapt, or redistribute an artifact.

## Governing contracts

The policy binding is pinned to Sabiqah merge commit
`58160d917b2c965f89c6d5d30a814562fe0b2dd6`:

- `content-source-compliance`
- `translation-quality-workflow`
- `canonical-book-promotion`

The binding, contract paths, and integrity reference are recorded in
[`policy-binding.v1.json`](policy-binding.v1.json).

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
Sabiqah may anonymously serve `al-isabah-public-openiti-5835c18-v1` because its
1,506 included records are rebuilt against the pinned licensed OpenITI authority,
attributed under CC BY-NC-SA 4.0, stripped of private apparatus and locators,
and checked for Arabic-form honorific preservation. All 73 failing legacy
records are named in the corpus quarantine ledger instead of being served.

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

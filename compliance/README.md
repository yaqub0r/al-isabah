# Al-Isabah source compliance

This directory applies Sabiqah's content-source and canonical-promotion
contracts to the actual Al-Isabah material presently available for research
and review.

It is a public operational record, not a source-specific legal opinion. Public
availability is recorded as provenance and is never treated by itself as
permission to reproduce, adapt, or redistribute an artifact.

## Governing contracts

The policy binding is pinned to Sabiqah merge commit
`348c0c4a5a1bc5943620d6bff61b1d0db836da67`:

- `content-source-compliance`
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

Promotion is blocked. In particular:

- the 1995 DKI Arabic facsimile, reader text, OCR, and aligned transcription are
  private/reference-only research witnesses, not approved public source text;
- the modern Urdu translation is a private comparison witness, not a public
  translation base;
- the current English and entry projections depend on that source lineage and
  have not completed human and compliance review; and
- the entry projections contain modern editorial apparatus from the 1995
  edition; and
- exact historical acquisition dates for retained research witnesses were not
  recorded, so the register states that gap instead of inventing dates.

The data is preserved for remediation and scholarly review. The block does not
assert that the underlying medieval work is protected, and it does not require
deleting research evidence. Promotion can be reconsidered after a reusable
Arabic base is established, protected modern expression is excluded, English
lineage is independently reviewed, and outstanding scholarly review is
complete.

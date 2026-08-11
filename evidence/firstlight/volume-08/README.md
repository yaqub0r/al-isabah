# al-Isabah Arabic-to-English workspace

This workspace implements the bounded translation workflow tracked by issue
#971. Arabic is the canonical source. English output remains an unapproved
research draft until an operator reviews it; the Urdu edition is a secondary
witness for ambiguity resolution.

## Volume 1 calibration wave

- Scan pages: 168-192 (printed pages 167-191)
- Coverage: first 25 pages of the biographical dictionary, entries 1-60
- Arabic OCR words: 8,871
- English draft words: 9,364
- Explicit review flags: 90
- Translation units: 25/25 populated
- Source/PDF alignment: 751 hOCR page-index records for 751 PDF scan pages

Artifacts:

- `volume_01.calibration-pages-0168-0192.jsonl` contains immutable Arabic page
  observations, English targets, source hashes, page citations, flags, and
  translation provenance.
- `volume_01.calibration-drafts.json` is the human-readable draft set used to
  populate the JSONL records.
- `volume_01.calibration-report.json` records measured scope and quality gates.

## Calibration finding

The main biographical prose, quotations, isnads, and identity disputes were
translated. Dense modern editorial bibliography lists were summarized in this
calibration wave. Production translation must preserve those references as
structured citations rather than summarize them. This is an explicit scope
finding, not approved full-page fidelity.

Every target is marked `draft`. Flags identify OCR damage, uncertain
transliterations, disputed identities, weak reports, poetry, and page-boundary
continuations. No flag is an operator decision.

## Volume 8 production translation

- PDF scan pages: 537
- Substantive text: scan pages 4-494 (491 pages)
- Source OCR words across all scans: 166,498
- Main Khadijah bint Khuwaylid entry begins on scan page 100
- Pages 495-537 are edition indexes retained as source metadata
- Production plan: ten reviewable waves using the complete-apparatus prompt

`volume_08.usul-aligned-source.jsonl` is now the canonical machine-readable
Arabic input for all 491 substantive pages. It contains 490 paired Usul reader
pages plus one facsimile transcription for the unavailable reader chunk; the
alignment report records zero heading mismatches.

The existing `volume_08.translation-units.jsonl` and `volume_08.review.html`
remain the legacy draft baseline until the Codex blind translation, independent
critic, required image-aware Urdu witness checks, full xhigh adjudication, and
deterministic QA all finish. The finalizer replaces those artifacts only after
all 491 pages pass; it then writes `volume_08.machine-readiness.json`, which is
the interface gate for human review. Machine readiness is not operator approval.

`volume_08.translation-plan.json` records the ten earlier production waves and
is retained as provenance rather than evidence that the new quality pipeline
has completed.

Wave 1 (scan pages 4-53) is draft-complete and unreviewed:

- Translation units populated: 50/50
- Arabic OCR words: 15,512
- English draft words: 19,352
- Explicit review flags: 227
- Pipeline tests: 8/8 passing
- Human review, Urdu cross-check, and name-authority reconciliation: pending

Wave 2 (scan pages 54-103) is draft-complete and unreviewed:

- Translation units populated: 50/50
- Arabic OCR words: 15,898
- English draft words: 19,663
- Explicit review flags: 317
- Pipeline tests: 8/8 passing
- Human review, Urdu cross-check, and name-authority reconciliation: pending

Wave 3 (scan pages 104-153) is draft-complete and unreviewed:

- Translation units populated: 50/50
- Arabic OCR words: 15,661
- English draft words: 18,850
- Explicit review flags: 353
- Pipeline tests: 8/8 passing
- Human review, Urdu cross-check, and name-authority reconciliation: pending

Wave 4 (scan pages 154-203) is draft-complete and unreviewed:

- Translation units populated: 50/50
- Arabic OCR words: 15,568
- English draft words: 15,225
- Explicit review flags: 391
- Pipeline tests: 8/8 passing
- Human review, Urdu cross-check, and name-authority reconciliation: pending

Wave 5 (scan pages 204-253) is draft-complete and unreviewed:

- Translation units populated: 50/50
- Arabic OCR words: 15,279
- English draft words: 14,135
- Explicit review flags: 493
- Pipeline tests: 8/8 passing
- Human review, Urdu cross-check, and name-authority reconciliation: pending

Wave 6 (scan pages 254-303) is draft-complete and unreviewed:

- Translation units populated: 50/50
- Arabic OCR words: 15,868
- English draft words: 13,868
- Explicit review flags: 585
- Pipeline tests: 8/8 passing
- Human review, Urdu cross-check, and name-authority reconciliation: pending

The main Khadijah bint Khuwaylid entry begins on scan page 100 and continues
through the opening of wave 3. All ten waves, ending at scan page 494, are now
draft-complete. No wave has operator approval.

Visual collation exposed OCR-shifted biography numbers in late wave 1. The
printed headings on scans 42-53 were corrected against the PDF. Wave 2 headings
were visually collated against the PDF, with disputed and corrupted name forms
retained as explicit review flags rather than silently normalized.

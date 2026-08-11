# al-Isabah fi Tamyiz al-Sahabah

The role-based implementation is recorded in
[`source-bundle.v1.json`](source-bundle.v1.json) under the repository-wide
[`source bundle contract`](../../source-bundle-contract-v1.md).

## Canonical Arabic edition

- Edition: Dar al-Kutub al-Ilmiyyah, first edition, 1415 AH / 1995
- Investigators: Adil Ahmad Abd al-Mawjud and Ali Muhammad Muawwad
- Coverage: complete eight-volume work
- Preferred paired provider: Usul version `4CPCkl83K7`
- Usul facsimile: one localized, verified 4,742-page PDF
- Volume 8 machine text: all 491 substantive scan pages are localized and
  aligned to reader pages 3916-4406. Of these, 490 use Usul reader text and scan
  page 4 uses a facsimile transcription because the reader omitted that page.
- Facsimile collation: exact, fail-closed repairs are recorded for scan pages 6,
  35, 84, 161, 287, 366, 369, and 404 in
  `volume_08.source-repairs.json`. The aligned source records each intervention
  rather than silently changing provider text.
- Entry invariant: the corrected Volume 8 source contains exactly 1,550
  biography headings, continuously numbered 10759-12308, with no gaps,
  duplicates, or reversals.
- Archive fallback: eight localized PDFs (4,750 scan pages) and eight OCR text
  layers, retained as an independent acquisition and recovery route

The eight-page scan-count difference is an acquisition/pagination fact, not a
claim that the bibliographic editions differ. Page alignment must reconcile it
before Usul and Archive page numbers are treated as interchangeable.

## English state

No complete independently published English edition of al-Isabah Volume 8 is
localized or used as the translation source. Codex translates the locked Arabic
edition directly. Published English passages from other works may be recorded as
passage-level witnesses, but they do not become the English source for
al-Isabah.

An earlier structured English draft covers all 491 substantive scan pages, but
it is not eligible for operator review. Issue #971 is replacing it with the
provenance-bound Codex pipeline: blind translation, independent fidelity
criticism, multilingual witness resolution for material uncertainties, xhigh
adjudication, deterministic final QA, durable name JSON, and a regenerated
presentation. The interface remains fail-closed until every autonomous stage
passes across the complete volume. There are **zero operator-approved units**.

## Witnesses

The complete Maktaba Rahmaniya Urdu edition (4,163 pages) is localized as a
secondary translation witness. Its OCR is too weak for unreviewed bulk use,
especially around names and isnads. Arabic remains canonical. Persian, Turkish,
or other translations may be added passage-by-passage when they resolve a
specific ambiguity and their contribution is recorded.

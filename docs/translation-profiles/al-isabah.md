# Al-Isabah translation profile

- **Status:** Active
- **Work:** _al-Isabah fi Tamyiz al-Sahabah_ by Ibn Hajar al-Asqalani
- **Governing contract:**
  [`translation-quality-workflow`](../contracts/translation-quality-workflow.md)
- **Ownership issue:** [#22](https://github.com/yaqub0r/al-isabah/issues/22)

## Purpose

This profile specializes the repository-local translation-quality contract for
Al-Isabah. It captures the proven Volume 8 workflow in a form that can fill the
other volumes and topic cohorts without renumbering existing records.

It contains policy and non-sensitive implementation requirements only. Private
facsimiles, OCR, model outputs, comparison passages, object locations, and
credentials remain in project-approved access-controlled storage and never in
public Git.

Every durable Al-Isabah Arabic/English record and generated reading
presentation is a public work product. It must satisfy the public-output
invariant in `translation-quality-workflow` before it is created or replaced.

## Authority and witnesses

The authoritative Arabic base must be a verified public-domain or otherwise
publication-approved witness of Ibn Hajar's text. Its facsimile and aligned
machine-readable Arabic remain hash-bound throughout the workflow. Modern
editorial introductions, footnotes, manuscript apparatus, indexes, and similar
paratext are outside the translation scope unless separately approved.

The current approved machine-readable authority is the OpenITI `0875AH`
repository at commit `5835c183b8bbf4ea454d5c1be2b168b669403771`, file
`0852IbnHajarCasqalani.IsabaFiTamyiz.JK000533-ara1.mARkdown`, SHA-256
`bc9db8134c8278973967c91c00324531833f643fc0fb2c8ebe318c9ed4469eea`.
Its published license is `CC-BY-NC-SA-4.0`; every public presentation must carry
the attribution and license recorded in
[`compliance/source-register.v1.json`](../../compliance/source-register.v1.json).
The independent Arabic
Collections Online 1905-1907 facsimile is a public-domain visual witness, not a
claim that its pagination matches the OpenITI edition.

This source bundle uses the contract's licensed-transcription pathway: the
human-viewable and machine-readable publication authority are the same pinned
OpenITI artifact. No reusable same-edition facsimile has been approved, so the
working edition reports OpenITI entry and page markers as source metadata but
does not describe them as scan-verified. The ACO facsimile can corroborate the
underlying medieval text only at an independently established passage; it never
supplies OpenITI pagination or public wording.

The 1995 Dar al-Kutub al-Ilmiyyah edition currently represented by the legacy
Usul-aligned research corpus is `private-reference`, not the public Arabic
authority. It may be consulted privately as an alternative-edition witness,
but neither its modern editorial expression nor a machine transcription that
embeds that expression may enter public records. Usul's availability is
provenance, not permission.

Witness roles are explicit:

- another Al-Isabah edition is an **alternative edition**;
- Urdu, Persian, Turkish, or another translation is a **translation witness**;
- _Usd al-Ghaba_, _al-Isti'ab_, and other biographical dictionaries are
  **collateral works**; and
- dictionaries or specialist references are **lexical references**.

A witness may reveal damage or clarify ambiguity. It never silently becomes
the translation base or supplies public wording. Clear Arabic from the
publication-approved authority remains decisive; a corrected reading requires
a cited, independently written, reviewable emendation.

### Honorific language profile

These rules are the repository authority for honorific semantics and
presentation. A machine-readable registry or renderer must implement them
without weakening them. The renderer prefers the following compact Unicode
forms when the detected formula is formulaic and the bundled font supports the
character:

- `صلى الله عليه وسلم` → `ﷺ`
- `صلى الله عليه وعلى آله وسلم` → `﵌`
- `رحمه الله` → `﵀`; `رحمهم الله` → `﵏`
- `رضي الله عنه` → `﵁`; `رضي الله عنها` → `﵂`
- `رضي الله عنهم` → `﵃`; `رضي الله عنهما` → `﵄`; `رضي الله عنهن` → `﵅`
- `عليه السلام` → `﵇`; `عليهم السلام` → `﵈`; `عليهما السلام` → `﵉`
- `عليه الصلاة والسلام` → `﵊`
- `تبارك وتعالى` → `﵎`; `عز وجل` → `﷿`

Arabic and English display the same preferred compact character for the same
semantic formula. The reader exposes expanded Arabic in Arabic context and an
English meaning in English context for accessibility, search, and copy.

The exact source form and the target realization are inventoried separately.
Literal spelling or global count differences open a semantic-review finding;
they do not withhold otherwise public-eligible working English. Known changes
to referent, masculine or feminine agreement, singular, dual or plural number,
or inclusion of the Prophet's family fail machine readiness. Formula wording
that is quoted or analyzed remains substantive and is not compacted.

## Stable units

Canonical publication uses permanent entry identifiers such as
`isabah-entry-00010759`; the apparent number is an allocation token rather than
mutable printed metadata. Segments receive entry-scoped stable identifiers.
Later volume or cohort fills allocate new identities without renumbering or
reusing existing ones.

Every translated unit binds at minimum:

- stable entry and segment identity;
- volume, printed page when available, and facsimile scan;
- printed entry number and heading where present;
- exact Arabic and upstream evidence hashes;
- English candidate, machine state, human-review state, and unresolved items;
- names and observed mentions; and
- complete stage provenance.

## Autonomous implementation

The established pipeline implements the general state machine as follows:

1. establish and rights-classify a publication-approved Arabic authority,
   excluding modern editorial paratext before alignment;
2. align its machine text to its facsimile and audit page, entry, and sequence
   coverage;
3. perform a provenance-bound blind Codex Arabic-to-English pass;
4. independently critique omissions, additions, names, isnads, negation,
   numbering, notes, and cross-page continuations;
5. resolve only flagged concerns against classified translation witnesses,
   alternative Al-Isabah editions, and exact-heading collateral searches;
6. adjudicate every substantive unit into a complete, independently worded
   candidate while retaining explicit unresolved findings;
7. validate exact scope, hashes, entry numbering, material numerals, notes,
   boundaries, model lineage, and all-stage coverage;
8. build stable JSON name candidates and mentions, preserving operator decisions
   across reruns;
9. generate the publicly consumable bilingual reading presentation from
   validated JSONL; and
10. publish a machine-readiness record only after all preceding checks pass.

The existing `al-isabah-reading-a3b76bf-v3` corpus predates this invariant and
is explicitly promotion-blocked private research material. It must not be made
anonymous or relabeled public. Its stable identities and previously generated
English may be migrated only after each displayed Arabic unit and resulting
record is reproducibly rebuilt or audited against the approved public source
bundle. Restricted workflow evidence remains private after migration.

The first deterministic remediation produced
`al-isabah-public-openiti-5835c18-v1`. It exposed all 1,565 source-bound book
entries but incorrectly withheld English from 69 of them. Version 2 restores
publicly consumable working English as
`al-isabah-public-openiti-5835c18-v2`, repairs five source-fidelity
interventions, preserves twelve valid title-only translations, and records
honorific semantic differences as translation-readiness findings rather than
public-output failures. Version 3 leaves the 1,565 public entries unchanged and
reclassifies the 14 legacy contextual passages as excluded pending approved
public-source alignment rather than implying that they are remediable book
records. Its public exclusion report records stable identifiers, safe titles,
dispositions, and reason codes without exposing restricted text or storage
details. Version 4 normalizes punctuation that belonged to expanded English
honorific phrases so the compact character attaches to its referent, and its
validator rejects regressions such as `the Prophet, ﷺ`. Every version is
immutable and bound to its own generated manifest.

The former FirstLight implementation, Sabiqah copies, and closed Al-Isabah
development branches are historical evidence, not governing locations.
Al-Isabah owns future translation execution, this profile, human-review state,
compliance approval, and explicit promotion. External applications may execute
or display the workflow only by consuming a pinned version of these local
contracts.

## Volume and cohort coverage

A whole-volume run locks every substantive page and entry in that volume. A
topic cohort additionally records the discovery query, relationship or
inclusion rationale, all direct-mention
include/exclude decisions, and source spans across Volumes 1-8.

Both shapes produce the same entry and segment contracts. A cohort is therefore
an incremental coverage view, not a competing corpus, and later work can fill
gaps without changing stable identities.

## Al-Isabah-specific quality targets

Machine readiness requires:

- exact coverage of the locked pages or cohort inventory;
- continuous printed-entry sequence where the edition supplies one;
- zero unexplained missing, duplicated, or reordered units;
- explicit preservation checks for names, isnads, negation, entry numbers,
  material numerals, citations, footnotes, and continuations;
- definitive `hit` or `no_match` witness results where witness work is required;
  transient provider failure remains `unavailable` and blocks that concern;
- a complete unresolved list linked to exact source locations;
- matching hashes across aligned Arabic, adjudicated English, the name index,
  source bundle, readiness record, and generated presentation; and
- human-review state still `unreviewed` when machine readiness first opens.

Reasoning effort is calibrated with blinded paired comparisons whose source,
prompt, schema, model family, and witnesses are otherwise identical. A lower
setting is used only when the versioned evaluation policy accepts it without a
material quality regression.

## Reviewer handoff

### Poetry presentation

Al-Isabah reading surfaces preserve poetry as a distinct literary structure.
When the working English supplies an explicit meter label, the complete verse
passage governed by that label is grouped, indented, and italicized; the meter
is shown as a caption rather than allowed to run into the prose. OpenITI `%`
verse delimiters are never displayed to readers. They become parallel Arabic
line boundaries with matching indentation and spacing. Arabic is not forced
into a synthetic italic face: separation, lineation, and the visual rule carry
the distinction while preserving the script's legibility.

The reader must return to ordinary prose styling after the poetry block. When
the source or translation does not establish a reliable poetry boundary, the
pipeline records a review finding rather than inventing one from line length
or punctuation alone.

The public bilingual presentation exposes the work product and its honest
review state through continuous reading, search, stable entry navigation,
names, workflow history, interventions, and unresolved findings. Name review
and English approval stay closed until the relevant source and presentation
satisfy machine readiness.

The reviewer evidence package is a separate governed artifact. It may reference
restricted evidence without copying that evidence into the public
presentation.

Human approval is append-only review evidence. It does not erase uncertainties,
alter canonical Arabic, or directly publish a release.

## Promotion boundary

Eligible records are packaged in an explicit promotion manifest referencing the
immutable translation corpus and evidence hashes without exposing restricted
expression or private object locations. Repository validation independently
checks stable identifiers, reviewed Arabic and English, public provenance,
compliance status, and promotion lineage before accepting canonical content.

Public readability precedes and does not bypass this promotion boundary. A
working record may be publicly consumable while still labeled unreviewed,
unresolved, or promotion-ineligible; canonical publication still requires the
independent gates above.

# Al-Isabah entry-title structure contract

- **Contract ID:** `al-isabah-entry-title-structure`
- **Status:** Active
- **Issue:** [#17](https://github.com/yaqub0r/al-isabah/issues/17)

## Purpose

This contract defines the semantic boundary between an Al-Isabah entry title
and the prose that follows it. The boundary is part of the scholarly dataset,
not a decision for a reader application to infer from line length, typography,
or available space.

## Title invariant

An entry title identifies the subject under whom Ibn Hajar files the notice. It
contains the shortest stable personal-name or heading phrase that identifies
that subject in context. It does not absorb text merely because the source
edition prints that text on the same heading line.

The title excludes:

- lineage that continues after the identifying name;
- nisbas, tribal descriptions, and relationships that function as explanatory
  continuation rather than necessary disambiguation;
- statements such as “the wife of,” “the mother of,” “mentioned by,” or “she
  narrated”;
- narration, biographical prose, cross-references, section furniture, and
  editorial apparatus.

A longer form may remain in the names index as an alias. That does not make the
longer form the entry title.

## Bilingual boundary

Arabic and English titles must represent the same semantic scope. They need not
contain the same number of tokens, but neither language may include lineage,
relationship, or prose that the other language places in the body.

Text removed from a title is never discarded. It becomes the first appropriate
body block in the same language, preserving source order and provenance. When
the continuation is lineage, use a `lineage` block. When a new person is
introduced in relation to the titled subject, begin a new `prose` block unless
the source evidence supports a more specific block kind.

## Presentation boundary

Consumers render the structured title with one consistent title role. Body
length, paragraph count, review state, and the length of the title must not
change that role or its type scale. Lineage and prose use body presentation.
The machine-review presentation and the public projection must both apply the
same governed bilingual boundary; neither may fall back to the raw source
heading or the unsplit adjudicated paragraph.

## Decisions and evidence

Book-specific boundary decisions live in the versioned
[`entry-title-decisions.v11.json`](../../profiles/entry-title-decisions.v11.json)
profile. Each decision records the pinned source authority and the exact title
realization in both languages. A consumer may use that profile to build a
working presentation, but it must not silently expand, shorten, or otherwise
reinterpret the title.

When the pinned source begins with a damaged, non-identifying name fragment, an
optional `editorialSupply` may provide only the missing subject head. The supply
must be visibly bracketed in both title languages and bound to an identified
same-work witness, its exact passage and evidence hashes, the literal pinned
Arabic and English prefixes, and a reviewed equal-scope bilingual personal
name. Projection removes only those literal prefixes from the bodies; it never
rewrites the canonical Arabic or treats the supplied title as source text.

Changing a decision requires reviewable evidence and a new profile version.
Canonical Arabic bytes, source hashes, and earlier decisions remain in history.

Printed entry numbers are display metadata rather than stable identity. When a
source range contains a repeated printed number, each new decision binds its
immutable `sourceUnitId` and exact source-unit hash. Consumers resolve that key
first and may use a printed-number fallback only when the active profile makes
the number unambiguous.

When a pinned source unit consists only of its identifying bilingual title,
the decision uses `bodyOpeningKind: "none"`, exact empty Arabic and English
body openings, and the pinned source-unit SHA-256. This mode is valid only when
the whole readable Arabic unit and cleaned heading equal the decided Arabic
title and the complete adjudicated English equals the decided English title.
Public projection marks the entry as title-only and emits no body paragraphs;
an empty-prefix check alone never proves this state.

## Validation

Validation fails closed when:

- a governed entry does not use the profile's exact bilingual title;
- a machine-review or public projection bypasses the governed title/body split;
- Arabic and English title scopes differ;
- moved title text is lost instead of retained at the beginning of the body;
- a supplied head, pinned prefix, witness passage, evidence hash, or cumulative
  witness binding is missing or has drifted;
- explanatory relationships or narration appear in the title; or
- a title-only decision has extra source or English text, a nonempty or
  one-sided body, a missing or mismatched unit hash, or an ordinary entry is
  marked title-only; or
- a consumer varies title semantics or presentation based on body length.

Entry 11426 is the positive reference for the title/body hierarchy. The initial
profile also resolves the observed boundary defects in 11427, 11430, 11439,
and 11441.

Profile v3 carries forward the immutable v2 decision history, adds the reviewed
Volume 2 decisions, and records witness-bound editorial supplies for damaged
subject headings 2784 and 2880. Profiles v1 and v2 remain immutable historical
decision sets.

Profile v4 carries forward every v3 decision unchanged and adds the 373
title/body-opening decisions for Volume 3 entries 3035–3407. Its new decisions
use the existing ordinary boundary representation, retaining damaged source
forms and unresolved readings without supplying missing letters. Profiles v1–v3
remain immutable historical decision sets. These title decisions do not assert
completion of full-biography translation or human scholarly review.

Profile v5 carries forward every v4 decision unchanged and adds the 373
source-only title/body-opening decisions for Volume 3 entries 3408–3780. Its
new decisions use the ordinary boundary representation, retain literal damaged
source forms, and exclude recognized OpenITI milestone controls from display
text through the existing source-boundary grammar. They make no witness-bound
editorial supplies. Profiles v1–v4 remain immutable historical decision sets,
and Issue 80 continues to bind profile v4 exactly.

Profile v6 carries forward every v5 decision unchanged and adds the 745
source-only title/body-opening decisions for Volume 3 entries 3781–4525.
Five headings begin with an isolated literal `ز`. Their decisions retain
that prefix visibly in both title languages without assigning its role or
altering source bytes. No witness-bound editorial supplies are made.
Profiles v1–v5 remain immutable historical decision sets; Issue 82 keeps
its exact v5 binding. These decisions do not assert full-biography
translation or human scholarly review.

Profile v7 carries forward every v6 decision unchanged and adds the 1,633
source-only title/body-opening decisions for Volume 4 entries 4526–6158.
Entry 5041 is the exact title-only source unit `عبد الله الأنصاري`; its decision
uses the title-only representation and binds the complete source-unit hash.
The remaining new decisions use the ordinary boundary representation and
retain damaged or unresolved source readings without silent repair. Profiles
v1–v6 remain immutable historical decision sets, and Issue 84 keeps its exact
v6 binding. These decisions do not assert full-biography translation or human
scholarly review.

Profile v8 carries forward every v7 decision unchanged and adds the 1,604
source-only title/body-opening decisions for Volume 5 source ordinals
6159–7762. Its new decisions bind source-unit identity and exact source hashes,
so the repeated printed numbers 6986 and 7760 remain distinct. Ordinal 7613 is
the exact title-only unit `مالك بن الجلاح`. Profiles v1–v7 remain immutable;
Issue 86 keeps its exact v7 binding. These decisions do not assert
full-biography translation or human scholarly review.

Profile v9 carries forward every v8 decision unchanged and adds the 1,722
source-only title/body-opening decisions for Volume 6 source ordinals
7763–9484. Ordinals 8282, 8357, and 9010 are exact title-only units. Ordinal
9484 remains one entry even though its source unit crosses into Volume 7; its
four preceding structural segments remain separately owned material and are
not absorbed into the entry title. Profiles v1–v8 remain immutable, and Issue
85 keeps its exact v8 binding. These decisions do not assert full-biography
translation or human scholarly review.

Profile v10 carries forward every v9 decision unchanged and adds the 1,940
source-only title/body-opening decisions for Volume 7 source ordinals
9485–11424. The prior cross-volume entry remains wholly owned by ordinal 9484;
the Volume 7 addition begins with the next complete source unit. New decisions
bind source-unit identity and exact source hashes and make no editorial supplies.
Ordinals 10139, 10168, 10313–10319, 10328, 10657, and 10728–10731 use the exact
title-only representation because the complete Arabic and adjudicated English
units are their decided titles. Profiles v1–v9 remain
immutable, and Issue 91 keeps its exact v9 binding. These decisions do not
assert human scholarly review.

Profile v11 carries forward every v10 decision unchanged and adds the 879
source-bound title/body-opening decisions for Volume 8 source ordinals
11425–12303. Historical unkeyed Volume 8 positive references remain immutable,
but current records resolve only through their exact `sourceUnitId` and source
hash; an unknown identity never falls back to the historical printed number.
Ordinals 11930 and 12023 use the exact title-only representation. Ordinal
11555 retains `بنت عجرة` / “daughter of ʿAjrah” as lineage body text rather
than misclassifying the relationship as part of the title or as an empty body. No
editorial supplies are added. Profiles v1–v10 remain immutable, and Issue 96
keeps its exact v10 binding. These decisions do not assert human scholarly
review.

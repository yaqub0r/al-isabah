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
[`entry-title-decisions.v5.json`](../../profiles/entry-title-decisions.v5.json)
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

## Validation

Validation fails closed when:

- a governed entry does not use the profile's exact bilingual title;
- a machine-review or public projection bypasses the governed title/body split;
- Arabic and English title scopes differ;
- moved title text is lost instead of retained at the beginning of the body;
- a supplied head, pinned prefix, witness passage, evidence hash, or cumulative
  witness binding is missing or has drifted;
- explanatory relationships or narration appear in the title; or
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

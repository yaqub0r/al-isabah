# Elixr-approved story projection

- **Contract ID:** `elixr-approved-story-projection`
- **Version:** `1.0.0`
- **Status:** Active, public-working, partial coverage
- **Issue:** [#47](https://github.com/yaqub0r/al-isabah/issues/47)
- **Schema:** [`elixr-approved-story-projection.v1.schema.json`](../../schemas/elixr-approved-story-projection.v1.schema.json)
- **Source admission:** [`khadijah.v1.json`](../../profiles/story-projections/khadijah.v1.json)
- **Projection:** [`khadijah.elixr-approved-story-projection.v1.json`](../../content/story-projections/khadijah.elixr-approved-story-projection.v1.json)

## Purpose and authority

This contract supplies a narrow, text-free Al-Isabah input for later Elixr
story-package assembly. Al-Isabah remains the source-admission, rights, review,
stable-ID, correction, and release authority. Elixr may assemble a package from
this projection; it must not infer a broader Khadijah corpus or turn a
presentation choice into an upstream scholarly decision.

Version 1 pins the immutable public-working schema-v2 release for commit
`278e4e43f983ff7733368557516406f1f53211dc`, release tag
`public-working-278e4e43f983ff7733368557516406f1f53211dc`, asset SHA-256
`41c3ffd1b665a7e9af689c5540b668907cb6b84f4fae23033ab418209d1e1329`,
and public proposal `issue-0026-public-proposal-v1`. The proposal in turn pins
the OpenITI JK000533 authority at revision
`5835c183b8bbf4ea454d5c1be2b168b669403771` and artifact SHA-256
`bc9db8134c8278973967c91c00324531833f643fc0fb2c8ebe318c9ed4469eea`.
The projection does not alter that release, create another release class, or
change canonical-promotion state.

Al-Isabah's authority over this projection is distinct from the critical status
of a report preserved in Ibn Hajar's compilation. Source-report existence,
source-critical qualification, evidentiary and transmission strength, and
story-use suitability are separate fields. The presence of a report in the
authority is not silently converted into a settled historical assertion.

## Public source admission and story use

All four scoped public records are admitted as source reports. `needs_attention`
is per-record review metadata, not an exclusion rule or release class. No raw
source or translation text is copied into the projection.

| Public record and locator | Source/review status | Permitted story use |
| --- | --- | --- |
| `openiti-5835c183-unit-000097`, volume 1, page 50, source ordinal and printed entry 97 | `needs_attention`; the source preserves competing genealogical attribution, criticism of a transmission route, and a separate killer variant. | Preserve the linked genealogy claims in an unresolved ambiguity set. Elixr may say that attributed accounts differ; it must not select a settled lineage. The criticized transmission is metadata and is not itself an exclusion. |
| `openiti-5835c183-unit-000171`, volume 1, page 76, source ordinal and printed entry 171 | `passed`; no unresolved public findings. | The supported kinship assertion is the factual spine. Two migration participations remain `qualified_context` with relative chronology only because they concern the related record rather than constituting a Khadijah biography. |
| `openiti-5835c183-unit-000399`, volume 1, page 175, source ordinal and printed entry 399 | `needs_attention`; an otherwise-unattested maternal attribution is recorded and rejected against a competing attribution. No transmission weakness is asserted by this contract. | Preserve both maternal-attribution assertions in parallel. The rejected claim remains evidence that the source reports and evaluates the claim, not permission to state it as fact; the competing claim also remains explicitly attributed within the ambiguity set. |
| `openiti-5835c183-unit-000795`, volume 1, pages 351-353, source ordinal 795 and printed entry 796 | `needs_attention`; the public findings distinguish identity/religious-affiliation and chronology ambiguity, interpolation, companion-status uncertainty, and mixed or unassessed transmission status. | Preserve the two journey-context assertions as parallel attributed reports. Elixr may present that accounts differ, but may not choose a journey context, resolve identities, or invent a date, location, causal sequence, or dialogue. Transmission status alone does not block use. |

These qualifications are inherited from the source record and its public
source-critical findings. The projection pipeline encodes and separates them;
it does not introduce a new translation claim or silently resolve them. All four
records remain `unreviewed` for human-review metadata in the pinned release.
Human review may later change per-record metadata and confidence through another
immutable release cycle, but not the release class.

## Story-use tiers and ambiguity

- `factual_spine` is limited to an unqualified, source-supported assertion with
  no unresolved factual ambiguity in this projection.
- `qualified_context` preserves usable attested context while carrying any
  required attribution or limitation.
- `attributed_disputed_report` preserves a report and its source-critical status
  without representing it as settled fact. Attribution is mandatory.
- `not_suitable_for_story` requires an explicit story-specific rationale such
  as an identity, chronology, interpolation, or unsupported-causation problem.
  Weak or criticized transmission alone is insufficient.

Competing or qualified assertions are members of closed `ambiguitySets` with an
`unresolved` status. `parallel_attributed_reports` permits Elixr to present the
alternatives side by side or say that accounts differ.
`qualified_ambiguity_context` permits a concise uncertainty statement without
selecting a resolution. Neither mode authorizes precise chronology, invented
causation, dialogue for an identified real person, or new prose claims.

Elixr is not making a religious determination. Transmission-strength metadata
must not be interpreted as a legal ruling or as establishing or negating a
religious obligation.

## Closed public boundary

The admission and output schemas set `additionalProperties: false` at every
object layer. The exporter admits only:

- stable person, event, relationship, claim, and ambiguity-set IDs;
- controlled roles, relationships, event types, assertion classes, critical
  statuses, strength fields, story-use tiers, and ambiguity presentation modes;
- immutable release, proposal, closure, source-record, and integrity identities;
- volume/page citation locators and exact hashes;
- public rights and required attribution;
- per-record machine and human-review state, completeness, confidence, and
  uncertainty codes; and
- active/corrected/superseded lifecycle links.

Arabic or English body text, display names, quotations, excerpts, dialogue,
prose, precise dates, locations, drafts, critiques, model or reasoning data,
witness material, OCR, private notes or locators, credentials, filesystem
paths, and unknown fields are not contract fields. Validation rejects these
recursively without echoing rejected values in diagnostics.

Attested and inferred claims are separate arrays. Version 1 contains ten
source-attested claims and no inferred claims. Human review remains source
record metadata and does not select a different release class.

## Elixr compatibility

Elixr must pin the projection file at an immutable Al-Isabah commit, verify its
file SHA-256, then verify every declared release, proposal, closure, rights,
admission, schema, source-record, claim-set, ambiguity-set, and payload digest.
It must reject:

- an unknown major schema version;
- any integrity or immutable-source pin mismatch;
- unknown or prohibited fields;
- claims backed by a source record outside the closed four-record inventory;
- disputed material promoted to the factual spine or stripped of attribution;
- an alternative removed from an unresolved ambiguity set; and
- a corrected or superseded claim/projection unless it deliberately follows
  the declared replacement.

Elixr may attach presentation or assembly metadata outside this contract. It
must preserve the Al-Isabah IDs, locators, source-report status, critical and
strength fields, story-use tiers, ambiguity membership and presentation mode,
review metadata, rights, and lifecycle links unchanged.

The exact downstream step after this contract merges is an Elixr-owned ingestion
change: pin the merged Al-Isabah commit and projection file digest, add a closed
ingress validator for this v1 shape, and assemble a story package that carries
these IDs, locators, qualifications, ambiguity sets, rights, and lifecycle
fields forward. That work belongs in Elixr and is not performed here.

## Deterministic verification

Run from the repository root:

```sh
python scripts/build_elixr_story_projection.py --check
python scripts/validate_elixr_story_projection.py
python -m unittest tests.test_elixr_story_projection
```

The full repository suite remains the delivery gate:

```sh
python -m unittest discover -s tests
```

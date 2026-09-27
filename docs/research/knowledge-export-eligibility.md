# Knowledge-export eligibility inventory

Issue [#87](https://github.com/yaqub0r/al-isabah/issues/87), inspected at canonical
`main` commit `b73333e71478b1e5eeb494f3274bc53a8b3c3606` on 2026-09-27.
Inventory used policy/coverage/closure metadata and exporter code, not source
bodies, private evidence, or downloaded distribution archives.

| Layer | Verified state | Export implication |
| --- | --- | --- |
| Volume 1 translation | 1,537 agent-complete units; 0 human-reviewed | Translation completion does not establish semantic extraction. |
| Volume 2 translation | 1,497 agent-complete units; 0 human-reviewed | Same distinction; no bulk approved knowledge registry exists. |
| Released structured records | Current release closure binds 3,034 records across V1/V2; latest observed immutable public-working release is `public-working-b73333e71478b1e5eeb494f3274bc53a8b3c3606` | Structured translation records are not independently approved text-free assertions. |
| Approved semantic projection | Khadijah v1: 4 V1 records, 10 attested claims, 0 inferred claims, 3 unresolved ambiguity sets | Only existing approved text-free knowledge artifact found; coverage remains partial. |
| V3/V4 local completion | Reported commits `a0492cc9d9b1f501eeead5b3cf800e9f4434e50c` / `722a158a410692bd62569056f1b386df713fd24e` are separate branches | No integration, release, projection eligibility, or consumer admission inferred; branches untouched. |
| Volume 8 legacy completion | 1,550 agent-complete legacy units; `legacy_audit_required`, public-working blocked | Agent completion alone grants no export eligibility. |
| Human scholarly review | Append-only ongoing metadata; current V1/V2 coverage 0 | Absence is disclosed, not an upstream publication blocker. |
| Canonical promotion | Current readiness record remains blocked under substantive controls | Neither exporter success nor consumer intake changes this state. |
| Elixr admission | Consumer-owned exact pins and distinct promotion rules | New schema is proposed; no real payload is authorized by this milestone. |

Evidence: `compliance/translation-coverage.v1.json`,
`compliance/publication/issue-0070.release-closure.v1.json`,
`compliance/promotions/available-data.v2.json`,
`profiles/story-projections/khadijah.v1.json`, and existing projection/build
contract. The promotion readiness working-publication count is an older scope;
it must not be mistaken for the current 3,034-record release closure.

## Exact real pilot candidate and missing prerequisites

The existing artifact is
`content/story-projections/khadijah.elixr-approved-story-projection.v1.json`,
unchanged at the inspected commit, exact file SHA-256
`24cd5e3b2e3ee055b9ecd15c5b6327d7166638103575fbc0456d8844bcaddb9c`.
It pins source release commit `278e4e43f983ff7733368557516406f1f53211dc`,
asset SHA-256
`41c3ffd1b665a7e9af689c5540b668907cb6b84f4fae23033ab418209d1e1329`.
Its rights, qualifications, unresolved alternatives, and existing consumer pins
continue to apply. It is eligible only for its existing reviewed v1 scope; no
copy or migration is made here.

A real pilot under the new contract needs a reviewed real source/predicate and
rights/attribution profile, approved exact semantic snapshot with complete
dependency closure, real immutable source identities and byte pins, and a
separate Elixr source-admission approval. Broader volumes also need semantic
extraction and assertion review; translation completion is insufficient.
Incomplete human review by itself is not that missing authorization. The
synthetic-only schema intentionally rejects real-mode payloads today.

## Delivery controls and recommendation

The canonical checkout was clean and matched remote main. A dedicated
`codex/issue-87-knowledge-export` branch contains only this milestone. Other
registered worktrees, translation branches, and open translation PRs are not
modified. The active main ruleset requires a PR, resolved review threads, and
the strict `Test inventory and contracts` check; force pushes and deletion are
restricted. There is no required approving reviewer under the solo-maintainer
ruleset. GitHub's legacy branch-protection summary omits these ruleset gates.

`publish-public-distribution.yml` is active. It runs on `main` pushes touching
`content/translation-proposals/**`, `content/public-proposals/**`,
`compliance/**`, `profiles/**`, `schemas/**`, the listed distribution/closure
builder/validator scripts, or the publication workflow itself; manual dispatch
also exists. It has write permission and creates a commit-addressed prerelease.
This change adds `schemas/al-isabah-knowledge-export.v1.schema.json`, so a later
merge can trigger publication even though all fixtures are synthetic. Documentation,
the new exporter, and tests alone do not match that publication path list.

Keep the work local until coordinated scope and tests are established, then
prepare a reviewable PR only under delivery coordination. **Before merge**, an
explicit release decision must address this exact schema-path trigger. Do not
merge assuming a code-only change cannot publish. No workflow change, disabling
step, push, PR, merge, tag, release, or real export is performed in this milestone.

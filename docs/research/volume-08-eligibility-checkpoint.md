# Volume 8 eligibility checkpoint

Issue [#89](https://github.com/yaqub0r/al-isabah/issues/89). Inspected from
`456944fe5d1a7e6bbb6404cc77f3109803893240`, 2026-09-28. This is an upstream
prerequisite checkpoint for complete real import into Elixr, not extraction,
publication approval, or a completed import. The user has since selected the full
legacy Volume 8 scope. The candidate v8 byte-domain crosswalk is now verified;
semantic identity/fidelity review remains separate. The current decision packet
is `docs/decisions/0002-volume08-real-extraction-admission-draft.md`. Earlier pending
statements below describe the initial checkpoint, not a new scope question.

## Authority and exact candidate scopes

The approved authority is the licensed OpenITI JK000533 transcription, revision
`5835c183b8bbf4ea454d5c1be2b168b669403771`, artifact SHA-256
`bc9db8134c8278973967c91c00324531833f643fc0fb2c8ebe318c9ed4469eea`,
9,762,988 bytes. The local source passed exact byte and whole-source inventory
verification: 12,303 source units, 12,298 distinct printed numbers. Its approved
use is the attributed, noncommercial, share-alike working edition described in
the source register. The transcription itself is the human-viewable authority;
no same-edition scan verification is claimed. The independent ACO edition is a
separate visual witness. These classifications do not decide a new Elixr use.

| Candidate scope | Source ordinals | Entries | Owned structural headings | Total substantive units |
| --- | --- | ---: | ---: | ---: |
| Complete women’s book | 10754–12303 | 1550 | 205 | 1755 |
| Entries touching OpenITI physical Volume 8 | 11424–12303 | 880 | 141 | 1021 |

The women’s-book opening is the first of three structural segments owned by
`openiti-5835c183-unit-010754`: segment `001`, raw source-fragment SHA-256
`cfc329c73630e07ec6653cf3278f21df30177558ba2481881b635fed8b18ac38`.
Its opening page metadata is V7 P472. 671 entries start in V7 and 879 in V8.
Unit `openiti-5835c183-unit-011424` spans recorded V7 P751 / V8 P003; counting
only entries whose first location is V8 drops that boundary entry. The final
unit is `openiti-5835c183-unit-012303`, recorded V8 P324–325.

Printed numbers are 10753–12304, with 11423 and 11424 absent. Direct inspection
of the pinned entry markers confirms a jump from 11422 to 11425; there is no
unparsed matching entry marker in between. No record is invented to fill the
numbering holes. This proves parser coverage, not that a manuscript passage is
absent or that an editorial numbering decision is correct. The contiguous
source ordinals are the identities used here. No duplicate printed number occurs
within either candidate range; the whole source has five duplicate numbers.

The two artifacts under `evidence/inventories/issue-0089-*.source-scope.v1.json`
contain complete entry and structural IDs, source-fragment hashes and public
page metadata. They contain no source text, translations, private locations,
semantic claims or approval states. Inherited heading dependencies are separate
from headings occurring inside a slice. The line-accounting guard rejects
unrepresented substantive material, including unowned trailing headings. Both
candidate ranges have zero unrepresented substantive lines and no explicit
modern-paratext exclusions within the selected source span. This is not a new
rights audit of every editorial intervention in the transcription.

## Historical evidence and unresolved reconciliation

The exact candidate commit `20264a5ca018fe2a2890dc070f9c6bd904e3cb84` is available
through GitHub although absent from this local object database. Metadata was
read in memory; restricted bodies were not copied into this checkout. Its
import summary SHA-256 is
`dd8bf591257b4c3d66d53a0b4a726ac60ed83b525c8d569b5bd93fc064861bd3`:
1,550 candidate records, allocated IDs 10759–12308, 491 substantive scan pages,
1,948 historical translation segments, 281 unresolved items, and 208 entries
needing attention. These translation segments are not the same segmentation
as the 205 OpenITI headings. The historical translation plan excludes index
scan pages 495–537 and includes substantive scan pages 4–494.

The original English SHA-256 remains
`f12585cea28d7c7b318728f74b1a95a0d8b2812cb25d6e70f1b9e7b0b9422a3f`
(14,444,214 bytes in the historical migration inventory); aligned Arabic is
`f7f5cd87489283249750778aec2a666300d731fc982f571380f5aad3e915c0ed`
(1,870,254 bytes). These hashes are verified metadata references, not a claim
that the underlying legacy files were obtained and revalidated in this task.
The legacy acquisition inventory still matches its retained summary identity.

The source register approves historical public-working corpus v1 with 1,565
entries from a 1,579-record source inventory, 14 excluded contextual passages,
1,496 English-bearing entries and 69 Arabic-only entries. It pins manifest
`fc5ae6fa659ff331feaccd68d20b6021e20595c1c42a81ffb12c786aef0586e8`
and quarantine report
`3225d59dff247c73a6cbb715d122ef4e8fbde7e6603bc492f0454ac0ae6d04d6`.
The governing profile documents restoration of all 1,565 working English entries
in v2, contextual-exclusion clarification in v3, and punctuation repair in v4.
The arithmetic is consistent with 1,550 legacy entries plus 15 cohort biographies
and 14 excluded contextual passages. That is a hypothesis until the actual
per-record derivative manifest and crosswalk are verified.

No approved local access to the v4 manifest/record mapping has yet been verified.
The coordinator has requested retained access context from the owning project.
Do not guess storage credentials or download a distribution archive as a
substitute. The 1,550 legacy IDs cannot be joined to OpenITI printed numbers:
the ranges differ, and permanent canonical IDs are allocation tokens. A complete
reviewed crosswalk must preserve unmatched, split, combined and duplicate
candidates instead of forcing a bijection because counts happen to match.

## Eligibility counts and next execution

- Publication-approved source units are inventoried for both candidate scopes;
  none of this establishes approved structured knowledge assertions.
- There are zero newly verified/admitted Volume 8 knowledge exports in this
  milestone. Record-level reuse eligibility is **unknown**, not zero, pending
  the remediated corpus mapping and its exact evidence. Current aggregate
  coverage continues to describe 1,550 legacy units as agent-complete.
- All 1,550 legacy candidate records retain their unresolved source/provenance
  and public-boundary classification. The possibly eligible remediated derivative
  is a distinct artifact and must not inherit the old candidate’s blockers by
  assumption. Conversely its historical aggregate approval is not a current
  exact per-record assertion approval.
- Human-review absence does not block upstream eligibility. Stale human-review
  wording in historical registry records cannot override the active contract.
- No exact count requiring new translation or source rework can yet be justified.
  Hash/inventory audit can prove identity and coverage; it cannot independently
  establish semantic fidelity, restricted-expression separation, or claim truth.

Next: settle the user scope; obtain the retained public-working manifest and
controlled crosswalk evidence; verify every legacy-to-source mapping and repair
history; preserve reusable work; classify only demonstrable gaps for targeted
source/translation remediation; approve the separately proposed real knowledge
profile; then perform bounded extraction and independent semantic review with
complete span dispositions before expanding. New translation semantic work
requires the active method and captured explicit task/worker settings. This task
has performed deterministic audit only and claims no semantic-stage execution.

## Reproduction and delivery boundary

Run `python scripts/inventory_source_scope.py --start-unit 10754 --end-unit 12303
--output evidence/inventories/issue-0089-womens-book.source-scope.v1.json --check`
and the same command with start 11424 and the `openiti-v8-touching` filename.
The CLI refuses overwrite; `--check` compares exact canonical output bytes.
Inventory digests hash the complete object excluding `inventorySha256`, using
sorted-key compact ASCII JSON plus LF; exact file digests are separate. Source
fragment hashes retain the existing parser’s LF text domain. Source artifact
hashes bind exact original bytes. Parser fingerprints use repository-normalized
LF text so a Windows checkout does not change the inventory. No scope inventory
is itself a trusted approval configuration.

Issue #89 uses a dedicated branch in the canonical checkout. Other worktrees,
V3–V5 translation branches and PRs #81/#83/#50 are untouched. Main requires a PR,
resolved review threads and the strict `Test inventory and contracts` check.
Publication is active and path-triggered. This checkpoint changes only docs,
new inventory tooling/tests and text-free evidence inventories, outside the
current distribution publication trigger. No merge, release, actual real export
or consumer admission is authorized or performed by this checkpoint.

Missing historical v4 access limits reuse and crosswalk verification. If that
access cannot be recovered, independently deriving knowledge from the approved
source is an alternative after scope, real profile, method and rights/admission
decisions are settled. It need not manufacture legacy translation lineage.
Compare the concrete reuse and fresh-derivation work before selecting either.

## Retained-artifact locator follow-up

The owning project confirmed that historical v4 was produced by the Sabiqa
preservation pipeline at canonical main commit
`b5631b3aa82a1ab3dfdfe91fe2e230a06ddba4fe`. Its immutable corpus ID is
`al-isabah-public-openiti-5835c18-v4`. The exact v4 manifest and record-index
hashes are not retained in the inspected local artifacts or pinned in the
repository metadata. Later v6/v7/v8 builds are distinct successors, not valid
silent substitutes. The coordinator is arranging read-only retrieval and
validation in the existing configured owning environment. Storage locators and
credentials remain outside this public checkpoint. This establishes where to
request evidence; it does not establish the crosswalk or record eligibility.

The final candidate exact-file inventory pins at this checkpoint are:

- Women’s book: `001ea04c30fe3e52dec2d38dd49bb087c74a909474715c07e5a41b19237b4062`.
- OpenITI V8 touching: `833c170425c4ca53e4a63390a7ee226fa08ee754c2cd32f32d7973809a76466d`.

Their embedded inventory digests are respectively
`6b80a92201e07685abbf766cd04a763b1568fab29a136ac915254136a5408584`
and `8c53de2dce499d8bc1c55ae40635a8a811dd113570ac85b3470f57b789bc8aab`.

Validation at the saved checkpoint: all 242 repository unit tests passed;
compliance and current public-tree validation passed; both candidate inventories
regenerated byte-for-byte with `--check`; staged whitespace validation passed.
New regression fixtures are synthetic. No real semantic fixture, restricted
source content, v1 modification, publication or consumer ingestion was added.

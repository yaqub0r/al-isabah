# Agent translation workflow

This is the executable path for distributing Al-Isabah translation across
independent Codex agents. An agent needs this repository, Python 3.11 or later,
Git, GitHub CLI authentication for claiming work, and network access only to
hydrate the pinned public OpenITI source. A downstream application, database, and model service
key are not prerequisites.

The repository contract remains authoritative. Read, in order:

1. [`../contracts/translation-quality-workflow.md`](../contracts/translation-quality-workflow.md);
2. [`../translation-profiles/al-isabah.md`](../translation-profiles/al-isabah.md);
3. [`../contracts/entry-title-structure.md`](../contracts/entry-title-structure.md);
4. this runbook.

## The path

```text
clone -> doctor -> hydrate -> claim -> prepare
      -> blind translate -> independent critique -> witness resolution
      -> adjudicate -> reconcile names -> render/finalize -> submit -> pull request
      -> aggregate agent-complete status for the locked scope
```

Human review is deliberately absent from the agent stages. A valid submission
must still say `unreviewed`; the pull request makes the machine-ready evidence
available for the later human gate.

When every substantive unit in the claimed volume or cohort has passed these
agent stages and the aggregate has zero remaining agent units, the scope is
`agent_complete`—the repository term for translation work being done. Human
review then continues as an independent management state. Review coverage or a
reviewer edit does not unset completion; a later machine-actionable correction
is a new revision with its own completion evidence.

## 1. Check the checkout

Start from an issue-specific branch based on current `main`, then run:

```sh
python scripts/translation_workflow.py doctor
python -m unittest discover -s tests
```

`doctor` verifies the local policy binding, pinned source manifest, ignored
runtime path, and GitHub CLI availability. It does not inspect or expose
credentials.

## 2. Hydrate the public Arabic authority

```sh
python scripts/translation_workflow.py hydrate
```

The command downloads exactly the source in
[`profiles/translation-source.v1.json`](../../profiles/translation-source.v1.json),
checks its byte length and SHA-256, and writes it below ignored
`.runtime/translation/sources/`. It will neither accept a different URL nor
fall back to a similar edition. A mismatch fails closed.

Restricted alternative editions and translation witnesses are not hydrated by
this command. Consult them only for a material flagged uncertainty, through an
approved access path, and never copy their expression into the packet.

## 3. Claim a non-overlapping range

GitHub issues are the shared assignment ledger. Check current claims:

```sh
python scripts/translation_workflow.py status
```

Then claim a small, reviewable range:

```sh
python scripts/translation_workflow.py locate --entry 11482
python scripts/translation_workflow.py claim \
  --start-unit <first-source-unit> \
  --end-unit <last-source-unit>
```

Printed entry numbers are not identity: the pinned OpenITI source contains five
duplicated printed numbers. `locate` therefore maps a printed number to one or
more unambiguous source ordinals. `claim` verifies the requested ordinal range,
checks all open assignment markers for overlap, creates an assigned GitHub
issue, and prints its URL. Use `--dry-run` to inspect the issue body without
creating it. Do not begin a range that lacks an open issue assigned to you.

Claims coordinate work; they do not allocate canonical entry IDs. Packet IDs
refer to immutable source units such as
`openiti-5835c183-unit-011482`. Canonical IDs are allocated separately and
must never be inferred from mutable printed numbering.

## 4. Prepare the source-locked packet

```sh
python scripts/translation_workflow.py prepare --issue 25
```

This rechecks the live assignment ledger, rejects overlapping claims, parses
the exact assigned OpenITI entry markers, and writes an ignored packet such as
`.runtime/translation/packets/issue-0025.json`. The packet binds:

- the issue and assignees;
- the source commit, path, whole-file hash, entry lines, page markers, and
  per-entry raw hash;
- the current local contract/profile hashes; and
- a content-derived run ID.

Run prepared-stage validation before translating:

```sh
python scripts/translation_workflow.py validate \
  --packet .runtime/translation/packets/issue-0025.json
```

## 5. Complete the autonomous stages

For a single-worker range, edit only the packet's output fields. For a
parallel whole-volume run, workers write disjoint ignored runtime shards and
the coordinating agent merges them with the commands below. Never rewrite
`authority`, `policy`, `assignment`, or any `source` field.

For every entry:

1. **Blind translation** — translate directly from `source.arabic`. Record a
   distinct run ID, Codex model identity, reasoning setting, and complete
   English. Do not look at an English translation witness first.
2. **Independent critique** — use a fresh critique pass with a different run
   ID. Inspect omissions, additions, reversals, names, relationships, isnads,
   numbers, negation, honorific semantics, poetry, notes, and continuations.
   Each material uncertainty sets `requiresWitness: true`. A complete critique
   also records the ordered semantic checklist in `semanticAudit`, bound to
   hashes of the readable Arabic and the exact English candidate. A status
   string and an empty findings array are not positive evidence of this pass.
3. **Witness resolution** — set `not_required` only when no critique finding
   requires a witness. Otherwise record the smallest useful classified
   witness checks. Every result ends as `hit` or `no_match`; `unavailable`
   remains a blocker rather than being converted to `no_match`. Record the
   query, classified role, witness identity, exact passage, location, decision,
   retrieval date, evidence kind, and passage/evidence hashes. When witnesses
   are not required, record the source-specific rationale rather than relying
   on the status alone. A material or blocking unresolved item also requires
   completed witness evidence.
4. **Adjudication** — write the complete final candidate and record material
   decisions. Fluent wording must not hide an unresolved reading.
5. **Names** — mark names complete and store durable JSON candidates and
   mentions. Candidate IDs remain packet-scoped until reconciled with the
   canonical identity ledger; do not invent canonical entry IDs. Bind the
   bilingual inventory pass to source and adjudicated-English hashes, and make
   sure every candidate has an English surface in that translation. Packet
   validation rejects the one-title-candidate pattern at collection scale.
6. **Unresolved inventory** — retain an array even when it is empty.
7. **Human state** — leave `humanReview.status` as `unreviewed`.

Do not silently rewrite a completed blind or adjudicated run during QA. If a
deterministic repair is necessary, retain the original run provenance and add
the packet-level `postRunRepairAudit`: it binds the base packet and repair
artifact hashes, a distinct repair-run ID, every affected JSON field, the
old/new text-hash chain, and the reason for the intervention. Machine readiness
fails if the final field values drift from that audit.

A minimal name candidate contains a packet-scoped ID, one person's observed
Arabic form, proposed English form, aliases, confidence evidence, and review
state. A genuine named group may instead be explicitly typed `collective`; do
not use that escape hatch for an unsplit list of people. A mention points to the
owning biography or structural segment through
`recordId` and includes hashed exact spans in `headingArabic` or `arabic`;
`rawOpeniti` may be supplementary, never the only readable binding. These
fields stay JSON even when an application later projects them into a database.

Parallel biography workers use a schema `1.0.0` shard envelope containing the
packet ID, issue number, exact starting and ending source ordinals, and only
the completed output fields for every source unit in that range. The
coordinator applies a completed shard atomically:

```sh
python scripts/translation_workflow.py merge-shard \
  --packet .runtime/translation/packets/issue-0025.json \
  --shard .runtime/translation/shards/issue-0025-units-000001-000010.json
```

Structural and front-matter text is owned by the following source unit. A
schema `1.1.0` structural shard may contain one source ordinal and translations
whose segment IDs exactly match that unit's `source.precedingSegments`:

```sh
python scripts/translation_workflow.py merge-structure-shard \
  --packet .runtime/translation/packets/issue-0025.json \
  --shard .runtime/translation/shards/issue-0025-structure-before-unit-000001.json
```

A worker handling a range may instead provide `startUnit`, `endUnit`, and a
`sourceUnits` array. Each array item contains `sourceOrdinal` and
`precedingTranslations`. The array must be ordered and must exactly include
every source unit in the declared range that owns structural material; units
without structural material are omitted. The same command applies either
shape atomically.

Both commands reject wrong or missing ordinals, source-ID drift, stale policy
hashes, non-final witnesses, reused critique runs, broken name references,
private fields, and structural coverage gaps before writing. Shards and the
working packet stay below ignored `.runtime`; only a separately derived strict
public proposal may enter Git.

## 6. Render and finalize machine readiness

When all autonomous fields are complete:

```sh
python scripts/translation_workflow.py render \
  --packet .runtime/translation/packets/issue-0025.json

python scripts/translation_workflow.py validate \
  --packet .runtime/translation/packets/issue-0025.json \
  --machine-ready
```

`render` creates an English-first bilingual Markdown review surface beside the
packet, records its hash, and sets machine readiness only after all prior gates
pass. It does not set human approval. Machine readiness is per packet; the
aggregate translation-coverage record may declare a volume or cohort
`agent_complete` only after every unit in its locked inventory is machine-ready.

## 7. Prepare the pull-request artifacts

```sh
python scripts/translation_workflow.py submit \
  --packet .runtime/translation/packets/issue-0025.json \
  --output-root <approved-external-evidence-destination>
```

The command revalidates the packet and presentation, rejects private fields and
absolute workstation paths, and writes immutable evidence only to an explicit,
repository-reviewed destination outside this public checkout. It refuses every
destination inside the repository and refuses to overwrite existing evidence.
Do not run `submit` until the project has approved the exact destination. A
separate reviewed process derives a strict `public-proposal.v1` artifact for a
public pull request. Never commit the raw packet, detailed review, `.runtime`,
downloaded sources, private witnesses, or model traces.

For a reviewed, contiguous set of machine-ready packets that has never entered
Git, derive the strict proposal with the packet-set projector:

```sh
python scripts/project_packet_set_public_proposal.py \
  --proposal-id issue-0053-public-proposal-v1 \
  --packet <first-runtime-packet.json> \
  --packet <next-runtime-packet.json> \
  --output content/public-proposals/issue-0053.public-proposal.json

python scripts/validate_public_proposal.py \
  content/public-proposals/issue-0053.public-proposal.json
```

The projector revalidates every packet and review presentation, requires one
contiguous source range under one authority and policy binding, and emits only
allowlisted public fields plus aggregate evidence hashes. The issue-specific
proposal and deterministic public-review artifact may enter Git only after the
strict boundary validator passes.

The pull request references the assignment issue without closing it unless the
complete assigned range is present and valid. Machine-ready does not mean
canonical. A fully covered machine-ready scope is agent-complete even while
human review remains open. Human review, compliance approval, canonical ID
allocation, and promotion remain later, independently recorded gates.

## Recovery and parallel work

- Re-running `hydrate` reuses an already valid source and replaces nothing.
- Re-running `prepare` with unchanged issue, source, and policy produces the
  same run ID. Preserve completed output fields instead of regenerating over
  them.
- If the source, policy, or assignment changes, the old packet fails as stale;
  create a new packet and migrate decisions explicitly.
- Divide work by non-overlapping source-ordinal ranges. Printed entry numbers
  are searchable metadata and cannot be used as shard identity because five
  printed numbers are duplicated. Topic cohorts may refer to the same source
  entries for discovery, but they must not create competing translation claims
  or new stable identities.
- An interrupted agent leaves its issue open and packet local. Another agent
  takes over only after assignment is transferred on GitHub.

## Network-free verification

Tests use a tiny synthetic OpenITI-format fixture and never download the book:

```sh
python -m unittest tests.test_translation_workflow
```

The fixture proves parsing, hashing, assignment overlap detection, packet
coverage, autonomous stage gates, and stale-policy rejection. The real
hydration command separately verifies the full 9,762,988-byte pinned source.

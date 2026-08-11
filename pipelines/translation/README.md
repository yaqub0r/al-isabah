# Translation Batch Toolkit (Production)

This directory now includes a resumable translation workflow for large Arabic source texts.

## al-Isabah Volume 8 autonomous quality pipeline

Issue #971 uses a provenance-bound Codex pipeline before any operator review:

1. `align_usul_volume.py` maps the canonical Usul reader text to facsimile scan
   pages. Volume 8 requires exactly 491 substantive pages. Exact facsimile
   repairs are applied only from the checked-in source-repair ledger and retain
   intervention provenance. The corrected source is also audited for the
   continuous 1,550-entry sequence 10759-12308 before translation.
2. `run_codex_volume_revision.py` performs a blind Arabic-to-English page pass.
   A page is resumable only when its source, prompt, schema, model, and reasoning
   fingerprints still match. Both the per-page state and aggregate JSONL are
   atomically checkpointed after every accepted page.
3. `run_codex_volume_critic.py` independently audits every page for omissions,
   additions, names, isnads, negation, numbering, notes, and continuation errors.
   Production invocations of this and every later model stage reject duplicate
   scan records or anything short of exact scan-page 4-494 input coverage;
   explicit `--page`/`--limit` runs remain available for isolated proofs.
   Each downstream stage also revalidates the record-level source, translation,
   critique, and witness hashes before it can contact Codex, so a stale upstream
   checkpoint fails at the first consumer rather than only at final publication.
4. `run_codex_witness_resolution.py` sends only explicitly flagged uncertainties
   through a provenance-bound witness pass. Candidate Urdu pages are retrieved
   from page-aware OCR, bounded to the volume body and a 20-scan alignment
   window, rendered from the witness PDF, and attached to Codex. Every candidate
   records its expected scan, alignment distance, and selection signals (exact
   heading, entry number, person name, token overlap, or page proximity) so the
   heuristic remains auditable. Rendered pages are reusable only when a sidecar
   matches the source-PDF hash, scan number, render settings, and current image
   hash; missing, stale, or altered images are rendered again atomically.
   Concern-local biography headings are also searched exactly in Usul's public
   keyword index across *Usd al-Ghaba*, *al-Isti'ab*, and the Dar Hajr and Dar
   al-Jil machine-readable editions of *al-Isabah*. Each query, witness role,
   edition/work/version, returned passage, volume/page citation, error, and text
   hash is cached with the decision. Multi-page continuations inherit the
   nearest preceding numbered biography heading across any number of pages;
   arbitrary prose and generic
   identities are never used as dictionary queries. If Usul rejects an exact
   identity query, progressively broader name-only fallbacks are recorded with
   the requested query and error that caused the fallback, so broader evidence
   cannot masquerade as an exact match. The Urdu translation is a cross-language
   witness; the two Arabic dictionaries are collateral works, while the Dar
   Hajr and Dar al-Jil records are explicitly labeled alternative editions.
   Canonical al-Isabah Arabic remains authoritative throughout, but agreement
   between independent editions can support a transparent correction when the
   locked edition is demonstrably damaged.
   Evidence acquired outside those automated routes can be recorded in
   `volume_08.supplemental-witness-evidence.jsonl`. Every record is tied to an
   exact scan and concern, classifies itself as an alternative edition,
   parallel transmission, translation witness, or lexical reference, and
   carries a SHA-256 hash of the quoted passage. The runner auto-loads this file
   beside the aligned source (or accepts `--supplemental-evidence`) and binds it
   into both the prompt and saved decision. Alternative editions may establish
   recurring readings; parallel reports may clarify shared material; neither
   may silently replace the canonical wording. Volume 8 scan 12 uses this path
   for an older al-Isabah reading and al-Daraqutni's own ruling on the chain.
   When flagged pages are intentionally split across parallel workers,
   `reconcile_codex_witness_shards.py` is the only supported merge boundary. It
   requires disjoint shards, zero failed or stale checkpoints, exact page-file
   and rendered-image hashes, current source/translation/critique provenance,
   the selected production model and effort, and exact coverage of every
   flagged page before emitting the ordered witness JSONL. Do not combine shard
   directories with a filesystem copy. A later evidence refresh is supplied as
   an explicit `--override-shard`; the report records both hashes for every
   replacement while leaving the completed base shards immutable.
5. `run_codex_volume_adjudication.py` gives every page a final xhigh pass after
   criticism and any required witness work, and emits a complete corrected page
   plus explicit unresolved items. Full-volume adjudication prevents an early
   critic pass from being mistaken for final publication approval. Structured
   English names must be clean ASCII identity labels; source
   ellipsis may be normalized into a complete attested name, but commas,
   parentheses, and identity explanations remain passage context rather than
   becoming unstable candidate keys.
   Parallel adjudication uses disjoint page lists and separate output
   directories. `reconcile_codex_adjudication_shards.py` reconstructs the exact
   prompt and upstream witness hash for every page, rejects failed, stale,
   overlapping, missing, or wrong-effort results, and emits the only combined
   adjudication JSONL accepted by finalization. If stronger evidence arrives
   after a base page has completed, rerun only that page and pass its shard as
   `--override-shard`; reconciliation records both record hashes and rejects
   duplicate or non-replacing overrides.
6. `build_codex_volume_final.py` refuses to publish the canonical English JSONL
   unless coverage, provenance, required passes, entry numbers, material numeric
   tokens, footnote labels, and cross-page boundary duplication validate across
   all 491 pages.
7. `build_translation_name_review.py` converts the validated page-level name
   mappings into stable, searchable candidate and mention JSON. It preserves
   operator reviews on rerun and updates the checked-in review index; ELIXR is
   still only a rebuildable projection.
8. `render_english_review.py` creates the bilingual operator presentation from
   the validated JSONL. `update_isabah_source_bundle.py` publishes its evidence
   into the role-based source bundle.
9. `publish_isabah_readiness.py` validates the English, presentation, durable
   name candidate/mention graph, name index, and source-bundle hashes, then
   atomically opens the interface gate. The presentation embeds the structured
   English hash, while the same aligned-Arabic hash and exact 1,550-entry audit
   must agree across the alignment report, finalizer, source bundle, and current
   file on disk. It also rechecks exact scan order, unreviewed target states,
   Codex high/high/xhigh model lineage, all-page adjudication, and the complete
   cited list of explicitly unresolved passages. A machine-QA candidate report
   alone never opens human review.

Reasoning effort is an evidence-backed production setting rather than a tuning
guess. `run_reasoning_effort_calibration.py` accepts paired high/xhigh witness
outputs only when all non-effort inputs and hashes match, assigns balanced
anonymous A/B labels, attaches the same witness facsimiles to an independent
xhigh judge, checkpoints each comparison, and applies a conservative
non-inferiority rule. Lower effort is permitted only when the blinded sample
shows no material regression; otherwise production remains xhigh.

`run_isabah_v8_pipeline.py` supervises stages 2-9 and writes a live state file
under `generated/isabah-v8-pipeline/`. The Source Review interface reads
`volume_08.machine-readiness.json`; its English-review and name-review controls
remain gated until `ready_for_human_review` is true. Machine readiness opens
human review but never records human approval. Even for an unsharded run, the
supervisor routes witness and adjudication output through the same reconciliation
validators used by parallel runs before finalization.

By default the supervisor starts or resumes the blind runner itself and verifies
both its 491-page state and aggregate before advancing. Use
`--external-blind-worker` only when another verified process intentionally owns
that stage. The supervisor defaults to live `api` witness acquisition; after an
independent `--prepare-evidence-only` run, start or resume it with
`--secondary-witness-mode cache` when the model process must not perform network
acquisition itself.

Usul book metadata and the primary keyword-search endpoint used by the witness
pass are public and do not require an API key. If that legacy route fails after
bounded retries, the backend may use the operator's DPAPI-protected key solely
for Usul's documented v1 text-search endpoint. The key is resolved through the
FirstLight credential helper and never enters prompts, caches, manifests, or
logs. A missing result or provider error is never converted into a positive
match. `--prepare-evidence-only` acquires and validates live API evidence
without invoking Codex; a per-query provider error that survives both search
routes and the labeled name fallbacks stops this phase. A later
`--secondary-witness-mode cache` model run performs no network calls and fails
on any missing cached evidence. This split supports restricted model execution
without weakening the evidence gate.
Before processing flagged pages, the pass runs known-hit health queries against
both collateral corpora and stops if either corpus is unavailable; an outage
therefore cannot be misreported as a volume full of absent matches.
If those health checks pass but one exact query and all of its labeled fallbacks
repeatedly fail, the pass records a short-lived `unavailable` result containing
the provider error. This state is shown to Codex as unavailable evidence, never
as a `no_match`, and expires with the cached-health window so a transient query
failure cannot become a permanent scholarly conclusion. A broad first pass may
retain that state so unrelated pages keep moving; a dedicated evidence-
preparation run, the cache-only model pass, and final reconciliation all reject
anything other than a definitive `hit` or `no_match`.
Usul AI/chat and vector-search routes are not used by this translation
pipeline; the authenticated fallback remains exact text search.

## Human review presentation

`render_english_review.py` converts translated JSONL units into a searchable,
printable HTML reading surface. The JSONL remains the English authority; do not
edit or approve text in the generated HTML.

```bash
python firstlight-research/scripts/translation/render_english_review.py \
  --input firstlight-research/data/translated/ibn_hajar_isabah/arabic_v1/volume_08.translation-units.jsonl \
  --output firstlight-research/data/translated/ibn_hajar_isabah/arabic_v1/volume_08.review.html
```

## Scripts

- `build_translation_chunks.py`
  - Builds `chunks.jsonl` from a source text file.
  - Paragraph-aware chunking with hard-wrap fallback for oversized paragraphs.
- `build_focus_subset.py`
  - Builds generic topic-focused subset JSONL from chunks using a focus spec.
  - Supports preset-driven focus specs (default preset: `khadijah`).
  - Can include adjacent context chunks around direct matches.
- `select_pending_wave.py`
  - Selects next N pending chunks from a full/focused chunk set based on `state.json`.
- `run_codex_translation_batch.py`
  - Resumable batch translator over `chunks.jsonl`.
  - Writes translations JSONL + state JSON.
  - Supports optional glossary enforcement.
- `estimate_translation_tokens.py`
  - Heuristic token/cost estimate from chunk manifest.

## Quick start

```bash
# 1) Build chunks
python3 firstlight-research/scripts/translation/build_translation_chunks.py \
  --input firstlight-research/data/raw/usul/ibn-hisham/al-sirah.txt \
  --out-dir firstlight-research/data/translated/ibn_hisham/al_sirah_batch \
  --book-key ibn_hisham_sirah_v1

# 2) Build topic-focused subset (optional, recommended for orbit-targeted work)
# (uses preset default: khadijah)
python3 firstlight-research/scripts/translation/build_focus_subset.py \
  --chunks firstlight-research/data/translated/ibn_hisham/al_sirah_batch/chunks.jsonl \
  --out firstlight-research/data/translated/ibn_hisham/al_sirah_batch/khadijah_focus_chunks.jsonl \
  --report firstlight-research/data/translated/ibn_hisham/al_sirah_batch/khadijah_focus_report.json \
  --preset khadijah

# 3) Estimate budget (full or focused)
python3 firstlight-research/scripts/translation/estimate_translation_tokens.py \
  --chunks firstlight-research/data/translated/ibn_hisham/al_sirah_batch/khadijah_focus_chunks.jsonl

# 4) Select next pending wave from focused subset
python3 firstlight-research/scripts/translation/select_pending_wave.py \
  --chunks firstlight-research/data/translated/ibn_hisham/al_sirah_batch/khadijah_focus_chunks.jsonl \
  --state firstlight-research/data/translated/ibn_hisham/al_sirah_batch/state.json \
  --out firstlight-research/data/translated/ibn_hisham/al_sirah_batch/khadijah_focus_wave10.jsonl \
  --limit 10

# 5) Run translation wave (resumable)
python3 firstlight-research/scripts/translation/run_codex_translation_batch.py \
  --chunks firstlight-research/data/translated/ibn_hisham/al_sirah_batch/khadijah_focus_wave10.jsonl \
  --out firstlight-research/data/translated/ibn_hisham/al_sirah_batch/translations.jsonl \
  --state firstlight-research/data/translated/ibn_hisham/al_sirah_batch/state.json \
  --model codex \
  --auth-profile openai-codex:yaqub0r \
  --style faithful
```

## Optional glossary file

JSON array:

```json
[
  {"source": "خديجة", "target": "Khadijah"},
  {"source": "رسول الله", "target": "Messenger of Allah"}
]
```

Use with:

```bash
--glossary path/to/glossary.json
```

Focus presets/specs:
- Preset directory: `firstlight-research/config/focus-presets/`
- Default preset: `khadijah.json`
- Schema: `firstlight-research/config/focus-presets/focus-spec.schema.json`
- You can pass a custom spec with `--focus-spec <path>`.

Credential routing:
- Prefers OpenClaw auth profile credentials first (`--auth-profile`, default `openai-codex:yaqub0r`), then OpenClaw provider config, then raw env vars.
- Base URL is resolved from active OpenClaw model config (supports `openai-codex` provider wiring).
- Use `--model codex` to force Codex (not spark variants).
- If primary codex auth path is blocked (quota/auth/edge), script can fallback to OpenRouter with the same codex model family; disable with `--no-openrouter-fallback`.

## Resume behavior

- Completed chunk IDs are tracked in `state.json`.
- Re-running skips completed chunks and only processes pending ones.
- Failed chunks remain in `state.json.failed` and can be retried by re-running.

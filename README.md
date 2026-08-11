# Al-Isabah Scholarly Platform

A platform-neutral scholarly edition and English translation of *al-Isabah fi
Tamyiz al-Sahabah* by Ibn Hajar al-Asqalani.

The permanent product is the versioned scholarly dataset: source evidence,
Arabic text, aligned English translation, editorial annotations, stable
identifiers, review state, and provenance. Web and future mobile applications
are clients of that dataset.

The repository is private while source rights and publication readiness are
being reviewed.

Bootstrap and Volume 8 migration are tracked in
[issue #1](https://github.com/yaqub0r/al-isabah/issues/1). The first
incrementally fillable story cohort—Khadijah and her immediate associates—is
tracked in [issue #4](https://github.com/yaqub0r/al-isabah/issues/4).

The cohort workflow locks the Arabic edition, exhaustively inventories direct
mentions, translates selected complete biographies, preserves substantive
context outside those entries, checks damaged readings against facsimile,
Urdu, and collateral Arabic witnesses, and only then marks a bundle ready for
human review. Complete biographies live in `content/entries/`; story-specific
coverage and context live in `derived/cohorts/` so later volume work can fill
the series without rewriting reviewed records.

The operator-facing dossier is
`derived/cohorts/khadijah-immediate.review.md`. A fresh clone can hydrate only
the three external objects needed to reproduce this cohort by passing
`evidence/manifests/khadijah-immediate-artifacts.v1.json` to
`scripts/artifact_store.py hydrate`; normal endpoint, bucket, and credential
configuration still applies.


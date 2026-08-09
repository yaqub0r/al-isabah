# ADR 0001: Standalone project boundary

- Status: accepted
- Date: 2026-08-09
- Issue: https://github.com/yaqub0r/al-isabah/issues/1

## Context

Al-Isabah began as source research inside FirstLight. It now has a canonical
edition lock, multilingual witnesses, a translation and QA pipeline, a complete
machine-validated Volume 8 English draft, a name-review dataset, and a human
review presentation. Its users, releases, editorial workflow, and future reader
and mobile clients are independent of the FirstLight game.

## Decision

The scholarly dataset, pipeline, reader, and editor belong to the standalone
`yaqub0r/al-isabah` repository. FirstLight consumes versioned, checksum-pinned
exports and retains only story-specific annotations.

## Consequences

- Al-Isabah can evolve and release without the FirstLight game lifecycle.
- FirstLight no longer carries the full source/editor implementation long term.
- Migration must preserve evidence and hashes before removing any duplicate.
- A release contract is required between the repositories.
- Cross-repository changes may temporarily require coordinated pull requests.

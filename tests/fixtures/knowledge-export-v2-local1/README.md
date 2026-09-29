# Authored local-contract conformance data

Every source passage, execution, host observation, owner authorization, and date
in this directory is authored synthetic test data. These files test the real
wire shape; they do not record actual source work or grant actual permission.
The use of pinned public authority/profile metadata exercises equality checks
and is not a claim that these fictional passages occur in that authority.

The initial and correction artifacts preserve rich typed semantics, scoped
coverage, immutable object versions and exporter-derived receipt projections.
Only the producer tests need receipts.json (full authored synthetic history).
Consumer tests should import snapshot, inventory, profile, export, trust and
explicit synthetic authorization, using a separately installed synthetic owner
configuration and explicit as-of 2026-01-02T00:00:00Z.

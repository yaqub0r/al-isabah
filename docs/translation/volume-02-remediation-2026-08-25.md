# Volume 2 autonomous-stage remediation

> **Historical status (2026-08-26): superseded and discredited as a current
> remediation claim.** Issue [#70](https://github.com/yaqub0r/al-isabah/issues/70)
> reopened the complete Volume 2 scope after independent review found that this
> remediation did not establish the claimed autonomous-stage depth. The exact
> prior proposal, review, and release closure remain immutable historical
> evidence, but they are blocked from current closure and distribution and must
> not be cited as current machine-readiness or agent-completion evidence.

Issue [#70](https://github.com/yaqub0r/al-isabah/issues/70) corrects the
autonomous-stage depth of source units 1538–3034. Human review remains the
independent, ongoing management state and was not part of either the original
completion claim or this remediation.

## Root cause

The Volume 2 batch materializer accepted authored records that usually supplied
one title candidate and no critique findings. It then defaulted missing
findings to an empty array, defaulted witness resolution to `not_required`, and
set critique, adjudication, and names to `complete`. The validator checked the
shape and status values but did not require positive, content-bound evidence
that critique and bilingual name reconciliation had occurred.

An earlier attempt to reuse Volume 1 names by matching short Arabic strings was
removed because it produced false entity matches. Removing those unsafe matches
was correct; declaring the resulting title-only inventories complete was not.

## Stage-depth evidence

The historical Volume 1 private packet is retained in Git object history as
blob `4f3ebf1ec42d17825f5957280b6d21636f05ee39` (34,475,553 bytes; SHA-256
`809de448fdb9079bdea6fc88ad73c6d092db7c20222d353ab640e84232c4c526`).
The same aggregate audit applied to that packet and to the pre-remediation
Volume 2 packet set produced:

| Measure | Volume 1 | Volume 2 before remediation |
| --- | ---: | ---: |
| Biographies | 1,537 | 1,497 |
| Name candidates and mentions | 13,014 | 1,499 |
| Critique findings | 3,962 | 42 |
| Biographies with no finding | 0 | 1,458 |
| Completed witness records | 514 | 31 |
| Witness results | 793 | 35 |
| Adjudication decisions | 2,718 | 42 |
| Unresolved items | 959 | 29 |

The comparable text size ruled out a small-volume explanation: the Volume 1
bilingual candidate contained about 1.79 million characters and Volume 2 about
1.75 million. The sparse stage evidence came from the materialization shortcut,
not from human-review status or a radically smaller source scope.

The remediation restored all 42 authored findings in 39 biographies, including
31 classified witness resolutions with 35 results. It reran and content-bound
the semantic checklist for all 1,497 biographies and 228 structural records,
and rebuilt the bilingual name inventory to 11,120 candidates. Of the 1,497
biographies, 1,364 now identify more than one named referent. The pass also
caught and corrected the Volume 2 form `Zabbān` to source-supported `Zabān`.
An exact old/new projection comparison found zero changes to biography body
Arabic, body English, preceding material, formula records, or source bindings;
the public change is the repaired name inventory and that one title correction.

## Durable prevention

Packet schema and workflow version 1.3 require:

- an ordered semantic audit covering eleven explicit risk categories, with
  exact source and English hashes;
- an explicit rationale for every `not_required` witness outcome;
- a bilingual, hash-bound name-inventory audit with exact readable-source spans
  and a grounded English form; and
- a packet-scale guard against the one-title-candidate placeholder signature.

Run the reusable aggregate report against any private packet set with:

```sh
python scripts/audit_translation_stage_depth.py \
  --packet <packet-1.json> \
  --packet <packet-2.json>
```

The public proposal intentionally excludes private findings and witness text;
its public-safe name and unresolved counts can be audited with `--proposal`.

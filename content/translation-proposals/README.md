# Translation proposals

This directory contains machine-ready, human-unreviewed translation packets
and their generated bilingual review presentations. They are public working
artifacts governed by `docs/contracts/translation-quality-workflow.md`; they
are not canonical entries or releases.

Create files here only through:

```sh
python scripts/translation_workflow.py submit --packet <runtime-packet.json>
```

Proposal filenames are bound to the GitHub assignment issue. The submit command
never overwrites an existing proposal. Human decisions and canonical promotion
are recorded separately and do not mutate the original proposal evidence.

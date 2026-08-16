# Translation proposals

This directory documents the internal translation-work submission path. Raw
translation packets and their detailed review presentations are not public
repository artifacts. They may contain autonomous-stage evidence,
reconstructive material, or restricted-reference details and must remain in an
approved non-public evidence system.

Generate external review evidence only through:

```sh
python scripts/translation_workflow.py submit --packet <runtime-packet.json> \
  --output-root <approved-external-evidence-destination>
```

Proposal filenames are bound to the GitHub assignment issue. The submit command
must target an approved external evidence destination; a repository path under
this directory is not an authorized destination. Public-working content enters
this repository only through the strict `public-proposal.v1` projection under
`content/public-proposals/`. Human decisions and canonical promotion remain
separate states.

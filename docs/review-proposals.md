# Review proposals

Sabiqah contributors submit proposals to this repository through GitHub forks
and pull requests. Each JSON file in `content/review-proposals/` is a workflow
input that must validate against `schemas/review-proposal.schema.json`.

A proposal names the release, entry, segment, target field, proposed text,
rationale, and evidence. It does not become canonical merely because its pull
request is merged. Maintainers review the evidence, apply or generate the
corresponding canonical content change, run book validation, and record the
decision. The repository may later automate that transformation once the
canonical entry model and reconciliation rules are stable.

Translation proposals and canonical-Arabic corrections are different targets.
Arabic corrections require a meaningful rationale and at least one evidence
reference. Automation must not set human `reviewed` or `verified` state.

The outer `proposal` key is a thin Decap workflow envelope. The object inside it
is Sabiqah's versioned, platform-neutral proposal. The envelope may be replaced
without changing the canonical book model.

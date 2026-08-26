# Public local-model evaluation results

This directory contains sanitized, declared evidence for issue #49.

Every file is listed in the closed results manifest with its byte hash, static trusted dependencies, and any upstream result artifact hashes. Machine-readable evidence is schema-validated and reports regenerate byte-for-byte from declared inputs.

Unreviewed runs remain no-role and promotion-blocked. Publication-admitted final outputs, review evidence, and sanitized attempt summaries may be admitted here.

Attempt summaries bind to one exact declared source packet and its tracked config, prompt, and ordered cases. They contain only controlled per-case outcomes and counts, bounded limitations, resource identity, generated UTC time, and config-owned public-safety admission. They never contain partial model text, raw errors or logs, paths, URLs, traces, credentials, private data, or thought text. Attempt summaries are permanently excluded from identified review, scoring, repeat counts, and role eligibility; they grant no role and cannot be promoted.

Create one with `python scripts/local_model_evaluation.py attempt-summary --packet <public packet> --outcomes <public temporary JSON array> --generated-at <UTC-date-time> --limitation <sanitized text> --output <public summary>`. Each outcomes item contains only `caseId`, `attemptCount`, and one of `completed`, `empty-response`, `timeout`, or `controller-unavailable`. Remove the temporary outcomes input after creating the summary; only manifest-declared evidence may remain tracked.

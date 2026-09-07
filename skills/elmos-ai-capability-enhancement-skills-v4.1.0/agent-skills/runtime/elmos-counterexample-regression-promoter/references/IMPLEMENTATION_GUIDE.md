# Implementation Guide — Counterexample Regression Promoter

## Purpose

Promote minimized verifier, fuzz, differential, security and production incident counterexamples into governed permanent regression assets and rule-improvement candidates.

## Required vertical slice

A conforming first implementation must execute one real, exact-version vertical slice through:

1. API command and idempotency validation;
2. PostgreSQL run/event/outbox persistence with tenant policy;
3. K7 authority, sandbox, lease and fencing acquisition;
4. the Skill-specific native operation;
5. at least one positive and one negative native fixture;
6. independent proof/evidence production;
7. K8 blocked-or-certified decision;
8. pause/resume and worker-loss recovery;
9. machine wall-clock and cost reporting;
10. safe uninstall/rollback or compensating action.

## Skill-specific work packages

1. Deduplicate and minimize failures
2. Attach requirement, cause and version lineage
3. Create stable fixtures and assertions
4. Route recurring failures to deterministic rule improvements
5. Prevent contaminated holdouts from entering training

## Native acceptance corpus

- `ELMOS_COUNTEREXAMPLE_REGRESSION_PROMOTER-01` — fuzz failure promotion
- `ELMOS_COUNTEREXAMPLE_REGRESSION_PROMOTER-02` — differential mismatch promotion
- `ELMOS_COUNTEREXAMPLE_REGRESSION_PROMOTER-03` — security incident promotion
- `ELMOS_COUNTEREXAMPLE_REGRESSION_PROMOTER-04` — deduplication
- `ELMOS_COUNTEREXAMPLE_REGRESSION_PROMOTER-05` — version-scoped regression
- `ELMOS_COUNTEREXAMPLE_REGRESSION_PROMOTER-06` — holdout contamination denial

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

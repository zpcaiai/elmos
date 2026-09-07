# Implementation Guide — Structured Output Contract Verifier

## Purpose

Verify model and framework structured outputs against exact schemas, semantic constraints, evolution rules, repair bounds and adversarial malformed cases.

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

1. JSON Schema and typed model validation
2. Semantic cross-field invariants
3. Strict versus repairable parse policy
4. Schema evolution compatibility
5. Malformed/adversarial output corpus

## Native acceptance corpus

- `ELMOS_STRUCTURED_OUTPUT_CONTRACT_VERIFIER-01` — valid output
- `ELMOS_STRUCTURED_OUTPUT_CONTRACT_VERIFIER-02` — missing/extra field
- `ELMOS_STRUCTURED_OUTPUT_CONTRACT_VERIFIER-03` — cross-field invariant
- `ELMOS_STRUCTURED_OUTPUT_CONTRACT_VERIFIER-04` — enum/version drift
- `ELMOS_STRUCTURED_OUTPUT_CONTRACT_VERIFIER-05` — bounded repair
- `ELMOS_STRUCTURED_OUTPUT_CONTRACT_VERIFIER-06` — malicious nested payload

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

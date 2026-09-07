# Implementation Guide — AIE0E5Certifier

## Purpose

Issue an independent bounded completion decision only when the exact RevisionSet, obligations, evidence freshness, side effects and E0–E5 gates satisfy policy.

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

1. Evaluate E0-E5 and P05 independently
2. Seal exact evidence and assumptions
3. Issue bounded certificates or blocked results
4. Invalidate and revoke on drift

## Native acceptance corpus

- `ELMOS_AI_E0_E5_CERTIFIER-01` — positive proof
- `ELMOS_AI_E0_E5_CERTIFIER-02` — counterexample
- `ELMOS_AI_E0_E5_CERTIFIER-03` — unknown verifier
- `ELMOS_AI_E0_E5_CERTIFIER-04` — AiE0E5Certifier representative end-to-end fixture
- `ELMOS_AI_E0_E5_CERTIFIER-05` — crash recovery preserves single-writer semantics
- `ELMOS_AI_E0_E5_CERTIFIER-06` — upstream or contract drift invalidates stale evidence
- `ELMOS_AI_E0_E5_CERTIFIER-07` — undeclared authority is denied
- `ELMOS_AI_E0_E5_CERTIFIER-08` — resource and wall-clock budget is measured
- `ELMOS_AI_E0_E5_CERTIFIER-09` — complete bundle
- `ELMOS_AI_E0_E5_CERTIFIER-10` — critical unknown block

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

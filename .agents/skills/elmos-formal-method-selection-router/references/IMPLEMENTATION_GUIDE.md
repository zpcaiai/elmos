# Implementation Guide — Formal Method Selection Router

## Purpose

Select SMT, symbolic execution, model checking, proof assistant, abstract interpretation or runtime monitoring per obligation, language and assurance envelope.

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

1. classify safety, liveness, equivalence and quantitative claims
2. estimate decidability, state space and TCB
3. compose verifier portfolios
4. record soundness/completeness and bounds
5. fallback to monitoring without status inflation

## Native acceptance corpus

- `ELMOS_FORMAL_METHOD_SELECTION_ROUTER-01` — native scenario: classify safety, liveness, equivalence and quantitative claims
- `ELMOS_FORMAL_METHOD_SELECTION_ROUTER-02` — native scenario: estimate decidability, state space and TCB
- `ELMOS_FORMAL_METHOD_SELECTION_ROUTER-03` — native scenario: compose verifier portfolios
- `ELMOS_FORMAL_METHOD_SELECTION_ROUTER-04` — native scenario: record soundness/completeness and bounds
- `ELMOS_FORMAL_METHOD_SELECTION_ROUTER-05` — native scenario: fallback to monitoring without status inflation

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

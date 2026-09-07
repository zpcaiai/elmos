# Implementation Guide — Structured Assurance Case Compiler

## Purpose

Compile auditable claims, arguments, assumptions, contexts, defeaters and evidence into SACM/GSN-compatible assurance cases for engineering and independent review.

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

1. Create structured top claim and decomposition
2. Link assumptions/context to exact versions
3. Require evidence for leaf claims
4. Represent rebuttals, defeaters and residual uncertainty
5. Export machine-readable and review visualization

## Native acceptance corpus

- `ELMOS_STRUCTURED_ASSURANCE_CASE_COMPILER-01` — complete claim tree
- `ELMOS_STRUCTURED_ASSURANCE_CASE_COMPILER-02` — missing leaf evidence blocks
- `ELMOS_STRUCTURED_ASSURANCE_CASE_COMPILER-03` — assumption version binding
- `ELMOS_STRUCTURED_ASSURANCE_CASE_COMPILER-04` — defeater remains visible
- `ELMOS_STRUCTURED_ASSURANCE_CASE_COMPILER-05` — evidence freshness propagation
- `ELMOS_STRUCTURED_ASSURANCE_CASE_COMPILER-06` — SACM-compatible export

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

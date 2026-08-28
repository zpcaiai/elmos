# Implementation Guide — Trusted Computing Base Minimization Governor

## Purpose

Inventory, minimize and version the compilers, solvers, runtimes, policies, signers and assumptions trusted by each certificate.

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

1. build per-claim TCB graph
2. classify trusted, verified and monitored components
3. minimize adapters and privileged code
4. track vulnerabilities and version drift
5. publish TCB and residual assumptions in certificate

## Native acceptance corpus

- `ELMOS_TRUSTED_COMPUTING_BASE_MINIMIZATION_GOVERNOR-01` — native scenario: build per-claim TCB graph
- `ELMOS_TRUSTED_COMPUTING_BASE_MINIMIZATION_GOVERNOR-02` — native scenario: classify trusted, verified and monitored components
- `ELMOS_TRUSTED_COMPUTING_BASE_MINIMIZATION_GOVERNOR-03` — native scenario: minimize adapters and privileged code
- `ELMOS_TRUSTED_COMPUTING_BASE_MINIMIZATION_GOVERNOR-04` — native scenario: track vulnerabilities and version drift
- `ELMOS_TRUSTED_COMPUTING_BASE_MINIMIZATION_GOVERNOR-05` — native scenario: publish TCB and residual assumptions in certificate

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

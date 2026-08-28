# Implementation Guide — Source-to-Target Debuggability and Observability Verifier

## Purpose

Verify that generated targets retain actionable logs, traces, metrics, stack attribution, correlation, replay and safe debugging comparable to the source system.

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

1. compare source and target trace topology
2. verify error and stack attribution
3. validate correlation IDs across protocols
4. exercise record/replay and break-glass debug paths
5. measure telemetry cost and cardinality

## Native acceptance corpus

- `ELMOS_SOURCE_TARGET_DEBUGGABILITY_OBSERVABILITY_VERIFIER-01` — native scenario: compare source and target trace topology
- `ELMOS_SOURCE_TARGET_DEBUGGABILITY_OBSERVABILITY_VERIFIER-02` — native scenario: verify error and stack attribution
- `ELMOS_SOURCE_TARGET_DEBUGGABILITY_OBSERVABILITY_VERIFIER-03` — native scenario: validate correlation IDs across protocols
- `ELMOS_SOURCE_TARGET_DEBUGGABILITY_OBSERVABILITY_VERIFIER-04` — native scenario: exercise record/replay and break-glass debug paths
- `ELMOS_SOURCE_TARGET_DEBUGGABILITY_OBSERVABILITY_VERIFIER-05` — native scenario: measure telemetry cost and cardinality

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

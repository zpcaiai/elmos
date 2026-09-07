# Implementation Guide — Polyglot Differential Runtime

## Purpose

Execute source and target systems under the same scenarios and compare normalized API, state, trace, tool, data, timing and side-effect semantics.

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

1. Launch source and target in isolated equivalent environments
2. Normalize nondeterminism without erasing semantics
3. Compare outputs, state, calls and side effects
4. Apply typed tolerances and partial-order trace comparison
5. Minimize and attribute mismatches

## Native acceptance corpus

- `ELMOS_POLYGLOT_DIFFERENTIAL_RUNTIME-01` — API result equivalence
- `ELMOS_POLYGLOT_DIFFERENTIAL_RUNTIME-02` — exception/error equivalence
- `ELMOS_POLYGLOT_DIFFERENTIAL_RUNTIME-03` — tool-call partial order
- `ELMOS_POLYGLOT_DIFFERENTIAL_RUNTIME-04` — database state equivalence
- `ELMOS_POLYGLOT_DIFFERENTIAL_RUNTIME-05` — concurrency scenario
- `ELMOS_POLYGLOT_DIFFERENTIAL_RUNTIME-06` — timeout/cancellation behavior
- `ELMOS_POLYGLOT_DIFFERENTIAL_RUNTIME-07` — nondeterminism normalization

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

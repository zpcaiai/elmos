# Implementation Guide — Polyglot Route Matrix Governor

## Purpose

Govern exact source-language, target-language, framework, runtime and toolchain route envelopes without treating an N×N matrix as independently trustworthy translators.

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

1. Model routes as frontend + semantic IR + backend + pair overlay
2. Track exact language/framework/runtime/toolchain pins
3. Classify route maturity and certified envelope
4. Compute route risk from semantic gaps and evidence freshness
5. Prevent unsupported cells from appearing as supported

## Native acceptance corpus

- `ELMOS_POLYGLOT_ROUTE_MATRIX_GOVERNOR-01` — exact route lookup
- `ELMOS_POLYGLOT_ROUTE_MATRIX_GOVERNOR-02` — unsupported cell blocks
- `ELMOS_POLYGLOT_ROUTE_MATRIX_GOVERNOR-03` — version drift invalidates route evidence
- `ELMOS_POLYGLOT_ROUTE_MATRIX_GOVERNOR-04` — pair-overlay precedence
- `ELMOS_POLYGLOT_ROUTE_MATRIX_GOVERNOR-05` — route deprecation and rollback
- `ELMOS_POLYGLOT_ROUTE_MATRIX_GOVERNOR-06` — matrix completeness without N×N code duplication

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

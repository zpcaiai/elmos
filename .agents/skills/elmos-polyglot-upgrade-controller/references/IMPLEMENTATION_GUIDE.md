# Implementation Guide — Polyglot Route Upgrade Controller

## Purpose

Upgrade certified language/framework routes across compiler, runtime and dependency versions with impact analysis, incremental proof invalidation and reversible rollout.

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

1. Detect semantic profile deltas between versions
2. Plan dependency-aware upgrade waves
3. Invalidate only affected proof/evidence
4. Run old/new differential and compatibility suites
5. Retain signed rollback artifacts and data path

## Native acceptance corpus

- `ELMOS_POLYGLOT_UPGRADE_CONTROLLER-01` — compiler minor upgrade
- `ELMOS_POLYGLOT_UPGRADE_CONTROLLER-02` — framework major upgrade
- `ELMOS_POLYGLOT_UPGRADE_CONTROLLER-03` — dependency lock refresh
- `ELMOS_POLYGLOT_UPGRADE_CONTROLLER-04` — schema/runtime compatibility
- `ELMOS_POLYGLOT_UPGRADE_CONTROLLER-05` — canary upgrade
- `ELMOS_POLYGLOT_UPGRADE_CONTROLLER-06` — rollback after failed differential

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

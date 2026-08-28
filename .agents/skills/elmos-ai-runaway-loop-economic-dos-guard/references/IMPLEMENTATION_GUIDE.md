# Implementation Guide — AI Runaway Loop and Economic DoS Guard

## Purpose

Enforce step, token, tool, cost, wall-clock, fanout and side-effect budgets while detecting retry storms, delegation loops and fallback cascades.

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

1. Multi-dimensional budget envelope
2. Cycle and repeated-state detection
3. Retry/fallback/fanout circuit breakers
4. Per-tenant and global rate governance
5. Graceful stop with checkpoint and reconciliation

## Native acceptance corpus

- `ELMOS_AI_RUNAWAY_LOOP_ECONOMIC_DOS_GUARD-01` — step budget
- `ELMOS_AI_RUNAWAY_LOOP_ECONOMIC_DOS_GUARD-02` — token/cost budget
- `ELMOS_AI_RUNAWAY_LOOP_ECONOMIC_DOS_GUARD-03` — agent ping-pong
- `ELMOS_AI_RUNAWAY_LOOP_ECONOMIC_DOS_GUARD-04` — retry storm
- `ELMOS_AI_RUNAWAY_LOOP_ECONOMIC_DOS_GUARD-05` — provider fallback cascade
- `ELMOS_AI_RUNAWAY_LOOP_ECONOMIC_DOS_GUARD-06` — graceful bounded stop

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

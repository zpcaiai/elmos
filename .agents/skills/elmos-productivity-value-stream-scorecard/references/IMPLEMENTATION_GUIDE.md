# Implementation Guide — Productivity and Value-Stream Scorecard

## Purpose

Measure Elmos commercial productivity through delivery throughput, instability, rework, verified automation yield, machine wall-clock, cost and developer experience rather than token volume.

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

1. Measure change lead time and deployment frequency
2. Measure failed deployment recovery, change failure and rework
3. Track verified autonomous work versus human correction
4. Report machine wall-clock and total cost separately
5. Use statistical/customer context instead of universal ranking

## Native acceptance corpus

- `ELMOS_PRODUCTIVITY_VALUE_STREAM_SCORECARD-01` — lead time
- `ELMOS_PRODUCTIVITY_VALUE_STREAM_SCORECARD-02` — deployment frequency
- `ELMOS_PRODUCTIVITY_VALUE_STREAM_SCORECARD-03` — failed deployment recovery
- `ELMOS_PRODUCTIVITY_VALUE_STREAM_SCORECARD-04` — change failure rate
- `ELMOS_PRODUCTIVITY_VALUE_STREAM_SCORECARD-05` — deployment rework rate
- `ELMOS_PRODUCTIVITY_VALUE_STREAM_SCORECARD-06` — verified automation yield
- `ELMOS_PRODUCTIVITY_VALUE_STREAM_SCORECARD-07` — developer satisfaction guardrail

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

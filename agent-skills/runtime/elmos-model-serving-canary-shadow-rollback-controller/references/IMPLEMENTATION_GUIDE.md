# Implementation Guide — Model Serving Canary, Shadow and Rollback Controller

## Purpose

Run no-side-effect shadow, bounded canary, traffic splitting, quality/SLO comparison and atomic rollback for model-server changes.

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

1. bind candidate model/server/config revision
2. mirror traffic with privacy controls
3. compare quality, safety, latency and cost
4. promote by staged policy gates
5. rollback model, cache and routing consistently

## Native acceptance corpus

- `ELMOS_MODEL_SERVING_CANARY_SHADOW_ROLLBACK_CONTROLLER-01` — native scenario: bind candidate model/server/config revision
- `ELMOS_MODEL_SERVING_CANARY_SHADOW_ROLLBACK_CONTROLLER-02` — native scenario: mirror traffic with privacy controls
- `ELMOS_MODEL_SERVING_CANARY_SHADOW_ROLLBACK_CONTROLLER-03` — native scenario: compare quality, safety, latency and cost
- `ELMOS_MODEL_SERVING_CANARY_SHADOW_ROLLBACK_CONTROLLER-04` — native scenario: promote by staged policy gates
- `ELMOS_MODEL_SERVING_CANARY_SHADOW_ROLLBACK_CONTROLLER-05` — native scenario: rollback model, cache and routing consistently

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

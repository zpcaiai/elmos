# Implementation Guide — Project Estimation and Machine ETA Calibrator

## Purpose

Estimate and continuously calibrate machine wall-clock, queue, retry, token, compute and verification duration for repository-scale generation and certification.

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

1. extract size, graph, route and risk features
2. separate execution, queue and approval time
3. calibrate distributions from completed runs
4. update ETA after checkpoints and failures
5. report confidence and driver decomposition

## Native acceptance corpus

- `ELMOS_PROJECT_ESTIMATION_MACHINE_ETA_CALIBRATOR-01` — native scenario: extract size, graph, route and risk features
- `ELMOS_PROJECT_ESTIMATION_MACHINE_ETA_CALIBRATOR-02` — native scenario: separate execution, queue and approval time
- `ELMOS_PROJECT_ESTIMATION_MACHINE_ETA_CALIBRATOR-03` — native scenario: calibrate distributions from completed runs
- `ELMOS_PROJECT_ESTIMATION_MACHINE_ETA_CALIBRATOR-04` — native scenario: update ETA after checkpoints and failures
- `ELMOS_PROJECT_ESTIMATION_MACHINE_ETA_CALIBRATOR-05` — native scenario: report confidence and driver decomposition

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

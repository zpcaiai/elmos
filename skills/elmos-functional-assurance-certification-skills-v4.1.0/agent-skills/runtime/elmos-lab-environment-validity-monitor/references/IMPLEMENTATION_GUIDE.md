# Implementation Guide — Laboratory Environment and Result Validity Monitor

## Purpose

Implement and independently certify laboratory environment and result validity monitor, including continuously monitor environment, dependency, network, data and provider conditions that influence results, apply control charts, check samples and trend rules to validity indicators and quarantine affected results and trigger re-evaluation.

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

1. continuously monitor environment, dependency, network, data and provider conditions that influence results
2. apply control charts, check samples and trend rules to validity indicators
3. quarantine affected results and trigger re-evaluation
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_LAB_ENVIRONMENT_VALIDITY_MONITOR-01` — native scenario: continuously monitor environment, dependency, network, data and provider conditions that influence results
- `ELMOS_LAB_ENVIRONMENT_VALIDITY_MONITOR-02` — native scenario: apply control charts, check samples and trend rules to validity indicators
- `ELMOS_LAB_ENVIRONMENT_VALIDITY_MONITOR-03` — native scenario: quarantine affected results and trigger re-evaluation
- `ELMOS_LAB_ENVIRONMENT_VALIDITY_MONITOR-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_LAB_ENVIRONMENT_VALIDITY_MONITOR-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

# Implementation Guide — AI TEVV-Athlon Scenario Orchestrator

## Purpose

Implement and independently certify ai tevv-athlon scenario orchestrator, including compose extensible real-world scenario events, actors, environments and outcomes, run baseline, stress, adversarial, recovery and longitudinal scenarios and compare technical behavior with impact and outcome evidence.

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

1. compose extensible real-world scenario events, actors, environments and outcomes
2. run baseline, stress, adversarial, recovery and longitudinal scenarios
3. compare technical behavior with impact and outcome evidence
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_AI_TEVV_ATHLON_SCENARIO_ORCHESTRATOR-01` — native scenario: compose extensible real-world scenario events, actors, environments and outcomes
- `ELMOS_AI_TEVV_ATHLON_SCENARIO_ORCHESTRATOR-02` — native scenario: run baseline, stress, adversarial, recovery and longitudinal scenarios
- `ELMOS_AI_TEVV_ATHLON_SCENARIO_ORCHESTRATOR-03` — native scenario: compare technical behavior with impact and outcome evidence
- `ELMOS_AI_TEVV_ATHLON_SCENARIO_ORCHESTRATOR-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_AI_TEVV_ATHLON_SCENARIO_ORCHESTRATOR-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

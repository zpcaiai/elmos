# Implementation Guide — Critical Infrastructure AI Resilience Profile

## Purpose

Implement and independently certify critical infrastructure ai resilience profile, including map essential function, dependencies, cascading failure and minimum service objectives, verify manual fallback, isolated operation, supply-chain resilience and recovery and exercise cyber-physical, provider, power, network and regional failure scenarios.

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

1. map essential function, dependencies, cascading failure and minimum service objectives
2. verify manual fallback, isolated operation, supply-chain resilience and recovery
3. exercise cyber-physical, provider, power, network and regional failure scenarios
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_CRITICAL_INFRASTRUCTURE_AI_RESILIENCE_PROFILE-01` — native scenario: map essential function, dependencies, cascading failure and minimum service objectives
- `ELMOS_CRITICAL_INFRASTRUCTURE_AI_RESILIENCE_PROFILE-02` — native scenario: verify manual fallback, isolated operation, supply-chain resilience and recovery
- `ELMOS_CRITICAL_INFRASTRUCTURE_AI_RESILIENCE_PROFILE-03` — native scenario: exercise cyber-physical, provider, power, network and regional failure scenarios
- `ELMOS_CRITICAL_INFRASTRUCTURE_AI_RESILIENCE_PROFILE-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_CRITICAL_INFRASTRUCTURE_AI_RESILIENCE_PROFILE-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

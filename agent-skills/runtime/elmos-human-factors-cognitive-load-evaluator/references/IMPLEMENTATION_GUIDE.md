# Implementation Guide — Human Factors and Cognitive Load Evaluator

## Purpose

Evaluate operator comprehension, interruption, trust calibration, alert fatigue, approval quality and recovery performance for agentic systems.

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

1. define role-specific usability scenarios
2. measure task completion and error recovery
3. test uncertainty and automation disclosure
4. evaluate alert/approval fatigue
5. capture qualitative evidence without overstating generality

## Native acceptance corpus

- `ELMOS_HUMAN_FACTORS_COGNITIVE_LOAD_EVALUATOR-01` — native scenario: define role-specific usability scenarios
- `ELMOS_HUMAN_FACTORS_COGNITIVE_LOAD_EVALUATOR-02` — native scenario: measure task completion and error recovery
- `ELMOS_HUMAN_FACTORS_COGNITIVE_LOAD_EVALUATOR-03` — native scenario: test uncertainty and automation disclosure
- `ELMOS_HUMAN_FACTORS_COGNITIVE_LOAD_EVALUATOR-04` — native scenario: evaluate alert/approval fatigue
- `ELMOS_HUMAN_FACTORS_COGNITIVE_LOAD_EVALUATOR-05` — native scenario: capture qualitative evidence without overstating generality

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

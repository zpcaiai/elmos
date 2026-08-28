# Implementation Guide — Human Factors, Automation Bias and Overreliance Verifier

## Purpose

Implement and independently certify human factors, automation bias and overreliance verifier, including evaluate operator workload, vigilance, trust calibration and intervention timing, test automation bias, anchoring, complacency and skill degradation and verify interface and procedure enable effective override, escalation and recovery.

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

1. evaluate operator workload, vigilance, trust calibration and intervention timing
2. test automation bias, anchoring, complacency and skill degradation
3. verify interface and procedure enable effective override, escalation and recovery
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_AI_HUMAN_FACTORS_AUTOMATION_BIAS_OVERRELIANCE_VERIFIER-01` — native scenario: evaluate operator workload, vigilance, trust calibration and intervention timing
- `ELMOS_AI_HUMAN_FACTORS_AUTOMATION_BIAS_OVERRELIANCE_VERIFIER-02` — native scenario: test automation bias, anchoring, complacency and skill degradation
- `ELMOS_AI_HUMAN_FACTORS_AUTOMATION_BIAS_OVERRELIANCE_VERIFIER-03` — native scenario: verify interface and procedure enable effective override, escalation and recovery
- `ELMOS_AI_HUMAN_FACTORS_AUTOMATION_BIAS_OVERRELIANCE_VERIFIER-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_AI_HUMAN_FACTORS_AUTOMATION_BIAS_OVERRELIANCE_VERIFIER-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

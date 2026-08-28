# Implementation Guide — Method Sensitivity, Specificity and Detection-Limit Certifier

## Purpose

Implement and independently certify method sensitivity, specificity and detection-limit certifier, including measure sensitivity, specificity, false alarm, missed detection and minimum detectable effect, characterize saturation, ceiling, floor and resolution limits and establish method applicability under noise and adversarial conditions.

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

1. measure sensitivity, specificity, false alarm, missed detection and minimum detectable effect
2. characterize saturation, ceiling, floor and resolution limits
3. establish method applicability under noise and adversarial conditions
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_METHOD_SENSITIVITY_SPECIFICITY_DETECTION_LIMIT_CERTIFIER-01` — native scenario: measure sensitivity, specificity, false alarm, missed detection and minimum detectable effect
- `ELMOS_METHOD_SENSITIVITY_SPECIFICITY_DETECTION_LIMIT_CERTIFIER-02` — native scenario: characterize saturation, ceiling, floor and resolution limits
- `ELMOS_METHOD_SENSITIVITY_SPECIFICITY_DETECTION_LIMIT_CERTIFIER-03` — native scenario: establish method applicability under noise and adversarial conditions
- `ELMOS_METHOD_SENSITIVITY_SPECIFICITY_DETECTION_LIMIT_CERTIFIER-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_METHOD_SENSITIVITY_SPECIFICITY_DETECTION_LIMIT_CERTIFIER-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

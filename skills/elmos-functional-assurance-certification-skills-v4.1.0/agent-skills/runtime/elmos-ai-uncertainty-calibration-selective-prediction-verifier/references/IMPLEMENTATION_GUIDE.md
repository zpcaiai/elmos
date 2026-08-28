# Implementation Guide — Uncertainty Calibration and Selective Prediction Verifier

## Purpose

Implement and independently certify uncertainty calibration and selective prediction verifier, including measure probability calibration, confidence reliability and abstention quality, verify risk-coverage curves and decision-aware thresholds and detect overconfidence under shift and adversarial inputs.

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

1. measure probability calibration, confidence reliability and abstention quality
2. verify risk-coverage curves and decision-aware thresholds
3. detect overconfidence under shift and adversarial inputs
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_AI_UNCERTAINTY_CALIBRATION_SELECTIVE_PREDICTION_VERIFIER-01` — native scenario: measure probability calibration, confidence reliability and abstention quality
- `ELMOS_AI_UNCERTAINTY_CALIBRATION_SELECTIVE_PREDICTION_VERIFIER-02` — native scenario: verify risk-coverage curves and decision-aware thresholds
- `ELMOS_AI_UNCERTAINTY_CALIBRATION_SELECTIVE_PREDICTION_VERIFIER-03` — native scenario: detect overconfidence under shift and adversarial inputs
- `ELMOS_AI_UNCERTAINTY_CALIBRATION_SELECTIVE_PREDICTION_VERIFIER-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_AI_UNCERTAINTY_CALIBRATION_SELECTIVE_PREDICTION_VERIFIER-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

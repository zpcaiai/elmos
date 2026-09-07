# Implementation Guide — Test Equipment and Software Calibration Traceability Governor

## Purpose

Implement and independently certify test equipment and software calibration traceability governor, including inventory physical equipment, clocks, GPUs, compilers, libraries, evaluators and reference services affecting results, maintain calibration or verification status and metrological traceability where applicable and block use of expired, tampered or unverified test assets.

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

1. inventory physical equipment, clocks, GPUs, compilers, libraries, evaluators and reference services affecting results
2. maintain calibration or verification status and metrological traceability where applicable
3. block use of expired, tampered or unverified test assets
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_TEST_EQUIPMENT_SOFTWARE_CALIBRATION_TRACEABILITY_GOVERNOR-01` — native scenario: inventory physical equipment, clocks, GPUs, compilers, libraries, evaluators and reference services affecting results
- `ELMOS_TEST_EQUIPMENT_SOFTWARE_CALIBRATION_TRACEABILITY_GOVERNOR-02` — native scenario: maintain calibration or verification status and metrological traceability where applicable
- `ELMOS_TEST_EQUIPMENT_SOFTWARE_CALIBRATION_TRACEABILITY_GOVERNOR-03` — native scenario: block use of expired, tampered or unverified test assets
- `ELMOS_TEST_EQUIPMENT_SOFTWARE_CALIBRATION_TRACEABILITY_GOVERNOR-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_TEST_EQUIPMENT_SOFTWARE_CALIBRATION_TRACEABILITY_GOVERNOR-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

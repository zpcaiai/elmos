# Implementation Guide — Medical Device AI Software Lifecycle and Risk Profile

## Purpose

Implement and independently certify medical device ai software lifecycle and risk profile, including compile software lifecycle, clinical risk, usability, cybersecurity and post-market obligations, trace intended use, patient population, clinical performance and change protocol and verify data representativeness, human factors and adverse-event monitoring.

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

1. compile software lifecycle, clinical risk, usability, cybersecurity and post-market obligations
2. trace intended use, patient population, clinical performance and change protocol
3. verify data representativeness, human factors and adverse-event monitoring
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_MEDICAL_DEVICE_AI_SOFTWARE_LIFECYCLE_RISK_PROFILE-01` — native scenario: compile software lifecycle, clinical risk, usability, cybersecurity and post-market obligations
- `ELMOS_MEDICAL_DEVICE_AI_SOFTWARE_LIFECYCLE_RISK_PROFILE-02` — native scenario: trace intended use, patient population, clinical performance and change protocol
- `ELMOS_MEDICAL_DEVICE_AI_SOFTWARE_LIFECYCLE_RISK_PROFILE-03` — native scenario: verify data representativeness, human factors and adverse-event monitoring
- `ELMOS_MEDICAL_DEVICE_AI_SOFTWARE_LIFECYCLE_RISK_PROFILE-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_MEDICAL_DEVICE_AI_SOFTWARE_LIFECYCLE_RISK_PROFILE-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

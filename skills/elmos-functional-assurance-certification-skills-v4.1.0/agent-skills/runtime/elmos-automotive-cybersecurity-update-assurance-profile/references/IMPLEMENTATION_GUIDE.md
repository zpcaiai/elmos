# Implementation Guide — Automotive Cybersecurity and Software Update Assurance Profile

## Purpose

Implement and independently certify automotive cybersecurity and software update assurance profile, including compile vehicle cybersecurity management, threat analysis and risk assessment, verify secure update, rollback, campaign monitoring and regulatory evidence and integrate safety-security co-assurance for connected AI functions.

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

1. compile vehicle cybersecurity management, threat analysis and risk assessment
2. verify secure update, rollback, campaign monitoring and regulatory evidence
3. integrate safety-security co-assurance for connected AI functions
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_AUTOMOTIVE_CYBERSECURITY_UPDATE_ASSURANCE_PROFILE-01` — native scenario: compile vehicle cybersecurity management, threat analysis and risk assessment
- `ELMOS_AUTOMOTIVE_CYBERSECURITY_UPDATE_ASSURANCE_PROFILE-02` — native scenario: verify secure update, rollback, campaign monitoring and regulatory evidence
- `ELMOS_AUTOMOTIVE_CYBERSECURITY_UPDATE_ASSURANCE_PROFILE-03` — native scenario: integrate safety-security co-assurance for connected AI functions
- `ELMOS_AUTOMOTIVE_CYBERSECURITY_UPDATE_ASSURANCE_PROFILE-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_AUTOMOTIVE_CYBERSECURITY_UPDATE_ASSURANCE_PROFILE-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

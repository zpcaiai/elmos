# Implementation Guide — Industrial Control Security-Safety Co-Assurance Profile

## Purpose

Implement and independently certify industrial control security-safety co-assurance profile, including combine functional safety lifecycle with industrial cybersecurity zones, conduits and security levels, analyze safety-security control conflicts and common-cause failures and verify patching, remote access, incident response and safe operation.

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

1. combine functional safety lifecycle with industrial cybersecurity zones, conduits and security levels
2. analyze safety-security control conflicts and common-cause failures
3. verify patching, remote access, incident response and safe operation
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_INDUSTRIAL_CONTROL_SECURITY_SAFETY_COASSURANCE_PROFILE-01` — native scenario: combine functional safety lifecycle with industrial cybersecurity zones, conduits and security levels
- `ELMOS_INDUSTRIAL_CONTROL_SECURITY_SAFETY_COASSURANCE_PROFILE-02` — native scenario: analyze safety-security control conflicts and common-cause failures
- `ELMOS_INDUSTRIAL_CONTROL_SECURITY_SAFETY_COASSURANCE_PROFILE-03` — native scenario: verify patching, remote access, incident response and safe operation
- `ELMOS_INDUSTRIAL_CONTROL_SECURITY_SAFETY_COASSURANCE_PROFILE-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_INDUSTRIAL_CONTROL_SECURITY_SAFETY_COASSURANCE_PROFILE-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

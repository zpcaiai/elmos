# Implementation Guide — Autonomous System Safety Case Profile

## Purpose

Implement and independently certify autonomous system safety case profile, including define operational design domain, minimum-risk condition, fallback and hazard scenarios, combine simulation credibility, closed-course, shadow and field evidence and monitor ODD exit, autonomy escalation and residual risk.

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

1. define operational design domain, minimum-risk condition, fallback and hazard scenarios
2. combine simulation credibility, closed-course, shadow and field evidence
3. monitor ODD exit, autonomy escalation and residual risk
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_AUTONOMOUS_SYSTEM_SAFETY_CASE_PROFILE-01` — native scenario: define operational design domain, minimum-risk condition, fallback and hazard scenarios
- `ELMOS_AUTONOMOUS_SYSTEM_SAFETY_CASE_PROFILE-02` — native scenario: combine simulation credibility, closed-course, shadow and field evidence
- `ELMOS_AUTONOMOUS_SYSTEM_SAFETY_CASE_PROFILE-03` — native scenario: monitor ODD exit, autonomy escalation and residual risk
- `ELMOS_AUTONOMOUS_SYSTEM_SAFETY_CASE_PROFILE-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_AUTONOMOUS_SYSTEM_SAFETY_CASE_PROFILE-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

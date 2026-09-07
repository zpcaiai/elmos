# Implementation Guide — AI Incident Regulatory Reporting Controller

## Purpose

Coordinate technical triage, legal/compliance review, deadlines, evidence, customer communication and regulator-ready reporting for AI incidents.

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

1. classify incident across jurisdictions
2. freeze evidence and timeline
3. compute deadlines with human validation
4. generate audience-specific draft reports
5. track submission, correction and recertification

## Native acceptance corpus

- `ELMOS_AI_INCIDENT_REGULATORY_REPORTING_CONTROLLER-01` — native scenario: classify incident across jurisdictions
- `ELMOS_AI_INCIDENT_REGULATORY_REPORTING_CONTROLLER-02` — native scenario: freeze evidence and timeline
- `ELMOS_AI_INCIDENT_REGULATORY_REPORTING_CONTROLLER-03` — native scenario: compute deadlines with human validation
- `ELMOS_AI_INCIDENT_REGULATORY_REPORTING_CONTROLLER-04` — native scenario: generate audience-specific draft reports
- `ELMOS_AI_INCIDENT_REGULATORY_REPORTING_CONTROLLER-05` — native scenario: track submission, correction and recertification

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

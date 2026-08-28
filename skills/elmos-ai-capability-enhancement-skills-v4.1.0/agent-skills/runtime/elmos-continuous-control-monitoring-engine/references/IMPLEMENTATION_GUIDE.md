# Implementation Guide — Continuous Control Monitoring Engine

## Purpose

Continuously evaluate runtime, security, compliance, quality, SLO and certification controls against current evidence and trigger restriction, incident or recertification.

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

1. compile controls into executable evidence queries
2. evaluate freshness, scope and operating effectiveness
3. correlate violations to affected certificates and tenants
4. trigger bounded remediation, restriction or recertification
5. preserve audit timeline and human accountability

## Native acceptance corpus

- `ELMOS_CONTINUOUS_CONTROL_MONITORING_ENGINE-01` — native scenario: compile controls into executable evidence queries
- `ELMOS_CONTINUOUS_CONTROL_MONITORING_ENGINE-02` — native scenario: evaluate freshness, scope and operating effectiveness
- `ELMOS_CONTINUOUS_CONTROL_MONITORING_ENGINE-03` — native scenario: correlate violations to affected certificates and tenants
- `ELMOS_CONTINUOUS_CONTROL_MONITORING_ENGINE-04` — native scenario: trigger bounded remediation, restriction or recertification
- `ELMOS_CONTINUOUS_CONTROL_MONITORING_ENGINE-05` — native scenario: preserve audit timeline and human accountability

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

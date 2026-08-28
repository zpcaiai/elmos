# Implementation Guide — Operability and Support Readiness Certifier

## Purpose

Certify ownership, on-call, alerts, runbooks, dashboards, diagnostic safety, support access, maintenance and incident communications before commercial launch.

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

1. Require named service and data owners
2. Test alerts and runbooks through game days
3. Verify safe diagnostics and break-glass access
4. Define maintenance, status and customer communication
5. Measure support escalation and incident response

## Native acceptance corpus

- `ELMOS_OPERABILITY_SUPPORT_READINESS_CERTIFIER-01` — alert fires on real fault
- `ELMOS_OPERABILITY_SUPPORT_READINESS_CERTIFIER-02` — runbook restores service
- `ELMOS_OPERABILITY_SUPPORT_READINESS_CERTIFIER-03` — on-call escalation
- `ELMOS_OPERABILITY_SUPPORT_READINESS_CERTIFIER-04` — break-glass audit
- `ELMOS_OPERABILITY_SUPPORT_READINESS_CERTIFIER-05` — customer communication
- `ELMOS_OPERABILITY_SUPPORT_READINESS_CERTIFIER-06` — maintenance rollback
- `ELMOS_OPERABILITY_SUPPORT_READINESS_CERTIFIER-07` — support data redaction

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

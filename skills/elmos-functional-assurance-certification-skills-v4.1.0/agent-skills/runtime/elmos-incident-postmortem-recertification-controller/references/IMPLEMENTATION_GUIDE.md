# Implementation Guide — Incident Postmortem and Recertification Controller

## Purpose

Convert production incidents into evidence-preserving timelines, root-cause claims, corrective actions, regression assets and mandatory certificate impact decisions.

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

1. Preserve incident evidence before remediation
2. Build causal timeline with confidence and counterevidence
3. Assign corrective/preventive actions and owners
4. Promote incident counterexamples
5. Suspend/revoke/recertify affected claims

## Native acceptance corpus

- `ELMOS_INCIDENT_POSTMORTEM_RECERTIFICATION_CONTROLLER-01` — security incident
- `ELMOS_INCIDENT_POSTMORTEM_RECERTIFICATION_CONTROLLER-02` — data inconsistency incident
- `ELMOS_INCIDENT_POSTMORTEM_RECERTIFICATION_CONTROLLER-03` — availability incident
- `ELMOS_INCIDENT_POSTMORTEM_RECERTIFICATION_CONTROLLER-04` — cost runaway incident
- `ELMOS_INCIDENT_POSTMORTEM_RECERTIFICATION_CONTROLLER-05` — root-cause uncertainty
- `ELMOS_INCIDENT_POSTMORTEM_RECERTIFICATION_CONTROLLER-06` — corrective action verification
- `ELMOS_INCIDENT_POSTMORTEM_RECERTIFICATION_CONTROLLER-07` — certificate reissue

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

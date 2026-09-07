# Implementation Guide — Security Incident, PSIRT and Disclosure Controller

## Purpose

Coordinate vulnerability intake, triage, embargo, remediation, customer notification, advisory publication, CVE/VEX updates and post-incident evidence.

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

1. Provide authenticated confidential reporting and duplicate correlation
2. Separate severity, exploitability, product scope and disclosure decision
3. Coordinate fix, backport, release, revocation and customer mitigation
4. Publish machine-readable advisory and update SBOM/VEX
5. Preserve evidence while respecting reporter and customer confidentiality

## Native acceptance corpus

- `ELMOS_SECURITY_INCIDENT_PSIRT_DISCLOSURE_CONTROLLER-01` — valid vulnerability intake
- `ELMOS_SECURITY_INCIDENT_PSIRT_DISCLOSURE_CONTROLLER-02` — duplicate report
- `ELMOS_SECURITY_INCIDENT_PSIRT_DISCLOSURE_CONTROLLER-03` — embargoed remediation
- `ELMOS_SECURITY_INCIDENT_PSIRT_DISCLOSURE_CONTROLLER-04` — customer notification
- `ELMOS_SECURITY_INCIDENT_PSIRT_DISCLOSURE_CONTROLLER-05` — advisory and VEX update
- `ELMOS_SECURITY_INCIDENT_PSIRT_DISCLOSURE_CONTROLLER-06` — post-incident regression

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

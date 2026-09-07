# Implementation Guide — External Audit and OSCAL Evidence Exporter

## Purpose

Export scoped controls, implementations, assessment plans, results, findings, POA&M and evidence references in OSCAL-compatible and auditor-friendly packages.

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

1. Map Elmos controls and evidence to machine-readable profiles
2. Generate assessment plan and result artifacts
3. Preserve evidence references without copying secrets
4. Support auditor sampling and query traceability
5. Record findings and remediation plans

## Native acceptance corpus

- `ELMOS_EXTERNAL_AUDIT_OSCAL_EVIDENCE_EXPORTER-01` — OSCAL catalog/profile export
- `ELMOS_EXTERNAL_AUDIT_OSCAL_EVIDENCE_EXPORTER-02` — system implementation export
- `ELMOS_EXTERNAL_AUDIT_OSCAL_EVIDENCE_EXPORTER-03` — assessment plan/result
- `ELMOS_EXTERNAL_AUDIT_OSCAL_EVIDENCE_EXPORTER-04` — finding and POA&M
- `ELMOS_EXTERNAL_AUDIT_OSCAL_EVIDENCE_EXPORTER-05` — redacted evidence link
- `ELMOS_EXTERNAL_AUDIT_OSCAL_EVIDENCE_EXPORTER-06` — auditor sample reproducibility

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

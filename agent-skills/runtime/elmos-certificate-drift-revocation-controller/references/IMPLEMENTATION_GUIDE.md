# Implementation Guide — Certificate Drift and Revocation Controller

## Purpose

Continuously map code, model, data, policy, adapter, database, environment and vulnerability drift to evidence invalidation, certificate narrowing, suspension or revocation.

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

1. Maintain dependency graph from certificate to evidence and inputs
2. Classify drift severity and affected claims
3. Suspend rapidly on critical uncertainty
4. Generate incremental recertification DAG
5. Publish revocation and replacement lineage

## Native acceptance corpus

- `ELMOS_CERTIFICATE_DRIFT_REVOCATION_CONTROLLER-01` — source commit change
- `ELMOS_CERTIFICATE_DRIFT_REVOCATION_CONTROLLER-02` — model fingerprint drift
- `ELMOS_CERTIFICATE_DRIFT_REVOCATION_CONTROLLER-03` — database parameter drift
- `ELMOS_CERTIFICATE_DRIFT_REVOCATION_CONTROLLER-04` — critical CVE/KEV
- `ELMOS_CERTIFICATE_DRIFT_REVOCATION_CONTROLLER-05` — policy change
- `ELMOS_CERTIFICATE_DRIFT_REVOCATION_CONTROLLER-06` — certificate suspension/reissue

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

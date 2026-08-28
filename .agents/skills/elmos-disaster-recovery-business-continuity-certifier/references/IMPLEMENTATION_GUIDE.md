# Implementation Guide — Disaster Recovery and Business Continuity Certifier

## Purpose

Certify backup, restore, regional failover, dependency loss, key recovery, evidence continuity and documented RTO/RPO under business continuity scenarios.

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

1. Map critical services and recovery priorities
2. Validate backups and cryptographic key recovery
3. Run region/dependency loss exercises
4. Measure RTO/RPO from declared points
5. Reconcile data, side effects and evidence after restore

## Native acceptance corpus

- `ELMOS_DISASTER_RECOVERY_BUSINESS_CONTINUITY_CERTIFIER-01` — PostgreSQL point-in-time restore
- `ELMOS_DISASTER_RECOVERY_BUSINESS_CONTINUITY_CERTIFIER-02` — object store restore
- `ELMOS_DISASTER_RECOVERY_BUSINESS_CONTINUITY_CERTIFIER-03` — region failover
- `ELMOS_DISASTER_RECOVERY_BUSINESS_CONTINUITY_CERTIFIER-04` — event bus recovery
- `ELMOS_DISASTER_RECOVERY_BUSINESS_CONTINUITY_CERTIFIER-05` — KMS/signer continuity
- `ELMOS_DISASTER_RECOVERY_BUSINESS_CONTINUITY_CERTIFIER-06` — customer VPC disconnection
- `ELMOS_DISASTER_RECOVERY_BUSINESS_CONTINUITY_CERTIFIER-07` — annual full exercise

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

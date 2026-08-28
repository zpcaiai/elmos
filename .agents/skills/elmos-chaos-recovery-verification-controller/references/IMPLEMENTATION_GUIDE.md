# Implementation Guide — Chaos and Recovery Verification Controller

## Purpose

Inject worker, process, network, storage, provider, database and region failures and verify checkpoint, fencing, reconciliation, RTO/RPO and safe degradation.

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

1. Generate failure campaigns from architecture graph
2. Inject faults at deterministic checkpoints
3. Verify lease/fencing and idempotency
4. Measure RTO/RPO and data loss
5. Block on unknown side effects or silent degradation

## Native acceptance corpus

- `ELMOS_CHAOS_RECOVERY_VERIFICATION_CONTROLLER-01` — worker SIGKILL
- `ELMOS_CHAOS_RECOVERY_VERIFICATION_CONTROLLER-02` — network partition
- `ELMOS_CHAOS_RECOVERY_VERIFICATION_CONTROLLER-03` — database failover
- `ELMOS_CHAOS_RECOVERY_VERIFICATION_CONTROLLER-04` — object store outage
- `ELMOS_CHAOS_RECOVERY_VERIFICATION_CONTROLLER-05` — provider timeout/rate limit
- `ELMOS_CHAOS_RECOVERY_VERIFICATION_CONTROLLER-06` — region loss tabletop
- `ELMOS_CHAOS_RECOVERY_VERIFICATION_CONTROLLER-07` — restore from backup

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

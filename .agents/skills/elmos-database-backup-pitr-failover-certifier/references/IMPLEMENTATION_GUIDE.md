# Implementation Guide — Database Backup, PITR and Failover Certifier

## Purpose

Certify backups, point-in-time recovery, replica promotion, consistency, encryption, retention and application reconnect behavior for every stateful target.

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

1. verify full and incremental backup chains
2. perform isolated PITR to selected timestamp
3. promote replica under failure injection
4. validate application reconnect and fencing
5. prove encryption, retention and deletion policy

## Native acceptance corpus

- `ELMOS_DATABASE_BACKUP_PITR_FAILOVER_CERTIFIER-01` — native scenario: verify full and incremental backup chains
- `ELMOS_DATABASE_BACKUP_PITR_FAILOVER_CERTIFIER-02` — native scenario: perform isolated PITR to selected timestamp
- `ELMOS_DATABASE_BACKUP_PITR_FAILOVER_CERTIFIER-03` — native scenario: promote replica under failure injection
- `ELMOS_DATABASE_BACKUP_PITR_FAILOVER_CERTIFIER-04` — native scenario: validate application reconnect and fencing
- `ELMOS_DATABASE_BACKUP_PITR_FAILOVER_CERTIFIER-05` — native scenario: prove encryption, retention and deletion policy

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

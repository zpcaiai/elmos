# Implementation Guide — Distributed Invariant TLA+/Alloy Verifier

## Purpose

Encode leases, fencing, outbox, replication, saga and multi-agent coordination models for bounded exhaustive verification.

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

1. generate TLA+/Alloy model from runtime IR
2. declare explicit assumptions and fairness
3. check split-brain, stale write and ghost completion
4. explore partition, retry and failover schedules
5. translate traces into regression tests

## Native acceptance corpus

- `ELMOS_DISTRIBUTED_INVARIANT_TLA_ALLOY_VERIFIER-01` — native scenario: generate TLA+/Alloy model from runtime IR
- `ELMOS_DISTRIBUTED_INVARIANT_TLA_ALLOY_VERIFIER-02` — native scenario: declare explicit assumptions and fairness
- `ELMOS_DISTRIBUTED_INVARIANT_TLA_ALLOY_VERIFIER-03` — native scenario: check split-brain, stale write and ghost completion
- `ELMOS_DISTRIBUTED_INVARIANT_TLA_ALLOY_VERIFIER-04` — native scenario: explore partition, retry and failover schedules
- `ELMOS_DISTRIBUTED_INVARIANT_TLA_ALLOY_VERIFIER-05` — native scenario: translate traces into regression tests

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

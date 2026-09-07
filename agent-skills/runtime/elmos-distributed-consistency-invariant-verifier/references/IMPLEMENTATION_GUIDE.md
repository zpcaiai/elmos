# Implementation Guide — Distributed Consistency Invariant Verifier

## Purpose

Verify business invariants across services, stores, caches and event streams under concurrency, partitions, retries and failover.

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

1. compile cross-component invariants
2. generate concurrent histories and partitions
3. check monotonicity and convergence
4. compare source/target consistency envelopes
5. attach runtime monitors where proof is bounded

## Native acceptance corpus

- `ELMOS_DISTRIBUTED_CONSISTENCY_INVARIANT_VERIFIER-01` — native scenario: compile cross-component invariants
- `ELMOS_DISTRIBUTED_CONSISTENCY_INVARIANT_VERIFIER-02` — native scenario: generate concurrent histories and partitions
- `ELMOS_DISTRIBUTED_CONSISTENCY_INVARIANT_VERIFIER-03` — native scenario: check monotonicity and convergence
- `ELMOS_DISTRIBUTED_CONSISTENCY_INVARIANT_VERIFIER-04` — native scenario: compare source/target consistency envelopes
- `ELMOS_DISTRIBUTED_CONSISTENCY_INVARIANT_VERIFIER-05` — native scenario: attach runtime monitors where proof is bounded

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

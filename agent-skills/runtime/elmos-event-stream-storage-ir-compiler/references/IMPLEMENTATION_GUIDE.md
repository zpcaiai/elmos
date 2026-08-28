# Implementation Guide — Event Stream Storage IR Compiler

## Purpose

Compile topics, partitions, keys, ordering, retention, compaction, consumer groups, offsets and transactional publication semantics.

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

1. model partitioning and ordering contracts
2. capture delivery and acknowledgement semantics
3. represent retention, compaction and replay
4. compile consumer-group ownership and rebalance
5. bind schema and transaction boundaries

## Native acceptance corpus

- `ELMOS_EVENT_STREAM_STORAGE_IR_COMPILER-01` — native scenario: model partitioning and ordering contracts
- `ELMOS_EVENT_STREAM_STORAGE_IR_COMPILER-02` — native scenario: capture delivery and acknowledgement semantics
- `ELMOS_EVENT_STREAM_STORAGE_IR_COMPILER-03` — native scenario: represent retention, compaction and replay
- `ELMOS_EVENT_STREAM_STORAGE_IR_COMPILER-04` — native scenario: compile consumer-group ownership and rebalance
- `ELMOS_EVENT_STREAM_STORAGE_IR_COMPILER-05` — native scenario: bind schema and transaction boundaries

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

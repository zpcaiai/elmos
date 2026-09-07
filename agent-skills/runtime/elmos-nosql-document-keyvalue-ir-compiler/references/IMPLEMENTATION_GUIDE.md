# Implementation Guide — NoSQL Document and Key-Value IR Compiler

## Purpose

Compile document, key-value, wide-column and aggregate-store schemas, access paths, consistency, TTL, indexing and update semantics into a store-neutral persistence IR.

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

1. model documents, partitions, keys and secondary indexes
2. represent atomic update and conditional-write semantics
3. capture TTL, tombstone and compaction behavior
4. encode consistency and quorum requirements
5. emit semantic gaps for cross-store migration

## Native acceptance corpus

- `ELMOS_NOSQL_DOCUMENT_KEYVALUE_IR_COMPILER-01` — native scenario: model documents, partitions, keys and secondary indexes
- `ELMOS_NOSQL_DOCUMENT_KEYVALUE_IR_COMPILER-02` — native scenario: represent atomic update and conditional-write semantics
- `ELMOS_NOSQL_DOCUMENT_KEYVALUE_IR_COMPILER-03` — native scenario: capture TTL, tombstone and compaction behavior
- `ELMOS_NOSQL_DOCUMENT_KEYVALUE_IR_COMPILER-04` — native scenario: encode consistency and quorum requirements
- `ELMOS_NOSQL_DOCUMENT_KEYVALUE_IR_COMPILER-05` — native scenario: emit semantic gaps for cross-store migration

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

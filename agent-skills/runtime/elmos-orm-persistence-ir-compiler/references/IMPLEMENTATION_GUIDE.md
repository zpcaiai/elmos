# Implementation Guide — ORM and Persistence IR Compiler

## Purpose

Compile ORM mappings, identity generation, cascades, lazy/eager loading, optimistic locking, transactions, native queries and migrations across Java, Python, TypeScript, .NET, Go and Rust.

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

1. Detect ORM/provider and exact version
2. Recover entity and relationship mappings
3. Model fetch/cascade/locking semantics
4. Link native SQL and migrations to DB-SIR
5. Generate target persistence mappings with explicit gaps

## Native acceptance corpus

- `ELMOS_ORM_PERSISTENCE_IR_COMPILER-01` — JPA/Hibernate mapping
- `ELMOS_ORM_PERSISTENCE_IR_COMPILER-02` — SQLAlchemy mapping
- `ELMOS_ORM_PERSISTENCE_IR_COMPILER-03` — Prisma/TypeORM mapping
- `ELMOS_ORM_PERSISTENCE_IR_COMPILER-04` — EF Core mapping
- `ELMOS_ORM_PERSISTENCE_IR_COMPILER-05` — Go/Rust persistence mapping
- `ELMOS_ORM_PERSISTENCE_IR_COMPILER-06` — native query and transaction boundary

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

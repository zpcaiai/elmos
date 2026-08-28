# Implementation Guide — Stored Routine to Service Extraction Compiler

## Purpose

Extract stored procedures, functions, packages and triggers into governed services while preserving transaction, error, lock, idempotency and side-effect semantics.

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

1. classify pure, transactional and side-effecting routine regions
2. generate typed service and database contracts
3. preserve transaction and lock boundaries
4. replace triggers with explicit outbox or workflow where approved
5. dual-run routine/service behavior and rollback

## Native acceptance corpus

- `ELMOS_STORED_ROUTINE_SERVICE_EXTRACTION_COMPILER-01` — native scenario: classify pure, transactional and side-effecting routine regions
- `ELMOS_STORED_ROUTINE_SERVICE_EXTRACTION_COMPILER-02` — native scenario: generate typed service and database contracts
- `ELMOS_STORED_ROUTINE_SERVICE_EXTRACTION_COMPILER-03` — native scenario: preserve transaction and lock boundaries
- `ELMOS_STORED_ROUTINE_SERVICE_EXTRACTION_COMPILER-04` — native scenario: replace triggers with explicit outbox or workflow where approved
- `ELMOS_STORED_ROUTINE_SERVICE_EXTRACTION_COMPILER-05` — native scenario: dual-run routine/service behavior and rollback

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

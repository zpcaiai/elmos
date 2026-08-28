# Implementation Guide — Certification Scope Compiler

## Purpose

Compile precise system, route, deployment, tenant, jurisdiction, assurance, exclusions and validity envelopes before any production certification run.

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

1. Freeze subjects and exact RevisionSet
2. Define claims, assurance levels and accepted evidence
3. Declare exclusions and external dependencies
4. Bind jurisdiction and customer constraints
5. Prevent scope expansion after tests

## Native acceptance corpus

- `ELMOS_CERTIFICATION_SCOPE_COMPILER-01` — route certificate scope
- `ELMOS_CERTIFICATION_SCOPE_COMPILER-02` — deployment certificate scope
- `ELMOS_CERTIFICATION_SCOPE_COMPILER-03` — multi-tenant scope
- `ELMOS_CERTIFICATION_SCOPE_COMPILER-04` — jurisdiction profile
- `ELMOS_CERTIFICATION_SCOPE_COMPILER-05` — scope change creates new request
- `ELMOS_CERTIFICATION_SCOPE_COMPILER-06` — excluded claim visible

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

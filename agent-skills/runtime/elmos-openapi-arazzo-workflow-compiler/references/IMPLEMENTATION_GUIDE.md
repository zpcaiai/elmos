# Implementation Guide — OpenAPI and Arazzo Workflow Compiler

## Purpose

Compile API operations, links, callbacks, security, examples and multi-step workflows into exact OpenAPI and Arazzo contracts with executable client/server conformance.

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

1. emit OpenAPI 3.2 operation and schema contracts
2. emit Arazzo 1.1 multi-step workflows
3. bind authentication, callbacks and runtime expressions
4. generate positive and negative workflow fixtures
5. verify mixed-version clients, servers and rollback

## Native acceptance corpus

- `ELMOS_OPENAPI_ARAZZO_WORKFLOW_COMPILER-01` — native scenario: emit OpenAPI 3.2 operation and schema contracts
- `ELMOS_OPENAPI_ARAZZO_WORKFLOW_COMPILER-02` — native scenario: emit Arazzo 1.1 multi-step workflows
- `ELMOS_OPENAPI_ARAZZO_WORKFLOW_COMPILER-03` — native scenario: bind authentication, callbacks and runtime expressions
- `ELMOS_OPENAPI_ARAZZO_WORKFLOW_COMPILER-04` — native scenario: generate positive and negative workflow fixtures
- `ELMOS_OPENAPI_ARAZZO_WORKFLOW_COMPILER-05` — native scenario: verify mixed-version clients, servers and rollback

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

# Implementation Guide — OpenAPI, GraphQL and gRPC Protocol Gateway Generator

## Purpose

Generate governed gateways and adapters among REST/OpenAPI, GraphQL and gRPC while preserving auth, streaming, errors, deadlines and compatibility.

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

1. lower unified contract IR to gateway routes
2. map deadlines, cancellation and streaming
3. translate error and pagination models
4. preserve authentication and field authorization
5. generate differential conformance tests

## Native acceptance corpus

- `ELMOS_OPENAPI_GRAPHQL_GRPC_PROTOCOL_GATEWAY_GENERATOR-01` — native scenario: lower unified contract IR to gateway routes
- `ELMOS_OPENAPI_GRAPHQL_GRPC_PROTOCOL_GATEWAY_GENERATOR-02` — native scenario: map deadlines, cancellation and streaming
- `ELMOS_OPENAPI_GRAPHQL_GRPC_PROTOCOL_GATEWAY_GENERATOR-03` — native scenario: translate error and pagination models
- `ELMOS_OPENAPI_GRAPHQL_GRPC_PROTOCOL_GATEWAY_GENERATOR-04` — native scenario: preserve authentication and field authorization
- `ELMOS_OPENAPI_GRAPHQL_GRPC_PROTOCOL_GATEWAY_GENERATOR-05` — native scenario: generate differential conformance tests

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

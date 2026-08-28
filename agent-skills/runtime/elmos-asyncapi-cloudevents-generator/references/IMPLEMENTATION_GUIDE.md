# Implementation Guide — AsyncAPI and CloudEvents Generator

## Purpose

Generate versioned AsyncAPI and CloudEvents-compatible contracts, bindings, examples, code stubs and conformance tests from Event Contract IR.

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

1. emit AsyncAPI channels, operations and messages
2. generate protocol bindings and CloudEvents envelopes
3. produce producer/consumer stubs
4. generate schema registry and compatibility tests
5. validate documentation and examples

## Native acceptance corpus

- `ELMOS_ASYNCAPI_CLOUDEVENTS_GENERATOR-01` — native scenario: emit AsyncAPI channels, operations and messages
- `ELMOS_ASYNCAPI_CLOUDEVENTS_GENERATOR-02` — native scenario: generate protocol bindings and CloudEvents envelopes
- `ELMOS_ASYNCAPI_CLOUDEVENTS_GENERATOR-03` — native scenario: produce producer/consumer stubs
- `ELMOS_ASYNCAPI_CLOUDEVENTS_GENERATOR-04` — native scenario: generate schema registry and compatibility tests
- `ELMOS_ASYNCAPI_CLOUDEVENTS_GENERATOR-05` — native scenario: validate documentation and examples

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

# Implementation Guide — Protocol Conformance Fuzzing Controller

## Purpose

Generate grammar, stateful and adversarial fuzz campaigns for MCP, A2A, ACP, HTTP, gRPC, WebSocket and event protocols.

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

1. derive generators from protocol schemas and state machines
2. fuzz framing, negotiation, cancellation and extensions
3. inject malformed and oversized payloads
4. minimize crashes and semantic violations
5. promote protocol counterexamples to regression

## Native acceptance corpus

- `ELMOS_PROTOCOL_CONFORMANCE_FUZZING_CONTROLLER-01` — native scenario: derive generators from protocol schemas and state machines
- `ELMOS_PROTOCOL_CONFORMANCE_FUZZING_CONTROLLER-02` — native scenario: fuzz framing, negotiation, cancellation and extensions
- `ELMOS_PROTOCOL_CONFORMANCE_FUZZING_CONTROLLER-03` — native scenario: inject malformed and oversized payloads
- `ELMOS_PROTOCOL_CONFORMANCE_FUZZING_CONTROLLER-04` — native scenario: minimize crashes and semantic violations
- `ELMOS_PROTOCOL_CONFORMANCE_FUZZING_CONTROLLER-05` — native scenario: promote protocol counterexamples to regression

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

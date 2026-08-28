# Implementation Guide — Service Virtualization and Contract Simulator

## Purpose

Generate deterministic simulators for unavailable services, brokers, tools and failure modes without letting mocks masquerade as native certification.

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

1. derive simulator behavior from contracts and traces
2. model latency, errors, retries and rate limits
3. record simulation fidelity and omissions
4. support deterministic seeds and replay
5. mark evidence as simulated and require native follow-up

## Native acceptance corpus

- `ELMOS_SERVICE_VIRTUALIZATION_CONTRACT_SIMULATOR-01` — native scenario: derive simulator behavior from contracts and traces
- `ELMOS_SERVICE_VIRTUALIZATION_CONTRACT_SIMULATOR-02` — native scenario: model latency, errors, retries and rate limits
- `ELMOS_SERVICE_VIRTUALIZATION_CONTRACT_SIMULATOR-03` — native scenario: record simulation fidelity and omissions
- `ELMOS_SERVICE_VIRTUALIZATION_CONTRACT_SIMULATOR-04` — native scenario: support deterministic seeds and replay
- `ELMOS_SERVICE_VIRTUALIZATION_CONTRACT_SIMULATOR-05` — native scenario: mark evidence as simulated and require native follow-up

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

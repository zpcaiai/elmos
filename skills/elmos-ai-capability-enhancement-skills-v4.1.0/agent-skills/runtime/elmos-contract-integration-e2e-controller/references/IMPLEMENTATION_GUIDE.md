# Implementation Guide — Contract, Integration and E2E Controller

## Purpose

Generate and run provider/consumer, API, event, tool, MCP/A2A, database integration and end-to-end journey suites against real dependencies.

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

1. Compile tests from recovered contracts
2. Provision real disposable dependencies
3. Exercise positive, negative and idempotency paths
4. Trace journeys across services and tools
5. Bind failures to requirement and artifact lineage

## Native acceptance corpus

- `ELMOS_CONTRACT_INTEGRATION_E2E_CONTROLLER-01` — consumer/provider compatibility
- `ELMOS_CONTRACT_INTEGRATION_E2E_CONTROLLER-02` — event schema/order
- `ELMOS_CONTRACT_INTEGRATION_E2E_CONTROLLER-03` — MCP/A2A contract
- `ELMOS_CONTRACT_INTEGRATION_E2E_CONTROLLER-04` — real database integration
- `ELMOS_CONTRACT_INTEGRATION_E2E_CONTROLLER-05` — multi-service journey
- `ELMOS_CONTRACT_INTEGRATION_E2E_CONTROLLER-06` — duplicate request idempotency
- `ELMOS_CONTRACT_INTEGRATION_E2E_CONTROLLER-07` — external dependency failure

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

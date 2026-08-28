# Implementation Guide — AIRequirementContractCompiler

## Purpose

Recover and normalize business, interaction, data, security, latency, cost, residency, operability and acceptance requirements into an executable AI solution contract.

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

1. Recover explicit and implicit requirements
2. Compile observable behavior and nonfunctional constraints
3. Track assumptions, conflicts and allowed deltas
4. Initialize proof obligations and acceptance scenarios

## Native acceptance corpus

- `ELMOS_AI_REQUIREMENT_CONTRACT_COMPILER-01` — schema validation
- `ELMOS_AI_REQUIREMENT_CONTRACT_COMPILER-02` — conflicting requirement fixture
- `ELMOS_AI_REQUIREMENT_CONTRACT_COMPILER-03` — revision-bound acceptance fixture
- `ELMOS_AI_REQUIREMENT_CONTRACT_COMPILER-04` — AiRequirementContractCompiler representative end-to-end fixture
- `ELMOS_AI_REQUIREMENT_CONTRACT_COMPILER-05` — crash recovery preserves single-writer semantics
- `ELMOS_AI_REQUIREMENT_CONTRACT_COMPILER-06` — upstream or contract drift invalidates stale evidence
- `ELMOS_AI_REQUIREMENT_CONTRACT_COMPILER-07` — undeclared authority is denied
- `ELMOS_AI_REQUIREMENT_CONTRACT_COMPILER-08` — resource and wall-clock budget is measured
- `ELMOS_AI_REQUIREMENT_CONTRACT_COMPILER-09` — complete requirement fixture
- `ELMOS_AI_REQUIREMENT_CONTRACT_COMPILER-10` — conflicting requirements

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

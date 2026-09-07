# Implementation Guide — AIGoldenRouteAutogenSkToAgentFramework

## Purpose

Migrate AutoGen or Semantic Kernel agent applications to Microsoft Agent Framework while preserving tools, sessions, workflows, human gates and telemetry contracts.

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

1. Execute a repeatable end-to-end commercial route
2. Use hidden holdouts and independent oracles
3. Capture machine ETA, cost, rollback and customer acceptance
4. Certify only exact route envelope

## Native acceptance corpus

- `ELMOS_AI_GOLDEN_ROUTE_AUTOGEN_SK_TO_AGENT_FRAMEWORK-01` — three independent repetitions
- `ELMOS_AI_GOLDEN_ROUTE_AUTOGEN_SK_TO_AGENT_FRAMEWORK-02` — holdout scenario
- `ELMOS_AI_GOLDEN_ROUTE_AUTOGEN_SK_TO_AGENT_FRAMEWORK-03` — rollback and recovery
- `ELMOS_AI_GOLDEN_ROUTE_AUTOGEN_SK_TO_AGENT_FRAMEWORK-04` — AiGoldenRouteAutogenSkToAgentFramework representative end-to-end fixture
- `ELMOS_AI_GOLDEN_ROUTE_AUTOGEN_SK_TO_AGENT_FRAMEWORK-05` — crash recovery preserves single-writer semantics
- `ELMOS_AI_GOLDEN_ROUTE_AUTOGEN_SK_TO_AGENT_FRAMEWORK-06` — upstream or contract drift invalidates stale evidence
- `ELMOS_AI_GOLDEN_ROUTE_AUTOGEN_SK_TO_AGENT_FRAMEWORK-07` — undeclared authority is denied
- `ELMOS_AI_GOLDEN_ROUTE_AUTOGEN_SK_TO_AGENT_FRAMEWORK-08` — resource and wall-clock budget is measured
- `ELMOS_AI_GOLDEN_ROUTE_AUTOGEN_SK_TO_AGENT_FRAMEWORK-09` — three independent repeats
- `ELMOS_AI_GOLDEN_ROUTE_AUTOGEN_SK_TO_AGENT_FRAMEWORK-10` — hidden holdout

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

# Implementation Guide — AI Tool Contract Compatibility Verifier

## Purpose

Verify schema, semantics, effects, idempotency, authorization and error compatibility as tools and MCP/OpenAPI providers evolve.

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

1. Input/output schema compatibility
2. Effect and idempotency preservation
3. Authorization and approval compatibility
4. Error/timeout/retry semantics
5. Dual-run and cutover verification

## Native acceptance corpus

- `ELMOS_AI_TOOL_CONTRACT_COMPATIBILITY_VERIFIER-01` — additive schema change
- `ELMOS_AI_TOOL_CONTRACT_COMPATIBILITY_VERIFIER-02` — breaking parameter
- `ELMOS_AI_TOOL_CONTRACT_COMPATIBILITY_VERIFIER-03` — effect change
- `ELMOS_AI_TOOL_CONTRACT_COMPATIBILITY_VERIFIER-04` — permission change
- `ELMOS_AI_TOOL_CONTRACT_COMPATIBILITY_VERIFIER-05` — error semantic change
- `ELMOS_AI_TOOL_CONTRACT_COMPATIBILITY_VERIFIER-06` — dual-run equivalence

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

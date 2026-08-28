# Implementation Guide — Golden Route: MCP 2026 Modernization

## Purpose

Certify migration of a legacy MCP server to the 2026-07-28 profile with stateless core, Tasks, Apps/Skills extensions and enterprise authorization.

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

1. Legacy protocol fingerprint
2. Exact-version migration plan
3. Tasks/UI/auth implementation
4. Native protocol differential tests
5. Canary, rollback and certification

## Native acceptance corpus

- `ELMOS_AI_GOLDEN_ROUTE_MCP_2026_MODERNIZATION-01` — legacy compatibility
- `ELMOS_AI_GOLDEN_ROUTE_MCP_2026_MODERNIZATION-02` — stateless core
- `ELMOS_AI_GOLDEN_ROUTE_MCP_2026_MODERNIZATION-03` — durable task recovery
- `ELMOS_AI_GOLDEN_ROUTE_MCP_2026_MODERNIZATION-04` — interactive UI
- `ELMOS_AI_GOLDEN_ROUTE_MCP_2026_MODERNIZATION-05` — enterprise auth
- `ELMOS_AI_GOLDEN_ROUTE_MCP_2026_MODERNIZATION-06` — downgrade denial
- `ELMOS_AI_GOLDEN_ROUTE_MCP_2026_MODERNIZATION-07` — rollback

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

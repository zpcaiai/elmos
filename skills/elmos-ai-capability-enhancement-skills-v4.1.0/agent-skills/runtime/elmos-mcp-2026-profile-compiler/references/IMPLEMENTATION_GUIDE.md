# Implementation Guide — MCP 2026 Profile Compiler

## Purpose

Compile exact-version MCP 2026-07-28 capability profiles for stateless core, extensions, Tasks, routing, caching, authorization and deprecation behavior.

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

1. Exact protocol-version negotiation
2. Stateless core and extension separation
3. Header routing and cache semantics
4. Tasks and interactive extension declarations
5. Deprecation and unsupported capability accounting

## Native acceptance corpus

- `ELMOS_MCP_2026_PROFILE_COMPILER-01` — version negotiation
- `ELMOS_MCP_2026_PROFILE_COMPILER-02` — stateless request replay
- `ELMOS_MCP_2026_PROFILE_COMPILER-03` — header routing
- `ELMOS_MCP_2026_PROFILE_COMPILER-04` — cache invalidation
- `ELMOS_MCP_2026_PROFILE_COMPILER-05` — extension discovery
- `ELMOS_MCP_2026_PROFILE_COMPILER-06` — deprecated capability block

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

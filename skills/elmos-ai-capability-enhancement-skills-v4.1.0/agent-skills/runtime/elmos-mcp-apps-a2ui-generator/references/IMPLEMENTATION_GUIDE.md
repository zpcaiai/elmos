# Implementation Guide — MCP Apps and A2UI Generator

## Purpose

Generate secure interactive agent interfaces for MCP Apps, A2UI and AG-UI from a common Interaction IR with capability negotiation and recoverable UI state.

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

1. Declarative component allowlist
2. Streaming UI state and action binding
3. Host capability negotiation
4. Approval-aware tool actions
5. Accessibility, CSP and sandbox policy generation

## Native acceptance corpus

- `ELMOS_MCP_APPS_A2UI_GENERATOR-01` — form and chart rendering
- `ELMOS_MCP_APPS_A2UI_GENERATOR-02` — stream reconnect
- `ELMOS_MCP_APPS_A2UI_GENERATOR-03` — approval action binding
- `ELMOS_MCP_APPS_A2UI_GENERATOR-04` — unsupported component fallback
- `ELMOS_MCP_APPS_A2UI_GENERATOR-05` — XSS/CSP campaign
- `ELMOS_MCP_APPS_A2UI_GENERATOR-06` — accessibility audit

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

# Implementation Guide — MCP, A2A and ACP Bridge Conformance Verifier

## Purpose

Verify bridges among tool, agent-to-agent and editor-agent protocols without authority, lifecycle, content or cancellation loss.

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

1. map identity, session and task semantics
2. translate content blocks and artifacts
3. preserve cancellation, progress and approval
4. verify extension/version negotiation
5. run cross-protocol differential traces

## Native acceptance corpus

- `ELMOS_MCP_A2A_ACP_BRIDGE_CONFORMANCE_VERIFIER-01` — native scenario: map identity, session and task semantics
- `ELMOS_MCP_A2A_ACP_BRIDGE_CONFORMANCE_VERIFIER-02` — native scenario: translate content blocks and artifacts
- `ELMOS_MCP_A2A_ACP_BRIDGE_CONFORMANCE_VERIFIER-03` — native scenario: preserve cancellation, progress and approval
- `ELMOS_MCP_A2A_ACP_BRIDGE_CONFORMANCE_VERIFIER-04` — native scenario: verify extension/version negotiation
- `ELMOS_MCP_A2A_ACP_BRIDGE_CONFORMANCE_VERIFIER-05` — native scenario: run cross-protocol differential traces

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

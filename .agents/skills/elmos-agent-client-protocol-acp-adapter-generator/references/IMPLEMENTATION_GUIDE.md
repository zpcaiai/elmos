# Implementation Guide — Agent Client Protocol ACP Adapter Generator

## Purpose

Generate ACP v1 agents and clients for local/remote coding-agent integration with sessions, capabilities, tool-call updates, permissions and extensibility.

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

1. compile ACP capability and transport profile
2. generate JSON-RPC agent/client endpoints
3. map sessions, plans, tool calls and permissions
4. support stdio/remote transport and extensions
5. run editor-agent interoperability tests

## Native acceptance corpus

- `ELMOS_AGENT_CLIENT_PROTOCOL_ACP_ADAPTER_GENERATOR-01` — native scenario: compile ACP capability and transport profile
- `ELMOS_AGENT_CLIENT_PROTOCOL_ACP_ADAPTER_GENERATOR-02` — native scenario: generate JSON-RPC agent/client endpoints
- `ELMOS_AGENT_CLIENT_PROTOCOL_ACP_ADAPTER_GENERATOR-03` — native scenario: map sessions, plans, tool calls and permissions
- `ELMOS_AGENT_CLIENT_PROTOCOL_ACP_ADAPTER_GENERATOR-04` — native scenario: support stdio/remote transport and extensions
- `ELMOS_AGENT_CLIENT_PROTOCOL_ACP_ADAPTER_GENERATOR-05` — native scenario: run editor-agent interoperability tests

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

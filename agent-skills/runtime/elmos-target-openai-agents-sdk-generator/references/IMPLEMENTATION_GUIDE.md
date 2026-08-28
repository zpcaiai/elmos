# Implementation Guide — TargetOpenaiAgentsSdkGenerator

## Purpose

Generate Python and TypeScript agent projects with tools, handoffs, guardrails, sessions, tracing, MCP, structured outputs and realtime integration contracts.

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

1. Generate Python/TypeScript agent projects
2. Generate tools, handoffs and guardrails
3. Generate session and tracing adapters
4. Generate MCP and structured outputs
5. Generate realtime/voice route when selected

## Native acceptance corpus

- `ELMOS_TARGET_OPENAI_AGENTS_SDK_GENERATOR-01` — agent run
- `ELMOS_TARGET_OPENAI_AGENTS_SDK_GENERATOR-02` — tool call
- `ELMOS_TARGET_OPENAI_AGENTS_SDK_GENERATOR-03` — handoff
- `ELMOS_TARGET_OPENAI_AGENTS_SDK_GENERATOR-04` — input/output guardrail
- `ELMOS_TARGET_OPENAI_AGENTS_SDK_GENERATOR-05` — session resume
- `ELMOS_TARGET_OPENAI_AGENTS_SDK_GENERATOR-06` — trace correlation
- `ELMOS_TARGET_OPENAI_AGENTS_SDK_GENERATOR-07` — MCP
- `ELMOS_TARGET_OPENAI_AGENTS_SDK_GENERATOR-08` — structured output

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

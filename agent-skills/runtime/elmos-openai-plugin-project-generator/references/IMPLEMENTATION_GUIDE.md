# Implementation Guide — OpenAI Plugin Project Generator

## Purpose

Generate a complete OpenAI Plugin project containing Skills, remote MCP server, optional MCP Apps UI, authentication, evaluations, packaging and submission evidence.

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

1. Plugin manifest and directory generation
2. Skill and MCP capability composition
3. Optional app UI resource generation
4. OAuth and secretless deployment contract
5. Complete-plugin evaluation and negative submission tests

## Native acceptance corpus

- `ELMOS_OPENAI_PLUGIN_PROJECT_GENERATOR-01` — manifest validation
- `ELMOS_OPENAI_PLUGIN_PROJECT_GENERATOR-02` — Skill discovery
- `ELMOS_OPENAI_PLUGIN_PROJECT_GENERATOR-03` — remote MCP handshake
- `ELMOS_OPENAI_PLUGIN_PROJECT_GENERATOR-04` — OAuth denial and consent
- `ELMOS_OPENAI_PLUGIN_PROJECT_GENERATOR-05` — optional UI sandbox
- `ELMOS_OPENAI_PLUGIN_PROJECT_GENERATOR-06` — complete-plugin eval
- `ELMOS_OPENAI_PLUGIN_PROJECT_GENERATOR-07` — upgrade rollback

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

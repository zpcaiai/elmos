# Implementation Guide — ChatGPT Apps SDK Project Generator

## Purpose

Generate MCP-backed ChatGPT plugin/app projects with tool plans, optional MCP Apps UI, CSP, authentication, submission metadata and review tests.

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

1. classify tool-only/widget/submission archetype
2. generate MCP server and UI resource contracts
3. set accurate tool annotations and output schemas
4. generate CSP/auth/deploy/submission artifacts
5. run local and review-oriented conformance

## Native acceptance corpus

- `ELMOS_CHATGPT_APPS_SDK_PROJECT_GENERATOR-01` — native scenario: classify tool-only/widget/submission archetype
- `ELMOS_CHATGPT_APPS_SDK_PROJECT_GENERATOR-02` — native scenario: generate MCP server and UI resource contracts
- `ELMOS_CHATGPT_APPS_SDK_PROJECT_GENERATOR-03` — native scenario: set accurate tool annotations and output schemas
- `ELMOS_CHATGPT_APPS_SDK_PROJECT_GENERATOR-04` — native scenario: generate CSP/auth/deploy/submission artifacts
- `ELMOS_CHATGPT_APPS_SDK_PROJECT_GENERATOR-05` — native scenario: run local and review-oriented conformance

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

# Implementation Guide — TargetGoogleAdkGenerator

## Purpose

Generate Python, TypeScript, Java/Kotlin and Go ADK projects with agent teams, workflow agents, A2A, evaluation, sessions, artifacts and deployment profiles.

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

1. Generate supported-language ADK projects
2. Generate sequential/parallel/loop workflows
3. Generate tools, sessions and artifacts
4. Generate A2A interfaces and deployment profile
5. Generate ADK evaluation suites

## Native acceptance corpus

- `ELMOS_TARGET_GOOGLE_ADK_GENERATOR-01` — language-native build
- `ELMOS_TARGET_GOOGLE_ADK_GENERATOR-02` — workflow agents
- `ELMOS_TARGET_GOOGLE_ADK_GENERATOR-03` — dynamic routing
- `ELMOS_TARGET_GOOGLE_ADK_GENERATOR-04` — session/artifact
- `ELMOS_TARGET_GOOGLE_ADK_GENERATOR-05` — A2A interface
- `ELMOS_TARGET_GOOGLE_ADK_GENERATOR-06` — evaluation
- `ELMOS_TARGET_GOOGLE_ADK_GENERATOR-07` — deployment smoke

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

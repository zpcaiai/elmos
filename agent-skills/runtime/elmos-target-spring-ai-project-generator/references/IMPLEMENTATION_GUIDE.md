# Implementation Guide — TargetSpringAIProjectGenerator

## Purpose

Generate enterprise Spring Boot AI services with ChatClient, Advisors, RAG, VectorStore, tools, MCP, memory, security, observability, Testcontainers and deployment assets.

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

1. Generate Boot modules with ChatClient and Advisors
2. Generate Tool Calling and MCP client/server
3. Generate RAG, VectorStore and ChatMemory
4. Generate Security, multitenancy and Actuator/OTel
5. Run Maven/Gradle, Testcontainers and native startup checks

## Native acceptance corpus

- `ELMOS_TARGET_SPRING_AI_PROJECT_GENERATOR-01` — Maven and Gradle build
- `ELMOS_TARGET_SPRING_AI_PROJECT_GENERATOR-02` — ApplicationContext startup
- `ELMOS_TARGET_SPRING_AI_PROJECT_GENERATOR-03` — structured output
- `ELMOS_TARGET_SPRING_AI_PROJECT_GENERATOR-04` — Advisor chain
- `ELMOS_TARGET_SPRING_AI_PROJECT_GENERATOR-05` — Tool Calling
- `ELMOS_TARGET_SPRING_AI_PROJECT_GENERATOR-06` — MCP client/server
- `ELMOS_TARGET_SPRING_AI_PROJECT_GENERATOR-07` — VectorStore Testcontainers
- `ELMOS_TARGET_SPRING_AI_PROJECT_GENERATOR-08` — Spring Security tenant isolation
- `ELMOS_TARGET_SPRING_AI_PROJECT_GENERATOR-09` — SSE streaming
- `ELMOS_TARGET_SPRING_AI_PROJECT_GENERATOR-10` — Flyway rollback
- `ELMOS_TARGET_SPRING_AI_PROJECT_GENERATOR-11` — Actuator metrics

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

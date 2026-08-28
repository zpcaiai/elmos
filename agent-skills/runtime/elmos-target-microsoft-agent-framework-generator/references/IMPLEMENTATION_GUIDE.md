# Implementation Guide — TargetMicrosoftAgentFrameworkGenerator

## Purpose

Generate .NET and Python projects with typed agents, sessions, graph workflows, human-in-the-loop, telemetry and migration assets from AutoGen or Semantic Kernel.

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

1. Generate .NET/Python agent projects
2. Generate typed graph workflows and sessions
3. Generate human-in-the-loop and long-running tasks
4. Generate middleware and telemetry
5. Generate AutoGen/Semantic Kernel migration adapters

## Native acceptance corpus

- `ELMOS_TARGET_MICROSOFT_AGENT_FRAMEWORK_GENERATOR-01` — .NET/Python build
- `ELMOS_TARGET_MICROSOFT_AGENT_FRAMEWORK_GENERATOR-02` — session persistence
- `ELMOS_TARGET_MICROSOFT_AGENT_FRAMEWORK_GENERATOR-03` — workflow graph
- `ELMOS_TARGET_MICROSOFT_AGENT_FRAMEWORK_GENERATOR-04` — human approval
- `ELMOS_TARGET_MICROSOFT_AGENT_FRAMEWORK_GENERATOR-05` — long task recovery
- `ELMOS_TARGET_MICROSOFT_AGENT_FRAMEWORK_GENERATOR-06` — telemetry
- `ELMOS_TARGET_MICROSOFT_AGENT_FRAMEWORK_GENERATOR-07` — compat migration

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

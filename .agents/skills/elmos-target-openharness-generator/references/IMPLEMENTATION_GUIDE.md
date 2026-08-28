# Implementation Guide — TargetOpenharnessGenerator

## Purpose

Generate provider, tool, skill, plugin, hook, permission, memory, session and multi-agent extensions against the OpenHarness adapter contract.

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

1. Generate inspectable Python harness components
2. Generate permission and hook policies
3. Generate memory/session backends
4. Generate personal and multi-agent configurations
5. Run resume, compaction and permission tests

## Native acceptance corpus

- `ELMOS_TARGET_OPENHARNESS_GENERATOR-01` — provider adapter
- `ELMOS_TARGET_OPENHARNESS_GENERATOR-02` — tool/Skill/plugin load
- `ELMOS_TARGET_OPENHARNESS_GENERATOR-03` — hook ordering
- `ELMOS_TARGET_OPENHARNESS_GENERATOR-04` — permission deny
- `ELMOS_TARGET_OPENHARNESS_GENERATOR-05` — session resume
- `ELMOS_TARGET_OPENHARNESS_GENERATOR-06` — memory backend
- `ELMOS_TARGET_OPENHARNESS_GENERATOR-07` — compaction
- `ELMOS_TARGET_OPENHARNESS_GENERATOR-08` — multi-agent coordination

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

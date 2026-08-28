# Implementation Guide — TargetDeepseekHarnessGenerator

## Purpose

Generate Cordis-based plugins, services, events, lifecycle effects, bundles, profiles and patch layers with hot-unload and authority conformance tests.

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

1. Generate Everything-is-a-Plugin components
2. Generate typed services/events and lifecycle cleanup
3. Generate bundles, profiles and ordered patches
4. Generate headless/web compositions
5. Run hot reload, unload and patch conflict tests

## Native acceptance corpus

- `ELMOS_TARGET_DEEPSEEK_HARNESS_GENERATOR-01` — plugin load/unload
- `ELMOS_TARGET_DEEPSEEK_HARNESS_GENERATOR-02` — service dependency
- `ELMOS_TARGET_DEEPSEEK_HARNESS_GENERATOR-03` — event lifecycle
- `ELMOS_TARGET_DEEPSEEK_HARNESS_GENERATOR-04` — bundle/profile composition
- `ELMOS_TARGET_DEEPSEEK_HARNESS_GENERATOR-05` — patch ordering
- `ELMOS_TARGET_DEEPSEEK_HARNESS_GENERATOR-06` — HMR cleanup
- `ELMOS_TARGET_DEEPSEEK_HARNESS_GENERATOR-07` — permission denial

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

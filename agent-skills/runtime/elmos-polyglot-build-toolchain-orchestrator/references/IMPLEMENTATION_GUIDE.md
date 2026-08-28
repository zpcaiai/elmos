# Implementation Guide — Polyglot Build Toolchain Orchestrator

## Purpose

Provision and execute hermetic Maven, Gradle, pip/uv, npm/pnpm, dotnet, Go and Cargo toolchains with exact locks, caches, sandboxes and reproducible logs.

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

1. Resolve exact compiler/build/package-manager versions
2. Run builds in isolated reproducible environments
3. Use content-addressed caches with semantic invalidation
4. Capture network and dependency acquisition evidence
5. Resume failed multi-module builds safely

## Native acceptance corpus

- `ELMOS_POLYGLOT_BUILD_TOOLCHAIN_ORCHESTRATOR-01` — Maven/Gradle build
- `ELMOS_POLYGLOT_BUILD_TOOLCHAIN_ORCHESTRATOR-02` — Python lock and wheel build
- `ELMOS_POLYGLOT_BUILD_TOOLCHAIN_ORCHESTRATOR-03` — TypeScript package build
- `ELMOS_POLYGLOT_BUILD_TOOLCHAIN_ORCHESTRATOR-04` — dotnet restore/build
- `ELMOS_POLYGLOT_BUILD_TOOLCHAIN_ORCHESTRATOR-05` — Go module build
- `ELMOS_POLYGLOT_BUILD_TOOLCHAIN_ORCHESTRATOR-06` — Cargo locked build
- `ELMOS_POLYGLOT_BUILD_TOOLCHAIN_ORCHESTRATOR-07` — offline rebuild

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

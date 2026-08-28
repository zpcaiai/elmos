# Implementation Guide — TargetPiPackageGenerator

## Purpose

Generate complete Pi packages containing extensions, custom tools, skills, prompt templates, themes, repository conventions, RPC/SDK embedding and load tests.

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

1. Generate package.json and Pi package layout
2. Generate extensions, tools and slash commands
3. Generate Skills, prompts and themes
4. Generate RPC/SDK embedding modes
5. Run package load, session and permission tests

## Native acceptance corpus

- `ELMOS_TARGET_PI_PACKAGE_GENERATOR-01` — package discovery
- `ELMOS_TARGET_PI_PACKAGE_GENERATOR-02` — extension load/unload
- `ELMOS_TARGET_PI_PACKAGE_GENERATOR-03` — custom tool schema
- `ELMOS_TARGET_PI_PACKAGE_GENERATOR-04` — Skill trigger
- `ELMOS_TARGET_PI_PACKAGE_GENERATOR-05` — RPC session
- `ELMOS_TARGET_PI_PACKAGE_GENERATOR-06` — SDK embedding
- `ELMOS_TARGET_PI_PACKAGE_GENERATOR-07` — permission denial
- `ELMOS_TARGET_PI_PACKAGE_GENERATOR-08` — upgrade

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

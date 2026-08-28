# Implementation Guide — TargetOpenclawAssistantGenerator

## Purpose

Generate isolated OpenClaw gateway/workspace configurations, agents, skills, plugins, channels, sandbox policies, pairing, service and recovery assets.

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

1. Generate gateway, workspace and assistant configuration
2. Generate Skills, Plugins and channels
3. Configure pairing and per-tenant isolation
4. Generate sandbox, daemon and backup/restore controls
5. Run gateway validation and plugin/Skill load tests

## Native acceptance corpus

- `ELMOS_TARGET_OPENCLAW_ASSISTANT_GENERATOR-01` — gateway config validation
- `ELMOS_TARGET_OPENCLAW_ASSISTANT_GENERATOR-02` — Skill load
- `ELMOS_TARGET_OPENCLAW_ASSISTANT_GENERATOR-03` — plugin manifest and allowlist
- `ELMOS_TARGET_OPENCLAW_ASSISTANT_GENERATOR-04` — channel pairing
- `ELMOS_TARGET_OPENCLAW_ASSISTANT_GENERATOR-05` — sandbox deny by default
- `ELMOS_TARGET_OPENCLAW_ASSISTANT_GENERATOR-06` — daemon restart
- `ELMOS_TARGET_OPENCLAW_ASSISTANT_GENERATOR-07` — backup/restore
- `ELMOS_TARGET_OPENCLAW_ASSISTANT_GENERATOR-08` — per-tenant gateway isolation
- `ELMOS_TARGET_OPENCLAW_ASSISTANT_GENERATOR-09` — plugin revocation

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

# Implementation Guide — Golden Route: Portable Agent Skill

## Purpose

Certify repository or runbook to portable Skill IR and host packages across Agent Skills, OpenAI Plugin, Codex, Claude Code, Pi and OpenClaw.

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

1. Source capability recovery
2. Skill IR compilation
3. Multi-host emission
4. Trigger and behavior differential evaluation
5. Supply-chain and customer certification

## Native acceptance corpus

- `ELMOS_AI_GOLDEN_ROUTE_PORTABLE_SKILL-01` — three repeated builds
- `ELMOS_AI_GOLDEN_ROUTE_PORTABLE_SKILL-02` — hidden trigger set
- `ELMOS_AI_GOLDEN_ROUTE_PORTABLE_SKILL-03` — cross-host trace equivalence
- `ELMOS_AI_GOLDEN_ROUTE_PORTABLE_SKILL-04` — malicious package negative
- `ELMOS_AI_GOLDEN_ROUTE_PORTABLE_SKILL-05` — upgrade/rollback
- `ELMOS_AI_GOLDEN_ROUTE_PORTABLE_SKILL-06` — customer acceptance

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

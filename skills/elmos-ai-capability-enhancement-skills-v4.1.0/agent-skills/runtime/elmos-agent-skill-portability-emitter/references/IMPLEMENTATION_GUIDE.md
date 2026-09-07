# Implementation Guide — Agent Skill Portability Emitter

## Purpose

Lower Skill IR into Agent Skills, Codex, Claude Code, Pi, OpenClaw, Gemini CLI, Continue and OpenCode packages while preserving semantics and recording every host-specific gap.

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

1. Host profile negotiation
2. Deterministic frontmatter and resource emission
3. Tool and sandbox policy lowering
4. Trigger adaptation without semantic widening
5. Cross-host normalized trace comparison

## Native acceptance corpus

- `ELMOS_AGENT_SKILL_PORTABILITY_EMITTER-01` — Agent Skills emission
- `ELMOS_AGENT_SKILL_PORTABILITY_EMITTER-02` — Codex and Claude load tests
- `ELMOS_AGENT_SKILL_PORTABILITY_EMITTER-03` — Pi/OpenClaw package tests
- `ELMOS_AGENT_SKILL_PORTABILITY_EMITTER-04` — unsupported host feature block
- `ELMOS_AGENT_SKILL_PORTABILITY_EMITTER-05` — cross-host behavior comparison

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

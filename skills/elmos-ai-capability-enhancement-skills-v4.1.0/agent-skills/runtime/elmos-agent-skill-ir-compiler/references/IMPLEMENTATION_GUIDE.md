# Implementation Guide — Agent Skill IR Compiler

## Purpose

Compile portable Agent Skill packages into a host-neutral semantic IR covering trigger intent, instructions, tools, resources, authority, tests, evidence and version constraints.

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

1. Parse SKILL.md frontmatter and Markdown instruction graph
2. Resolve scripts/references/assets without path escape
3. Normalize trigger, tool, environment and output contracts
4. Preserve source locations and package hashes
5. Emit unsupported host semantics as explicit obligations

## Native acceptance corpus

- `ELMOS_AGENT_SKILL_IR_COMPILER-01` — valid skill package round trip
- `ELMOS_AGENT_SKILL_IR_COMPILER-02` — malformed frontmatter rejection
- `ELMOS_AGENT_SKILL_IR_COMPILER-03` — resource path traversal rejection
- `ELMOS_AGENT_SKILL_IR_COMPILER-04` — tool authority extraction
- `ELMOS_AGENT_SKILL_IR_COMPILER-05` — lossless instruction/source-map test

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

# Implementation Guide — Prompt Program IR Compiler

## Purpose

Compile prompts into typed, versioned programs with parameters, roles, examples, tool visibility, output schemas, safety policies, lineage and tests.

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

1. Typed parameters and role segments
2. Few-shot example provenance
3. Tool visibility and authority binding
4. Output schema and refusal policy
5. Versioning, inheritance and target lowering

## Native acceptance corpus

- `ELMOS_PROMPT_PROGRAM_IR_COMPILER-01` — parameter validation
- `ELMOS_PROMPT_PROGRAM_IR_COMPILER-02` — prompt rendering determinism
- `ELMOS_PROMPT_PROGRAM_IR_COMPILER-03` — tool visibility
- `ELMOS_PROMPT_PROGRAM_IR_COMPILER-04` — example provenance
- `ELMOS_PROMPT_PROGRAM_IR_COMPILER-05` — injection delimiters
- `ELMOS_PROMPT_PROGRAM_IR_COMPILER-06` — target lowering equivalence

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

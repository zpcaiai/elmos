# Implementation Guide — AISolutionArchetypeSelector

## Purpose

Select one or more solution archetypes—RAG, agentic RAG, multi-agent workflow, coding harness, personal assistant, data agent, realtime agent or automation—using evidence rather than framework popularity.

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

1. Generate and rank feasible alternatives
2. Negotiate exact target capabilities
3. Allocate semantic gaps and validation obligations
4. Produce reversible plans with cost and machine ETA

## Native acceptance corpus

- `ELMOS_AI_SOLUTION_ARCHETYPE_SELECTOR-01` — supported target
- `ELMOS_AI_SOLUTION_ARCHETYPE_SELECTOR-02` — bounded target
- `ELMOS_AI_SOLUTION_ARCHETYPE_SELECTOR-03` — all-targets-blocked
- `ELMOS_AI_SOLUTION_ARCHETYPE_SELECTOR-04` — AiSolutionArchetypeSelector representative end-to-end fixture
- `ELMOS_AI_SOLUTION_ARCHETYPE_SELECTOR-05` — crash recovery preserves single-writer semantics
- `ELMOS_AI_SOLUTION_ARCHETYPE_SELECTOR-06` — upstream or contract drift invalidates stale evidence
- `ELMOS_AI_SOLUTION_ARCHETYPE_SELECTOR-07` — undeclared authority is denied
- `ELMOS_AI_SOLUTION_ARCHETYPE_SELECTOR-08` — resource and wall-clock budget is measured
- `ELMOS_AI_SOLUTION_ARCHETYPE_SELECTOR-09` — feasible route selection
- `ELMOS_AI_SOLUTION_ARCHETYPE_SELECTOR-10` — unsupported critical feature

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

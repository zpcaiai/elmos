# Implementation Guide — Model Fallback Semantic Degradation Verifier

## Purpose

Verify that provider/model fallback preserves required schemas, tool behavior, safety, language, memory and task quality or blocks explicitly.

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

1. compile per-task minimum capability contract
2. run primary/fallback paired scenarios
3. verify structured output and tool-call semantics
4. measure safety and multilingual degradation
5. gate cascade depth and user-visible disclosure

## Native acceptance corpus

- `ELMOS_MODEL_FALLBACK_SEMANTIC_DEGRADATION_VERIFIER-01` — native scenario: compile per-task minimum capability contract
- `ELMOS_MODEL_FALLBACK_SEMANTIC_DEGRADATION_VERIFIER-02` — native scenario: run primary/fallback paired scenarios
- `ELMOS_MODEL_FALLBACK_SEMANTIC_DEGRADATION_VERIFIER-03` — native scenario: verify structured output and tool-call semantics
- `ELMOS_MODEL_FALLBACK_SEMANTIC_DEGRADATION_VERIFIER-04` — native scenario: measure safety and multilingual degradation
- `ELMOS_MODEL_FALLBACK_SEMANTIC_DEGRADATION_VERIFIER-05` — native scenario: gate cascade depth and user-visible disclosure

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

# Implementation Guide — Formal Model to Runtime Refinement Verifier

## Purpose

Implement and independently certify formal model to runtime refinement verifier, including define abstraction relation between executable system and formal model, validate implementation traces refine allowed model behavior and monitor open-world boundaries and unmodeled side effects.

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

1. define abstraction relation between executable system and formal model
2. validate implementation traces refine allowed model behavior
3. monitor open-world boundaries and unmodeled side effects
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_FORMAL_MODEL_RUNTIME_REFINEMENT_VERIFIER-01` — native scenario: define abstraction relation between executable system and formal model
- `ELMOS_FORMAL_MODEL_RUNTIME_REFINEMENT_VERIFIER-02` — native scenario: validate implementation traces refine allowed model behavior
- `ELMOS_FORMAL_MODEL_RUNTIME_REFINEMENT_VERIFIER-03` — native scenario: monitor open-world boundaries and unmodeled side effects
- `ELMOS_FORMAL_MODEL_RUNTIME_REFINEMENT_VERIFIER-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_FORMAL_MODEL_RUNTIME_REFINEMENT_VERIFIER-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

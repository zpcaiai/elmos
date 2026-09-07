# Implementation Guide — Tool Discovery and Description Quality Evaluator

## Purpose

Evaluate tool naming, descriptions, schemas, examples and annotations for correct selection, non-selection and safe argument formation.

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

1. build positive and nearby-negative intent corpus
2. measure tool selection precision/recall
3. check schema constraints and sensitive inputs
4. evaluate side-effect annotations and descriptions
5. optimize metadata under versioned experiments

## Native acceptance corpus

- `ELMOS_TOOL_DISCOVERY_DESCRIPTION_QUALITY_EVALUATOR-01` — native scenario: build positive and nearby-negative intent corpus
- `ELMOS_TOOL_DISCOVERY_DESCRIPTION_QUALITY_EVALUATOR-02` — native scenario: measure tool selection precision/recall
- `ELMOS_TOOL_DISCOVERY_DESCRIPTION_QUALITY_EVALUATOR-03` — native scenario: check schema constraints and sensitive inputs
- `ELMOS_TOOL_DISCOVERY_DESCRIPTION_QUALITY_EVALUATOR-04` — native scenario: evaluate side-effect annotations and descriptions
- `ELMOS_TOOL_DISCOVERY_DESCRIPTION_QUALITY_EVALUATOR-05` — native scenario: optimize metadata under versioned experiments

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

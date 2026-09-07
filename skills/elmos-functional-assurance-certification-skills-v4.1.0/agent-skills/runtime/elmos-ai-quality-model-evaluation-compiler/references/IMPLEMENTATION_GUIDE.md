# Implementation Guide — AI Quality Model and Evaluation Compiler

## Purpose

Compile measurable product, service, data and AI quality characteristics into requirements, metrics, evaluation modules and release evidence.

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

1. Select applicable software and AI quality characteristics
2. Define operational measures and thresholds
3. Connect probabilistic quality to statistical evidence
4. Evaluate functional suitability, reliability, security, maintainability and interaction quality
5. Report tradeoffs and bounded context of use

## Native acceptance corpus

- `ELMOS_AI_QUALITY_MODEL_EVALUATION_COMPILER-01` — functional suitability
- `ELMOS_AI_QUALITY_MODEL_EVALUATION_COMPILER-02` — performance efficiency
- `ELMOS_AI_QUALITY_MODEL_EVALUATION_COMPILER-03` — reliability/recoverability
- `ELMOS_AI_QUALITY_MODEL_EVALUATION_COMPILER-04` — security
- `ELMOS_AI_QUALITY_MODEL_EVALUATION_COMPILER-05` — maintainability/portability
- `ELMOS_AI_QUALITY_MODEL_EVALUATION_COMPILER-06` — interaction/accessibility
- `ELMOS_AI_QUALITY_MODEL_EVALUATION_COMPILER-07` — AI robustness/grounding

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

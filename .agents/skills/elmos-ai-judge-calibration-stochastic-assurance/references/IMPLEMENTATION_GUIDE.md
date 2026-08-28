# Implementation Guide — AI Judge Calibration and Stochastic Assurance

## Purpose

Calibrate LLM judges against authoritative labels, quantify uncertainty and bias, and prevent probabilistic judgments from becoming unbounded completion evidence.

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

1. Human-label calibration and adjudication
2. Multi-judge agreement and bias analysis
3. Bootstrap confidence intervals and sequential tests
4. Order/style/self-preference probes
5. Abstention and code-oracle precedence

## Native acceptance corpus

- `ELMOS_AI_JUDGE_CALIBRATION_STOCHASTIC_ASSURANCE-01` — accuracy and Brier calibration
- `ELMOS_AI_JUDGE_CALIBRATION_STOCHASTIC_ASSURANCE-02` — inter-rater agreement
- `ELMOS_AI_JUDGE_CALIBRATION_STOCHASTIC_ASSURANCE-03` — position/style bias
- `ELMOS_AI_JUDGE_CALIBRATION_STOCHASTIC_ASSURANCE-04` — self-preference probe
- `ELMOS_AI_JUDGE_CALIBRATION_STOCHASTIC_ASSURANCE-05` — confidence interval coverage
- `ELMOS_AI_JUDGE_CALIBRATION_STOCHASTIC_ASSURANCE-06` — uncertain abstention

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

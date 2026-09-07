# Implementation Guide — AI Online Shadow Evaluation Controller

## Purpose

Run privacy-safe, no-side-effect production shadow evaluation with paired comparison, promotion thresholds, canary control and automatic rollback.

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

1. Deterministic traffic sampling
2. No-side-effect shadow isolation
3. Paired trace and outcome comparison
4. Sequential promotion/canary thresholds
5. Privacy filtering and rollback triggers

## Native acceptance corpus

- `ELMOS_AI_ONLINE_SHADOW_EVAL_CONTROLLER-01` — 1 percent shadow
- `ELMOS_AI_ONLINE_SHADOW_EVAL_CONTROLLER-02` — side-effect denial
- `ELMOS_AI_ONLINE_SHADOW_EVAL_CONTROLLER-03` — paired outcome comparison
- `ELMOS_AI_ONLINE_SHADOW_EVAL_CONTROLLER-04` — privacy redaction
- `ELMOS_AI_ONLINE_SHADOW_EVAL_CONTROLLER-05` — promotion threshold
- `ELMOS_AI_ONLINE_SHADOW_EVAL_CONTROLLER-06` — rollback on regression

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

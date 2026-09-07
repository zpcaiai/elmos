# Implementation Guide — Prompt Registry and Experiment Controller

## Purpose

Operate prompt registries, controlled experiments, review gates, canaries, rollback and evidence-based promotion without bypassing canonical Prompt Program IR.

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

1. Immutable prompt versions and aliases
2. Experiment assignment and guardrails
3. Offline and online paired evaluation
4. Approval and staged promotion
5. Rollback and evidence invalidation

## Native acceptance corpus

- `ELMOS_PROMPT_REGISTRY_EXPERIMENT_CONTROLLER-01` — version immutability
- `ELMOS_PROMPT_REGISTRY_EXPERIMENT_CONTROLLER-02` — A/B assignment
- `ELMOS_PROMPT_REGISTRY_EXPERIMENT_CONTROLLER-03` — holdout comparison
- `ELMOS_PROMPT_REGISTRY_EXPERIMENT_CONTROLLER-04` — failed promotion block
- `ELMOS_PROMPT_REGISTRY_EXPERIMENT_CONTROLLER-05` — canary rollback
- `ELMOS_PROMPT_REGISTRY_EXPERIMENT_CONTROLLER-06` — alias drift detection

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

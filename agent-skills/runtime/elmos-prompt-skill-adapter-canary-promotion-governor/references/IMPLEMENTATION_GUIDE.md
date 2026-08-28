# Implementation Guide — Prompt, Skill and Adapter Canary Promotion Governor

## Purpose

Stage behavioral configuration changes through offline, shadow, canary and broad rollout with exact version, metrics and rollback.

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

1. freeze candidate prompt/skill/adapter bundle
2. run holdout and negative activation tests
3. shadow without side effects
4. canary by tenant/risk cohort
5. promote or rollback with evidence invalidation

## Native acceptance corpus

- `ELMOS_PROMPT_SKILL_ADAPTER_CANARY_PROMOTION_GOVERNOR-01` — native scenario: freeze candidate prompt/skill/adapter bundle
- `ELMOS_PROMPT_SKILL_ADAPTER_CANARY_PROMOTION_GOVERNOR-02` — native scenario: run holdout and negative activation tests
- `ELMOS_PROMPT_SKILL_ADAPTER_CANARY_PROMOTION_GOVERNOR-03` — native scenario: shadow without side effects
- `ELMOS_PROMPT_SKILL_ADAPTER_CANARY_PROMOTION_GOVERNOR-04` — native scenario: canary by tenant/risk cohort
- `ELMOS_PROMPT_SKILL_ADAPTER_CANARY_PROMOTION_GOVERNOR-05` — native scenario: promote or rollback with evidence invalidation

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

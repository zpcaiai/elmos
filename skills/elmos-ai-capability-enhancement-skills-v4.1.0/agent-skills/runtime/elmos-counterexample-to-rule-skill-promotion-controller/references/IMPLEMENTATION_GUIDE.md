# Implementation Guide — Counterexample-to-Rule and Skill Promotion Controller

## Purpose

Turn verified recurring counterexamples into deterministic rules, tests, Skills or adapter improvements through isolated review, canary and rollback.

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

1. cluster recurring verified root causes
2. choose rule/test/skill/adapter intervention
3. generate bounded candidate and fixtures
4. run holdout, adversarial and canary evaluation
5. promote with signer, owner and rollback

## Native acceptance corpus

- `ELMOS_COUNTEREXAMPLE_TO_RULE_SKILL_PROMOTION_CONTROLLER-01` — native scenario: cluster recurring verified root causes
- `ELMOS_COUNTEREXAMPLE_TO_RULE_SKILL_PROMOTION_CONTROLLER-02` — native scenario: choose rule/test/skill/adapter intervention
- `ELMOS_COUNTEREXAMPLE_TO_RULE_SKILL_PROMOTION_CONTROLLER-03` — native scenario: generate bounded candidate and fixtures
- `ELMOS_COUNTEREXAMPLE_TO_RULE_SKILL_PROMOTION_CONTROLLER-04` — native scenario: run holdout, adversarial and canary evaluation
- `ELMOS_COUNTEREXAMPLE_TO_RULE_SKILL_PROMOTION_CONTROLLER-05` — native scenario: promote with signer, owner and rollback

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

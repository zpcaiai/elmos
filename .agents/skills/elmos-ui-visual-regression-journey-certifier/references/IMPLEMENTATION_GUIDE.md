# Implementation Guide — UI Visual Regression and Journey Certifier

## Purpose

Certify generated web, desktop and agent UI through visual diffs, semantic journeys, responsive layouts, accessibility and cross-browser behavior.

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

1. derive journeys from observable contracts
2. capture stable visual baselines and masks
3. verify responsive and theme variants
4. combine DOM/accessibility and screenshot oracles
5. test error, recovery and approval UX

## Native acceptance corpus

- `ELMOS_UI_VISUAL_REGRESSION_JOURNEY_CERTIFIER-01` — native scenario: derive journeys from observable contracts
- `ELMOS_UI_VISUAL_REGRESSION_JOURNEY_CERTIFIER-02` — native scenario: capture stable visual baselines and masks
- `ELMOS_UI_VISUAL_REGRESSION_JOURNEY_CERTIFIER-03` — native scenario: verify responsive and theme variants
- `ELMOS_UI_VISUAL_REGRESSION_JOURNEY_CERTIFIER-04` — native scenario: combine DOM/accessibility and screenshot oracles
- `ELMOS_UI_VISUAL_REGRESSION_JOURNEY_CERTIFIER-05` — native scenario: test error, recovery and approval UX

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

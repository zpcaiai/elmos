# Implementation Guide — Customer Holdout Acceptance Controller

## Purpose

Govern hidden customer scenarios, independent labels, contamination controls, execution, review and cryptographic acceptance for commercial Golden Routes.

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

1. Separate holdout custody from implementers
2. Hash and freeze scenarios before candidate release
3. Run in approved customer-equivalent environment
4. Capture authorized acceptance/rejection and conditions
5. Prevent holdout reuse as development data

## Native acceptance corpus

- `ELMOS_CUSTOMER_HOLDOUT_ACCEPTANCE_CONTROLLER-01` — hidden functional scenario
- `ELMOS_CUSTOMER_HOLDOUT_ACCEPTANCE_CONTROLLER-02` — hidden security scenario
- `ELMOS_CUSTOMER_HOLDOUT_ACCEPTANCE_CONTROLLER-03` — hidden recovery scenario
- `ELMOS_CUSTOMER_HOLDOUT_ACCEPTANCE_CONTROLLER-04` — contamination detection
- `ELMOS_CUSTOMER_HOLDOUT_ACCEPTANCE_CONTROLLER-05` — authorized customer signoff
- `ELMOS_CUSTOMER_HOLDOUT_ACCEPTANCE_CONTROLLER-06` — conditional acceptance expiry

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

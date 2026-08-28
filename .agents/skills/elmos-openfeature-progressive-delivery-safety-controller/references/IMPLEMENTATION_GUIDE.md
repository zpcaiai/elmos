# Implementation Guide — OpenFeature Progressive Delivery Safety Controller

## Purpose

Generate and govern feature-flag evaluation, targeting, exposure, shadow, canary, rollback and kill-switch controls for generated AI systems.

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

1. compile provider-neutral flag and context contracts
2. bind flag state to exact artifact and policy digests
3. enforce tenant/risk cohort targeting
4. record exposure and guardrail evidence
5. rollback atomically across model, prompt, cache and workflow

## Native acceptance corpus

- `ELMOS_OPENFEATURE_PROGRESSIVE_DELIVERY_SAFETY_CONTROLLER-01` — native scenario: compile provider-neutral flag and context contracts
- `ELMOS_OPENFEATURE_PROGRESSIVE_DELIVERY_SAFETY_CONTROLLER-02` — native scenario: bind flag state to exact artifact and policy digests
- `ELMOS_OPENFEATURE_PROGRESSIVE_DELIVERY_SAFETY_CONTROLLER-03` — native scenario: enforce tenant/risk cohort targeting
- `ELMOS_OPENFEATURE_PROGRESSIVE_DELIVERY_SAFETY_CONTROLLER-04` — native scenario: record exposure and guardrail evidence
- `ELMOS_OPENFEATURE_PROGRESSIVE_DELIVERY_SAFETY_CONTROLLER-05` — native scenario: rollback atomically across model, prompt, cache and workflow

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

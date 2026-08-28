# Implementation Guide — AI Model Provider Availability and Resilience Controller

## Purpose

Control provider health, regional routing, retries, hedging, fallback, rate limits and circuit breakers while preserving capability and data-policy constraints.

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

1. Provider health and rate-limit state
2. Capability/policy-aware fallback
3. Retry/hedge/circuit-breaker bounds
4. Region and data-residency enforcement
5. Recovery and brownout modes

## Native acceptance corpus

- `ELMOS_AI_MODEL_PROVIDER_AVAILABILITY_RESILIENCE_CONTROLLER-01` — healthy route
- `ELMOS_AI_MODEL_PROVIDER_AVAILABILITY_RESILIENCE_CONTROLLER-02` — rate limit fallback
- `ELMOS_AI_MODEL_PROVIDER_AVAILABILITY_RESILIENCE_CONTROLLER-03` — region constraint
- `ELMOS_AI_MODEL_PROVIDER_AVAILABILITY_RESILIENCE_CONTROLLER-04` — capability mismatch block
- `ELMOS_AI_MODEL_PROVIDER_AVAILABILITY_RESILIENCE_CONTROLLER-05` — circuit breaker
- `ELMOS_AI_MODEL_PROVIDER_AVAILABILITY_RESILIENCE_CONTROLLER-06` — provider recovery

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.

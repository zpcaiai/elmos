---
name: elmos-risk-classifier
version: 1.0.0
description: Classify blast radius and semantic risk for security, auth, data migration, concurrency, money, public APIs and infrastructure.
---

# Risk Classifier

Classify blast radius and semantic risk for security, auth, data migration, concurrency, money, public APIs and infrastructure.

## Trigger conditions
- before model routing

## Inputs
- `task`
- `impact map`

## Outputs
- `risk vector`
- `minimum model tier`
- `required gates`

## Procedure
1. Evaluate security/privacy/auth.
2. Evaluate irreversible data/state mutation.
3. Evaluate concurrency/idempotency.
4. Evaluate public contract compatibility.
5. Evaluate blast radius and rollback difficulty.
6. Emit mandatory promotion and review gates.

## Guardrails
- High-risk gates cannot be downgraded by cost pressure.

## Acceptance criteria
- minimum tier and validation gates determined

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

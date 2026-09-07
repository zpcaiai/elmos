---
name: elmos-integration-edge-planner
version: 2.0.0
description: Plan validated handoffs and integration checkpoints at dependency edges so bad outputs cannot silently propagate downstream.
---

# Integration Edge Planner

Treat dependency edges as executable contracts, not just arrows.

## Inputs
- task DAG
- boundary contracts
- proof obligations

## Outputs
- `edge handoff contracts`
- `edge validators`
- `integration checkpoints`

## Procedure
1. For each dependency edge, declare producer artifact, consumer expectation, compatibility range and verifier.
2. Place a checkpoint before fan-out from risky shared contracts.
3. Validate generated types, schemas, stubs and fixtures before unlocking downstream tasks.
4. Group tightly coupled edges into a boundary cluster with one integration gate.
5. Block propagation of failed or ambiguous handoffs.

## Guardrails
- A task status of `passed` does not unlock consumers until its outgoing handoffs are validated.

## Acceptance criteria
- every nontrivial edge has a machine-checkable or explicitly reviewed handoff

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

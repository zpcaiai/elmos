---
name: elmos-contract-boundary-generator
version: 1.0.0
description: Define stable interfaces between tasks so cheap workers can implement leaves without needing whole-repository context.
---

# Boundary Contract Generator

Define stable interfaces between tasks so cheap workers can implement leaves without needing whole-repository context.

## Trigger conditions
- DAG contains cross-task boundaries

## Inputs
- `tasks`
- `architecture index`

## Outputs
- `interface contracts`
- `fixtures/stubs`
- `compatibility rules`

## Procedure
1. Specify inputs/outputs, schemas, errors and invariants.
2. Generate or identify compile-time contracts where possible.
3. Create fixtures/stubs for downstream parallelism.
4. Mark compatibility expectations.

## Guardrails
- Contract changes affecting public APIs require elevated review tier.

## Acceptance criteria
- downstream task can execute from contract without hidden assumptions

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

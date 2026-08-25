---
name: elmos-integration-manager
version: 1.0.0
description: Merge passed task patches into a dedicated integration branch in dependency order and keep evidence attached.
---

# Patch Integration Manager

Merge passed task patches into a dedicated integration branch in dependency order and keep evidence attached.

## Trigger conditions
- task passed local gates/review

## Inputs
- `task branches`
- `DAG`
- `integration branch`

## Outputs
- `integrated commit(s)`
- `integration log`

## Procedure
1. Integrate by topological order.
2. Run affected smoke/build checks after each risky merge.
3. Record commit mapping task->SHA.
4. Pause dependent waves if integration changes contracts.

## Guardrails
- Never squash away evidence mapping unless mapping retained.

## Acceptance criteria
- integration branch contains only approved task diffs

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

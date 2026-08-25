---
name: elmos-task-dag-builder
version: 1.0.0
description: Create an acyclic dependency graph, identify critical path, parallel waves and path-lock conflicts.
---

# Task DAG Builder

Create an acyclic dependency graph, identify critical path, parallel waves and path-lock conflicts.

## Trigger conditions
- validated task set

## Inputs
- `tasks`

## Outputs
- `DAG`
- `waves`
- `critical path`
- `path lock plan`

## Procedure
1. Derive dependency edges from contracts, generated artifacts and path overlap.
2. Topologically sort.
3. Group ready tasks into waves with non-overlapping write ownership.
4. Identify critical path for ETA.
5. Reject cycles and ambiguous ownership.

## Guardrails
- No concurrent tasks may own overlapping paths unless declared merge-safe.

## Acceptance criteria
- DAG acyclic
- all tasks reachable or explicitly independent
- waves obey locks

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

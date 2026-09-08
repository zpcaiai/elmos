---
name: elmos-integration-manager
version: 2.0.0
description: Integrate validated task outputs by boundary cluster while checking semantic conflicts and contract/proof obligations at each checkpoint.
---

# Patch Integration Manager v2

Integrate patches as a sequence of validated semantic checkpoints, not merely git merges.

## Inputs
- `task worktrees/branches`
- `typed DAG`
- `edge handoffs`
- `integration checkpoint plan`

## Outputs
- `integrated commits`
- `integration evidence`
- `semantic conflict findings`

## Procedure
1. Integrate in dependency/boundary-cluster order.
2. Validate outgoing handoff artifacts before unlocking consumer patches.
3. Invoke semantic conflict detection for patches sharing symbols, schemas, state or scenarios even if git reports no conflict.
4. Run checkpoint proof obligations and affected baseline comparisons after risky shared changes.
5. Record task->commit->plan revision mapping.
6. If integration changes a contract or reveals new impact, stop dependents and trigger dynamic replan.

## Guardrails
- Never treat clean textual merge as semantic compatibility evidence.

## Acceptance criteria
- integration branch contains only approved diffs with checkpoint evidence

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

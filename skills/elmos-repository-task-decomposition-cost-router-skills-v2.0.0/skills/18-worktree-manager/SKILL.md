---
name: elmos-worktree-manager
version: 1.0.0
description: Create disposable git branches/worktrees per task and preserve user/integration state.
---

# Isolated Worktree Manager

Create disposable git branches/worktrees per task and preserve user/integration state.

## Trigger conditions
- task dispatched

## Inputs
- `repo root`
- `task id`
- `base commit`

## Outputs
- `worktree path`
- `task branch`

## Procedure
1. Verify clean base snapshot reference.
2. Create task branch/worktree.
3. Copy only required local non-git runtime metadata when policy allows.
4. Record base SHA.
5. Clean up only after evidence and patch are persisted.

## Guardrails
- Never delete user branches/worktrees.
- Never run destructive git reset on user workspace.

## Acceptance criteria
- task patch is attributable to base SHA

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

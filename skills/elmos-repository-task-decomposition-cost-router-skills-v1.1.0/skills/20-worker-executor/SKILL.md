---
name: elmos-worker-executor
version: 1.1.0
description: Execute an atomic task with the routed model, tool access and bounded attempts, producing a patch and evidence.
---

# Atomic Worker Executor

Execute an atomic task with the routed model, tool access and bounded attempts, producing a patch and evidence.

## Trigger conditions
- task dispatched

## Inputs
- `worker prompt`
- `worktree`
- `model alias`
- `model_selection`

## Outputs
- `patch`
- `execution record`
- `worker evidence`

## Procedure
1. Resolve alias through model-selection controller and registry guard; verify it matches the effective Smart/manual policy.
2. Invoke configured provider/CLI adapter.
3. Allow repository tools only inside worktree.
4. Capture commands, diffs and model usage.
5. Stop on forbidden write or hard budget.

## Guardrails
- No direct integration-branch write.
- No model outside allowlist.
- No primary-model substitution in manual strict mode.

## Acceptance criteria
- patch exists or failure classified
- execution record complete

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

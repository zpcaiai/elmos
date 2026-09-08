---
name: elmos-deterministic-validator
version: 1.0.0
description: Use build tools, compilers, linters and tests as the cheapest first-line judge of a worker patch.
---

# Deterministic Validator

Use build tools, compilers, linters and tests as the cheapest first-line judge of a worker patch.

## Trigger conditions
- worker patch produced

## Inputs
- `task`
- `worktree`
- `gate config`

## Outputs
- `validation evidence`
- `failure signals`

## Procedure
1. Run cheapest/high-signal checks first.
2. Run task-local tests and type/build gates.
3. Capture exit codes and minimal logs.
4. Run conditional gates triggered by risk.

## Guardrails
- Never treat model self-review as substitute for executable validation.

## Acceptance criteria
- all required local gates have explicit pass/fail/skip reason

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

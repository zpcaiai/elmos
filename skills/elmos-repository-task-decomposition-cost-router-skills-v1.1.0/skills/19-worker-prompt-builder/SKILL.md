---
name: elmos-worker-prompt-builder
version: 1.0.0
description: Generate constrained execution prompts that make lower-cost models reliable on atomic repository tasks.
---

# Worker Prompt Builder

Generate constrained execution prompts that make lower-cost models reliable on atomic repository tasks.

## Trigger conditions
- before model invocation

## Inputs
- `task`
- `context pack`
- `contracts`
- `validation commands`

## Outputs
- `worker prompt`

## Procedure
1. State single objective and non-goals.
2. List owned/read/forbidden paths.
3. Include exact acceptance commands.
4. Require minimal diff and no unrelated refactors.
5. Require worker to run deterministic checks and return evidence/patch summary.

## Guardrails
- Never expose secrets.
- Never ask worker to bypass tests or permissions.

## Acceptance criteria
- prompt is executable without ambiguous scope

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

---
name: elmos-conflict-resolver
version: 1.0.0
description: Resolve merge conflicts using task contracts and repository invariants, not textual preference.
---

# Semantic Conflict Resolver

Resolve merge conflicts using task contracts and repository invariants, not textual preference.

## Trigger conditions
- integration conflict

## Inputs
- `conflicting patches`
- `task contracts`
- `architecture index`

## Outputs
- `resolved patch`
- `conflict evidence`

## Procedure
1. Identify semantic owners.
2. Reconcile contracts before code.
3. Prefer minimal combined behavior.
4. Rerun both tasks acceptance tests.
5. Escalate architecture-level conflict to L3.

## Guardrails
- No automatic choose-ours/theirs on semantic files.

## Acceptance criteria
- both task intents preserved or explicit supersession recorded

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

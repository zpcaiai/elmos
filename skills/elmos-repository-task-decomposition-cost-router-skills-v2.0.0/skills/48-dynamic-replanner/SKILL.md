---
name: elmos-dynamic-replanner
version: 2.0.0
description: Apply bounded local or global graph edits when runtime evidence invalidates the original plan.
---

# Dynamic Replanner

Make the plan an evolving executable hypothesis.

## Inputs
- current plan/DAG
- run-state journal
- validation failures
- discovered graph changes

## Outputs
- `plan revision`
- `preserved evidence set`
- `invalidated tasks`
- `new refinement frontier`

## Replan triggers
- repeated same failure
- unexpected impacted path
- new dependency edge
- invariant violation
- contract change
- integration conflict
- verifier failure outside predicted surface
- missing context or tool requirement

## Procedure
1. Classify trigger as local node, boundary cluster or global-plan invalidation.
2. Prefer the smallest graph edit that restores executability.
3. Preserve passed evidence whose assumptions remain valid.
4. Invalidate only descendants or peers affected by changed contracts/invariants.
5. Re-run graph verifier and budget/ETA/model routing for changed nodes.
6. Cap replans and escalate when repeated plan instability indicates requirement/architecture misunderstanding.

## Guardrails
- Never rewrite plan history in place; append a revision.

## Acceptance criteria
- every replan identifies trigger, changed assumptions and invalidated evidence

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

---
name: elmos-uncertainty-exploration-planner
version: 2.0.0
description: Create bounded read-only or disposable probe tasks to resolve uncertain repository behavior before costly implementation.
---

# Uncertainty & Exploration Planner

Use cheap probes to reduce uncertainty before committing to a plan.

## Inputs
- ambiguity ledger
- impact confidence
- unknown graph edges
- high-risk plan nodes

## Outputs
- `exploration tasks`
- `expected information gain`
- `replan triggers`

## Procedure
1. Identify uncertainties that materially change architecture, scope, risk or model routing.
2. Prefer read-only inspection, targeted test runs, executable probes, trace capture and minimal throwaway patches.
3. Estimate information gain versus exploration cost.
4. Run the smallest probe that can discriminate between competing plan hypotheses.
5. Write findings into the graph and trigger local replan.

## Guardrails
- Exploration tasks may not silently become production implementation.
- Bound exploration spend by policy.

## Acceptance criteria
- each probe has a decision it is intended to resolve
- findings update downstream planning state

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

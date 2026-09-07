---
name: elmos-adaptive-hierarchical-planner
version: 2.0.0
description: Create a coarse-to-fine hierarchical plan and refine only branches whose complexity, uncertainty or readiness justify more detail.
---

# Adaptive Hierarchical Planner

Replace fixed-granularity decomposition with progressive refinement.

## Hierarchy
`goal -> capability -> changeset -> atomic_task -> microstep`

## Inputs
- requirement/scenario graph
- repository intelligence graph
- invariant ledger
- semantic seams
- impact map

## Outputs
- `hierarchical plan`
- `refinement frontier`
- `task candidates`
- `plan confidence`

## Procedure
1. Start with a small capability-level macro plan that covers all acceptance scenarios.
2. Refine only the next executable or high-risk branches; leave distant branches coarse.
3. At each refinement, minimize cross-boundary coupling while preserving scenario and invariant ownership.
4. Stop refinement when a node is independently executable, context-bounded and locally verifiable.
5. Allow microsteps only inside one worker context; do not schedule microsteps globally unless needed for recovery.
6. Recompute refinement frontier after execution evidence or repository discoveries.

## Guardrails
- Do not fully expand a large plan at run start merely for completeness.
- Do not make every node equally fine-grained.

## Acceptance criteria
- plan covers all scenarios without forced full-depth expansion
- every executable leaf satisfies the current granularity policy
- coarse nodes retain enough contract information for future refinement

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

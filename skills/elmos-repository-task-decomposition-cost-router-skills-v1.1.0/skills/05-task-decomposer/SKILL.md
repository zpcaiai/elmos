---
name: elmos-task-decomposer
version: 1.0.0
description: Split the impacted work into low-complexity, independently testable tasks while preserving repository-level semantics.
---

# Atomic Task Decomposer

Split the impacted work into low-complexity, independently testable tasks while preserving repository-level semantics.

## Trigger conditions
- impact map ready

## Inputs
- `requirement spec`
- `impact map`
- `architecture index`

## Outputs
- `atomic task candidates`

## Procedure
1. Prefer tasks that produce one coherent code/test/config outcome.
2. Keep each task within a small bounded write surface.
3. Separate contract changes from implementations when it enables safe parallelism.
4. Extract migrations and shared types before dependents.
5. Create explicit integration tasks where cross-module behavior cannot be validated locally.

## Guardrails
- Do not split transactional invariants across independently mergeable tasks.
- Do not split solely to make task count larger.

## Acceptance criteria
- each task has one objective
- each task has local acceptance evidence
- cross-task invariants explicitly represented

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

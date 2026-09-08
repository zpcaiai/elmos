---
name: elmos-task-dag-builder
version: 2.0.0
description: Compile the current hierarchical plan frontier into a typed execution DAG with contracts, proof edges, locks and integration barriers.
---

# Typed Task DAG Builder v2

Compile executable leaves into a dependency graph whose edges carry semantics.

## Inputs
- `validated leaves`
- `hierarchical plan`
- `boundary contracts`
- `proof obligations`

## Outputs
- `typed DAG`
- `edge contracts`
- `path/resource locks`
- `integration barriers`
- `critical path seed`

## Procedure
1. Derive edges from artifact production/consumption, contract dependencies, data/schema ordering, path locks and proof prerequisites.
2. Type each edge (`data`, `contract`, `schema`, `build`, `runtime`, `verification`, `integration`).
3. Attach producer artifact, consumer expectation and edge validator.
4. Topologically sort and reject cycles or ambiguous ownership.
5. Insert integration barriers before unsafe fan-out and after high-risk shared changes.
6. Group ready nodes only after incoming handoffs are validated.
7. Pass graph to `elmos-plan-graph-verifier` before scheduling.

## Guardrails
- An arrow without a handoff contract is insufficient for nontrivial cross-task dependency.

## Acceptance criteria
- DAG is acyclic, typed, acceptance-complete and edge-validatable

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

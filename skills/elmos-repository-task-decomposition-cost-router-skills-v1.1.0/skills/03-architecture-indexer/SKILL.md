---
name: elmos-architecture-indexer
version: 1.0.0
description: Build a compact architecture index optimized for downstream task planning and context slicing.
---

# Architecture Indexer

Build a compact architecture index optimized for downstream task planning and context slicing.

## Trigger conditions
- repo intake complete

## Inputs
- `repo profile`
- `source tree`

## Outputs
- `component index`
- `dependency edges`
- `entry-point map`
- `data-flow hints`

## Procedure
1. Identify public interfaces and module boundaries.
2. Map static dependency edges.
3. Identify persistence, messaging, external APIs and shared domain types.
4. Record high-centrality files and architectural invariants.

## Guardrails
- Prefer structural summaries over dumping entire files.

## Acceptance criteria
- major modules and cross-boundary dependencies represented

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

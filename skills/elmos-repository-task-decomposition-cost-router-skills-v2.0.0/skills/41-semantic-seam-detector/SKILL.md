---
name: elmos-semantic-seam-detector
version: 2.0.0
description: Find safe decomposition boundaries using architecture seams, contracts, ownership, data-flow cuts and verification locality.
---

# Semantic Seam Detector

Find boundaries where work can be split with minimal coordination cost.

## Inputs
- repository intelligence graph
- invariant ledger
- scenario graph

## Outputs
- `candidate seams`
- `unsafe seams`
- `coupling score`
- `recommended change clusters`

## Procedure
1. Locate explicit interfaces, modules, adapters, ports, schemas, generated clients and testable boundaries.
2. Penalize cuts through transactions, shared mutable state, tightly coupled call/data cycles and migration compatibility windows.
3. Score seams by semantic cohesion, cross-edge count, contract stability and verification locality.
4. Identify bridge seams where a stub/fixture can unlock safe parallelism.
5. Feed recommended clusters into hierarchical planner and granularity controller.

## Guardrails
- A directory boundary is not automatically a semantic seam.

## Acceptance criteria
- proposed split points minimize hidden cross-task assumptions
- unsafe splits carry explicit reasons

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

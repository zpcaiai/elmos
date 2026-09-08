---
name: elmos-architecture-indexer
version: 2.0.0
description: Produce a compact architecture view and seed the evidence-backed Repository Intelligence Graph used by adaptive planning.
---

# Architecture Indexer v2

Recover the repository's architectural language before task decomposition.

## Inputs
- `repo profile`
- `source/build/test tree`

## Outputs
- `component index`
- `entry-point map`
- `architecture conventions`
- `RIG seed`

## Procedure
1. Identify modules, boundaries, public interfaces, adapters, domain cores and generated surfaces.
2. Recover build/test entry points, deployable units and package-manager/build-tool relationships.
3. Identify persistence, messaging, external APIs, shared domain types and config surfaces.
4. Record architecture conventions from sibling implementations and repeated patterns.
5. Mark high-centrality nodes, ownership ambiguity and suspected architectural seams.
6. Delegate full typed graph construction to `elmos-repository-intelligence-graph`.

## Guardrails
- Prefer structural summaries and exact evidence pointers over large source dumps.

## Acceptance criteria
- major modules and build/test/runtime boundaries are represented
- downstream RIG construction has evidence anchors

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

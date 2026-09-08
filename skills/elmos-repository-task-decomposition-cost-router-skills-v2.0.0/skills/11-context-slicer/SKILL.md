---
name: elmos-context-slicer
version: 2.0.0
description: Build graph-derived, task-specific context packs that include contracts/invariants/proof obligations while minimizing unrelated repository content.
---

# Graph-Aware Context Slicer v2

Provide the smallest sufficient context for a worker without hiding boundary assumptions.

## Inputs
- `task`
- `repository intelligence graph`
- `scenario links`
- `invariant/contract/proof links`

## Outputs
- `context pack manifest`
- `context provenance graph`
- `cache key`

## Procedure
1. Start from task-owned symbols/paths and traverse only required typed dependency edges.
2. Include incoming/outgoing contracts, scenario slice, invariants, proof obligations and nearby tests.
3. Include sibling examples when they encode repository conventions.
4. Summarize distant dependencies while preserving exact signatures/schemas where required.
5. Attach acceptance commands, baseline evidence and forbidden paths.
6. Hash stable context segments separately to maximize cache reuse across sibling tasks.
7. If worker discovers a missing required edge, treat it as a replan signal rather than repeatedly expanding context blindly.

## Guardrails
- Do not omit critical invariants to save tokens.

## Acceptance criteria
- context is sufficient, provenance-backed and cache-segmented

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

---
name: elmos-context-slicer
version: 1.0.0
description: Build the smallest sufficient context pack for each atomic task to reduce token cost and context dilution.
---

# Context Slicer

Build the smallest sufficient context pack for each atomic task to reduce token cost and context dilution.

## Trigger conditions
- task ready for routing

## Inputs
- `task`
- `architecture index`
- `repo`

## Outputs
- `context pack manifest`

## Procedure
1. Include task contract, owned/read paths and nearby tests.
2. Include only transitive definitions required to compile/reason.
3. Summarize rather than paste large unrelated modules.
4. Attach acceptance commands and forbidden paths.
5. Hash pack for cache reuse.

## Guardrails
- Do not omit architectural invariants referenced by risk classifier.

## Acceptance criteria
- worker can execute without whole-repo dump
- context pack has provenance

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

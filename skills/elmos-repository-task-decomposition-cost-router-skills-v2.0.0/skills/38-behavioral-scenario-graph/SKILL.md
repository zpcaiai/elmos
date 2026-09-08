---
name: elmos-behavioral-scenario-graph
version: 2.0.0
description: Convert requirements into end-to-end behavioral scenarios and map each scenario to repository surfaces and proof obligations.
---

# Behavioral Scenario Graph

Represent the request as user-visible and system-visible behavior before decomposing by files.

## Inputs
- `requirement spec`
- `implicit requirement set`
- `repository intelligence graph`

## Outputs
- `scenario graph`
- `scenario-to-component map`
- `scenario-to-proof map`

## Procedure
1. Create happy-path, failure-path, boundary, compatibility and rollback scenarios.
2. Model each scenario as ordered observable states/events, not prose-only intentions.
3. Link each step to API, domain, persistence, messaging, UI, infra and test surfaces.
4. Identify shared scenario prefixes/suffixes and cross-cutting invariants.
5. Mark scenarios that require end-to-end or integration verification.
6. Require every atomic task to claim which scenario steps it advances.

## Guardrails
- File ownership alone is not a valid decomposition axis.
- A scenario may cross many modules; preserve its semantic chain in the plan graph.

## Acceptance criteria
- every acceptance criterion is covered by one or more scenarios
- every scenario has an observable verifier path or an explicit verification gap

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

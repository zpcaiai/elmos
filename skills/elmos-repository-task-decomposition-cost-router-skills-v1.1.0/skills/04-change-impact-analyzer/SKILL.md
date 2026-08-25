---
name: elmos-change-impact-analyzer
version: 1.0.0
description: Estimate blast radius of the normalized requirement across code, schema, API, tests, infra and documentation.
---

# Change Impact Analyzer

Estimate blast radius of the normalized requirement across code, schema, API, tests, infra and documentation.

## Trigger conditions
- normalized requirement + architecture index

## Inputs
- `requirement spec`
- `architecture index`

## Outputs
- `impact map`
- `risk triggers`
- `candidate write/read paths`

## Procedure
1. Trace each acceptance scenario to likely components.
2. Separate direct changes from transitive validation impact.
3. Flag API/schema/security/concurrency/migration triggers.
4. Estimate affected test surfaces.

## Guardrails
- Treat uncertain high-impact paths conservatively.

## Acceptance criteria
- all acceptance scenarios have candidate impact paths
- risk triggers emitted

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

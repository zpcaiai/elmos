---
name: elmos-model-capability-profiler
version: 1.0.0
description: Maintain task-class-specific priors and telemetry posteriors for the ten allowed models.
---

# Model Capability Profiler

Maintain task-class-specific priors and telemetry posteriors for the ten allowed models.

## Trigger conditions
- router evaluation
- telemetry update

## Inputs
- `model registry`
- `historical execution records`

## Outputs
- `capability matrix`
- `success probability estimates`

## Procedure
1. Seed by role hints, not marketing claims.
2. Compute per-task-class success/quality/latency distributions from Elmos runs.
3. Use Bayesian/shrunk estimates for low-sample models.
4. Track context-length and repository-size effects.

## Guardrails
- Do not overfit from fewer than configured samples.

## Acceptance criteria
- every eligible model has a usable prior/posterior

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

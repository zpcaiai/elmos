---
name: elmos-repository-orchestrator
version: 1.1.0
description: Own the entire repository-level requirement from intake through certification and resume an interrupted run without losing completed work.
---

# Repository Orchestrator

Own the entire repository-level requirement from intake through certification and resume an interrupted run without losing completed work.

## Trigger conditions
- medium/large repository feature
- multi-module change
- migration/refactor
- request explicitly asks for complete repository-level implementation

## Inputs
- `requirement`
- `repository root`
- `budget policy`
- `model registry`
- `model_selection` (Smart or manual, validated by `elmos-model-selection-controller`)

## Outputs
- `run manifest`
- `task DAG`
- `integrated patch`
- `certification report`

## Procedure
1. Create run_id and durable run directory.
2. Resolve and persist Smart/manual model selection before dispatch.
3. Invoke repo intake, architecture index and impact analysis.
4. Decompose into atomic tasks and validate DAG.
5. Route and execute ready waves under model-selection constraints, budget and path locks.
6. Integrate passed tasks, rerun affected gates, then full repository certification.
7. Persist every transition and support resume from last durable state.

## Guardrails
- Never bypass the 10-model allowlist.
- Never override a manual strict selection with a silent fallback.
- Never mark complete from worker self-report alone.
- Never allow parallel write overlap.
- Hard budget/security gates override throughput.

## Acceptance criteria
- all required tasks terminal
- repository final gates pass
- traceability matrix complete
- cost/runtime/model usage reported

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

---
name: elmos-repository-orchestrator
version: 2.0.0
description: Own a repository-level requirement through adaptive planning, execution, dynamic replanning, integration and final certification.
---

# Repository Orchestrator v2

Own the entire repository-level requirement from intake through certification while treating the plan as a versioned executable hypothesis.

## Trigger conditions
- medium/large repository feature
- multi-module change
- migration/refactor
- request asks for complete repository-level implementation

## Inputs
- `requirement`
- `repository root`
- `budget policy`
- `model registry`
- `model_selection`

## Outputs
- `run manifest`
- `scenario graph`
- `repository intelligence graph`
- `hierarchical plan + execution DAG`
- `integrated patch`
- `certification report`

## Procedure
1. Create run_id, durable run directory and baseline environment fingerprint.
2. Resolve/persist Smart or manual model selection policy.
3. Normalize explicit requirements, mine implicit requirements and build behavioral scenarios.
4. Build Repository Intelligence Graph, change impact map and invariant ledger.
5. Detect semantic seams and create a coarse-to-fine hierarchical plan.
6. Use granularity controller + plan graph verifier to produce executable leaves and validated handoffs.
7. Route ready leaves, schedule critical path/resource-safe waves and execute in isolated worktrees.
8. After every handoff/integration checkpoint, run proof obligations and affected regression.
9. When evidence invalidates assumptions, invoke bounded dynamic replanning instead of forcing the stale DAG forward.
10. Integrate accepted patches, detect semantic conflicts, run repository certification and write telemetry for both model routing and decomposition learning.

## Guardrails
- Never bypass the 10-model allowlist.
- Never override manual strict model selection with a silent fallback.
- Never mark completion from worker self-report alone.
- Never allow an unvalidated dependency edge to unlock downstream work.
- Preserve plan revision history; never mutate prior plan evidence in place.
- Hard security/data/compatibility/budget gates override throughput.

## Acceptance criteria
- all acceptance scenarios and critical invariants are covered by proof evidence
- every executable task references a plan revision and validated incoming contracts
- final repository gates pass
- traceability matrix, cost/runtime/model usage and replan history are reported

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

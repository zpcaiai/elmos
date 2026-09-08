---
name: "elmos-repository-orchestrator"
description: "Own a repository-level requirement through adaptive planning, execution, dynamic replanning, integration and final certification."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "2.0.0"
  source_version: "2.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/00-repository-orchestrator/SKILL.md"
  source_sha256: "sha256:4898ddb18ee1ae45a195cdb56b684fc934c373e91685bb8fd1d1aff50eb11022"
  namespace: "repository-task-router-v2"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "repository_orchestrator"
  canonical_owner: "canonical.elmos.durable-runtime"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/00-repository-orchestrator/SKILL.md` (`sha256:4898ddb18ee1ae45a195cdb56b684fc934c373e91685bb8fd1d1aff50eb11022`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/schemas/`.
- Repository-corrected contracts and the exact 54-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
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

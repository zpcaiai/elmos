---
name: "elmos-telemetry-learner"
description: "Learn actual Elmos cost/performance per model and task class so routing improves over time."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "1.1.0"
  source_version: "1.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/34-telemetry-learner/SKILL.md"
  source_sha256: "sha256:123422adb86dc28252395582e47bb11d7fea01ab748cd09214f79dfe1aedc266"
  namespace: "repository-task-router-v1"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "telemetry_learner"
  canonical_owner: "canonical.elmos.execution-intelligence"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/34-telemetry-learner/SKILL.md` (`sha256:123422adb86dc28252395582e47bb11d7fea01ab748cd09214f79dfe1aedc266`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/schemas/`.
- Repository-corrected contracts and the exact 37-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Model Telemetry Learner

Learn actual Elmos cost/performance per model and task class so routing improves over time.

## Trigger conditions
- task/certification completion

## Inputs
- `execution records`
- `validation outcomes`
- `review defects`

## Outputs
- `updated model metrics`

## Procedure
1. Record first-pass success, total attempts, token/cost, latency, defect escape, integration conflict and task class.
2. Separate provider outages from model capability failures.
3. Update posterior after minimum sample thresholds.
4. Decay stale performance data.

## Guardrails
- Do not optimize solely for cheapness; retain quality and defect-escape metrics.

## Acceptance criteria
- metrics are auditable and task-class-specific

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

---
name: "elmos-eta-estimator"
description: "Estimate machine wall-clock completion time for the Elmos run and update ETA from observed execution durations."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "1.1.0"
  source_version: "1.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/16-eta-estimator/SKILL.md"
  source_sha256: "sha256:db97bada0f2e77299557027eed9faf1338e2168c90f2e3305daa4d73779f11f2"
  namespace: "repository-task-router-v1"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "eta_estimator"
  canonical_owner: "canonical.elmos.execution-intelligence"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/16-eta-estimator/SKILL.md` (`sha256:db97bada0f2e77299557027eed9faf1338e2168c90f2e3305daa4d73779f11f2`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/schemas/`.
- Repository-corrected contracts and the exact 37-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Autonomous ETA Estimator

Estimate machine wall-clock completion time for the Elmos run and update ETA from observed execution durations.

## Trigger conditions
- DAG and model routes known

## Inputs
- `task durations priors`
- `concurrency`
- `critical path`

## Outputs
- `P50/P90 autonomous ETA`
- `optional human-effort comparison`

## Procedure
1. Estimate per-task tool/model duration.
2. Compute wave and critical-path runtime under concurrency limits.
3. Update posterior after every completed wave.
4. Report autonomous wall-clock separately from human comparison.

## Guardrails
- Never substitute person-days for system runtime ETA.

## Acceptance criteria
- ETA includes confidence range and dominant critical-path tasks

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

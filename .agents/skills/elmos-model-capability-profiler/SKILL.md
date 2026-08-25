---
name: "elmos-model-capability-profiler"
description: "Maintain task-class-specific priors and telemetry posteriors for the ten allowed models."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "1.1.0"
  source_version: "1.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/13-model-capability-profiler/SKILL.md"
  source_sha256: "sha256:5d95a6a2a57aca11355f538bad69732327406dc36af27d2c0c461fe6900bdb8a"
  namespace: "repository-task-router-v1"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "model_capability_profiler"
  canonical_owner: "canonical.elmos.model-gateway"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/13-model-capability-profiler/SKILL.md` (`sha256:5d95a6a2a57aca11355f538bad69732327406dc36af27d2c0c461fe6900bdb8a`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/schemas/`.
- Repository-corrected contracts and the exact 37-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
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

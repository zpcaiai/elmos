---
name: "elmos-model-registry-guard"
description: "Enforce the immutable set of ten allowed logical model aliases at planning, execution, retry and review time."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "1.1.0"
  source_version: "1.1.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/12-model-registry-guard/SKILL.md"
  source_sha256: "sha256:3bd387c83d0d1a34a4f24b1385e795c597ad011cf596361daab0097c165eab21"
  namespace: "repository-task-router-v1"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "model_registry_guard"
  canonical_owner: "canonical.elmos.model-gateway"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/12-model-registry-guard/SKILL.md` (`sha256:3bd387c83d0d1a34a4f24b1385e795c597ad011cf596361daab0097c165eab21`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/schemas/`.
- Repository-corrected contracts and the exact 37-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Model Registry Guard

Enforce the immutable set of ten allowed logical model aliases at planning, execution, retry and review time.

## Trigger conditions
- any model selection

## Inputs
- `model alias`
- `registry`
- `model_selection`

## Outputs
- `allow/deny decision`

## Procedure
1. Resolve logical alias.
2. Verify alias is allowed by the run model-selection policy (Smart candidate, manual selected model, permitted fallback, or required verifier).
3. Verify enabled flag.
4. Hard fail unknown alias.
5. Record resolved provider ID and selection provenance in execution record.

## Guardrails
- No dynamic fallback to unregistered models.

## Acceptance criteria
- all executed model aliases belong to hard allowlist

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

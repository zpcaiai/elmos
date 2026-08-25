---
name: "elmos-cost-performance-router"
description: "Choose the model with the lowest expected completed-task cost subject to quality, risk, budget and deadline constraints."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "1.1.0"
  source_version: "1.1.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/14-cost-performance-router/SKILL.md"
  source_sha256: "sha256:b1f8d50af1b06a569f49b0f04134d96260f8680aa0f11c5400cd306f7da356af"
  namespace: "repository-task-router-v1"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "cost_performance_router"
  canonical_owner: "canonical.elmos.model-gateway"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/14-cost-performance-router/SKILL.md` (`sha256:b1f8d50af1b06a569f49b0f04134d96260f8680aa0f11c5400cd306f7da356af`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/schemas/`.
- Repository-corrected contracts and the exact 37-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Cost/Performance Router

Choose the model with the lowest expected completed-task cost subject to quality, risk, budget and deadline constraints.

## Trigger conditions
- task complexity/risk/context ready

## Inputs
- `task profile`
- `capability matrix`
- `live/normalized pricing`
- `budget`
- `model_selection`

## Outputs
- `ranked model candidates`
- `chosen model`
- `routing explanation`

## Procedure
1. Resolve `model_selection` first.
2. If mode is `manual`, lock primary implementation to `selected_model`; validate hard compatibility and do not score-replace it.
3. If mode is `smart`, apply risk minimum tier, then score all eligible allowlisted models.
4. Estimate invocation cost from context/output/tool cycles.
5. Estimate p_success and escalation cost.
6. Add integration-risk and latency penalties.
7. Rank eligible models by route score.
8. Prefer cheaper model only when expected completion cost remains lower.
9. On manual fallback, switch only when `fallback_policy=smart_within_allowlist` and record the switch reason/evidence.

## Guardrails
- Never select outside allowlist.
- Never let missing pricing silently mean zero cost.
- Never silently override a manual strict model choice.
- Risk tiers constrain Smart routing; manual mode reports risk mismatch and relies on universal gates/verification unless the chosen model is technically incompatible.

## Acceptance criteria
- selection is reproducible from inputs
- runner records runner-up and reason

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

---
name: "elmos-retry-escalation-controller"
description: "Bound retries and escalate intelligently instead of repeatedly spending on a model that has hit its capability limit."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "1.1.0"
  source_version: "1.1.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/23-retry-escalation-controller/SKILL.md"
  source_sha256: "sha256:0cb2527b36ec7703374bd49c65673245e8ab3770c503fb1ad09e3f49b6cb710a"
  namespace: "repository-task-router-v1"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "retry_escalation_controller"
  canonical_owner: "canonical.elmos.durable-runtime"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/23-retry-escalation-controller/SKILL.md` (`sha256:0cb2527b36ec7703374bd49c65673245e8ab3770c503fb1ad09e3f49b6cb710a`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/schemas/`.
- Repository-corrected contracts and the exact 37-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Retry & Escalation Controller

Bound retries and escalate intelligently instead of repeatedly spending on a model that has hit its capability limit.

## Trigger conditions
- classified failure

## Inputs
- `task`
- `attempt history`
- `router policy`
- `model_selection`

## Outputs
- `next attempt plan or terminal stop`

## Procedure
1. Retry same model only for allowed failure classes and attempt count.
2. Reuse cached context/evidence.
3. In Smart mode, on semantic/integration failure reroute at a higher eligible tier; architecture/long-horizon rules may promote as configured.
4. In manual `strict` mode, never change the primary implementation model; return `model_reselection_required` when another model is necessary.
5. In manual `smart_within_allowlist` mode, classify failure and ask the cost/performance router for the best eligible fallback from the same ten-model allowlist.
6. Record every fallback with from/to model, failure class, reason and incremental cost estimate.

## Guardrails
- Max total attempts enforced.
- Do not hide repeated failures.
- Never promote outside the hard allowlist or bypass a manual strict selection.

## Acceptance criteria
- next action follows policy and preserves attempt history

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

---
name: "elmos-task-dag-builder"
description: "Create an acyclic dependency graph, identify critical path, parallel waves and path-lock conflicts."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "1.1.0"
  source_version: "1.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/07-task-dag-builder/SKILL.md"
  source_sha256: "sha256:c4b6058426bd52a0b73f28b6cbc86502d81ae3b03f69b97d82e0589bea11320d"
  namespace: "repository-task-router-v1"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "task_dag_builder"
  canonical_owner: "canonical.elmos.durable-runtime"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/07-task-dag-builder/SKILL.md` (`sha256:c4b6058426bd52a0b73f28b6cbc86502d81ae3b03f69b97d82e0589bea11320d`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/schemas/`.
- Repository-corrected contracts and the exact 37-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Task DAG Builder

Create an acyclic dependency graph, identify critical path, parallel waves and path-lock conflicts.

## Trigger conditions
- validated task set

## Inputs
- `tasks`

## Outputs
- `DAG`
- `waves`
- `critical path`
- `path lock plan`

## Procedure
1. Derive dependency edges from contracts, generated artifacts and path overlap.
2. Topologically sort.
3. Group ready tasks into waves with non-overlapping write ownership.
4. Identify critical path for ETA.
5. Reject cycles and ambiguous ownership.

## Guardrails
- No concurrent tasks may own overlapping paths unless declared merge-safe.

## Acceptance criteria
- DAG acyclic
- all tasks reachable or explicitly independent
- waves obey locks

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

---
name: "elmos-worktree-manager"
description: "Create disposable git branches/worktrees per task and preserve user/integration state."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "1.1.0"
  source_version: "1.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/18-worktree-manager/SKILL.md"
  source_sha256: "sha256:3c89bc2f958b411aa2b3416dc87cb5986223a601807360109e4b34c16a49a0ba"
  namespace: "repository-task-router-v1"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "worktree_manager"
  canonical_owner: "canonical.elmos.workspace-scm"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/18-worktree-manager/SKILL.md` (`sha256:3c89bc2f958b411aa2b3416dc87cb5986223a601807360109e4b34c16a49a0ba`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/schemas/`.
- Repository-corrected contracts and the exact 37-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Isolated Worktree Manager

Create disposable git branches/worktrees per task and preserve user/integration state.

## Trigger conditions
- task dispatched

## Inputs
- `repo root`
- `task id`
- `base commit`

## Outputs
- `worktree path`
- `task branch`

## Procedure
1. Verify clean base snapshot reference.
2. Create task branch/worktree.
3. Copy only required local non-git runtime metadata when policy allows.
4. Record base SHA.
5. Clean up only after evidence and patch are persisted.

## Guardrails
- Never delete user branches/worktrees.
- Never run destructive git reset on user workspace.

## Acceptance criteria
- task patch is attributable to base SHA

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

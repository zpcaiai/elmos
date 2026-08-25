---
name: "elmos-rollback-recovery"
description: "Recover from integration failures or interrupted sessions without losing validated work."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "1.1.0"
  source_version: "1.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/32-rollback-recovery/SKILL.md"
  source_sha256: "sha256:123d02f5c34a1e28eb5f45194cf3e8bdfcda67f5ad36f5d3c0dd2873a1e9e20a"
  namespace: "repository-task-router-v1"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "rollback_recovery"
  canonical_owner: "canonical.elmos.workspace-scm"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/32-rollback-recovery/SKILL.md` (`sha256:123d02f5c34a1e28eb5f45194cf3e8bdfcda67f5ad36f5d3c0dd2873a1e9e20a`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/schemas/`.
- Repository-corrected contracts and the exact 37-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Rollback & Recovery Manager

Recover from integration failures or interrupted sessions without losing validated work.

## Trigger conditions
- run interruption
- bad integration
- provider/network failure

## Inputs
- `run journal`
- `task branches`
- `integration log`

## Outputs
- `resumed state or rollback state`

## Procedure
1. Reconstruct state from durable journal.
2. Reuse passed tasks and cached context.
3. Rollback only integration commits attributable to failed wave.
4. Requeue unfinished tasks.
5. Verify repository integrity before resume.

## Guardrails
- Never discard unrelated user changes.

## Acceptance criteria
- resume point deterministic and repository consistent

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

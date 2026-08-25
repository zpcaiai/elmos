---
name: "elmos-worker-executor"
description: "Execute an atomic task with the routed model, tool access and bounded attempts, producing a patch and evidence."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "1.1.0"
  source_version: "1.1.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/20-worker-executor/SKILL.md"
  source_sha256: "sha256:5f40feba6802620b1466f02bf08ec6aeb5709dcb8bb02330210559d3945708a0"
  namespace: "repository-task-router-v1"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "worker_executor"
  canonical_owner: "canonical.elmos.model-gateway"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/20-worker-executor/SKILL.md` (`sha256:5f40feba6802620b1466f02bf08ec6aeb5709dcb8bb02330210559d3945708a0`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/schemas/`.
- Repository-corrected contracts and the exact 37-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Atomic Worker Executor

Execute an atomic task with the routed model, tool access and bounded attempts, producing a patch and evidence.

## Trigger conditions
- task dispatched

## Inputs
- `worker prompt`
- `worktree`
- `model alias`
- `model_selection`

## Outputs
- `patch`
- `execution record`
- `worker evidence`

## Procedure
1. Resolve alias through model-selection controller and registry guard; verify it matches the effective Smart/manual policy.
2. Invoke configured provider/CLI adapter.
3. Allow repository tools only inside worktree.
4. Capture commands, diffs and model usage.
5. Stop on forbidden write or hard budget.

## Guardrails
- No direct integration-branch write.
- No model outside allowlist.
- No primary-model substitution in manual strict mode.

## Acceptance criteria
- patch exists or failure classified
- execution record complete

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

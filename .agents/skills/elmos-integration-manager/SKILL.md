---
name: "elmos-integration-manager"
description: "Merge passed task patches into a dedicated integration branch in dependency order and keep evidence attached."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "1.1.0"
  source_version: "1.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/28-integration-manager/SKILL.md"
  source_sha256: "sha256:6d1daa2e6430b61de41d481a2294f5e44eaa7c2bd28ae30c1fdfc5b79eb17f52"
  namespace: "repository-task-router-v1"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "integration_manager"
  canonical_owner: "canonical.elmos.workspace-scm"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/28-integration-manager/SKILL.md` (`sha256:6d1daa2e6430b61de41d481a2294f5e44eaa7c2bd28ae30c1fdfc5b79eb17f52`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/schemas/`.
- Repository-corrected contracts and the exact 37-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Patch Integration Manager

Merge passed task patches into a dedicated integration branch in dependency order and keep evidence attached.

## Trigger conditions
- task passed local gates/review

## Inputs
- `task branches`
- `DAG`
- `integration branch`

## Outputs
- `integrated commit(s)`
- `integration log`

## Procedure
1. Integrate by topological order.
2. Run affected smoke/build checks after each risky merge.
3. Record commit mapping task->SHA.
4. Pause dependent waves if integration changes contracts.

## Guardrails
- Never squash away evidence mapping unless mapping retained.

## Acceptance criteria
- integration branch contains only approved task diffs

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

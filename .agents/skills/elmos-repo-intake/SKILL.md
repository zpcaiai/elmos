---
name: "elmos-repo-intake"
description: "Establish repository topology, build systems, languages, modules, ownership boundaries and runnable validation commands."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "1.1.0"
  source_version: "1.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/02-repo-intake/SKILL.md"
  source_sha256: "sha256:e6bf0e0f4950a772386a1ee9e1aac023e6bfbfd47f1ced665ccd9cc4f8a49576"
  namespace: "repository-task-router-v1"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "repo_intake"
  canonical_owner: "canonical.elmos.repository-snapshot"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/02-repo-intake/SKILL.md` (`sha256:e6bf0e0f4950a772386a1ee9e1aac023e6bfbfd47f1ced665ccd9cc4f8a49576`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/schemas/`.
- Repository-corrected contracts and the exact 37-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Repository Intake

Establish repository topology, build systems, languages, modules, ownership boundaries and runnable validation commands.

## Trigger conditions
- start of repository run

## Inputs
- `repository root`

## Outputs
- `repo profile`
- `build/test command catalog`
- `module map`

## Procedure
1. Inspect manifests and workspace files.
2. Identify services/apps/packages/libraries.
3. Detect build, test, lint, typecheck and migration commands.
4. Capture current git state and uncommitted changes.
5. Mark generated/vendor/large-data paths.

## Guardrails
- Do not mutate repository.
- Never overwrite user changes.

## Acceptance criteria
- repo profile is sufficient for later task planning
- validation commands are executable or explicitly unavailable

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

---
name: "elmos-conflict-resolver"
description: "Resolve merge conflicts using task contracts and repository invariants, not textual preference."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "1.1.0"
  source_version: "1.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/29-conflict-resolver/SKILL.md"
  source_sha256: "sha256:7e285ab6cfa02372e6f8e9fbc93c51cd8ff1b4710d581bb022ba9243ac85342c"
  namespace: "repository-task-router-v1"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "conflict_resolver"
  canonical_owner: "canonical.elmos.workspace-scm"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/29-conflict-resolver/SKILL.md` (`sha256:7e285ab6cfa02372e6f8e9fbc93c51cd8ff1b4710d581bb022ba9243ac85342c`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/schemas/`.
- Repository-corrected contracts and the exact 37-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Semantic Conflict Resolver

Resolve merge conflicts using task contracts and repository invariants, not textual preference.

## Trigger conditions
- integration conflict

## Inputs
- `conflicting patches`
- `task contracts`
- `architecture index`

## Outputs
- `resolved patch`
- `conflict evidence`

## Procedure
1. Identify semantic owners.
2. Reconcile contracts before code.
3. Prefer minimal combined behavior.
4. Rerun both tasks acceptance tests.
5. Escalate architecture-level conflict to L3.

## Guardrails
- No automatic choose-ours/theirs on semantic files.

## Acceptance criteria
- both task intents preserved or explicit supersession recorded

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

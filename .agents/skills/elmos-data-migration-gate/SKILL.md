---
name: "elmos-data-migration-gate"
description: "Validate schema/data migrations for forward correctness, rollback, compatibility and data integrity."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "1.1.0"
  source_version: "1.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/26-data-migration-gate/SKILL.md"
  source_sha256: "sha256:020b22e8c36f741a26ab12920e9edbfff2d5ce10580940ecd162df11bf1c7ff1"
  namespace: "repository-task-router-v1"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "data_migration_gate"
  canonical_owner: "canonical.elmos.verification-fabric"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/26-data-migration-gate/SKILL.md` (`sha256:020b22e8c36f741a26ab12920e9edbfff2d5ce10580940ecd162df11bf1c7ff1`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/schemas/`.
- Repository-corrected contracts and the exact 37-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Data Migration Gate

Validate schema/data migrations for forward correctness, rollback, compatibility and data integrity.

## Trigger conditions
- database/schema migration task

## Inputs
- `migration files`
- `schema`
- `fixtures`

## Outputs
- `migration evidence`
- `rollback evidence`

## Procedure
1. Test migration on representative fixture DB.
2. Verify rollback or documented irreversible strategy.
3. Check mixed-version compatibility when rolling deploys apply.
4. Validate constraints/indexes/data transformations.

## Guardrails
- Never treat successful DDL parse as sufficient.

## Acceptance criteria
- forward + integrity + rollback/irreversibility evidence complete

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

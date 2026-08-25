---
name: "elmos-security-auth-gate"
description: "Add threat-focused negative validation for security/auth/privacy-sensitive tasks."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "1.1.0"
  source_version: "1.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/25-security-auth-gate/SKILL.md"
  source_sha256: "sha256:4f1594fc168a06aefe93698f6c07465cca59b16d4610dbad06cf84ee4e32ba0d"
  namespace: "repository-task-router-v1"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "security_auth_gate"
  canonical_owner: "canonical.elmos.verification-fabric"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/25-security-auth-gate/SKILL.md` (`sha256:4f1594fc168a06aefe93698f6c07465cca59b16d4610dbad06cf84ee4e32ba0d`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/schemas/`.
- Repository-corrected contracts and the exact 37-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Security & Authorization Gate

Add threat-focused negative validation for security/auth/privacy-sensitive tasks.

## Trigger conditions
- risk.security high or auth touched

## Inputs
- `diff`
- `threat surface`
- `tests`

## Outputs
- `security evidence`
- `block/approve`

## Procedure
1. Check authn/authz boundaries.
2. Check input validation and injection surfaces.
3. Check secret exposure.
4. Add negative-path tests.
5. Require high-tier review for material changes.

## Guardrails
- Fail closed on missing critical evidence.

## Acceptance criteria
- security-required tests pass and reviewer signs off

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

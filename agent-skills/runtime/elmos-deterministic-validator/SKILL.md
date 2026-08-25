---
name: "elmos-deterministic-validator"
description: "Use build tools, compilers, linters and tests as the cheapest first-line judge of a worker patch."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "1.1.0"
  source_version: "1.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/21-deterministic-validator/SKILL.md"
  source_sha256: "sha256:b0e3b1285296188bcf1c0b139a99c22ea890b09e5b352428dfb4d512cba68eae"
  namespace: "repository-task-router-v1"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "deterministic_validator"
  canonical_owner: "canonical.elmos.runner"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/21-deterministic-validator/SKILL.md` (`sha256:b0e3b1285296188bcf1c0b139a99c22ea890b09e5b352428dfb4d512cba68eae`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/schemas/`.
- Repository-corrected contracts and the exact 37-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Deterministic Validator

Use build tools, compilers, linters and tests as the cheapest first-line judge of a worker patch.

## Trigger conditions
- worker patch produced

## Inputs
- `task`
- `worktree`
- `gate config`

## Outputs
- `validation evidence`
- `failure signals`

## Procedure
1. Run cheapest/high-signal checks first.
2. Run task-local tests and type/build gates.
3. Capture exit codes and minimal logs.
4. Run conditional gates triggered by risk.

## Guardrails
- Never treat model self-review as substitute for executable validation.

## Acceptance criteria
- all required local gates have explicit pass/fail/skip reason

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

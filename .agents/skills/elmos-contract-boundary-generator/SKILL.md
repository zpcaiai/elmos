---
name: "elmos-contract-boundary-generator"
description: "Define stable interfaces between tasks so cheap workers can implement leaves without needing whole-repository context."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "1.1.0"
  source_version: "1.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/08-contract-boundary-generator/SKILL.md"
  source_sha256: "sha256:b265a780ca516b7139b297eb8918cebfed6048af8862a98c61849cb770af3a1a"
  namespace: "repository-task-router-v1"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "contract_boundary_generator"
  canonical_owner: "canonical.elmos.contract-registry"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/08-contract-boundary-generator/SKILL.md` (`sha256:b265a780ca516b7139b297eb8918cebfed6048af8862a98c61849cb770af3a1a`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/schemas/`.
- Repository-corrected contracts and the exact 37-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Boundary Contract Generator

Define stable interfaces between tasks so cheap workers can implement leaves without needing whole-repository context.

## Trigger conditions
- DAG contains cross-task boundaries

## Inputs
- `tasks`
- `architecture index`

## Outputs
- `interface contracts`
- `fixtures/stubs`
- `compatibility rules`

## Procedure
1. Specify inputs/outputs, schemas, errors and invariants.
2. Generate or identify compile-time contracts where possible.
3. Create fixtures/stubs for downstream parallelism.
4. Mark compatibility expectations.

## Guardrails
- Contract changes affecting public APIs require elevated review tier.

## Acceptance criteria
- downstream task can execute from contract without hidden assumptions

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

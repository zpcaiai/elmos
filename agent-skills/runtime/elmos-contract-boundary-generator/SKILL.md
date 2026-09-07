---
name: "elmos-contract-boundary-generator"
description: "Create executable handoff contracts between tasks, including schemas, stubs, compatibility ranges and validators."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "2.0.0"
  source_version: "2.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/08-contract-boundary-generator/SKILL.md"
  source_sha256: "sha256:5cd8853a6201d038505f1f3d78be6b960fb2a49063609de0413ac5ed33c37935"
  namespace: "repository-task-router-v2"
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

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/08-contract-boundary-generator/SKILL.md` (`sha256:5cd8853a6201d038505f1f3d78be6b960fb2a49063609de0413ac5ed33c37935`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/schemas/`.
- Repository-corrected contracts and the exact 54-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Boundary Contract Generator v2

Turn cross-task assumptions into artifacts that can be validated before downstream execution.

## Inputs
- `tasks`
- `repository graph`
- `scenario graph`
- `invariant ledger`

## Outputs
- `interface/handoff contracts`
- `fixtures/stubs`
- `compatibility rules`
- `edge validators`

## Procedure
1. Specify produced/consumed artifacts, types/schemas, errors, invariants and lifecycle assumptions.
2. Prefer compile-time contracts, generated clients/types or schemas where available.
3. Generate stable fixtures/stubs only when they accurately model the contract.
4. Define backward/forward compatibility window for migrations and public APIs.
5. Bind every contract to a validator and affected scenarios.
6. Mark unstable contracts so scheduler prevents premature fan-out.

## Guardrails
- A prose handoff is not enough when a machine-checkable contract is possible.

## Acceptance criteria
- downstream task can start without hidden assumptions once incoming contracts validate

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

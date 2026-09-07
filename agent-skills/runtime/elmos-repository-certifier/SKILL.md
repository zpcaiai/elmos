---
name: "elmos-repository-certifier"
description: "Independently prove that the final integrated repository satisfies original explicit/implicit requirements and preserves required invariants."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "2.0.0"
  source_version: "2.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/31-repository-certifier/SKILL.md"
  source_sha256: "sha256:21d4ad66e7483c543d0c5c1b9b6a116a3cd21e3fd54ead162412a48f5958c96f"
  namespace: "repository-task-router-v2"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "repository_certifier"
  canonical_owner: "canonical.elmos.local-verification-gate"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/31-repository-certifier/SKILL.md` (`sha256:21d4ad66e7483c543d0c5c1b9b6a116a3cd21e3fd54ead162412a48f5958c96f`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/schemas/`.
- Repository-corrected contracts and the exact 54-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Repository-Level Certifier v2

Certify the complete repository change against behavior, architecture and evidence.

## Inputs
- `explicit + evidence-backed implicit requirements`
- `scenario graph`
- `invariant ledger`
- `integration branch`
- `baselines`
- `all task/edge proof evidence`

## Outputs
- `certification report`
- `go/no-go`
- `requirement-to-scenario-to-task-to-proof traceability matrix`

## Procedure
1. Run clean build and full applicable regression from a reproducible environment.
2. Execute original behavioral scenarios, including negative/compatibility/rollback cases.
3. Verify all critical invariants and proof obligations are closed.
4. Compare against baselines/golden outputs and inspect unexplained diff surfaces.
5. Validate no scenario or inferred requirement became orphaned through replanning.
6. Use an independent high-tier model only where deterministic evidence cannot resolve semantic correctness.
7. Record unresolved uncertainty and certification limitations explicitly.

## Guardrails
- Leaf-task success or model confidence cannot substitute for repository-level proof.

## Acceptance criteria
- all mandatory scenarios/invariants/proofs pass or produce blocking findings

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

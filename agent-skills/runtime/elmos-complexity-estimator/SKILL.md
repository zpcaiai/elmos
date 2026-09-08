---
name: "elmos-complexity-estimator"
description: "Estimate execution complexity, coordination complexity and uncertainty separately so planning and model routing can optimize completed-task cost."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "2.0.0"
  source_version: "2.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/09-complexity-estimator/SKILL.md"
  source_sha256: "sha256:fc394740e7ad3809a1258f2a78716804ea9576d6b6499f31ea6c2ee825dc740c"
  namespace: "repository-task-router-v2"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "complexity_estimator"
  canonical_owner: "canonical.elmos.execution-intelligence"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/09-complexity-estimator/SKILL.md` (`sha256:fc394740e7ad3809a1258f2a78716804ea9576d6b6499f31ea6c2ee825dc740c`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/schemas/`.
- Repository-corrected contracts and the exact 54-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Complexity Estimator v2

Estimate both implementation difficulty and decomposition/coordination difficulty.

## Inputs
- `task or hierarchical node`
- `repository subgraph`
- `proof obligations`

## Outputs
- `execution complexity vector`
- `coordination complexity vector`
- `context/tool-cycle estimate`
- `uncertainty score`

## Procedure
1. Score logic novelty, algorithmic difficulty, context demand, tool use, test difficulty and expected edit/review loops.
2. Score cross-boundary coupling, number of handoffs, invariant density and integration sensitivity.
3. Estimate prompt/context/output footprint and expected completed-task duration.
4. Record confidence and evidence behind estimates.
5. Feed execution complexity to model router and coordination complexity to granularity/scheduler.

## Guardrails
- Low LOC/file count does not imply low complexity, risk or coordination cost.

## Acceptance criteria
- complexity and uncertainty are separate, evidence-backed dimensions

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

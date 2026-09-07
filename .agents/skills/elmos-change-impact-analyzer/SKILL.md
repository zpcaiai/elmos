---
name: "elmos-change-impact-analyzer"
description: "Estimate direct/transitive behavioral blast radius using scenarios, repository graph reachability, data-flow and confidence."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "2.0.0"
  source_version: "2.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/04-change-impact-analyzer/SKILL.md"
  source_sha256: "sha256:ff77e04c06fca832e07c162fc0eba7ff2343efd56385a9476b3f21cf0ff7ad52"
  namespace: "repository-task-router-v2"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "change_impact_analyzer"
  canonical_owner: "canonical.elmos.impact-graph"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/04-change-impact-analyzer/SKILL.md` (`sha256:ff77e04c06fca832e07c162fc0eba7ff2343efd56385a9476b3f21cf0ff7ad52`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/schemas/`.
- Repository-corrected contracts and the exact 54-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Change Impact Analyzer v2

Estimate what can change and what must be revalidated, with uncertainty explicitly represented.

## Inputs
- `requirement/scenario graph`
- `repository intelligence graph`
- `invariant ledger`

## Outputs
- `impact subgraph`
- `direct/transitive impact sets`
- `risk triggers`
- `impact confidence`
- `candidate exploration tasks`

## Procedure
1. Trace each behavioral scenario through typed repository graph edges.
2. Separate write candidates from validation-only impact and runtime/deployment impact.
3. Expand through public contracts, data schemas, side effects and shared state until an evidence-backed cut set is reached.
4. Flag security/auth/transaction/concurrency/migration/public-API/global-config triggers.
5. Score confidence per impacted region based on graph evidence quality and unknown runtime edges.
6. If confidence is below policy threshold and consequences are meaningful, emit a bounded exploration task.
7. Produce test/build/observability surfaces for regression selection.

## Guardrails
- Conservative expansion is preferable to false certainty, but unexplained whole-repo impact is not acceptable.

## Acceptance criteria
- all acceptance scenarios have graph-backed impact paths
- uncertainty and cut-set reasons are recorded

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

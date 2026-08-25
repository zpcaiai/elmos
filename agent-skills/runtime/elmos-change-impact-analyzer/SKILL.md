---
name: "elmos-change-impact-analyzer"
description: "Estimate blast radius of the normalized requirement across code, schema, API, tests, infra and documentation."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "1.1.0"
  source_version: "1.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/04-change-impact-analyzer/SKILL.md"
  source_sha256: "sha256:d93ba127ccc683787b6eb517351c97a59006324e2ae87d3cbd7078d87fe8be8c"
  namespace: "repository-task-router-v1"
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

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/04-change-impact-analyzer/SKILL.md` (`sha256:d93ba127ccc683787b6eb517351c97a59006324e2ae87d3cbd7078d87fe8be8c`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/schemas/`.
- Repository-corrected contracts and the exact 37-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Change Impact Analyzer

Estimate blast radius of the normalized requirement across code, schema, API, tests, infra and documentation.

## Trigger conditions
- normalized requirement + architecture index

## Inputs
- `requirement spec`
- `architecture index`

## Outputs
- `impact map`
- `risk triggers`
- `candidate write/read paths`

## Procedure
1. Trace each acceptance scenario to likely components.
2. Separate direct changes from transitive validation impact.
3. Flag API/schema/security/concurrency/migration triggers.
4. Estimate affected test surfaces.

## Guardrails
- Treat uncertain high-impact paths conservatively.

## Acceptance criteria
- all acceptance scenarios have candidate impact paths
- risk triggers emitted

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

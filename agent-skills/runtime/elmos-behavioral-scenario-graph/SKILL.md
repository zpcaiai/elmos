---
name: "elmos-behavioral-scenario-graph"
description: "Convert requirements into end-to-end behavioral scenarios and map each scenario to repository surfaces and proof obligations."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "2.0.0"
  source_version: "2.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/38-behavioral-scenario-graph/SKILL.md"
  source_sha256: "sha256:fd7a8f53c37b0c679edbfeb7dc8e57032a977c36e3349c14f954c7eb88b34bf5"
  namespace: "repository-task-router-v2"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "behavioral_scenario_graph"
  canonical_owner: "canonical.elmos.scenario-graph"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/38-behavioral-scenario-graph/SKILL.md` (`sha256:fd7a8f53c37b0c679edbfeb7dc8e57032a977c36e3349c14f954c7eb88b34bf5`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/schemas/`.
- Repository-corrected contracts and the exact 54-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Behavioral Scenario Graph

Represent the request as user-visible and system-visible behavior before decomposing by files.

## Inputs
- `requirement spec`
- `implicit requirement set`
- `repository intelligence graph`

## Outputs
- `scenario graph`
- `scenario-to-component map`
- `scenario-to-proof map`

## Procedure
1. Create happy-path, failure-path, boundary, compatibility and rollback scenarios.
2. Model each scenario as ordered observable states/events, not prose-only intentions.
3. Link each step to API, domain, persistence, messaging, UI, infra and test surfaces.
4. Identify shared scenario prefixes/suffixes and cross-cutting invariants.
5. Mark scenarios that require end-to-end or integration verification.
6. Require every atomic task to claim which scenario steps it advances.

## Guardrails
- File ownership alone is not a valid decomposition axis.
- A scenario may cross many modules; preserve its semantic chain in the plan graph.

## Acceptance criteria
- every acceptance criterion is covered by one or more scenarios
- every scenario has an observable verifier path or an explicit verification gap

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

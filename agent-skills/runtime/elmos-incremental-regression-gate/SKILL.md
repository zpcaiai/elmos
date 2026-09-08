---
name: "elmos-incremental-regression-gate"
description: "Run graph/scenario-based regression after each integration checkpoint and use unexpected failures as impact-model feedback."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "2.0.0"
  source_version: "2.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/30-incremental-regression-gate/SKILL.md"
  source_sha256: "sha256:ffb78c6cbfb9fe0dccf40a21cf01d4b05e9472c65b69b6e0c87e5e55381a267b"
  namespace: "repository-task-router-v2"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "incremental_regression_gate"
  canonical_owner: "canonical.elmos.runner"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/30-incremental-regression-gate/SKILL.md` (`sha256:ffb78c6cbfb9fe0dccf40a21cf01d4b05e9472c65b69b6e0c87e5e55381a267b`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/schemas/`.
- Repository-corrected contracts and the exact 54-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Incremental Regression Gate v2

Detect incorrect impact assumptions as early as possible.

## Inputs
- `repository graph delta`
- `scenario graph`
- `changed paths/symbols`
- `baseline evidence`
- `test catalog`

## Outputs
- `checkpoint regression evidence`
- `unexpected-impact findings`

## Procedure
1. Select tests from changed nodes, typed dependency reach and affected scenarios.
2. Include baseline comparison and previously failing related tests.
3. Add contract/invariant-specific probes for high-risk boundaries.
4. Attribute failures to integration checkpoint/task where evidence permits.
5. When a failure occurs outside predicted impact, update RIG/impact confidence and trigger local replan.
6. Block downstream dependent work on unresolved regressions.

## Guardrails
- High-centrality or global-invariant changes require broader regression than changed-file selection.

## Acceptance criteria
- checkpoint passes its graph-derived regression/proof set

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

---
name: "elmos-repository-orchestrator"
description: "Own the entire repository-level requirement from intake through certification and resume an interrupted run without losing completed work."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "1.1.0"
  source_version: "1.1.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/00-repository-orchestrator/SKILL.md"
  source_sha256: "sha256:6d5d84c5ef465914224d7b0010c8e6df6b5d60cea541364e7f2129054bc08010"
  namespace: "repository-task-router-v1"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "repository_orchestrator"
  canonical_owner: "canonical.elmos.durable-runtime"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/00-repository-orchestrator/SKILL.md` (`sha256:6d5d84c5ef465914224d7b0010c8e6df6b5d60cea541364e7f2129054bc08010`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/schemas/`.
- Repository-corrected contracts and the exact 37-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Repository Orchestrator

Own the entire repository-level requirement from intake through certification and resume an interrupted run without losing completed work.

## Trigger conditions
- medium/large repository feature
- multi-module change
- migration/refactor
- request explicitly asks for complete repository-level implementation

## Inputs
- `requirement`
- `repository root`
- `budget policy`
- `model registry`
- `model_selection` (Smart or manual, validated by `elmos-model-selection-controller`)

## Outputs
- `run manifest`
- `task DAG`
- `integrated patch`
- `certification report`

## Procedure
1. Create run_id and durable run directory.
2. Resolve and persist Smart/manual model selection before dispatch.
3. Invoke repo intake, architecture index and impact analysis.
4. Decompose into atomic tasks and validate DAG.
5. Route and execute ready waves under model-selection constraints, budget and path locks.
6. Integrate passed tasks, rerun affected gates, then full repository certification.
7. Persist every transition and support resume from last durable state.

## Guardrails
- Never bypass the 10-model allowlist.
- Never override a manual strict selection with a silent fallback.
- Never mark complete from worker self-report alone.
- Never allow parallel write overlap.
- Hard budget/security gates override throughput.

## Acceptance criteria
- all required tasks terminal
- repository final gates pass
- traceability matrix complete
- cost/runtime/model usage reported

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

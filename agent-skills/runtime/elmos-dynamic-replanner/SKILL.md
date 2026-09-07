---
name: "elmos-dynamic-replanner"
description: "Apply bounded local or global graph edits when runtime evidence invalidates the original plan."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "2.0.0"
  source_version: "2.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/48-dynamic-replanner/SKILL.md"
  source_sha256: "sha256:a3691c6e451411b5a1c54832d62365926de6a2cd485c64cf230474b943151152"
  namespace: "repository-task-router-v2"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "dynamic_replanner"
  canonical_owner: "canonical.elmos.durable-runtime"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/48-dynamic-replanner/SKILL.md` (`sha256:a3691c6e451411b5a1c54832d62365926de6a2cd485c64cf230474b943151152`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/schemas/`.
- Repository-corrected contracts and the exact 54-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Dynamic Replanner

Make the plan an evolving executable hypothesis.

## Inputs
- current plan/DAG
- run-state journal
- validation failures
- discovered graph changes

## Outputs
- `plan revision`
- `preserved evidence set`
- `invalidated tasks`
- `new refinement frontier`

## Replan triggers
- repeated same failure
- unexpected impacted path
- new dependency edge
- invariant violation
- contract change
- integration conflict
- verifier failure outside predicted surface
- missing context or tool requirement

## Procedure
1. Classify trigger as local node, boundary cluster or global-plan invalidation.
2. Prefer the smallest graph edit that restores executability.
3. Preserve passed evidence whose assumptions remain valid.
4. Invalidate only descendants or peers affected by changed contracts/invariants.
5. Re-run graph verifier and budget/ETA/model routing for changed nodes.
6. Cap replans and escalate when repeated plan instability indicates requirement/architecture misunderstanding.

## Guardrails
- Never rewrite plan history in place; append a revision.

## Acceptance criteria
- every replan identifies trigger, changed assumptions and invalidated evidence

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

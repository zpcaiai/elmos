---
name: "elmos-integration-manager"
description: "Integrate validated task outputs by boundary cluster while checking semantic conflicts and contract/proof obligations at each checkpoint."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "2.0.0"
  source_version: "2.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/28-integration-manager/SKILL.md"
  source_sha256: "sha256:ad0c79e6c040288b4688c055ff48605eae094ee55f39669f0ccec89ac80485f7"
  namespace: "repository-task-router-v2"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "integration_manager"
  canonical_owner: "canonical.elmos.workspace-scm"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/28-integration-manager/SKILL.md` (`sha256:ad0c79e6c040288b4688c055ff48605eae094ee55f39669f0ccec89ac80485f7`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/schemas/`.
- Repository-corrected contracts and the exact 54-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Patch Integration Manager v2

Integrate patches as a sequence of validated semantic checkpoints, not merely git merges.

## Inputs
- `task worktrees/branches`
- `typed DAG`
- `edge handoffs`
- `integration checkpoint plan`

## Outputs
- `integrated commits`
- `integration evidence`
- `semantic conflict findings`

## Procedure
1. Integrate in dependency/boundary-cluster order.
2. Validate outgoing handoff artifacts before unlocking consumer patches.
3. Invoke semantic conflict detection for patches sharing symbols, schemas, state or scenarios even if git reports no conflict.
4. Run checkpoint proof obligations and affected baseline comparisons after risky shared changes.
5. Record task->commit->plan revision mapping.
6. If integration changes a contract or reveals new impact, stop dependents and trigger dynamic replan.

## Guardrails
- Never treat clean textual merge as semantic compatibility evidence.

## Acceptance criteria
- integration branch contains only approved diffs with checkpoint evidence

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

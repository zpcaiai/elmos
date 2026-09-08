---
name: "elmos-plan-diff-audit-journal"
description: "Persist immutable plan revisions and graph diffs so decomposition decisions are explainable, replayable and resumable."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "2.0.0"
  source_version: "2.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/52-plan-diff-audit-journal/SKILL.md"
  source_sha256: "sha256:c67302a6bd139c35d66ba76d466c9a6917efd5089fdf12ff19eca2d50a201baa"
  namespace: "repository-task-router-v2"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "plan_diff_audit_journal"
  canonical_owner: "canonical.elmos.durable-runtime"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/52-plan-diff-audit-journal/SKILL.md` (`sha256:c67302a6bd139c35d66ba76d466c9a6917efd5089fdf12ff19eca2d50a201baa`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/schemas/`.
- Repository-corrected contracts and the exact 54-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Plan Diff & Audit Journal

Persist planning as a versioned artifact.

## Inputs
- plan revisions
- replan triggers
- split/merge decisions

## Outputs
- `.elmos/runs/<run_id>/plans/rev-*.json`
- `plan diff ledger`
- `decision reasons`

## Procedure
1. Assign monotonically increasing plan revision IDs.
2. Record added/removed/merged/split nodes and edges.
3. Record assumptions, confidence changes, affected evidence and budget/ETA delta.
4. Link execution records to the exact plan revision used.
5. Support replay from any stable checkpoint.

## Acceptance criteria
- current plan can be reconstructed from revision history
- no execution task lacks a plan revision reference

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

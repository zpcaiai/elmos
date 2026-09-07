---
name: "elmos-plan-graph-verifier"
description: "Structurally validate hierarchical plans and DAG edges before execution using deterministic graph checks and typed contracts."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "2.0.0"
  source_version: "2.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/44-plan-graph-verifier/SKILL.md"
  source_sha256: "sha256:3f483448b5b0d88d5d6b5b55d954890bd45a3e2d3ee0d689ce0f49cc23e5fd28"
  namespace: "repository-task-router-v2"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "plan_graph_verifier"
  canonical_owner: "canonical.elmos.local-verification-gate"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/44-plan-graph-verifier/SKILL.md` (`sha256:3f483448b5b0d88d5d6b5b55d954890bd45a3e2d3ee0d689ce0f49cc23e5fd28`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/schemas/`.
- Repository-corrected contracts and the exact 54-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Plan Graph Verifier

Verify planning structure before spending model budget on implementation.

## Inputs
- hierarchical plan
- execution DAG
- scenario graph
- invariant ledger
- task contracts

## Outputs
- `plan verification report`
- `node risks`
- `edge risks`
- `repair suggestions`

## Procedure
1. Reject cycles, orphan nodes, missing prerequisites and impossible readiness states.
2. Check producer/consumer type and schema compatibility on every dependency edge.
3. Check that every cross-task edge has a handoff contract and validation method.
4. Verify all acceptance scenarios and critical invariants have complete task/evidence coverage.
5. Detect path ownership overlaps, hidden shared-state coupling and unsupported parallel waves.
6. Apply local graph repairs first: insert bridge task, merge nodes, split node, add missing edge or move integration gate.

## Guardrails
- An LLM prose review cannot override failed deterministic structural checks.

## Acceptance criteria
- graph is executable, acyclic and acceptance-complete
- all critical edge risks are resolved or explicitly waived

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

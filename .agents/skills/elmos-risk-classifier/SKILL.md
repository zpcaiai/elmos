---
name: "elmos-risk-classifier"
description: "Classify semantic consequence, rollback difficulty and blast radius independently from task size and complexity."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "2.0.0"
  source_version: "2.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/10-risk-classifier/SKILL.md"
  source_sha256: "sha256:bc823d3b46d89f5cf8eabf7920cdc7fdad5b7deb25eac7fe05445f3ba935f40b"
  namespace: "repository-task-router-v2"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "risk_classifier"
  canonical_owner: "canonical.elmos.identity-policy"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/10-risk-classifier/SKILL.md` (`sha256:bc823d3b46d89f5cf8eabf7920cdc7fdad5b7deb25eac7fe05445f3ba935f40b`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/schemas/`.
- Repository-corrected contracts and the exact 54-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Risk Classifier v2

Classify how costly it would be for a locally plausible patch to be wrong.

## Inputs
- `task`
- `impact subgraph`
- `invariant ledger`

## Outputs
- `risk vector`
- `minimum model/review tier`
- `mandatory proof obligations/gates`

## Procedure
1. Evaluate security, privacy, authn/authz and secrets boundaries.
2. Evaluate irreversible state/data mutations and migration compatibility.
3. Evaluate concurrency, idempotency, ordering and distributed side effects.
4. Evaluate public API/schema compatibility and downstream ecosystem blast radius.
5. Evaluate rollback complexity, observability gaps and deployment coupling.
6. Promote verification/model tier independently of task granularity.

## Guardrails
- Cost pressure cannot downgrade mandatory safety/compatibility gates.

## Acceptance criteria
- risk consequences, required gates and rollback expectations are explicit

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

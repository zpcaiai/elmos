---
name: "elmos-risk-classifier"
description: "Classify blast radius and semantic risk for security, auth, data migration, concurrency, money, public APIs and infrastructure."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "1.1.0"
  source_version: "1.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/10-risk-classifier/SKILL.md"
  source_sha256: "sha256:08feca8cc1b702217ee5fd87d530a43754d17cf72673047882b58f0d4c99d5f7"
  namespace: "repository-task-router-v1"
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

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/10-risk-classifier/SKILL.md` (`sha256:08feca8cc1b702217ee5fd87d530a43754d17cf72673047882b58f0d4c99d5f7`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/schemas/`.
- Repository-corrected contracts and the exact 37-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Risk Classifier

Classify blast radius and semantic risk for security, auth, data migration, concurrency, money, public APIs and infrastructure.

## Trigger conditions
- before model routing

## Inputs
- `task`
- `impact map`

## Outputs
- `risk vector`
- `minimum model tier`
- `required gates`

## Procedure
1. Evaluate security/privacy/auth.
2. Evaluate irreversible data/state mutation.
3. Evaluate concurrency/idempotency.
4. Evaluate public contract compatibility.
5. Evaluate blast radius and rollback difficulty.
6. Emit mandatory promotion and review gates.

## Guardrails
- High-risk gates cannot be downgraded by cost pressure.

## Acceptance criteria
- minimum tier and validation gates determined

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

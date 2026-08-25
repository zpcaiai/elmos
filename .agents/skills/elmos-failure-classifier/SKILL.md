---
name: "elmos-failure-classifier"
description: "Classify execution/validation failure so Elmos knows whether to retry, repair context, escalate model or stop."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "1.1.0"
  source_version: "1.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/22-failure-classifier/SKILL.md"
  source_sha256: "sha256:c1cb61bac4c5d394eee851fa73f32be18a28724febe19f4149612aaa58e586c3"
  namespace: "repository-task-router-v1"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "failure_classifier"
  canonical_owner: "canonical.elmos.durable-runtime"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/22-failure-classifier/SKILL.md` (`sha256:c1cb61bac4c5d394eee851fa73f32be18a28724febe19f4149612aaa58e586c3`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/schemas/`.
- Repository-corrected contracts and the exact 37-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Failure Classifier

Classify execution/validation failure so Elmos knows whether to retry, repair context, escalate model or stop.

## Trigger conditions
- worker/validator failure

## Inputs
- `execution logs`
- `test output`
- `diff`

## Outputs
- `failure class`
- `recommended action`

## Procedure
1. Distinguish transient tool, formatting, localized test, semantic, integration, architecture, context loss, policy and budget failures.
2. Estimate whether same model can fix cheaply.
3. Emit promotion trigger when needed.

## Guardrails
- Policy/security violations are not ordinary retries.

## Acceptance criteria
- one actionable class selected with evidence

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

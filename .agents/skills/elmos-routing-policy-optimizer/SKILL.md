---
name: "elmos-routing-policy-optimizer"
description: "Periodically optimize thresholds, tier ordering and escalation rules from telemetry while preserving safety constraints and the ten-model allowlist."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "1.1.0"
  source_version: "1.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/35-routing-policy-optimizer/SKILL.md"
  source_sha256: "sha256:53a7b046290b409998b90fd181ffd0dadfe0809cd6569a4b22342a4bc0e1023c"
  namespace: "repository-task-router-v1"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "routing_policy_optimizer"
  canonical_owner: "canonical.elmos.model-gateway"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/35-routing-policy-optimizer/SKILL.md` (`sha256:53a7b046290b409998b90fd181ffd0dadfe0809cd6569a4b22342a4bc0e1023c`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/schemas/`.
- Repository-corrected contracts and the exact 37-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Routing Policy Optimizer

Periodically optimize thresholds, tier ordering and escalation rules from telemetry while preserving safety constraints and the ten-model allowlist.

## Trigger conditions
- sufficient telemetry or scheduled tuning

## Inputs
- `historical telemetry`
- `current policy`
- `budget goals`

## Outputs
- `candidate policy`
- `offline evaluation`
- `approved policy`

## Procedure
1. Backtest candidate routes against historical tasks.
2. Compare cost, first-pass success, total completion cost, latency and escaped defects.
3. Reject regressions in critical-task quality.
4. Canary new policy on low-risk tasks.

## Guardrails
- Cannot add an 11th model.
- Cannot lower mandatory high-risk tier without explicit policy change.

## Acceptance criteria
- candidate shows measurable expected-cost improvement without quality regression

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

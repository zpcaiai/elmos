---
name: "elmos-patch-reviewer"
description: "Apply model review only when expected defect reduction justifies the extra cost or policy requires a second model."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "1.1.0"
  source_version: "1.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/24-patch-reviewer/SKILL.md"
  source_sha256: "sha256:2b9362520631f76b2e7236baaf388de3223fe47a39e9e33e7af64d6e5e92856c"
  namespace: "repository-task-router-v1"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "patch_reviewer"
  canonical_owner: "canonical.elmos.verification-fabric"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/24-patch-reviewer/SKILL.md` (`sha256:2b9362520631f76b2e7236baaf388de3223fe47a39e9e33e7af64d6e5e92856c`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/schemas/`.
- Repository-corrected contracts and the exact 37-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Risk-Aware Patch Reviewer

Apply model review only when expected defect reduction justifies the extra cost or policy requires a second model.

## Trigger conditions
- local validation passes
- review trigger present

## Inputs
- `task`
- `diff`
- `evidence`
- `risk`

## Outputs
- `review findings`
- `approve/rework`

## Procedure
1. Check contract adherence, edge cases, security and repository conventions.
2. Use deterministic evidence as input.
3. Prefer reviewer from L3 for critical areas.
4. Avoid stylistic churn.

## Guardrails
- Reviewer cannot waive mandatory tests.

## Acceptance criteria
- findings are severity-ranked and actionable

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

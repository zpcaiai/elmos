---
name: "elmos-decomposition-telemetry-learner"
description: "Learn repository- and task-family-specific decomposition priors from execution, replans, integration failures and final certification."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "2.0.0"
  source_version: "2.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/53-decomposition-telemetry-learner/SKILL.md"
  source_sha256: "sha256:1720ef2adabbff0b8d39aa1f32b21e39b2ab19e9a958233491367d0d07b5cc8e"
  namespace: "repository-task-router-v2"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "decomposition_telemetry_learner"
  canonical_owner: "canonical.elmos.execution-intelligence"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/53-decomposition-telemetry-learner/SKILL.md` (`sha256:1720ef2adabbff0b8d39aa1f32b21e39b2ab19e9a958233491367d0d07b5cc8e`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/schemas/`.
- Repository-corrected contracts and the exact 54-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Decomposition Telemetry Learner

Improve how Elmos decomposes future work from its own outcomes.

## Inputs
- task execution telemetry
- plan revisions
- integration conflicts
- verifier results
- final certification outcome

## Outputs
- `decomposition priors`
- `granularity calibration`
- `seam quality statistics`
- `replan predictors`

## Procedure
1. Measure first-pass success, replan rate, hidden dependency discovery, split/merge-after-start, context overflow and integration conflicts.
2. Aggregate by repository, task family, architecture region, harness and model tier.
3. Learn which seams and task sizes minimize completed-task cost and defect escape.
4. Decay observations after major repository architecture or tooling changes.
5. Feed calibrated priors into granularity, impact and scheduling decisions.

## Guardrails
- Do not optimize solely for fewer tasks or fewer tokens.
- Final repository acceptance and keep/revert outcomes outweigh self-reported model success.

## Acceptance criteria
- learned policy is versioned, replayable and can be disabled to restore deterministic defaults

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

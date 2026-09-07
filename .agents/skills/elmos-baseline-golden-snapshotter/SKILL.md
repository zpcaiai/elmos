---
name: "elmos-baseline-golden-snapshotter"
description: "Capture repository behavior and build/test baselines before change so decomposition and final verification can detect unintended regressions."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "2.0.0"
  source_version: "2.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/51-baseline-golden-snapshotter/SKILL.md"
  source_sha256: "sha256:94a5b586cab5411cdb4056e915de17b85e3c563324b9f4043f44cacc5b794be5"
  namespace: "repository-task-router-v2"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "baseline_golden_snapshotter"
  canonical_owner: "canonical.elmos.verification-fabric"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/51-baseline-golden-snapshotter/SKILL.md` (`sha256:94a5b586cab5411cdb4056e915de17b85e3c563324b9f4043f44cacc5b794be5`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/schemas/`.
- Repository-corrected contracts and the exact 54-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Baseline & Golden Snapshotter

Capture what must remain true before implementation begins.

## Inputs
- impacted scenarios
- repository graph
- available test/build commands

## Outputs
- `baseline evidence`
- `golden outputs`
- `known failing tests`
- `environment fingerprint`

## Procedure
1. Run scoped baseline builds/tests and record pre-existing failures.
2. Capture stable API responses, schemas, generated artifacts or traces when useful.
3. Fingerprint toolchain/environment so post-change failures are comparable.
4. Attach baseline evidence to relevant proof obligations.
5. Use differential validation after each integration checkpoint.

## Guardrails
- Never attribute a pre-existing failure to a new patch without differential evidence.

## Acceptance criteria
- impacted high-risk surfaces have a before/after comparison path

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

---
name: "elmos-worker-prompt-builder"
description: "Generate constrained execution prompts that make lower-cost models reliable on atomic repository tasks."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "1.1.0"
  source_version: "1.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/19-worker-prompt-builder/SKILL.md"
  source_sha256: "sha256:38f52e250f108b43073d3518321335e19d6576d656367577b396338c4b820258"
  namespace: "repository-task-router-v1"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "worker_prompt_builder"
  canonical_owner: "canonical.elmos.context-builder"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/19-worker-prompt-builder/SKILL.md` (`sha256:38f52e250f108b43073d3518321335e19d6576d656367577b396338c4b820258`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/schemas/`.
- Repository-corrected contracts and the exact 37-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Worker Prompt Builder

Generate constrained execution prompts that make lower-cost models reliable on atomic repository tasks.

## Trigger conditions
- before model invocation

## Inputs
- `task`
- `context pack`
- `contracts`
- `validation commands`

## Outputs
- `worker prompt`

## Procedure
1. State single objective and non-goals.
2. List owned/read/forbidden paths.
3. Include exact acceptance commands.
4. Require minimal diff and no unrelated refactors.
5. Require worker to run deterministic checks and return evidence/patch summary.

## Guardrails
- Never expose secrets.
- Never ask worker to bypass tests or permissions.

## Acceptance criteria
- prompt is executable without ambiguous scope

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

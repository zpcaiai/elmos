---
name: "elmos-context-slicer"
description: "Build the smallest sufficient context pack for each atomic task to reduce token cost and context dilution."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "1.1.0"
  source_version: "1.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/11-context-slicer/SKILL.md"
  source_sha256: "sha256:f4d5a0b36648121f305bd643cbae891f12ce295821ce04e17221ddb3d130c4e7"
  namespace: "repository-task-router-v1"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "context_slicer"
  canonical_owner: "canonical.elmos.context-builder"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/11-context-slicer/SKILL.md` (`sha256:f4d5a0b36648121f305bd643cbae891f12ce295821ce04e17221ddb3d130c4e7`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/schemas/`.
- Repository-corrected contracts and the exact 37-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Context Slicer

Build the smallest sufficient context pack for each atomic task to reduce token cost and context dilution.

## Trigger conditions
- task ready for routing

## Inputs
- `task`
- `architecture index`
- `repo`

## Outputs
- `context pack manifest`

## Procedure
1. Include task contract, owned/read paths and nearby tests.
2. Include only transitive definitions required to compile/reason.
3. Summarize rather than paste large unrelated modules.
4. Attach acceptance commands and forbidden paths.
5. Hash pack for cache reuse.

## Guardrails
- Do not omit architectural invariants referenced by risk classifier.

## Acceptance criteria
- worker can execute without whole-repo dump
- context pack has provenance

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

---
name: "elmos-context-slicer"
description: "Build graph-derived, task-specific context packs that include contracts/invariants/proof obligations while minimizing unrelated repository content."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "2.0.0"
  source_version: "2.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/11-context-slicer/SKILL.md"
  source_sha256: "sha256:261a6357a3fd35e0b06c2e6346d5dad308704aa878fc9139fac414d7472b46b2"
  namespace: "repository-task-router-v2"
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

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/11-context-slicer/SKILL.md` (`sha256:261a6357a3fd35e0b06c2e6346d5dad308704aa878fc9139fac414d7472b46b2`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/schemas/`.
- Repository-corrected contracts and the exact 54-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Graph-Aware Context Slicer v2

Provide the smallest sufficient context for a worker without hiding boundary assumptions.

## Inputs
- `task`
- `repository intelligence graph`
- `scenario links`
- `invariant/contract/proof links`

## Outputs
- `context pack manifest`
- `context provenance graph`
- `cache key`

## Procedure
1. Start from task-owned symbols/paths and traverse only required typed dependency edges.
2. Include incoming/outgoing contracts, scenario slice, invariants, proof obligations and nearby tests.
3. Include sibling examples when they encode repository conventions.
4. Summarize distant dependencies while preserving exact signatures/schemas where required.
5. Attach acceptance commands, baseline evidence and forbidden paths.
6. Hash stable context segments separately to maximize cache reuse across sibling tasks.
7. If worker discovers a missing required edge, treat it as a replan signal rather than repeatedly expanding context blindly.

## Guardrails
- Do not omit critical invariants to save tokens.

## Acceptance criteria
- context is sufficient, provenance-backed and cache-segmented

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

---
name: "elmos-repository-intelligence-graph"
description: "Build an evidence-backed multi-layer repository graph covering architecture, build, tests, runtime data flows and change coupling."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "2.0.0"
  source_version: "2.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/39-repository-intelligence-graph/SKILL.md"
  source_sha256: "sha256:de43e9607e28b7790a334d6ab867dca6d2cb0bd7272d5c8444efee375224d21e"
  namespace: "repository-task-router-v2"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "repository_intelligence_graph"
  canonical_owner: "canonical.elmos.semantic-index"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/39-repository-intelligence-graph/SKILL.md` (`sha256:de43e9607e28b7790a334d6ab867dca6d2cb0bd7272d5c8444efee375224d21e`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/schemas/`.
- Repository-corrected contracts and the exact 54-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Repository Intelligence Graph

Build a deterministic, evidence-backed graph used as authoritative planning context.

## Inputs
- source tree
- build manifests
- test metadata
- schemas/migrations
- API definitions
- configuration
- CI/CD definitions

## Outputs
- `RIG nodes`
- `typed edges`
- `evidence pointers`
- `centrality and cut-set hints`

## Procedure
1. Index modules, source files, public symbols, APIs, data entities, migrations, queues/topics, configs, build targets and test targets.
2. Emit typed edges: imports, calls, implements, exposes, reads, writes, publishes, consumes, migrates, configures, builds, tests and covers.
3. Attach concrete evidence locations to every non-heuristic edge.
4. Compute high-centrality nodes, strongly connected components, architectural seams and likely change cut sets.
5. Expose a compact subgraph query interface for planners and context slicers.
6. Refresh only affected graph regions after patches.

## Guardrails
- Separate deterministic edges from heuristic edges.
- Never present inferred runtime data flow as certain without evidence.

## Acceptance criteria
- build/test/runtime critical surfaces are represented
- graph edges are typed and evidence-backed
- downstream planner can query a bounded impact subgraph

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.

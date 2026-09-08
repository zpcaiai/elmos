---
name: elmos-repository-intelligence-graph
version: 2.0.0
description: Build an evidence-backed multi-layer repository graph covering architecture, build, tests, runtime data flows and change coupling.
---

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

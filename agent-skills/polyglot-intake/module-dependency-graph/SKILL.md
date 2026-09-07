---
name: module-dependency-graph
description: Build evidence-backed repository, project, module and external-package dependency graphs and identify cycles and migration candidates without inventing call targets.
---

# Module Dependency Graph

## Workflow

1. Create Repository, Project and ExternalPackage nodes from snapshot/build evidence.
2. Add `CONTAINS` and build-level `DEPENDS_ON` edges with descriptor path and coordinate evidence.
3. Resolve internal project edges only when exact coordinates match.
4. Calculate strongly connected components and flag multi-project cycles.
5. Calculate coupling from observed edges and list low-coupling migration candidates.
6. Keep build-level and source-level graphs distinguishable.
7. Route `IMPORTS`, `REFERENCES`, `IMPLEMENTS`, `EXTENDS` and `CALLS` extraction to Batch 2 language adapters.
8. Preserve unresolved edges instead of creating guessed targets.

## Hard boundaries

- Every critical edge requires an evidence path/location.
- Never infer a call target from a same-named method or file.
- A missing source semantic graph is `unresolved`, not an empty proven graph.

## Acceptance

The graph is deterministic, cycles are explicit, internal/external dependencies are distinct, and no semantic edge lacks parser evidence.

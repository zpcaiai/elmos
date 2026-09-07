# ADR-0015: Static health check and approved build evidence

Status: Accepted

## Decision

Batch 3 separates deterministic static discovery from commands that execute a customer build. Static discovery parses Maven XML with external entities disabled, reads Gradle declarations without evaluating build scripts, scans bounded Java sources, and binds every result to an immutable Snapshot.

Declared dependencies are not described as a complete dependency graph. Transitive dependencies, effective plugins, coverage, and runtime behavior require artifacts from an approved Workspace build. Until attached, those conclusions are `INCONCLUSIVE`.

## Consequences

- Health checks remain safe on untrusted source.
- Reports preserve partial value without converting missing execution evidence into a pass.
- Maven and Gradle execution remains under the Batch 2 Workspace boundary.


# Incremental Parsing, Semantic Index, Impact Analysis, and Test Selection

- Skill: `elmos-incremental-semantic-index`
- Priority: `P1`
- Phase: `G4`
- Dependencies: `elmos-repository-snapshot-workspace`, `elmos-content-addressed-cache`, `elmos-reproducible-toolchain`

## Objective

Recompute only affected source, symbols, IR, generated files, builds, and tests while preserving the correctness conclusion of a full run.

## Task groups

### Merkle changes

- [ ] `ELMOS-INC-001` Generate Merkle tree for every source snapshot.
- [ ] `ELMOS-INC-002` Detect add, modify, delete, move, permission, and type changes.
- [ ] `ELMOS-INC-003` Reuse identical blobs after moves.
- [ ] `ELMOS-INC-004` Version/digest eLMOS ignore rules independently of .gitignore.
- [ ] `ELMOS-INC-005` Produce changed-file and changed-module manifests.

### Incremental syntax

- [ ] `ELMOS-INC-006` Use Tree-sitter or equivalent incremental CST for supported languages.
- [ ] `ELMOS-INC-007` Include grammar version/options in parse cache key.
- [ ] `ELMOS-INC-008` Persist parse trees by digest and reparse only changed files.
- [ ] `ELMOS-INC-009` Preserve byte/line/column mapping and syntax-error nodes.
- [ ] `ELMOS-INC-010` Diagnose encoding, generated code, and parser recovery ambiguity.

### Semantic queries

- [ ] `ELMOS-INC-011` Define query keys and exact input dependencies.
- [ ] `ELMOS-INC-012` Reuse results when dependencies are unchanged.
- [ ] `ELMOS-INC-013` Invalidate only transitive dependents.
- [ ] `ELMOS-INC-014` Detect cycles, query explosions, nondeterministic ordering, and invalid cache.
- [ ] `ELMOS-INC-015` Parallelize independent modules and record hit/miss/recompute reason.

### Symbol and domain graph

- [ ] `ELMOS-INC-016` Define stable language-qualified symbol IDs including module, namespace, signature, and generic arity.
- [ ] `ELMOS-INC-017` Index definitions, references, calls, inheritance, implementation, reads, writes, publishes, subscribes, database queries, API exposure, configuration use, and module dependencies.
- [ ] `ELMOS-INC-018` Map routes to handlers/contracts.
- [ ] `ELMOS-INC-019` Map code to tables/columns, messages, configuration, services, and files.
- [ ] `ELMOS-INC-020` Store versioned graphs in PostgreSQL initially and expose a measured upgrade boundary.

### Impact analysis

- [ ] `ELMOS-INC-021` Compute direct/transitive symbol impact.
- [ ] `ELMOS-INC-022` Propagate across API, database, message, serialization, security, transaction, and configuration.
- [ ] `ELMOS-INC-023` Map impacted symbols to target generation and validation actions.
- [ ] `ELMOS-INC-024` Explain inclusion with graph paths.
- [ ] `ELMOS-INC-025` Escalate reflection, dynamic import, code generation, native calls, and framework magic conservatively.

### Test selection

- [ ] `ELMOS-INC-026` Build test-to-code maps from static references, coverage, framework metadata, and runtime traces.
- [ ] `ELMOS-INC-027` Select affected unit/integration tests and record why.
- [ ] `ELMOS-INC-028` Escalate public contract, persistence, security, concurrency, build-tool, or unknown changes to broader suites.
- [ ] `ELMOS-INC-029` Regularly compare incremental selection with full-suite results and fail on missed regressions.

### Metrics

- [ ] `ELMOS-INC-030` Measure parse, query, IR, build, and test cache hit.
- [ ] `ELMOS-INC-031` Measure unaffected work rerun after one-file changes.
- [ ] `ELMOS-INC-032` Benchmark a goal of no more than ten percent unnecessary reprocessing for representative local changes.
- [ ] `ELMOS-INC-033` Record false-negative and false-positive impact selections.

## Validation

- [ ] Run file, symbol, signature, API, database, message, configuration, build-file, and dependency changes.
- [ ] Compare every incremental result to full recomputation.
- [ ] Test reflection, dynamic loading, generated code, cycles, and syntax errors.
- [ ] Change parser/compiler versions and invalidate caches.

## Exit gate

- [ ] Local changes avoid full recomputation when safe.
- [ ] Incremental/full runs reach the same conclusions.
- [ ] Every selected/escalated test has an explainable path.
- [ ] Unknown dynamic behavior is conservative and visible.

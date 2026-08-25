---
name: elmos-incremental-semantic-index
description: Implement Merkle change detection, incremental CST/AST, dependency-tracked
  semantic queries, symbol graphs, precise invalidation, and conservative test selection.
version: 1.0.0
priority: P1
phase: G4
dependencies:
- elmos-repository-snapshot-workspace
- elmos-content-addressed-cache
- elmos-reproducible-toolchain
---

# Incremental Parsing, Semantic Index, Impact Analysis, and Test Selection

## Objective

Recompute only affected source, symbols, IR, generated files, builds, and tests while preserving the correctness conclusion of a full run.

## Use this skill when

Use this skill when implementing, repairing, reviewing, validating, or productionizing the **Incremental Parsing, Semantic Index, Impact Analysis, and Test Selection** capability in an eLMOS repository. Invoke the program orchestrator first for work spanning multiple skills.

## Dependencies

- `elmos-repository-snapshot-workspace`
- `elmos-content-addressed-cache`
- `elmos-reproducible-toolchain`

Do not mark this skill complete until required dependency contracts are present and their blocking gates pass. A dependency can be implemented in the same change only when the plan preserves reviewable boundaries.

## Non-negotiable constraints

- Continuously compare incremental results with full recomputation.
- When impact cannot be proven, broaden scope conservatively.
- Compiler-native semantic binding is authoritative where syntax-only parsing is insufficient.

## Required inputs

- Current and previous snapshot Merkle trees.
- Grammar/compiler versions.
- Build/module graphs, runtime traces, test coverage, APIs, database, messages, and configuration.

## Required outputs

- `Changed-file/symbol manifests.`
- `Incremental parse and semantic query cache.`
- `Cross-language symbol/domain graph.`
- `Impact and selected-test manifests.`

## Repository discovery

Before editing:

1. Locate `AGENTS.md`, `CLAUDE.md`, repository-local Skills, architecture decision records, manifests, schemas, migrations, and build commands.
2. Identify actual control-plane, workflow, runner, engine, web, database, object-store, policy, telemetry, and test modules; do not assume the reference layout exists.
3. Search for existing contracts and implementations before creating duplicates.
4. Record current behavior, known gaps, security boundaries, external side effects, and the exact validation commands that are available.
5. Create or update a durable implementation plan from `templates/IMPLEMENTATION-PLAN.yaml`.

## Execution workflow

1. Select the smallest dependency-resolved vertical slice.
2. Freeze input snapshots, schema/toolchain/policy versions, and rollback boundaries.
3. Implement contract/schema changes before consumers, using backward-compatible transitions.
4. Implement production behavior, authorization, idempotency, telemetry, audit, failure handling, tests, documentation, and runbooks together.
5. Execute focused tests, integration tests, race/failure tests, security tests, and clean-environment reproduction as applicable.
6. Save large outputs by digest; record commands, results, durations, cost, evidence, and residual risk.
7. Report autonomous **system wall-clock runtime** separately from human-equivalent engineering/review effort.
8. Never claim production completion from generated files or static validation alone.

## Implementation checklist

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

## Required artifacts

At minimum, produce or update:

- Versioned contracts and schemas.
- Database migrations and compatibility/rollback notes where state changes.
- Production implementation with explicit authorization, idempotency, retries, cancellation, and failure classification as applicable.
- Unit, integration, end-to-end, race/failure, and security tests appropriate to risk.
- OpenTelemetry instrumentation, operational metrics, alerts, and runbooks for production components.
- Audit/evidence records with immutable input and output digests.
- Updated architecture and operational documentation.
- Task report based on `templates/TASK-REPORT.md`.

## Validation

- [ ] Run file, symbol, signature, API, database, message, configuration, build-file, and dependency changes.
- [ ] Compare every incremental result to full recomputation.
- [ ] Test reflection, dynamic loading, generated code, cycles, and syntax errors.
- [ ] Change parser/compiler versions and invalidate caches.

Run repository-native format, lint, typecheck, unit, integration, packaging, and security commands. Also run the package validators when Skill content or schemas change:

```bash
python3 scripts/validate_skill_bundle.py
python3 scripts/validate_json_schemas.py
python3 -m unittest discover -s tests -v
```

## Definition of done

- [ ] Local changes avoid full recomputation when safe.
- [ ] Incremental/full runs reach the same conclusions.
- [ ] Every selected/escalated test has an explainable path.
- [ ] Unknown dynamic behavior is conservative and visible.

Additionally:

- [ ] No placeholder, TODO-only, mock-only, or documentation-only implementation is counted as production completion.
- [ ] All modified public contracts are versioned and compatibility-tested.
- [ ] All side effects are idempotent or reconciled.
- [ ] Critical actions are authorized, audited, and observable.
- [ ] Evidence identifies exact source, toolchain, rule/model/policy, commands, results, and residual risk.
- [ ] Static bundle validation is described accurately as structural validation only.

## Failure handling and handoff

Classify failures as `ENVIRONMENT`, `DEPENDENCY`, `CODE`, `POLICY`, `SECURITY`, `DATA`, `CAPACITY`, `PROVIDER`, or `UNKNOWN`. Preserve successful checkpoints. Put ambiguous side effects in `UNKNOWN_RESULT`/`MANUAL_RECOVERY`; reconcile before retrying. Update the implementation plan with status, commit, commands, measured wall-clock duration, cost, evidence digest, blockers, and the next dependency-resolved task.

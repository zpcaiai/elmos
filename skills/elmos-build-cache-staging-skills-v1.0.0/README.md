# ELMOS Build Cache, File Staging & Recovery Skills Package

Version **1.0.0** — 2026-08-19

This package adds a production-grade cache, durable workspace, intermediate-state, checkpoint, recovery, and atomic publication subsystem to ELMOS. It follows the existing convention:

```text
agent-skills/runtime/<skill-name>/SKILL.md
```

## Scope

The package covers:

- deterministic repository snapshots and Merkle trees;
- content-addressable storage and Action Cache;
- explainable ActionKey fingerprinting;
- semantic/public-interface hashing and incremental conversion DAGs;
- **durable staging of every file generated during complete-project conversion**;
- atomic file writes, sealing, CAS promotion, complete-tree publication, rollback, and conflict handling;
- persistence of CST/AST, symbol/type/call/dataflow graphs, Semantic IR, mapping plans, generated fragments, patches, build outputs, tests, repair candidates, and certification evidence;
- run journals, worker leases, pause/resume/cancel, checkpoints, and crash recovery;
- remote shared cache and native build-cache adapters;
- tenant isolation, provenance, secret scanning, GC, observability, performance tuning, chaos tests, and production certification.

It is language-agnostic and explicitly covers ELMOS conversion profiles involving Java, Kotlin, Python, C#, Go, Rust, C++, PHP, TypeScript/React, JavaScript, Objective-C, Swift, and Flutter/Dart.

## Package contents

- **24 implementation skills** in `agent-skills/runtime/`.
- `manifest.json`: skill registry and dependency DAG.
- `AGENTS.md`: mandatory execution rules for Codex/Claude Code.
- `docs/source-packages/elmos-build-cache-staging-spec.md`: authoritative subsystem specification.
- `references/`: JSON Schemas, SQL, OpenAPI, state machines, and storage contracts.
- `templates/`: local/production configuration and manifest examples.
- `reference-implementation/`: standard-library Python reference for canonical keys, local CAS, append-only journal, atomic staging, sealing, and promotion.
- `tests/acceptance/`: production acceptance matrix.
- `install.sh` and `scripts/install.py`: installers for Codex and Claude Code.
- `validate.sh` and `scripts/validate_package.py`: structure, DAG, schema, checksum, and reference-test validation.

## Recommended implementation order

1. **P0 foundation** — architecture, metadata database, API/CLI.
2. **P1 local cache** — snapshots, CAS, ActionKey, Action Cache.
3. **P2 staging** — generated-file workspace, atomic writes, overlays, intermediate manifests.
4. **P3 incremental** — Stage Contracts, semantic hashing, minimal execution closure.
5. **P4 recovery** — journal, leases, checkpoints, conflict/merge.
6. **P5 distributed** — remote cache and native build adapters.
7. **P6 assurance** — security, retention, observability, performance, chaos, certification.
8. **P7 rollout** — staging-first migration, shadow comparison, progressive reuse, end-to-end release.

## Install

```bash
./install.sh --all
```

Codex only:

```bash
./install.sh --codex
```

Claude Code only:

```bash
./install.sh --claude
```

Custom destination:

```bash
./install.sh --dest /path/to/skills
```

Existing skill directories are rejected unless `--overwrite` is supplied.

## Validate

```bash
./validate.sh
```

## Generated-file lifecycle

```text
RESERVED → WRITING → SEALED → CAS_PROMOTED → TREE_INCLUDED → PUBLISHED
                 ↘ ABORTED
                 ↘ QUARANTINED
```

A file is not complete merely because it exists. Only a sealed, digest-verified file linked to a manifest can be reused or checkpointed. Final output is exposed only after the **entire generated project tree** is assembled and validated.

## Workspace model

```text
.elmos/workspaces/<tenant>/<project>/<run_id>/
├── control/
├── source/                  # immutable snapshot
├── overlay/                 # writable copy-on-write layer
├── scratch/                 # disposable
├── generated/
│   ├── pending/             # active writes
│   └── sealed/              # immutable verified files
├── artifacts/
├── checkpoints/
├── quarantine/
├── publish/                 # complete versioned output trees
└── logs/
```

## Storage model

- Immutable bytes and manifests: local CAS and/or S3/MinIO.
- Mutable state: SQLite WAL locally; PostgreSQL in production.
- Optional Redis: hot index, leases, coordination—not artifact truth.
- Published output: versioned complete-tree directories with atomic pointer/rename promotion.

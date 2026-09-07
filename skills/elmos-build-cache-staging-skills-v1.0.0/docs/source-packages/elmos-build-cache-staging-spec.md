# ELMOS Build Cache, Generated-File Staging, and Recovery Specification

## 1. Purpose

ELMOS converts complete projects across Java, Kotlin, Python, C#, Go, Rust, C++, PHP, TypeScript/React, JavaScript, Objective-C, Swift, and Flutter/Dart. A conversion run may scan thousands of files, capture a baseline, parse CST/AST, recover symbols and type/call/dataflow graphs, build Semantic IR, select migration rules, invoke coding models, generate a target project, compile, test, repair, validate behavior, and issue production evidence.

Repeating all work after a small edit or service interruption wastes model tokens, CPU, compiler time, network transfer, and operator attention. This subsystem provides deterministic cache reuse and durable execution without weakening correctness.

## 2. Core design

The authoritative flow is:

```text
Repository snapshot
  → discovery and normalization
  → syntax and semantic analysis
  → Semantic IR
  → target/migration plan
  → cache resolution
  → isolated workspace allocation
  → generation into staging
  → file seal and CAS promotion
  → complete target-tree assembly
  → compile/test/behavior validation
  → repair and revalidation
  → evidence bundle
  → atomic publication
```

The system separates:

| Data class | Authoritative store | Examples |
|---|---|---|
| Immutable bytes | Local CAS and/or S3/MinIO | source snapshots, AST, IR, source, archives, build outputs |
| Immutable manifests | CAS plus searchable metadata | ActionResult, file tree, checkpoint, evidence |
| Mutable orchestration state | SQLite WAL locally; PostgreSQL in production | runs, nodes, retries, leases, staged-file states |
| Hot coordination | Optional Redis | short leases, hot indexes, rate limiting, queues |
| User-visible output | Versioned publish tree | complete converted project and evidence |

Redis must never be the only store for artifacts or recoverable run truth.

## 3. Workspace and generated-file staging

Every run receives a scoped workspace:

```text
.elmos/workspaces/<tenant>/<project>/<run_id>/
├── control/
│   ├── run.json
│   ├── plan.json
│   ├── journal.ndjson
│   └── leases/
├── source/                 # immutable materialized source snapshot
├── overlay/                # writable copy-on-write conversion layer
├── scratch/                # disposable temporary files
├── generated/
│   ├── pending/            # active temporary writes
│   └── sealed/             # immutable digest-verified files
├── artifacts/              # materialized CAS objects
├── checkpoints/            # checkpoint manifests/local indexes
├── quarantine/             # ambiguous, corrupt, conflicting, secret-bearing output
├── publish/                # complete versioned target trees
└── logs/                   # redacted structured logs
```

A worker can write only to explicitly mounted roots. The source snapshot is read-only. The worker cannot write directly to the source repository or the live final output.

### 3.1 File classes

- `SCRATCH`: disposable parser/compiler/model temp data; not checkpointed by default.
- `STAGED_INTERMEDIATE`: durable intermediate state needed by later stages.
- `SEALED_ARTIFACT`: immutable, digest-verified file linked to a producer and manifest.
- `PUBLISH_CANDIDATE`: sealed artifact included in a complete target-tree manifest.
- `PUBLISHED`: file reachable from the active published tree.
- `QUARANTINED`: corrupt, ambiguous, conflicting, secret-bearing, or undeclared file.

### 3.2 Staged-file state machine

```text
RESERVED
   |
   v
WRITING -- error/stale lease --> ABORTED or QUARANTINED
   |
   v
SEALED -- digest/schema/security failure --> QUARANTINED
   |
   v
CAS_PROMOTED
   |
   v
TREE_INCLUDED
   |
   v
PUBLISHED
```

Required fields:

- `tenant_id`, `project_id`, `run_id`, `node_id`, `attempt`;
- `staged_file_id`, `logical_path`, file class, status;
- internal temporary and sealed paths;
- `lease_id`, monotonic `lease_epoch`, optimistic `version`;
- expected/actual size, media type, artifact kind;
- SHA-256 digest and CAS reference;
- ActionKey, source snapshot, stage ID/version;
- source-map and dependency references;
- validation level and secret-scan status;
- quarantine reason;
- created/sealed/promoted/tree-included/published timestamps.

A file is never complete merely because it exists on disk.

## 4. Atomic file-write protocol

1. Normalize the logical path.
2. Reject absolute paths, traversal, unsafe Unicode, case collisions, reserved device names, and symlink escapes.
3. Reserve the logical path transactionally with node, attempt, lease epoch, media type, and overwrite/merge policy.
4. Create an exclusive no-follow temporary file in the same filesystem as the sealed destination.
5. Stream bytes while computing digest and size.
6. Enforce per-file and per-workspace quotas.
7. Flush and `fsync` the file.
8. Validate expected digest, size, media/schema policy, and secret policy as applicable.
9. Recheck the worker lease epoch and staged-file version.
10. Atomically rename into `generated/sealed/`.
11. `fsync` the parent directory where supported.
12. Compare-and-swap the metadata state to `SEALED`.
13. Promote the content to CAS using create-if-absent.
14. Verify the canonical CAS digest.
15. Attach the CAS reference and set `CAS_PROMOTED`.

For cross-device moves, copy into a temporary file in the destination filesystem, verify digest, `fsync`, and rename there.

## 5. Complete project-tree publication

ELMOS must not publish target files one by one into a live output folder. It must:

1. build a file-tree manifest from sealed artifacts;
2. reject duplicate, traversal, reserved, symlink-escape, and case-colliding logical paths;
3. resolve generated/user ownership and merge conflicts;
4. materialize a complete versioned directory under `publish/<run_id>/<tree_digest>/`;
5. verify all required file digests;
6. bind compile, test, behavior, and security evidence to the exact tree digest;
7. atomically rename the complete directory or switch a versioned `current` pointer;
8. retain the previous complete tree for rollback according to policy.

Readers must observe either the old complete tree or the new complete tree, never a partial mixture.

## 6. Recovery of staged output

After process restart, host failure, or lease expiry:

- `RESERVED` with no active owner: release or reassign after timeout.
- `WRITING` with stale lease: never trust as complete; delete or quarantine partial bytes.
- `SEALED`: verify digest, permissions, and metadata; continue CAS promotion idempotently.
- `CAS_PROMOTED`: verify artifact reference; continue tree inclusion.
- `TREE_INCLUDED`: reconstruct the publish candidate and continue validation/publication.
- `PUBLISHED`: leave unchanged; verify active pointer if policy requires.
- undeclared files: quarantine and emit a contract violation.

Recovery must converge or terminate with a bounded, explicit failure. It must not loop indefinitely.

## 7. Project snapshots and Merkle trees

The snapshot engine records:

- raw byte digest;
- normalized syntax digest;
- semantic digest where available;
- executable bit and symlink policy;
- dependency lockfile digests;
- submodule/vendor roots;
- ignore/normalization policy version;
- directory/module Merkle nodes.

Absolute machine paths, access timestamps, run IDs, and UI state are excluded.

Small changes alter only affected Merkle branches. Renames can be detected through content identity.

## 8. ActionKey

A stage fingerprint is canonical JSON containing all result-affecting inputs:

```text
ActionKey = SHA256(canonical_json({
  stage_id,
  stage_version,
  stage_contract_schema,
  input_artifact_digests,
  source_semantic_digest,
  dependency_public_interface_digests,
  target_language,
  target_framework,
  target_runtime,
  target_triple,
  rule_pack_digest,
  toolchain_digest,
  compiler_flags,
  dependency_lock_digests,
  declared_environment,
  prompt_template_digest,
  model_snapshot_digest,
  decoding_parameters,
  tool_output_digests,
  feature_flags
}))
```

Excluded dimensions include absolute workspace path, run ID, wall-clock time, host name, temporary filename, and unrelated environment values.

The system stores an explainable fingerprint document so operators can identify the exact miss dimension.

## 9. Cache correctness and validation levels

An Action Cache entry references an immutable ActionResult manifest and has one validation level:

- `UNVERIFIED`
- `COMPILE_VERIFIED`
- `TEST_VERIFIED`
- `BEHAVIOR_VERIFIED`
- `PRODUCTION_CERTIFIED`
- `QUARANTINED`

A consumer declares a minimum validation level. Lower, expired, revoked, cross-tenant, trust-mismatched, or schema-incompatible entries are misses.

If one ActionKey produces two different result-manifest digests, both results are quarantined and the stage is marked potentially nondeterministic.

Deterministic failures may be negative-cached with a short bounded TTL. Transient network, quota, availability, or rate-limit failures must not be treated as deterministic.

## 10. Exact cache versus semantic reuse

Exact cache requires the same ActionKey and may directly restore compatible output.

Semantic reuse may retrieve similar:

- Semantic IR patterns;
- framework mapping plans;
- repair patches;
- test templates;
- migration decisions.

Semantic reuse is candidate-only. Candidate output must receive a new exact ActionKey and fresh compile/test/behavior validation before trusted use.

## 11. Semantic and public-interface hashing

The system separates:

- raw implementation digest;
- normalized syntax digest;
- method/body implementation digest;
- public API/ABI digest;
- route/event/schema/database digest;
- UI component/platform-capability digest;
- Semantic IR digest.

A private implementation change should not invalidate unrelated dependents. Public type, route, event, serialized field, ABI, schema, or framework-capability changes propagate through relevant graph edges. Unsupported cases use conservative invalidation.

## 12. Incremental conversion DAG

DAG node granularities may include:

- repository;
- module/package;
- file;
- class/type;
- function/method;
- IR partition;
- generated file;
- compile target;
- test shard;
- certification evidence unit.

Every node declares:

- input/output artifact schemas;
- fingerprint dimensions;
- determinism class;
- cache mode and validation floor;
- workspace mounts;
- resources;
- side effects and idempotency;
- checkpoint policy.

The planner computes the minimal affected closure before scheduling and records why each node is executed, restored, skipped, or invalidated.

## 13. Run journal, leases, and state

Node states include:

```text
PENDING
READY
RUNNING
CHECKPOINTED
SUCCEEDED
FAILED_RETRYABLE
FAILED_FINAL
PAUSED
CANCELED
RECOVERING
STALE
```

Worker ownership uses `lease_id` plus monotonic `lease_epoch`. A stale worker cannot commit after recovery changes the epoch.

Events include sequence number, actor, run/node/attempt, lease epoch, payload digest, and correlation IDs. Duplicate delivery is idempotent. Materialized state can be rebuilt from the journal plus immutable manifests.

## 14. Checkpoints

A checkpoint manifest references:

- run/node/attempt and lease epoch;
- source snapshot and ActionKey;
- completed partitions;
- sealed/promoted artifacts;
- staged-file states;
- side-effect receipts;
- journal sequence boundary;
- dependency checkpoint digests;
- resume cursor;
- compatibility profile.

Checkpoint commit is atomic with node state. Resume validates every relevant version and digest. Unsealed partial files cannot enter a checkpoint.

## 15. Local and production profiles

### Local profile

- filesystem CAS;
- SQLite WAL metadata;
- file/database leases;
- reflink/hardlink materialization with copy fallback;
- optional zstd compression;
- no mandatory network dependency.

### Production profile

- S3/MinIO immutable objects;
- PostgreSQL metadata and transactional outbox;
- optional Redis for leases, hot index, rate limiting, and coordination;
- Temporal/NATS/Kafka or existing ELMOS durable orchestrator;
- sandboxed workers;
- OpenTelemetry traces and Prometheus-compatible metrics.

## 16. Native build-cache adapters

Adapters may integrate:

- Gradle Build Cache and Maven repositories;
- MSBuild incremental build and NuGet cache;
- Cargo and sccache;
- CMake/Ninja with ccache or sccache;
- TypeScript incremental state, pnpm store, Vite cache;
- Python wheel/download caches;
- Xcode DerivedData and Swift module cache;
- Flutter/Dart pub cache.

Native caches accelerate underlying builds but never replace ELMOS ActionResults, manifests, or evidence. Clean-room rebuilds remain mandatory certification checks.

## 17. Security and provenance

Required controls:

- tenant/project/trust namespace isolation;
- authorization on metadata and blob access;
- no-follow file operations;
- sandboxed roots and quotas;
- encryption at rest and in transit;
- secret scanning before remote upload and publication;
- signed provenance binding digest, producer, ActionKey, validation level, scope, and time bounds;
- untrusted branch/fork outputs blocked from official namespaces;
- revocation propagation to dependent cache entries, checkpoints, trees, and certificates;
- archive-bomb and executable policies;
- audit events for sensitive reads and destructive changes.

## 18. Retention and garbage collection

Protected roots include:

- active runs;
- checkpoints;
- pins;
- published trees;
- valid production certificates;
- legal/audit holds.

GC uses mark-and-sweep, a grace period, idempotent deletion receipts, and orphan reconciliation. Eviction value should combine recomputation cost, expected reuse, storage cost, restore cost, validation level, artifact size, and quota pressure. TTL alone is insufficient.

## 19. Observability and hit-rate tuning

Required measurements:

- local/remote/partial hit rate by stage;
- CPU, wall-clock, compiler, and model-token savings;
- bytes stored, deduplicated, restored, uploaded, downloaded, and evicted;
- lookup/materialize/write/seal/promote/checkpoint/resume/publish latency;
- miss reasons by fingerprint dimension;
- stale leases and recovery attempts;
- digest mismatches, corruption, nondeterminism, and quarantine counts;
- workspace bytes/files/inodes and quota failures.

Do not use source paths, code, raw prompts, secrets, or full digests as unbounded metric labels.

Benchmark scenarios:

1. identical rerun;
2. formatting/comment-only change;
3. private body change;
4. public API change;
5. route/event/database/schema change;
6. rule-pack upgrade;
7. compiler/SDK upgrade;
8. dependency lock change;
9. prompt/model snapshot change;
10. remote outage and recovery.

## 20. Chaos and certification

Fault injection must cover:

- process kill and restart;
- host reboot simulation;
- disk full and inode exhaustion;
- partial write and `fsync` failure;
- permission loss;
- network partition;
- duplicate event delivery;
- stale lease;
- clock skew;
- corrupt object;
- remote metadata/blob inconsistency;
- kill before/after reservation, write, seal, CAS put, metadata commit, checkpoint, remote publish, and final tree switch.

Certification must compare clean, cached, resumed, and failure-injected output-tree digests and bind fresh security, determinism, recovery, behavior, and performance evidence to exact artifacts.

## 21. Minimum release gates

1. Cross-platform deterministic snapshot fixtures pass.
2. CAS concurrent-write, interruption, and corruption tests pass.
3. ActionKey dimension tests pass.
4. Staged-file kill-point tests pass at all critical boundaries.
5. No partial final file is exposed.
6. Checkpoint resume matches clean-run output digest for deterministic fixtures.
7. Stale-worker and duplicate-message tests pass.
8. Tenant isolation, secret leakage, and cache-poisoning tests pass.
9. No-change and small-change benchmarks meet declared budgets.
10. A production certificate binds to exact artifacts, scope, expiry, and fresh evidence.

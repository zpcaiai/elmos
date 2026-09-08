# P0–P2 concurrency implementation ledger

Base: `660c52a8cc3687c94dcc701a7eb77fb67a3e307a`. Implementation is isolated
in `codex/concurrency-p0-p2-20260906`; shared-worktree edits are not inputs.

| Order | Deliverable | State |
| --- | --- | --- |
| 1 | Project Graph capture reuse with byte-level drift verification | LOCAL_VERIFIED: 39 tests, Ruff |
| 2 | Workspace-scoped Git locking and concurrency regressions | LOCAL_VERIFIED: 11 tests |
| 3 | Existing PostgreSQL admission/lease adapter and Node hosted selection | LOCAL_VERIFIED: fresh PostgreSQL migration replay + 10 tests, 3 Node tests |
| 4 | Streaming snapshot/CAS and per-object cache coordination | LOCAL_VERIFIED |
| 5 | Existing Rust scanner/CAS integration with parity and bounded buffers | LOCAL_VERIFIED; new file ABI opt-in |
| 6 | Existing Go runner/supervisor, bounded toolchain execution and logs | LOCAL_VERIFIED; host opt-in |
| 7 | Profiles, load/correctness checks and measured language-boundary decision | LOCAL_VERIFIED |

Checks must exercise real code and preserve graph bytes, tenant scope,
durability, cancellation, fencing, parser errors and independent verification.
Performance measurements are local engineering evidence; production workload
and independent performance evidence are not yet collected. No C/C++ rewrite
is presumed necessary until profiles justify a specific boundary.

## 1–2 evidence

- Initial Project Graph/pipeline/snapshot run: 39 passed in 723.89 s, Python
  3.12.12 and the existing `libelmos_native.dylib`. Final newly-built-library
  run: 38 passed and one fault-injection fixture failed in 3769.81 s under
  heavy host contention. That fixture's real `tsc` process failed before its
  source mutation executed (`late-resource.json` was absent), so the intended
  drift never occurred. The injection now runs in `finally`, retaining the
  real verifier and every original rejection/cleanup assertion. Its exact
  focused replay passed in 47.21 s. All 39 distinct cases are covered; this is
  not represented as a clean single-invocation final run. Graph bytes and drift
  checks are preserved; final verification hashes without retaining bytes.
- Integrations: 10 Git workspace tests and 1 lock lifecycle test passed. Exercises
  16 competing creates against capacity 3 and same-workspace blocking alongside
  independent-workspace progress across two service instances.
- Workspace locking is JVM-wide, keyed by canonical root and UUID, with safe
  waiter retirement and reentry. It does not claim cross-host Git worktree safety.

## 3 architecture correction

The current baseline already has `ExecutionJobPort`, `JdbcExecutionJobStore`,
the PostgreSQL V57/V80 queue and a Node control-plane client. Reuse these authorities;
do not create another queue/schema or add direct database credentials to the BFF.
The existing production queue policy was not wired into the hosted selector.
V82 addresses unlocked tenant claim counters and lease lifecycle lock order.
Existing filesystem leases remain bounded local executor coordination, not the
distributed scheduling authority. Hosted provider/deployment evidence is NOT_RUN.

Final PostgreSQL 17.5 qualification used a new disposable UTF-8 database and
replayed all 82 migrations. Seven live queue tests and three JDBC error-mapping
tests passed. New scenarios cover eight competing runners against tenant
capacity one, bad lease credentials, heartbeat, expired completion rejection,
busy counter skip-without-wait and capacity restoration after rollback. The
fixture capability is unique per test; a shared capability would legitimately
claim other tests' queued jobs and is not a valid isolation oracle.
Node's actual hosted selector and policy tests: 3 passed; routes using this
selector cannot silently downgrade production to filesystem scheduling if the
hosted flag is false/unset. This is not a rewrite of every local translation
executor into a hosted route; local coordination is not a distributed authority.

## 4 streaming and cache coordination

- The actual snapshot capture and artifact read/write adapters now use owned,
  verified disk spools. Public byte-array APIs remain backward compatible.
  Snapshot manifests, archive digest, source lease checks and tenant/resource
  authorization are retained. Java local disk and S3 have streaming overrides;
  third-party/encrypted stores using the default compatibility methods may still
  buffer whole values and are not represented as streaming-qualified.
- Multipart buffers retain the existing operator-owned `partSizeBytes` budget
  (MinIO default 8 MiB); large valid configurations remain compatible. The
  streaming path does not invent a smaller hard limit for existing settings.
- Shared-tier transfer and write-back operations coordinate per digest, not with
  a cache-wide remote-I/O lock. Cache-admitted read-through misses coalesce;
  unrelated remote misses advance independently. Streaming/oversized misses
  may refetch if not admitted to L1. L1 eviction/admission bookkeeping still uses
  its consistency lock, including local I/O; no lock-free cache claim is made.
- Targeted reactor exact breakdown: CAS 43/43; snapshot
  27 passed + 2 skipped; integrations 31/31 (20 artifact, 10 Git, 1 locks).
  Targeted total: **101 passed, 2 skipped**.
- Final multipart-configuration compatibility rerun: 18 S3 tests passed,
  including the new 128 MiB configured-part-budget regression through both
  write ports. Distinct covered cases across the final selection: 102 passed,
  2 platform skips (do not double-count repeated S3 tests).
- `StreamingHeapProbe`: real 128 MiB pseudo-random file, `-Xmx64m`, snapshot
  archive 134,221,331 bytes, local durable CAS and verified read completed with
  exact digest parity in 27,159 ms. This verifies heap boundedness, not an SLO.

## 5 native integration and language decision

- Extend the existing Rust core with `elmos_cas_put_fd`, using bounded 64 KiB
  reads from a borrowed descriptor without changing its offset. Drift/quota/
  digest failures precede publication. Existing compressed winners retain their
  encoding metadata. Native errors never silently downgrade to Python.
- Python byte FFI removes one redundant copy. Compression, decompression,
  restore and verification use bounded chunks; readers verify before exposing
  any bytes, and staging I/O failures do not quarantine healthy objects.
- Native core: 4 tests passed. Python storage/snapshot/action-cache/chaos
  selection: 76 passed, 3 existing environment/platform skips, with the newly
  built native library. Scope includes six new streaming/FFI regression tests.
- Existing Python skips remain explicit: cross-platform golden receipts are
  missing for macOS/Windows, and this filesystem cannot create the tested
  Unicode/case-collision pairs. The two Java skips require a symlink inode
  hard-link anchor unsupported on this host. No fixture baselines were weakened.
- `ContentAddressableStore(..., native_file_io=True)` explicitly enables the
  new file ABI. Default stays on bounded Python/hashlib: measured Rust file
  writes were slower on this host. No C/C++ replacement is justified by this
  profile, and no parser or semantic support claim is broadened.

## 6 runner integration

The existing Java Runner is the operational fleet client. The top-level Go
agent is an unintegrated prototype, not the production wire protocol. The new
Go `cmd/elmos-supervisor` is an optional local process adapter behind the Java
`ProcessRunner`; it does not replace credentials, admission, leases, sandbox
policy or artifact publication. See `apps/runner-agent/SUPERVISOR.md`.

- Lease capacity is reserved before HTTP claiming, transferred only on task
  submission, and released on error, empty response, late drain or shutdown.
- Bounded output capture and oversized-line rejection apply to both adapters.
  OS pipes provide backpressure; Go process groups support cancellation and
  ordinary descendant cleanup. Container cleanup remains engine-authoritative.
- Go race suite passed (original agent tests plus 3 supervisor tests). Java
  Runner self-test passed 112 checks; representative container test NOT_RUN.
  Actual Java subprocess tests passed with and without the Go adapter: eight
  worker invocations, 4 MiB outputs, long lines, scrubbed environment, timeout.

## 7 reproducible measurements

Raw results: `tools/performance/local-concurrency-profile.json`.
Three fresh-process rounds, 32 MiB CAS payload, 48-file graph; output identities
match across paths. macOS arm64, Python 3.12.12, shared busy development host.
The runs show substantial scheduling noise; do not extrapolate to production
or interpret three samples as a p95/p99 distribution.

| Kernel | Baseline median | Candidate median | Decision |
| --- | ---: | ---: | --- |
| Three graph builds vs one capture/materialization plus two byte-verification passes | 2.299 s | 0.400 s | Keep snapshot reuse; about 5.75x in this local sample |
| Python/hashlib streaming vs Rust file-descriptor CAS | 0.317 s | 1.984 s | Keep Python default; Rust explicit opt-in |

Python-tracked peak allocations: graph 1,248,145 -> 990,766 bytes; CAS 2,107,791
-> 6,438 bytes. Process RSS medians were 39.9 MB (Python) and 35.8 MB (Rust),
with substantial cross-run variation; tracemalloc
does not account for native allocations. No production throughput, multi-host
Git safety, independent verification, deployment or certification is claimed.

These are the final digest-bound profile results. The earlier exploratory run
(graph 9.09 -> 2.84 s, CAS 1.51 -> 4.44 s) led to the same default decisions;
its absolute timings were more affected by concurrent development workloads.

## Replay

Run from this worktree root with the intended Python 3.12 project venv available
as `ELMOS_TEST_PYTHON` and the release library as `ELMOS_NATIVE_LIB`.

```sh
cargo build --release --offline --manifest-path native/rust-core/Cargo.toml
cargo test --offline -p elmos-cas-core --manifest-path native/rust-core/Cargo.toml
PYTHONPATH=engines/build-cache-engine/src "$ELMOS_TEST_PYTHON" -m pytest engines/build-cache-engine/tests/test_cas.py engines/build-cache-engine/tests/test_cas_streaming.py engines/build-cache-engine/tests/test_snapshot.py engines/build-cache-engine/tests/test_snapshot_portability.py engines/build-cache-engine/tests/test_action_cache.py engines/build-cache-engine/tests/test_chaos.py
PYTHONPATH=engines/polyglot-route-engine/src "$ELMOS_TEST_PYTHON" -m pytest engines/polyglot-route-engine/tests/test_project_graph.py engines/polyglot-route-engine/tests/test_project_snapshot.py engines/polyglot-route-engine/tests/test_pipeline.py
mvn -q -o -f tools/performance/pom.xml -Dtest=TieredCasStoreTest,LocalDiskCasStoreTest,S3CasStoreTest,CasStreamingConcurrencyTest,DeterministicSnapshotArchiverTest,SnapshotCaptureServiceTest,CasBackedArtifactStoreTest,GitRepositoryWorkspaceServiceTest,WorkspaceLocksTest -Dsurefire.failIfNoSpecifiedTests=false test
"$ELMOS_TEST_PYTHON" tools/performance/run_java_probe.py
mvn -q -o -f apps/runner-agent/pom.xml test
"$ELMOS_TEST_PYTHON" tools/performance/concurrency_profile.py --rounds 3 --file-mib 32 --graph-files 48
```

For the real PostgreSQL tests, provide a **new disposable UTF-8 database** with
`ELMOS_EXECUTION_QUEUE_TEST_JDBC_URL`, `ELMOS_EXECUTION_QUEUE_TEST_DATABASE_USER`
and `ELMOS_EXECUTION_QUEUE_TEST_DISPOSABLE=true`, then run the persistence
`JdbcExecutionJobEnqueueConcurrencyLiveTest` and `JdbcExecutionJobStoreErrorMappingTest`.
This applies every migration; never point it at production. Node and Go replay
commands live in their module test files and `SUPERVISOR.md` respectively.

The dedicated local PostgreSQL instance used for this task was stopped and
`pg_ctl status` confirmed no server running. No production database, deployment,
shared-worktree changes, Git push or merge are part of this local qualification.

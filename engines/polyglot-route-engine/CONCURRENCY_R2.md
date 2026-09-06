# Round 2 bounded native/compute engineering evidence

Scope: base `9dd3567e7bcd9cfaa11cf9786cb4fbf92f486bce`, isolated
`codex/concurrency-round2-native-20260906`; no deployment or certification.
The async/backpressure and API-compatible incremental-refactor Skills informed
bounded submission, cancellation/cleanup, and exact protocol preservation.

## Implemented boundaries

* Captured native, validation, assembly, single-unit, React, Dart, Clang and
  toolchain-probe subprocesses use bounded concurrent pipe drainage. Default
  stdout/stderr limits are separately 16 MiB; Clang AST output is explicitly
  64 MiB. Exceeding a limit fails instead of accepting truncated JSON. Optional
  host-owned binary log handles receive/flushed chunks within the same cap;
  there is no global/raw tenant-source log sink.
* The common POSIX runner creates an isolated process group, waits for exit
  without reaping the leader, and cleans the group before releasing its PID.
  Darwin uses kqueue; Linux uses WNOWAIT. No drainage helper threads exist.
  Repeated timeout/flood and normal-exit descendant tests cover cleanup.
  This is **not a sandbox**: arbitrary session escape requires the host runner;
  Swift retains its specialized existing session-enumeration/reap protocol.
  Non-POSIX execution is explicitly unsupported, not silently degraded.
* ZIP construction, member digest validation and final archive hashing use
  64 KiB streams. Atomic output publication and pinned source descriptors
  preserve change detection. Published archive replacement and changes during
  source reads fail closed. The existing archive semantic evidence verifier
  still independently checks source and copied evidence, one unit at a time.
  A unit's structured evidence still requires bounded full-document parsing;
  this does not claim constant memory for arbitrarily large JSON evidence.
* `ExecutionBudget` limits running **and submitted** work to 1–8 workers,
  reduced by the host-selected memory reservation (default 512 MiB/worker).
  CLI defaults remain sequential. Results/checkpoints retain input order;
  failure cancels queued tasks and joins active tasks before cleanup.
  Reservations are scheduling estimates, **not RSS/cgroup enforcement**.
* TypeScript same-file batch analysis reuses the official compiler parse tree
  and one invocation-owned sealed private snapshot. Successes and domain errors
  match the single-function protocol. Two parser receipts retain all **four
  compiler-closure captures per batch**, rather than four per function. No
  mtime-only receipt shortcut or cross-tenant source cache was introduced.
* Exact toolchain selection and Java analyzer cold initialization are keyed
  single-flight. Existing live content/provenance validation stays in place;
  disabled/untrusted Kotlin artifact-cache behavior is not re-enabled.
* Graph semantic inventory binds through an existing path index instead of
  re-scanning all files for every inventory entry. Native loader initialization
  is synchronized; the native graph kernel is not promoted as semantic authority.
* CAS bytes reads/writes and file-descriptor writes have independent explicit
  native opt-ins. Python remains default; streams remain bounded Python.
  A selected native bytes write owns the hash (no duplicate Python prehash).
  Unavailable kernels may fall back, but native integrity errors do not.

## Focused validation

Use the repository's intended Python 3.12 interpreter, with `PYTHONPATH=src`
from each engine directory. No full multi-language pipeline matrix was started
by this worktree. Counts below are separate selections, not additive coverage.

| Selection | Result |
| --- | --- |
| `tests/test_process_io.py` | 12 passed, including real processes, byte caps, live logs, repeated cleanup |
| `tests/test_cas.py tests/test_cas_streaming.py` with native dylib configured | 23 passed, including backend-identical digest/dedup/quota ordering |
| project graph + snapshot focused selection | 26 passed |
| archive streaming + existing archived assembly evidence closure selection | 44 passed |
| resource budget + TypeScript batch + initial transport selection | 21 passed |
| final transport/resource/archive/preflight/assembly selected negatives | 28 passed |
| final TypeScript batch differential (`tests/test_typescript_batch.py`) | 5 passed, official Node/TypeScript toolchain |
| native cache/vendor/Swift/detached analyzer selection | 97 passed, 1 failed before fixture readiness; see below |

The existing Swift test
`test_swift_build_step_timeout_reaps_same_session_moved_process_group[exited-leader-held-pipes]`
failed twice at reading `parent.json`: its one-second timeout elapsed before
the two Python child processes established the target fixture state on this
heavily loaded host. That does **not** establish the exited-leader/held-pipe
semantic case passed. No assertions or timeout values were weakened. Parent
integration owns a separate readiness-barrier review and re-run for this case.

Replay the new tests (from `engines/polyglot-route-engine`):

```sh
PYTHONPATH=src /path/to/project/.venv/bin/python -m pytest tests/test_process_io.py tests/test_resource_budget.py tests/test_archive_streaming.py tests/test_typescript_batch.py -q
```

TypeScript success/error parity and receipt-count checks execute real official
compiler code. Scheduler migration-failure injection is explicitly a local
control-flow test, not source/target conversion certification. The ZIP 4 MiB
transport fixture proves exact legacy ZIP bytes; existing semantic-closure
tests independently cover evidence tampering and unsupported behavior.
Ruff passes for the polyglot source, new tests, CAS changes and profile script;
mypy passes for all 17 changed/reached polyglot source modules.

## CAS profile replay and results

`tools/performance/r2_native_profile.py` launches sequential fresh processes.
Each sample writes/reads an independent 8 MiB object and verifies the output
SHA outside the timed operation. Reports pin source files and native library.

```sh
python tools/performance/r2_native_profile.py --rounds 3 --file-mib 8 --native-library /absolute/path/libelmos_native.dylib --output /new/path/report.json
```

Historical write report: `tools/performance/r2_native_profile_20260906.json`.
Read-backend report: `tools/performance/r2_native_profile_reads_20260907.json`.
Each report binds its measured script/CAS revision, preserved in Git; later
additive read modes and over-budget compatibility changes do not retroactively
change that evidence. These samples configured no quota.

| API/backend | Observed median seconds, 3 samples |
| --- | ---: |
| Python bytes write | 0.051156 |
| Native bytes write | 3.439545 |
| Python file write | 0.244126 |
| Native file-descriptor write | 3.473490 |
| Python stream write | 0.258946 |
| Python bytes read | 0.413030 |
| Native bytes read | 3.585322 |

These are **LOCAL_EXECUTED_SELF_ATTESTED** samples on a shared, severely loaded
macOS ARM64 development host, not p95/p99, a speedup promise, or production SLO.
Python tracemalloc excludes native allocations; RSS includes inputs/runtime.
Lower traced memory must not be described as higher throughput. Native Rust
code was unchanged and its existing release dylib was independently hashed.
The evidence supports retaining explicit opt-ins, not a default Rust migration.
Cross-platform tests, representative concurrent load, independent verification,
production rollout and certification remain **NOT_RUN / NOT_CERTIFIED**.

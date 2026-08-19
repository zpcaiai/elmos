# BUILD_CACHE_TEST_RESULTS.md

> Executed results only. Anything not run here is marked `NOT EXECUTED`.

- **Date:** 2026-08-19 (pass 2)
- **Platform:** Linux x86_64, cloud sandbox (not the Mac)
- **Python:** 3.12.3
- **Pinned tools:** `pytest==8.4.1`, `ruff==0.12.5`, `mypy==1.17.0`,
  `jsonschema==4.25.1`, `cryptography==50.0.0`,
  `tree-sitter==0.26.0`, `tree-sitter-language-pack==1.14.3`
- **Live services:** PostgreSQL 16.10, a moto S3 server on `127.0.0.1` (real HTTP)
- **Real toolchains:** Gradle 8.14.3 · javac 21.0.10 · .NET SDK 8.0.130 ·
  Cargo 1.95.0 · ccache 4.9.1 + CMake + gcc · tsc 6.0.3 + npm (Node 22) ·
  pip 24.0 · Go 1.24.7
- **Working directory:** `engines/build-cache-engine`

## Commands

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e '.[postgres,s3]' \
    ruff==0.12.5 mypy==1.17.0 pytest==8.4.1 'moto[s3,server]>=5.0'

.venv/bin/ruff check src tests
.venv/bin/mypy
ELMOS_TEST_POSTGRES_DSN="postgresql://elmos:elmos@127.0.0.1:5432/elmos_cache" \
  .venv/bin/pytest tests
```

Without `ELMOS_TEST_POSTGRES_DSN` the PostgreSQL parameterisations skip; without
a toolchain on `PATH` the corresponding toolchain test skips. Both skip with a
printed reason — they never pass silently.

## Results

| Gate | Command | Result |
| --- | --- | --- |
| Lint | `ruff check src tests` | **All checks passed** (rules `E,F,I,B,UP,S`, line length 120) |
| Types | `mypy` (`strict = true`) | **Success: no issues found in 42 source files** |
| Tests | `pytest tests` | **550 passed, 5 skipped** in 105.6 s, 0 failed, 0 xfail |

The five skips, verbatim:

```text
SKIPPED tests/test_native_toolchains.py: swiftc is not available in this environment
SKIPPED tests/test_native_toolchains.py: flutter is not available in this environment
SKIPPED tests/test_native_toolchains.py: Maven Central is unreachable from this sandbox
        (plugin resolution fails online and offline), so only the Gradle half of
        gradle-maven is certified here
SKIPPED tests/test_treesitter_hash.py: javascript has no statically private member in this fixture
SKIPPED tests/test_treesitter_hash.py: objectivec has no statically private member in this fixture
```

## Per-file test counts

| File | Tests | Acceptance rows | New in pass 2 |
| --- | ---: | --- | --- |
| `test_action_cache.py` | 19 | CACHE-001..003 | |
| `test_api.py` | 16 | API contract | |
| `test_cas.py` | 12 | CAS-001..003 | |
| `test_chaos.py` | 12 | CHAOS-001..002, CERT-001 | |
| `test_chaos_process.py` | 17 | CHAOS-001..002 (real `SIGKILL`, real tmpfs) | ● |
| `test_checkpoint.py` | 15 | CHECK-001..003 | |
| `test_cli.py` | 11 | CLI contract | |
| `test_contracts_and_config.py` | 20 | schema/config/state-machine contracts | |
| `test_dag.py` | 14 | DAG-001..003 | |
| `test_e2e.py` | 10 | E2E-001..003 | |
| `test_e2e_real_stages.py` | 9 | E2E-001 with real stages | ● |
| `test_fingerprint.py` | 18 | KEY-001..003 | |
| `test_gc.py` | 11 | GC-001..002 | |
| `test_interface_hash.py` | 20 | semantic/interface hashing | |
| `test_journal.py` | 13 | JOURNAL-001, LEASE-001 | |
| `test_merge.py` | 17 | conflict and merge | |
| `test_metadata_store_contract.py` | 47 | store contract × {SQLite, PostgreSQL 16} | ● |
| `test_native_adapters.py` | 15 | native build caches (contract) | |
| `test_native_toolchains.py` | 12 | native build caches (real tools) | ● |
| `test_observability.py` | 11 | OBS-001..002, PERF-001..002 | |
| `test_provenance_crypto.py` | 24 | SEC-003, envelope encryption | ● |
| `test_publish.py` | 11 | PUB-001..003 | |
| `test_remote.py` | 15 | REMOTE-001..003 (filesystem) | |
| `test_remote_s3.py` | 12 | REMOTE-001..003 (live S3) | ● |
| `test_security.py` | 15 | SEC-001..003 | |
| `test_snapshot.py` | 7 | SNAP-001..003 | |
| `test_stage_contract.py` | 22 | stage contracts and lint | |
| `test_staging.py` | 27 | STAGE-001..007 | |
| `test_treesitter_hash.py` | 103 | exact interface hashing, 13 languages | ● |
| **Total** | **555** | | 7 new files |

## What the new suites actually executed

### Real process kills (`test_chaos_process.py`)

A child process runs the reserve → write → seal → promote → publish scenario and
is `SIGKILL`ed at each of 8 kill points. The parent — a separate process that
never shared the victim's memory — then asserts that nothing was partially
published, that recovery converges, and that the staged-file rows are
consistent. Disk exhaustion is a **real** `tmpfs` mounted through `libc.mount`
with a 1 MiB size and 96 inodes; both `ENOSPC` and `ENOSPC`-by-inode surface as
a controlled `QuotaExceeded`, not corruption.

### PostgreSQL 16 (`test_metadata_store_contract.py`)

23 contract tests run twice, once per dialect, plus a guard test asserting that
the PostgreSQL parameterisation really reached PostgreSQL (`SELECT version()`).
Covered: optimistic `version` CAS, lease-epoch fencing, expiry and heartbeats,
the staged-file lifecycle including the single `ABORTED → RESERVED` edge,
reference-aware artifact edges, the validation ratchet, the action-cache round
trip, event idempotency, checkpoint supersession, at-most-once side effects,
the outbox, pins, certificates and revocations, GC plans and receipts, and tree
publication.

### Live S3 (`test_remote_s3.py`)

Against a real HTTP endpoint, not a stubbed client:

- `put_if_absent` bypassing the client-side pre-check is refused by the service
  with `412 PreconditionFailed`;
- six concurrent identical writers converge on one object;
- a 12 MiB payload round-trips through a genuine multipart create/upload-part/
  complete cycle;
- an upload interrupted before completion leaves **no** readable object and
  **no** in-flight upload (the abort really ran), and the retry then succeeds;
- a tampered object is rejected by digest before it can enter the local CAS.

### Asymmetric provenance and AEAD (`test_provenance_crypto.py`)

Ed25519 signatures with the algorithm and key id inside the signed payload, so
an algorithm downgrade and a key substitution are both forgeries; per-field
tamper detection over six fields; key rotation; domain separation; and an
AES-256-GCM envelope whose every header byte is authenticated, with the tenant
identity as AAD so a ciphertext cannot be replayed into another tenant.

### Real toolchains (`test_native_toolchains.py`)

Each tool is run twice with its build directory destroyed in between, under an
environment built by the adapter and a private `HOME`:

| Adapter | Tool | Warm-build evidence |
| --- | --- | --- |
| `gradle-maven` | Gradle 8.14.3 (offline, `--build-cache`) | `> Task :compileJava FROM-CACHE` after `clean` |
| `msbuild-nuget` | .NET SDK 8.0.130 | `Skipping target "CoreCompile" because all output files are up-to-date` |
| `cmake-ccache` | ccache 4.9.1 + CMake + gcc | `Hits: 1 / 2`, `Misses: 1 / 2` |
| `cargo-sccache` | Cargo 1.95.0 | `Fresh probe` (cold run said `Compiling probe`) |
| `typescript-node` | tsc 6.0.3, npm | `Project 'tsconfig.json' is up to date` |
| `python-wheel` | pip 24.0 | `Using cached six-1.16.0-…whl` |
| `go-build` | Go 1.24.7 | second `go build -v` prints nothing at all |

Each test also asserts the tool's *default* cache location under the private
`HOME` was never created — the redirection is what put the cache in the sandbox.

### Exact interface hashing (`test_treesitter_hash.py`)

For each of the thirteen languages: extraction is `EXACT` (or `HEURISTIC` for
the dynamic ones, deliberately), private members are not public API, a
**body-only edit does not propagate**, a public-signature edit does, a
comment-only edit changes nothing, and extraction is deterministic. Plus the
structures the line scanner could not see: signatures split across lines,
one-line bodies, braces inside generic type arguments, nested types, overloads,
an Objective-C declaration merged with its definition, Go methods scoped to
their receiver, Rust `impl` blocks, and C++ access labels.

One differential test is worth calling out: on a Go method the old line scanner
reported *no change at all* when a parameter was added — an under-invalidation.
The grammar catches it. `test_the_scanner_can_miss_a_go_signature_change_the_grammar_catches`
pins that down and will fail if the scanner is ever fixed, so the note cannot
go stale.

### End-to-end with real stages (`test_e2e_real_stages.py`)

`javac` really compiles a five-file Java project into the sandbox; a translator
reads the Java parse tree and emits C#; the emitted C# is parsed back with the
C# grammar and its public surface is compared against the Java source's — a
dropped method or a changed arity fails the run. Then, over those real
artifacts: a no-change rerun reruns neither the compiler nor the translator and
reproduces the same tree digest; editing a **private** Java method regenerates
only that module and restores the dependent from cache; adding a **public**
method retranslates both and the new method appears in the published C#.

## Package validation

```bash
cd agent-skills/packages/elmos-build-cache-staging-recovery && ./validate.sh
```

```text
package structure and checksums OK: 24 skills
Ran 10 tests in 0.030s
OK
reference implementation tests OK
```

## Codebase size

| Area | Files | Lines |
| --- | ---: | ---: |
| Implementation (`src/elmos_build_cache/`) | 37 | 17 891 |
| Tests (`tests/`) | 30 | 8 047 |
| SQL migrations | 6 | ~380 |

## NOT EXECUTED

| Item | Why |
| --- | --- |
| Xcode/Swift and Flutter/pub adapters against their tools | neither toolchain exists for this platform |
| The Maven half of `gradle-maven` | Maven Central is unreachable from this sandbox (plugin resolution fails online *and* offline) |
| macOS / Windows snapshot fixtures | Linux-only sandbox |
| Real ELMOS conversion workload benchmarks | the model-driven stage is not registered here |
| AWS-specific S3 behaviour (IAM, lifecycle, regional consistency) | the endpoint is a local S3 service, not AWS |
| Repository-wide suite (`run_polyglot_routes.py`) | out of scope; also blocked in this environment |

## Transfer verification (cloud → Mac)

Recorded in `BUILD_CACHE_EVIDENCE.md` §Transfer for this pass.

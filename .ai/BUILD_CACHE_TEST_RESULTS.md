# BUILD_CACHE_TEST_RESULTS.md

> Executed results only. Anything not run here is marked `NOT EXECUTED`.

- **Date:** 2026-08-20 (pass 4)
- **Platform:** Linux x86_64, cloud sandbox (not the Mac)
- **Python:** 3.12.3
- **Pinned tools:** `pytest==8.4.1`, `ruff==0.12.5`, `mypy==1.17.0`,
  `jsonschema==4.25.1`, `cryptography==50.0.0`,
  `tree-sitter==0.26.0`, `tree-sitter-language-pack==1.14.3`
- **Live services:** PostgreSQL 16.13, a moto S3 server on `127.0.0.1` (real HTTP)
- **Real toolchains:** Gradle 8.14.3 · javac/java 21.0.10 · .NET SDK 8.0.130 ·
  Cargo 1.95.0 · ccache 4.9.1 + CMake + gcc · tsc 6.0.3 + npm (Node 22) ·
  pip 24.0 · Go 1.24.7 · Maven 3.x (offline)
- **Also exercised:** a real kernel `overlayfs` mount, a real `tmpfs` with a
  1 MiB size and 96 inodes, real `SIGKILL`, a real macOS APFS volume (through
  the desktop bridge), and ELMOS's own `polyglot-route-engine`
- **Working directory:** `engines/build-cache-engine`

## Commands

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e '.[postgres,s3]' \
    ruff==0.12.5 mypy==1.17.0 pytest==8.4.1 'moto[s3,server]>=5.0'

.venv/bin/ruff check src tests tools
.venv/bin/mypy
ELMOS_TEST_POSTGRES_DSN="postgresql://elmos:elmos@127.0.0.1:5432/elmos_cache" \
  .venv/bin/pytest tests
```

Every optional dependency degrades to a **printed skip**, never to a silent
pass: no PostgreSQL DSN, no toolchain on `PATH`, no route engine beside this
one, no `CAP_SYS_ADMIN` for the overlayfs mount.

## Results

| Gate | Command | Result |
| --- | --- | --- |
| Lint | `ruff check src tests tools` | **All checks passed** (rules `E,F,I,B,UP,S`, line length 120) |
| Types | `mypy` (`strict = true`) | **Success: no issues found in 52 source files** |
| Tests | `pytest tests` | **926 passed, 7 skipped** in 136.8 s, 0 failed, 0 xfail |
| Skills package | `agent-skills/packages/elmos-build-cache-staging-sota/validate.sh` | **31 skills, checksums OK, 20 reference tests OK** (run on the Mac, not only in the sandbox) |

The seven skips, verbatim:

```text
SKIPPED tests/test_native_toolchains.py: swiftc is unavailable on this platform; the real
        cold/warm build is uncertified
SKIPPED tests/test_native_toolchains.py: flutter is unavailable on this platform; the real
        cold/warm build is uncertified
SKIPPED tests/test_native_toolchains.py: Maven Central is unreachable from this sandbox
        (plugin resolution fails online and offline), so only the Gradle half of
        gradle-maven and Maven's repository redirection are certified here
SKIPPED tests/test_overlay.py: root ignores the write bit; the mode assertion above is the check
SKIPPED tests/test_snapshot_portability.py: no snapshot digest has been captured on: darwin,
        windows -- run tools/cross_platform_snapshot.py there and add its output to
        cross_platform_snapshot.json
SKIPPED tests/test_treesitter_hash.py: javascript has no statically private member in this fixture
SKIPPED tests/test_treesitter_hash.py: objectivec has no statically private member in this fixture
```

## Per-file test counts

| File | Tests | Acceptance rows | Added in |
| --- | ---: | --- | --- |
| `test_action_cache.py` | 19 | CACHE-001..003 | 1 |
| `test_api.py` | 16 | API contract | 1 |
| `test_cache_admission.py` | 16 | SOTA-06, SOTA-08 | 4 |
| `test_cache_policy.py` | 74 | SOTA-03..06, SOTA-13 | 4 |
| `test_cache_simulator.py` | 24 | SOTA-01..02, SOTA-15 | 4 |
| `test_cache_trace.py` | 33 | SOTA-14 | 4 |
| `test_cas.py` | 12 | CAS-001..003 | 1 |
| `test_chaos.py` | 12 | CHAOS-001..002, CERT-001 | 1 |
| `test_chaos_process.py` | 17 | CHAOS-001..002 (real `SIGKILL`, real tmpfs) | 2 |
| `test_checkpoint.py` | 15 | CHECK-001..003 | 1 |
| `test_cli.py` | 11 | CLI contract | 1 |
| `test_contracts_and_config.py` | 20 | schema/config/state-machine contracts | 1 |
| `test_dag.py` | 14 | DAG-001..003 | 1 |
| `test_dag_prefetch.py` | 23 | SOTA-07 | 4 |
| `test_e2e.py` | 13 | E2E-001..003, SOTA-25 | 1 |
| `test_e2e_real_stages.py` | 9 | E2E-001 with real stages | 2 |
| `test_elmos_route_stages.py` | 16 | E2E-001 with **ELMOS's own engine** | 3 |
| `test_fingerprint.py` | 18 | KEY-001..003 | 1 |
| `test_gc.py` | 11 | GC-001..002 | 1 |
| `test_interface_hash.py` | 20 | semantic/interface hashing | 1 |
| `test_journal.py` | 13 | JOURNAL-001, LEASE-001 | 1 |
| `test_learned_control.py` | 23 | SOTA-11 | 4 |
| `test_merge.py` | 17 | conflict and merge | 1 |
| `test_metadata_store_contract.py` | 47 | store contract × {SQLite, PostgreSQL 16} | 2 |
| `test_native_adapters.py` | 15 | native build caches (contract) | 1 |
| `test_native_toolchains.py` | 13 | native build caches (real tools) | 2 |
| `test_observability.py` | 11 | OBS-001..002, PERF-001..002 | 1 |
| `test_overlay.py` | 36 | sandbox overlay workspaces | 3 |
| `test_policy_integration.py` | 50 | SOTA-19..24 (the wiring) | 4 |
| `test_policy_orchestrator.py` | 22 | SOTA-09..10 | 4 |
| `test_provenance_crypto.py` | 24 | SEC-003, envelope encryption | 2 |
| `test_publish.py` | 11 | PUB-001..003 | 1 |
| `test_remote.py` | 15 | REMOTE-001..003 (filesystem) | 1 |
| `test_remote_s3.py` | 12 | REMOTE-001..003 (live S3) | 2 |
| `test_security.py` | 15 | SEC-001..003 | 1 |
| `test_snapshot.py` | 7 | SNAP-001..003 | 1 |
| `test_snapshot_portability.py` | 21 | SNAP-001 cross-platform | 3 |
| `test_sota_acceptance.py` | 36 | SOTA-01..18 | 4 |
| `test_stage_contract.py` | 22 | stage contracts and lint | 1 |
| `test_staging.py` | 27 | STAGE-001..007 | 1 |
| `test_treesitter_hash.py` | 103 | exact interface hashing, 13 languages | 2 |
| **Total** | **933** | | |

## What pass 3 actually executed

### ELMOS's own conversion engine (`test_elmos_route_stages.py`)

`elmos_route_stages.py` imports `engines/polyglot-route-engine` and drives it:

- the analyzer reports `CPython ast 3.12.3` and produces a schema-`1.0.0`
  semantic IR from a real Python function;
- the emitter produces Java containing `Math.multiplyExact` — the engine's
  overflow-checked lowering, not a template;
- the same IR emits for `java`, `typescript` and `go`;
- the emitted Java **compiles with `javac`** and the emitted Go **builds with
  `go build`**;
- the emitted Java is then **executed against the Python original** over six
  input tuples including negatives and a large value. That is what earns
  `TEST_VERIFIED`;
- a deliberately sabotaged translation (`Math.multiplyExact(a,b)` replaced with
  `0L`) is caught by the differential runner, gets `COMPILE_VERIFIED`, and is
  therefore below the stage contract's reuse floor;
- through the pipeline: two units generate, publish, and on rerun **RESTORE**;
- **a comment-only edit to the Python source re-emits nothing** — the IR digest
  is unchanged, so the ActionKey does not move;
- editing a unit's own body re-emits only that unit; editing the unit its
  neighbour depends on re-emits both;
- `strict_toolchain=True` propagates the engine's own
  `EXACT_TOOLCHAIN_PLATFORM_MISMATCH` instead of inventing a toolchain digest,
  and an unpinned identity is proven not to collide with a pinned one.

### The overlay workspace (`test_overlay.py`)

- projection shares storage (`st_ino` equal, `st_nlink >= 2`) and
  `open_for_write` breaks it (`st_ino` changes, the base keeps its bytes,
  `st_nlink` returns to 1);
- the hazard the API exists to prevent is demonstrated: writing through the
  shared link *without* it corrupts the base;
- the whole lifecycle runs again **inside a real kernel overlayfs mount** — the
  lower layer is untouched and the upper layer holds exactly the workspace;
- the materialised source is `0o444` on disk;
- `/etc`, `/root`, `/proc`, `/sys`, `/dev`, `/home/...` and every credential
  basename (`.ssh`, `.aws`, `.gnupg`, `.netrc`, `.docker`, `.kube`, `.npmrc`,
  `.pypirc`, `.git-credentials`) are refused, including inside an allowed root;
- byte and file-count quotas, declared/undeclared export split, scratch disposal.

### Cross-platform snapshots (`test_snapshot_portability.py`)

`tools/cross_platform_snapshot.py` builds one repository from bytes — composed
Unicode, CRLF, a BOM, an empty file, an executable bit, an eight-deep path —
and prints the digest the host computed. Captured so far:

| Capture | Python | Root digest |
| --- | --- | --- |
| `linux` (cloud sandbox, ext4) | 3.12.3 | `sha256:e6b1584f…891daa7` |
| `apfs-via-linux-vm` (real macOS APFS, FUSE-exported) | 3.10.12 | `sha256:e6b1584f…891daa7` |

Identical. The APFS volume was probed first and is genuinely case-insensitive
and normalisation-insensitive. A **native Darwin** run and a **Windows** run
have not been captured, and the suite names them in a skip.

Also executed here: a decomposed (NFD) filename now snapshots as the composed
one — a real bug this pass fixed, and the exact way macOS used to produce a
different root digest for the same checkout. And `portability_findings` is
asserted against real on-disk fixtures for case collisions, normalisation
folds, ten Windows-hostile names, symlinks and over-long paths.

### Maven (`test_native_toolchains.py`)

The adapter now sets `MAVEN_OPTS=-Dmaven.repo.local=<sandbox>`, which is what
Maven actually reads. Running `mvn -o` under that environment, Maven's own
error names the repositories it resolved against, and the local one is the
sandbox path — with `~/.m2/repository` never created. A full build still needs
Central.

## Package validation

```bash
cd agent-skills/packages/elmos-build-cache-staging-sota && ./validate.sh
```

```text
package structure and checksums OK: 31 skills
Python compilation OK
Ran 20 tests in 0.086s
OK
reference implementation tests OK
```

Run twice: once in the sandbox and once **on the Mac**, after the package was
vendored there. Same output both times.

## Codebase size

| Area | Files | Lines |
| --- | ---: | ---: |
| Implementation (`src/elmos_build_cache/`) | 46 | 24 322 |
| Tests (`tests/`) | 42 | 12 165 |
| Tools (`tools/`) | 1 | 92 |
| SQL migrations | 6 | ~380 |

## NOT EXECUTED

| Item | Why |
| --- | --- |
| Xcode/Swift and Flutter/pub adapters against their tools | neither toolchain exists for Linux, and neither swift.org nor the Flutter SDK host is on this sandbox's network allowlist |
| A full Maven build | Maven Central is unreachable (plugin resolution fails online *and* offline) |
| A native Darwin snapshot capture | nothing executes macOS binaries from this session; the APFS volume was reached through a Linux VM |
| A Windows snapshot capture | no Windows host |
| The route engine's non-Python analyzers | they shell out to the pinned Darwin/arm64 toolchain trees, which is exactly what `strict_toolchain` refuses to fake |
| Real ELMOS workload benchmarks | the conversion corpus is not in this sandbox |
| Cache policies against **captured production traces** | none exist yet; `cache_trace.TraceRecorder` is the capture path and is off by default. The ten corpora in `cache_trace.GENERATORS` are synthetic and shaped after ELMOS conversion patterns, and every certificate records which corpus it was issued against |
| A policy promoted past `SHADOW` on a real deployment | the rollout ladder is exercised in tests (`SIMULATOR → SHADOW → RECOMMENDATION → CANARY → PROGRESSIVE → FULL`, plus rollback); no ELMOS deployment has run one |
| Learning-augmented tuning with a trained production model | the model is trained and clipped in tests against synthetic features; no production feature history exists |
| AWS-specific S3 behaviour (IAM, lifecycle, regional consistency) | the endpoint is a local S3 service |

## What pass 4 executed that pass 3 did not

| Command | Result |
| --- | --- |
| `elmos-cache policy show` | prints the configured tier policies and a configuration digest |
| `elmos-cache policy benchmark --workload monorepo-scan --capacity-fraction 0.05` | six arms, one shared capacity, report valid against `cache-benchmark-report.schema.json` |
| `elmos-cache policy matrix` | 30 cells (10 workloads × 3 capacities); `no_single_winner = True`; wins GDSF 14, W-TinyLFU 8, size-aware TinyLFU 4, SIEVE 2, LRU 1, S3-FIFO 1 |
| `elmos-cache policy select --workload monorepo-scan` | a recommendation with reason codes and the workload fingerprint |
| `elmos-cache policy certify …` without rollout evidence | **refused**: `NO_SHADOW_EVIDENCE`, `NO_ROLLBACK_EXERCISE` |
| `elmos-cache policy certify …` with all three evidence files | certified, Ed25519-signed statement |
| `elmos-cache trace generate` → `trace verify` | round-trips; privacy check passes; split digests identical |

Avoided-compute ratio at 5 % of the working set, measured this pass:

| Workload | LRU | SIEVE | S3-FIFO | W-TinyLFU | size-aware | GDSF | selected |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| monorepo-scan | 0.000 | 0.000 | 0.216 | **0.346** | 0.000 | 0.017 | W_TINY_LFU |
| identical-rerun | 0.000 | 0.000 | 0.000 | 0.061 | 0.167 | **0.581** | GDSF |
| multi-tenant-burst | 0.549 | 0.090 | 0.451 | 0.086 | 0.086 | 0.533 | **none** |
| large-binaries | 0.076 | 0.076 | 0.076 | 0.076 | 0.076 | 0.076 | **none** |

The last two rows are the point of the gates: when no candidate clears the
weighted-improvement threshold over LRU, `selected` is `None` and nothing is
recommended. A benchmark that always picks a winner is not measuring anything.

## Transfer verification (cloud → Mac)

Recorded in `BUILD_CACHE_EVIDENCE.md` §Transfer for this pass.

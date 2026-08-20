# ELMOS Build Cache, Generated-File Staging and Recovery Engine

Implements the `elmos-build-cache-staging-sota` skills package (31 skills,
phases P0–P8) as production code inside this repository. Phases P0–P7 are the
correctness engine; P8 adds the SOTA cache-policy plane -- admission, eviction,
prefetch, adaptive selection, learning-augmented tuning and certification -- on
top of it without being allowed to touch it.

The subsystem gives ELMOS deterministic cache reuse and durable execution
without weakening correctness. Its central rule is that **file existence never
equals completion**: a generated file becomes visible only after it has been
sealed, digest-verified, promoted into content-addressable storage, included in
a validated whole-tree manifest, and published by an atomic pointer switch.

## Layout

```text
engines/build-cache-engine/
├── src/elmos_build_cache/     implementation (42 modules, mypy --strict clean)
│   ├── _data/                 packaged JSON Schemas, SQL migrations, OpenAPI
│   └── db/                    SQLite (local) and PostgreSQL (production) store
├── tests/                     921 tests mapped to the acceptance matrix
├── config/                    elmos-cache.yaml, elmos-cache.local.yaml
├── migrations/                postgres/0001_init.sql, 0002_elmos_extensions.sql
│                              sqlite/0001_init.sql
├── openapi/                   cache-control-plane.openapi.yaml
├── schemas/                   the ten contract schemas
└── docs/                      spec, acceptance matrix, recovery runbook,
                               miss-reason taxonomy, storage layout, CLI contract
```

The copies under `schemas/`, `openapi/` and `migrations/` are the human-facing
contract; `src/elmos_build_cache/_data/` holds the importable copies. A test
asserts the two are byte-identical, so they cannot drift.

## Capability map

| Phase | Skill | Module |
|---|---|---|
| P0 | `elmos-cache-system-architecture` | `enums`, `errors`, `config`, `canonical` |
| P0 | `elmos-cache-metadata-database` | `db/` (`store`, `records`, migrations) |
| P0 | `elmos-cache-api-cli-contracts` | `api`, `cli` |
| P1 | `elmos-project-snapshot-merkle` | `snapshot` |
| P1 | `elmos-content-addressable-storage` | `cas` |
| P1 | `elmos-cache-key-fingerprinting` | `fingerprint` |
| P1 | `elmos-action-cache` | `action_cache` |
| P2 | `elmos-project-generation-file-staging` | `staging` |
| P2 | `elmos-atomic-file-write-promotion` | `atomic`, `publish` |
| P2 | `elmos-sandbox-overlay-workspaces` | `overlay` |
| P2 | `elmos-intermediate-artifact-manifest` | `manifests` |
| P3 | `elmos-stage-contract-registry` | `stage_contract` |
| P3 | `elmos-semantic-interface-hashing` | `interface_hash` |
| P3 | `elmos-incremental-conversion-dag` | `dag` |
| P4 | `elmos-run-journal-state-machine` | `journal` |
| P4 | `elmos-checkpoint-resume` | `checkpoint` |
| P4 | `elmos-generation-conflict-merge` | `merge` |
| P5 | `elmos-remote-shared-cache` | `remote` |
| P5 | `elmos-native-build-cache-adapters` | `native_adapters` |
| P6 | `elmos-cache-security-provenance` | `security` |
| P6 | `elmos-cache-retention-gc` | `gc` |
| P6 | `elmos-cache-observability-performance` | `observability` |
| P6 | `elmos-cache-chaos-certification` | `chaos` |
| P7 | `elmos-cache-rollout-end-to-end` | `pipeline` |
| P8 | `elmos-sota-cache-policy-portfolio` | `cache_policy` |
| P8 | `elmos-cache-trace-replay-simulator` | `cache_trace`, `cache_simulator` |
| P8 | `elmos-cost-aware-cache-admission` | `cache_admission` |
| P8 | `elmos-dag-aware-cache-prefetch` | `dag_prefetch` |
| P8 | `elmos-adaptive-cache-policy-orchestrator` | `policy_orchestrator` |
| P8 | `elmos-learning-augmented-cache-control` | `learned_control` |
| P8 | `elmos-cache-autotuning-certification` | `policy_certification` |

### The policy plane

The correctness plane decides what is *valid*; the policy plane decides only
what is *kept*, *fetched early* and *let in*. They are separate objects with
separate tests, and every crossing is one-way:

- **Six policies, one baseline.** `cache_policy` implements LRU (mandatory
  baseline), SIEVE, S3-FIFO, W-TinyLFU, size-aware TinyLFU and GDSF behind one
  SPI. `benchmark_matrix(...)["no_single_winner"]` is `True` on this
  repository's own traces -- which is why the portfolio exists rather than a
  single "best" algorithm.
- **Protected roots are never victims.** Active runs, checkpoints, published
  trees, pins and legal holds are declared to the policy *before* it is asked
  anything. When only protected objects remain, admission is refused; nothing
  protected is ever evicted to make room.
- **Invalidation is not eviction.** `CachePolicy.forget()` exists so a
  revocation or quarantine removes an entry without being counted as a capacity
  decision, and it is accounted separately (`counters.invalidations`).
- **Where it takes effect.** `HotIndex` (the in-process action-cache
  accelerator) and the GC candidate ordering both run the configured policy.
  The hot index is deliberately the first seam: it is never authoritative, so
  the worst a policy bug can cost there is one database read.
- **Nothing switches itself on.** `policy.adaptive_selection` and
  `policy.learned_tuning` default to off, learned parameters are clipped to
  certified bounds, and the pinned fallback is a fixed policy (SIEVE).

## Storage model

| Data class | Store |
|---|---|
| Immutable bytes | filesystem CAS (`cas`), optionally mirrored to S3/MinIO (`remote`) |
| Immutable manifests | CAS, indexed in the metadata database |
| Mutable orchestration state | SQLite WAL locally, PostgreSQL in production |
| Hot coordination | optional Redis — never the only recoverable truth (rejected by config validation) |
| User-visible output | `publish/<run_id>/<tree-digest>/` with an atomic `current` pointer |

## Generated-file lifecycle

```text
RESERVED → WRITING → SEALED → CAS_PROMOTED → TREE_INCLUDED → PUBLISHED
              ↘ ABORTED (retryable: the same producer may re-reserve its path)
              ↘ QUARANTINED
```

Transitions are guarded by an optimistic `version` *and* the worker's
`lease_epoch`. Recovery bumps the epoch when it claims a node, which is what
makes a stale worker's later commit impossible rather than merely unlikely.

## Quick start

```bash
cd engines/build-cache-engine
uv sync                                    # or: pip install -e .

# inspect and maintain a local cache
elmos-cache --base /path/to/repo cache status
elmos-cache --base /path/to/repo doctor cache
elmos-cache --base /path/to/repo cache gc            # dry-run plan
elmos-cache --base /path/to/repo cache gc --apply <plan-id> --idempotency-key k

# recover a workspace after a crash
elmos-cache --base /path/to/repo workspace recover <run-id>

# cache-policy evidence (read-only; none of these change the cache)
elmos-cache policy show
elmos-cache policy benchmark --workload monorepo-scan --capacity-fraction 0.05
elmos-cache policy matrix
elmos-cache policy select --workload monorepo-scan
elmos-cache policy certify --workload monorepo-scan --candidate SIEVE \
    --elmos-commit "$(git rev-parse HEAD)" --signing-key policy.key \
    --shadow-evidence shadow.json --canary-evidence canary.json \
    --rollback-evidence rollback.json
elmos-cache trace generate --workload monorepo-scan --out trace.jsonl
elmos-cache trace verify --trace trace.jsonl
```

A policy is promoted by editing the `policy:` section of `elmos-cache.yaml`
after a certificate exists -- not by a CLI flag. `policy certify` refuses
without the rollout evidence (`NO_SHADOW_EVIDENCE`, `NO_ROLLBACK_EXERCISE`) and
without a large enough untouched test window, and it says so in `reasons`.

Destructive commands are dry-run by default and require an explicit scope plus
an idempotency key; run mutations additionally require `--expected-version`.

## Library usage

```python
from pathlib import Path

from elmos_build_cache.cas import ContentAddressableStore
from elmos_build_cache.config import default_config
from elmos_build_cache.db import open_store
from elmos_build_cache.pipeline import ConversionPipeline, build_run
from elmos_build_cache.snapshot import take_snapshot

config = default_config()
store = open_store(".elmos/cache/index.sqlite")
cas = ContentAddressableStore(Path(".elmos/cache"))

snapshot = take_snapshot(Path("."))
workspace, coordinator, checkpoints = build_run(
    store, cas, config, Path("."), "tenant", "project", "run-1", snapshot
)
pipeline = ConversionPipeline(config, store, cas, Path("."), "tenant", "project")
```

## Verification

```bash
PYTHONPATH=src pytest tests -q          # 921 tests
ruff check src tests
mypy src/elmos_build_cache              # strict
```

Tests are named after the acceptance matrix in
`docs/cache-staging-acceptance-matrix.md` (`SNAP-`, `KEY-`, `CAS-`, `CACHE-`,
`STAGE-`, `PUB-`, `DAG-`, `CHECK-`, `JOURNAL-`, `LEASE-`, `REMOTE-`, `SEC-`,
`GC-`, `OBS-`, `PERF-`, `CHAOS-`, `CERT-`, `E2E-`, `SOTA-`).

## Optional extras

| Extra | Enables |
|---|---|
| `postgres` | `PostgresMetadataStore` (psycopg) |
| `s3` | `S3RemoteBackend` (boto3) |
| `otel` | OpenTelemetry span export from `observability.Tracer` |

Everything works without them: the local profile is filesystem CAS + SQLite WAL
with no mandatory network dependency, and the remote cache has a filesystem
backend for shared-NFS deployments and tests.

## ELMOS integration

`elmos_route_stages` registers the conversion engine ELMOS ships
(`engines/polyglot-route-engine`) against the stage contracts here: its
analyzer produces the semantic IR, its emitter produces the target file, and
generation is keyed by the **IR digest** rather than the source digest -- so a
comment or a reformat that the analyzer discards does not re-emit anything,
while an emitter change does (the emitter's own source is folded into
`rule_pack_digest`).

The dependency is optional and one-way: nothing imports the route engine at
module scope, it is not in this package's dependency set, and
`elmos_route_stages.available()` reports whether it can be found (via
`ELMOS_POLYGLOT_ROUTE_SRC` or the sibling engine directory).

Generation claims `TEST_VERIFIED` only when it has been earned: the bridge
compiles the emitted Java and runs it against the Python original over a set of
inputs. Without a JDK it downgrades to `COMPILE_VERIFIED`, which is below the
`target-code-generation` contract's reuse floor -- so an unverified result is
produced but never restored.

## Known limitations

- The route engine pins each toolchain to an exact platform-specific tree. On a
  host that does not match the pin, `RouteStages(strict_toolchain=True)`
  refuses rather than substituting a plausible toolchain digest; the unpinned
  identity available for local work is marked unpinned inside the ActionKey, so
  it cannot collide with a pinned one.
- Native build-cache adapters are certified against real toolchains for Gradle,
  MSBuild/NuGet, Cargo, CMake/ccache, TypeScript/npm, pip and Go, and Maven's
  local-repository redirection is certified against Maven itself
  (`tests/test_native_toolchains.py`). A full Maven build needs a reachable
  Maven Central, and Xcode/Swift and Flutter/pub need toolchains that do not
  exist on Linux; those three skip loudly rather than passing quietly.
- Snapshot root digests are captured on Linux and on a real macOS APFS volume
  (`tests/fixtures/cross_platform_snapshot.json`) and asserted equal. A native
  Darwin run and a Windows run have not been captured;
  `tools/cross_platform_snapshot.py` produces the entry, and
  `snapshot.portability_findings` predicts from any host which paths would
  behave differently elsewhere.
- The performance budgets in `observability.DEFAULT_SLOS` are engineering
  estimates. `PerformanceGate` is exercised against the benchmark harness and
  against real compiler work, not against a full ELMOS workload.
- The policy corpora in `cache_trace.GENERATORS` are synthetic workloads shaped
  after real ELMOS conversion patterns, not captured production traces. They are
  enough to show that no single policy dominates and to refuse a policy that
  regresses, but a certificate issued against them binds to *them*:
  `CertificationContext` records the corpus, capacity, objective and commit, and
  `expired_reasons()` invalidates the certificate when any of those move.
  `TraceRecorder` is the path to real traces and is privacy-preserving by
  construction (digests, HMAC tenant pseudonyms, closed vocabularies, positive
  `assert_privacy` rule), but capture is off by default.
- Learning-augmented tuning is off by default and shadow-only when on. The model
  is a ridge regression over workload features with clipping to certified
  bounds as its safety property -- clipping, not the model's accuracy, is what
  makes it safe -- and it falls back to fixed parameters on drift, staleness,
  out-of-distribution input or low confidence.
- The policy plane is wired into the in-process `HotIndex` and into GC candidate
  ordering. It does not yet order eviction inside the CAS itself; that seam is
  authoritative storage and is deliberately last.

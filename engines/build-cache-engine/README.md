# ELMOS Build Cache, Generated-File Staging and Recovery Engine

Implements the `elmos-build-cache-staging-recovery` skills package (24 skills,
phases P0–P7) as production code inside this repository.

The subsystem gives ELMOS deterministic cache reuse and durable execution
without weakening correctness. Its central rule is that **file existence never
equals completion**: a generated file becomes visible only after it has been
sealed, digest-verified, promoted into content-addressable storage, included in
a validated whole-tree manifest, and published by an atomic pointer switch.

## Layout

```text
engines/build-cache-engine/
├── src/elmos_build_cache/     implementation (36 modules, mypy --strict clean)
│   ├── _data/                 packaged JSON Schemas, SQL migrations, OpenAPI
│   └── db/                    SQLite (local) and PostgreSQL (production) store
├── tests/                     331 tests mapped to the acceptance matrix
├── config/                    elmos-cache.yaml, elmos-cache.local.yaml
├── migrations/                postgres/0001_init.sql, 0002_elmos_extensions.sql
│                              sqlite/0001_init.sql
├── openapi/                   cache-control-plane.openapi.yaml
├── schemas/                   the seven contract schemas
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
```

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
PYTHONPATH=src pytest tests -q          # 331 tests
ruff check src tests
mypy src/elmos_build_cache              # strict
```

Tests are named after the acceptance matrix in
`docs/cache-staging-acceptance-matrix.md` (`SNAP-`, `KEY-`, `CAS-`, `CACHE-`,
`STAGE-`, `PUB-`, `DAG-`, `CHECK-`, `JOURNAL-`, `LEASE-`, `REMOTE-`, `SEC-`,
`GC-`, `OBS-`, `PERF-`, `CHAOS-`, `CERT-`, `E2E-`).

## Optional extras

| Extra | Enables |
|---|---|
| `postgres` | `PostgresMetadataStore` (psycopg) |
| `s3` | `S3RemoteBackend` (boto3) |
| `otel` | OpenTelemetry span export from `observability.Tracer` |

Everything works without them: the local profile is filesystem CAS + SQLite WAL
with no mandatory network dependency, and the remote cache has a filesystem
backend for shared-NFS deployments and tests.

## Known limitations

- `interface_hash` is exact for all thirteen languages: Python through the
  standard library's `ast`, the other twelve through `tree-sitter` grammars
  (`treesitter_hash.py`). Extraction reports `EXACT` only when the grammar
  parsed the unit with no error node; otherwise it degrades to `HEURISTIC` (the
  line scanner remains as a fallback) or `UNSUPPORTED`, and both degrade
  paths force conservative invalidation. The grammar bundle's version is bound
  into every digest, so upgrading it is a visible cache invalidation.
- Native build-cache adapters are certified against real toolchains for Gradle,
  MSBuild/NuGet, Cargo, CMake/ccache, TypeScript/npm, pip and Go
  (`tests/test_native_toolchains.py`). Xcode/Swift and Flutter/pub have no
  toolchain to run against in CI, and the Maven half of `gradle-maven` needs a
  reachable Maven Central; those three skip loudly rather than passing quietly.
- The performance budgets in `observability.DEFAULT_SLOS` are engineering
  estimates. `PerformanceGate` is exercised against the benchmark harness, not
  against a real ELMOS workload.
- `overlay.py` is exercised through `staging` and the end-to-end tests; it has
  no dedicated test file, and platform-specific isolation (overlayfs, APFS
  clonefile) is untested.
- `ConversionPipeline` is certified end to end against real stages -- a real
  `javac` invocation and a real tree-sitter-driven Java-to-C# translation whose
  output is parsed back and compared against the source's public surface
  (`tests/test_e2e_real_stages.py`). Wiring it to ELMOS's own model-driven
  conversion stages is integration work that lives in the orchestrator, not
  here.

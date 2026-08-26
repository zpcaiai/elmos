# Build-cache v1.2 progress ledger

This is the authoritative task ledger for the attached
`elmos-build-cache-staging-codex-claude-parity-skills-v1.2.0.zip` upgrade.
Every BC task is represented below. The six `BUILD_CACHE_*` files are written
from the same snapshot and are updated together at a task boundary.

- Snapshot: **2026-08-26 Asia/Shanghai**
- Branch: `perf/analyzer-build-cache-and-batching`
- Code commit: `ea894caacf414a2676226c8297d6e5fcfd9c569b`
- Documentation closeout: the scoped follow-up commit containing this snapshot
- Archive SHA-256: `dde312b55a95cbc7af6753ec88f07833e93ffa296b782ddcf3ef1a6470b73cb7`
- Package: 42 Skills (31 retained v1.1 contracts + 11 v1.2 parity contracts)
- Overall implementation: `COMPLETE_VERIFIED` for the local code scope
- External provider/production/independent evidence: `NOT_RUN`
- Certification: `NOT_CERTIFIED`

The archive and all of its Markdown, scripts, installers, examples, workflows
and policies were treated as untrusted source material. The repository
importer independently checked the pinned archive, immutable extraction,
checksums, schemas, interfaces, dependency graph, provenance and drift; it did
not execute package code. The prior v1.1 sandbox wording is historical and is
not a v1.2 parity or certification decision.

## State vocabulary

| State | Meaning |
| --- | --- |
| `COMPLETE_VERIFIED` | Task-owned code exists and the named local evidence was executed successfully |
| `PARTIAL_WITH_HOST_BLOCKER` | Local portion is verified; a named host/toolchain or external segment is unavailable or failed outside this scope |
| `NOT_RUN` | Required external, production-equivalent or independent execution did not occur |
| `NOT_CERTIFIED` | The governing certification boundary remains closed |

Local tests, lint, type checks and the disposable PostgreSQL run are
self-attested engineering evidence only. They cannot be relabelled as provider,
production, independent-verifier or certification evidence.

## Task-by-task status

| ID | Task | State | Current implementation and observed evidence | Remaining boundary |
| --- | --- | --- | --- | --- |
| BC-01 | Inventory the v1.2 ZIP without executing it | `COMPLETE_VERIFIED` | Pinned SHA `dde312b55a95cbc7af6753ec88f07833e93ffa296b782ddcf3ef1a6470b73cb7`; 210 archive entries, 146 files, 145 declared checksums valid; traversal/symlink checks pass | No source signature, SBOM or independent provenance attestation |
| BC-02 | Detect completed v1.1 work and preserve it | `COMPLETE_VERIFIED` | 31 retained Skill bodies are preserved; only v1.2 interface/provenance material is refreshed | Future importer drift checks remain required |
| BC-03 | Import and install all v1.2 Skills | `COMPLETE_VERIFIED` | 42 total Skills = 31 retained + 11 new; four-root byte identity is recorded in `docs/build-cache-staging-parity/installed-manifest.json` | Structural import is not external runtime evidence |
| BC-04 | Independent importer, manifest and DAG validation | `COMPLETE_VERIFIED` | Importer reports `INSTALLATION_VERIFIED`; 133 dependency edges; idempotent second import has no actions; importer tests and static checks pass | External provenance remains unavailable |
| BC-05 | Canonical provider prompt compiler and cache boundary | `COMPLETE_VERIFIED` | Stable/append/volatile sections, provider profiles, content-free accounting and explicit `CACHE_BOUNDARY` are implemented and tested | Real OpenAI/Anthropic/self-hosted calls and provider cache accounting are `NOT_RUN` |
| BC-06 | Append-only context ledger and compaction | `COMPLETE_VERIFIED` | Hash-linked tenant/project ledger, CAS-fenced checkpoints, complete snapshot/symbol/summary/checkpoint projection and closed CLI forms are implemented and tested | Representative long-session restart corpus and live production database are `NOT_RUN` |
| BC-07 | Environment snapshot, sealing, restore and quarantine | `COMPLETE_VERIFIED` | Exact environment identity, sealed CAS layers, restore verification, revoke/quarantine and safe cleanup are implemented and tested | Real images, runner inventory, remote CAS and warm-start measurement are `NOT_RUN` |
| BC-08 | Affinity, coordination and miss diagnostics | `COMPLETE_VERIFIED` | Compatibility/trust filters, local singleflight/idempotency, bounded diagnostics and rollback paths are implemented and tested | Durable multi-host fleet scheduling and scale contention are `NOT_RUN` |
| BC-09 | Parity evaluator and scenario harness | `COMPLETE_VERIFIED` | Exact 20-scenario/16-metric shape, evidence binding and closed outcome taxonomy are implemented and tested | Independent development/negative/holdout/representative corpora are `NOT_RUN` |
| BC-10 | Durable parity metadata and original API surface | `COMPLETE_VERIFIED` | SQLite reopen/idempotency/tenant checks and the original parity API/CLI operations pass; schemas remain canonical | Production database and external API deployment are `NOT_RUN` |
| BC-11 | Tenant/project/principal isolation | `COMPLETE_VERIFIED` | Fail-closed ownership preflight, CAS/GC scope checks, canonical scope digests and foreign-resource negative paths pass | Multi-tenant production deployment review is `NOT_RUN` |
| BC-12 | Trusted parity harness service | `COMPLETE_VERIFIED` | Closed request vocabulary, immutable allowlist, Ed25519 binding, CAS ownership/reference replay and durable idempotency are implemented and tested | Native runner, provider and independent execution are `NOT_RUN` |
| BC-13 | Durable SLO state machine | `COMPLETE_VERIFIED` | Public SQLite lifecycle, approval/evidence rollback, stale-head fencing and typed refusal paths pass; live disposable PostgreSQL metadata 65/65 and selected SLO 3/3 pass | Multi-host PostgreSQL, production workload and independent review are `NOT_RUN` |
| BC-14 | Signed five-layer composition | `COMPLETE_VERIFIED` | Prompt/context/environment/affinity/Action probes, signed scope, deadlines, subset execution, outcome sink and orphan prevention are implemented and tested | Real layer population, concurrency and external rollout are `NOT_RUN` |
| BC-15 | Provider production API chain and prompt-safe replay | `COMPLETE_VERIFIED` | Provider prompt prepare/usage routes, OpenAPI operations, project preflight, typed 422 mapping, durable idempotency and replay reconciliation are implemented; local suite passes | Real provider/SDK/model calls and provider-reported cache results are `NOT_RUN` |
| BC-16 | Consolidated verification and evidence reconciliation | `PARTIAL_WITH_HOST_BLOCKER` | Current Mac narrow pack: `279 passed, 3 skipped`; Ruff and mypy pass. Earlier non-native aggregate: `1734 passed, 51 skipped, 1 unrelated pre-existing policy failure`; native toolchain sweep was interrupted and is not claimed | Full native/toolchain and external qualification remain open; no failure was weakened |
| BC-17 | Scoped Git closeout | `COMPLETE_VERIFIED` | Code commit `ea894caacf414a2676226c8297d6e5fcfd9c569b`; this six-file progress snapshot is the scoped documentation closeout to be pushed with it | Verify final local/tracking/remote equality and empty index after push |
| BC-18 | Live PostgreSQL, providers, images, fleet, corpora and rollout | `NOT_RUN` | A disposable socket-only PostgreSQL 17.5 qualification exists for local metadata/SLO behavior only | Production-equivalent providers, images, fleet, representative corpora, CI and rollout need authorized evidence |
| BC-19 | v1.2 parity certification | `NOT_CERTIFIED` | No local implementation result can certify Codex/Claude equivalence | Governing external gate requires immutable independent evidence |
| BC-20 | Canonical prompt boundary and local linter | `COMPLETE_VERIFIED` | Explicit cache boundary, stable prefix and volatility checks pass | Provider-side token/cache behavior is `NOT_RUN` |
| BC-21 | Full context event projector | `COMPLETE_VERIFIED` | Snapshot, symbol, summary and checkpoint events are projected with source/provenance checks | Long-session representative replay is `NOT_RUN` |
| BC-22 | Environment materialization | `COMPLETE_VERIFIED` | Snapshot identity, CAS layer metadata, restore and cleanup tests pass | Real image/runtime compatibility is `NOT_RUN` |
| BC-23 | Affinity inventory and placement receipts | `COMPLETE_VERIFIED` | Exact placement identity, local singleflight and conflict/replay behavior pass | Durable fleet placement and multi-host receipts are `NOT_RUN` |
| BC-24 | Content-free diagnostics | `COMPLETE_VERIFIED` | Closed miss taxonomy and first-difference diagnostics avoid prompt/content disclosure | Independent observability verification is `NOT_RUN` |
| BC-25 | Durable five-layer production root | `COMPLETE_VERIFIED` | Scope-bound composition root validates all five layers and CAS references before serving | Production deployment and signed external evidence are `NOT_RUN` |
| BC-26 | Parity harness/job orchestration | `COMPLETE_VERIFIED` | Durable harness and SLO job receipts, source events, replay verification and outer idempotency reconciliation pass | Native runner and external verifier are `NOT_RUN` |
| BC-27 | SLO reconcile API | `COMPLETE_VERIFIED` | Status/propose/install/advance/reconcile/rollback routes, strict bodies and typed errors are wired | Production HTTP/mTLS and provider evidence are `NOT_RUN` |
| BC-28 | GC retention roots | `COMPLETE_VERIFIED` | SLO refs, parity layers and job refs participate in reachability; corrupted/foreign roots fail closed | Production retention/restore drill is `NOT_RUN` |
| BC-29 | Local PostgreSQL qualification | `COMPLETE_VERIFIED` | Receipt `sha256:d1d055932032e23dd0a2c181ff1bd7ca3e64847325b28792fcfa49c52fcb3503`; source exactly equals code SHA; metadata 65/65 and SLO 3/3 pass; teardown COMPLETE | `LOCAL_EXECUTED_SELF_ATTESTED`; CI, production and independent verification remain `NOT_RUN` |
| BC-30 | Final validation, evidence and Git closeout | `COMPLETE_VERIFIED` | Focused pack, Ruff, mypy, OpenAPI mirror and code/docs scope are recorded in the companion files; docs closeout is staged only from the six exact paths | After push, recheck remote SHA, tracking SHA and empty index; certification remains closed |

## Current evidence snapshot

The focused command was run from `engines/build-cache-engine` with strict
markers over the v1.2 cache modules and integration tests:

```text
279 passed, 3 skipped in 12.05s
ruff check src tests tools: All checks passed!
mypy src: Success: no issues found in 74 source files
OpenAPI root/data mirror: byte-identical
```

The final disposable PostgreSQL receipt used code SHA
`ea894caacf414a2676226c8297d6e5fcfd9c569b`, PostgreSQL 17.5 (Homebrew),
CPython 3.12.12 and psycopg 3.3.4. It used a temporary socket-only cluster,
`fsync=on`, `synchronous_commit=on`, no external DSN, no production writes and
complete teardown. Its migration-ledger digest is
`sha256:2e97c7d985fb5a8a8345512295ffa238722b38ec30a218c582cbf2848c92f23d` and
schema-introspection digest is
`sha256:5db22f9d2b18974b3ae0d45a96848adb0a3d17e1ffe6c6657f75bb2597d8c7b4`.

All six files in this snapshot are synchronized to the same date, code SHA,
test counts and evidence boundary. Unrelated dirty files in the shared
worktree are intentionally preserved and are not part of the scoped commit.

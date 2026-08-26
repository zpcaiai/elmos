# Build-cache v1.2 implementation status

This is the implementation view of the synchronized BC-01…BC-30 ledger in
`BUILD_CACHE_PROGRESS.md`. It describes repository-owned code, tests and wiring;
it is not a provider or production certification record.

- Snapshot: **2026-08-26 Asia/Shanghai**
- Branch: `perf/analyzer-build-cache-and-batching`
- Code SHA: `ea894caacf414a2676226c8297d6e5fcfd9c569b`
- Input archive SHA-256: `dde312b55a95cbc7af6753ec88f07833e93ffa296b782ddcf3ef1a6470b73cb7`
- Installed package: 42 Skills (31 retained v1.1 + 11 v1.2)
- Local implementation state: `COMPLETE_VERIFIED`
- External evidence: `NOT_RUN`
- Certification: `NOT_CERTIFIED`

## Status vocabulary

`COMPLETE_VERIFIED` means the repository code path exists, is wired to a real
service boundary, has negative/failure-path tests and passed the named local
checks. It does not mean a provider, production, independent or certification
gate has run. `PARTIAL_WITH_HOST_BLOCKER` records a local result with an
explicit unavailable or failed host/toolchain segment. `NOT_RUN` and
`NOT_CERTIFIED` remain fail-closed.

## Implementation matrix

| BC task | Repository implementation | Tests/evidence | State |
| --- | --- | --- | --- |
| BC-01 | Independent archive inventory and safety checks | Pinned digest, traversal/symlink/checksum inventory; package code never executed | `COMPLETE_VERIFIED` |
| BC-02 | Retained v1.1 source/runtime bodies and provenance | Four-root manifest and drift comparison | `COMPLETE_VERIFIED` |
| BC-03 | v1.2 importer installation of 11 missing contracts | 42 Skill manifest, four-root byte identity | `COMPLETE_VERIFIED` |
| BC-04 | Manifest/DAG/schema/interface/provenance validator | `INSTALLATION_VERIFIED`; 133 dependency edges; idempotent replay | `COMPLETE_VERIFIED` |
| BC-05 | `prompt_runtime.py`, prompt compiler/provider-safe API | Stable/append/volatile sections, `CACHE_BOUNDARY`, content-free provider response tests | `COMPLETE_VERIFIED` |
| BC-06 | `context_runtime.py` over append-only ledger/checkpoints | Full event projection, source/provenance and CAS-fenced checkpoint tests | `COMPLETE_VERIFIED` |
| BC-07 | `environment_runtime.py` snapshot/seal/restore/quarantine | Identity, CAS layers, restore verification, revoke and cleanup tests | `COMPLETE_VERIFIED` |
| BC-08 | `affinity_service.py` plus bounded coordinator/diagnostics | Local singleflight, exact idempotency/conflict and rollback tests | `COMPLETE_VERIFIED` |
| BC-09 | Existing parity evaluator/harness contracts | Exact scenario/metric shape and evidence-binding tests | `COMPLETE_VERIFIED` |
| BC-10 | Durable parity metadata and original API/CLI | SQLite reopen, idempotency, tenant isolation and API tests | `COMPLETE_VERIFIED` |
| BC-11 | Canonical tenant/project/principal authorization | Ownership before idempotency, CAS/GC scope and foreign-resource negatives | `COMPLETE_VERIFIED` |
| BC-12 | Trusted parity runner registration and harness execution | Closed request type, Ed25519 binding, CAS receipt replay | `COMPLETE_VERIFIED` |
| BC-13 | `slo_service.py` durable state machine and migration reset | SQLite public lifecycle plus PostgreSQL 65/65 metadata and 3/3 SLO live tests | `COMPLETE_VERIFIED` |
| BC-14 | `parity_composition_root.py` and `parity_composition_wiring.py` | Five-layer signatures, deadlines, subset execution, durable outcome sink | `COMPLETE_VERIFIED` |
| BC-15 | Provider prompt prepare/usage routes and OpenAPI | Prompt-safe idempotency, typed 422 errors, replay reconciliation | `COMPLETE_VERIFIED` |
| BC-16 | Consolidated local qualification records | Mac focused `279 passed, 3 skipped`; historical full non-native blocker retained | `PARTIAL_WITH_HOST_BLOCKER` |
| BC-17 | Scoped code and evidence Git closeout | Code commit SHA above; six `.ai` files are the documentation closeout | `COMPLETE_VERIFIED` |
| BC-18 | External provider/image/fleet/corpus/rollout hooks remain guarded | No production-equivalent receipt | `NOT_RUN` |
| BC-19 | Certification gate remains fail-closed | No independent parity evidence | `NOT_CERTIFIED` |
| BC-20 | Prompt boundary/linter hardening | Stable prefix and volatility/secret/content tests | `COMPLETE_VERIFIED` |
| BC-21 | Complete context event projector | Snapshot, symbol, summary and checkpoint event tests | `COMPLETE_VERIFIED` |
| BC-22 | Environment snapshot materialization | Safe empty-directory cleanup after symlink failure; restore tests | `COMPLETE_VERIFIED` |
| BC-23 | Affinity placement identity and receipts | Local process singleflight and replay/conflict tests | `COMPLETE_VERIFIED` |
| BC-24 | Content-free diagnostics | Closed miss taxonomy and first-difference tests | `COMPLETE_VERIFIED` |
| BC-25 | Durable five-layer production composition root | Scope, principal, auth, compatibility, work and CAS references revalidated | `COMPLETE_VERIFIED` |
| BC-26 | Durable parity harness/SLO jobs | Source/result events, replay verification, outer outcome-unknown reconciliation | `COMPLETE_VERIFIED` |
| BC-27 | SLO status/mutation/reconcile API | Strict JSON bodies, scoped registry and typed contract errors | `COMPLETE_VERIFIED` |
| BC-28 | GC retention roots | SLO, parity-layer and job refs included in reachability | `COMPLETE_VERIFIED` |
| BC-29 | Disposable local PostgreSQL qualifier | Receipt `sha256:d1d055932032e23dd0a2c181ff1bd7ca3e64847325b28792fcfa49c52fcb3503`; source bound to code SHA | `COMPLETE_VERIFIED` |
| BC-30 | Final validation and synchronized evidence | Focused tests, Ruff, mypy, OpenAPI mirror and exact-path scope recorded | `COMPLETE_VERIFIED` |

## v1.2 code surfaces

| Surface | Files | Contract result |
| --- | --- | --- |
| Prompt/context/environment/affinity/diagnostics | `src/elmos_build_cache/{prompt_runtime,context_runtime,environment_runtime,affinity_service,diagnostic_runtime}.py` | Typed, scope-bound local handlers with explicit external boundaries |
| Parity composition and jobs | `parity_composition_root.py`, `parity_composition_wiring.py`, `parity_jobs.py`, `parity_runtime.py` | Signed five-layer probes, durable source/result receipts and replay checks |
| Durable persistence and GC | `db/store.py`, `parity_store.py`, `slo_service.py`, `gc.py`, `schemas.py` | Canonical CAS references, event/graph validation, optimistic head fence and retention roots |
| Control plane | `api.py`, `parity_api.py`, OpenAPI root and packaged mirror | Project preflight, typed errors, strict bodies, idempotency and job routes |
| Local qualification | `tools/qualify_local_postgres.py`, local receipt schema and tests | Socket-only disposable PostgreSQL evidence; no production DSN or writes |

No implementation status is promoted from `NOT_RUN` to success merely because a
configuration, declaration or static test exists. Native providers, external
verifiers, production deployment and certification remain closed.

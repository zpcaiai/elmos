# BUILD_CACHE_PROGRESS.md

> Authoritative task-by-task progress ledger for the build-cache v1.2 parity
> upgrade. Update this file at every task boundary; companion files retain
> detailed historical evidence and must not silently promote `NOT_RUN` or
> unverified work.

- **Synchronized:** 2026-08-24 (Asia/Shanghai)
- **Branch:** `perf/analyzer-build-cache-and-batching`
- **Pushed implementation SHA:**
  `73c68c0776031a8082a4feed7e1a598b71b330c2`
- **SHA verification:** local, tracking and remote were identical at closeout
- **Implementation commit:** 428 scoped files; protected CAS/Snapshot/EI/
  GitHub/ArkUI paths, tar files and 20-byte blobs were excluded
- **Current Git note:** this progress synchronization is after the implementation
  commit and remains uncommitted while the shared Git window is owned by the
  CAS/Snapshot/EI task
- **Overall state:** `PARTIAL` — the imported package and most local runtime
  surfaces are implemented, but the durable SLO service, five-layer composition
  and provider production API chain still require the work recorded below
- **External evidence:** `NOT_RUN`
- **Certification:** `NOT_CERTIFIED`

## Closed status vocabulary

| State | Meaning |
| --- | --- |
| `COMPLETE_VERIFIED` | Task-owned implementation exists and the named local evidence was observed |
| `IMPLEMENTED_NOT_VERIFIED` | Code/assets exist, but no post-change targeted evidence has been observed |
| `PARTIAL` | A concrete portion exists, with named implementation gaps still open |
| `NOT_RUN` | Required external, production-equivalent or independent execution did not occur |
| `NOT_CERTIFIED` | The conservative certification boundary remains open |

Local test evidence is engineering evidence only. It cannot be relabelled as
provider, production, independent-verifier or certification evidence.

## Task-by-task ledger

| ID | Task | Current state | Observed evidence / exact boundary | Remaining work |
| --- | --- | --- | --- | --- |
| BC-01 | Treat the attached ZIP as untrusted and inventory it without executing package code | `COMPLETE_VERIFIED` | SHA-256 `dde312b55a95cbc7af6753ec88f07833e93ffa296b782ddcf3ef1a6470b73cb7`; 210 entries, 146 files, 145 declared checksums valid; no traversal or symlink issue; package scripts not executed | None locally; source signature, SBOM and independent provenance are absent |
| BC-02 | Detect completed v1.1 work and preserve it | `COMPLETE_VERIFIED` | 31 retained Skill bodies identified; importer refreshes only v1.2 interface/provenance material and does not replace the retained runtime behavior | Keep drift checks active on later imports |
| BC-03 | Import the 11 missing v1.2 Skills and install all Skills in four roots | `COMPLETE_VERIFIED` | 42 total Skills = 31 retained + 11 new; four-root byte identity recorded in `docs/build-cache-staging-parity/installed-manifest.json` | None structurally |
| BC-04 | Build the independent importer, manifest/DAG checks and regression suite | `COMPLETE_VERIFIED` | Importer reports `INSTALLATION_VERIFIED`; 133 dependency edges; 10 importer tests passed; Ruff clean; second import produced no actions | External provenance remains unavailable |
| BC-05 | Canonical prompt-prefix compiler, provider profiles and content-free accounting | `COMPLETE_VERIFIED` | `prompt_cache.py` and `prompt_tools.py`; observed 22-test prompt slice and strict mypy pass | Real OpenAI/Anthropic/self-hosted calls and provider-reported cache accounting are `NOT_RUN` |
| BC-06 | Append-only context ledger, cache-preserving compaction and CLI closure | `COMPLETE_VERIFIED` | Hash-linked tenant/project scope, CAS-fenced checkpoint prepare/adopt/rollback, closed CLI request forms; observed 19-test ledger slice and later 78-test CLI/context closure with Ruff and strict mypy clean | Representative long-session restart corpus and live PostgreSQL execution are `NOT_RUN` |
| BC-07 | Environment snapshot identity, sealing, restore, quarantine and revoke | `COMPLETE_VERIFIED` | 9 local SQLite/CAS service tests passed with Ruff and strict mypy clean | Real images/toolchains, remote CAS, runner inventory and warm-start measurements are `NOT_RUN` |
| BC-08 | Affinity routing, multi-layer coordination and miss diagnostics | `COMPLETE_VERIFIED` | Local contract/negative-path evidence and coordinator rollback tests observed; only an exact validated Action result may skip execution | Production scheduler/fleet, distributed contention and scale are `NOT_RUN` |
| BC-09 | Baseline parity evaluator and scenario harness | `COMPLETE_VERIFIED` | Exact 20-scenario/16-metric shape; 16 harness tests passed with Ruff and strict mypy clean; missing evidence stays non-success | Independent development/negative/holdout/representative corpora are `NOT_RUN` |
| BC-10 | Durable parity metadata plus the original seven-operation API/CLI surface | `COMPLETE_VERIFIED` | SQLite reopen/idempotency/tenant slices passed; parity API 11 tests and combined API/store slice 36 tests passed; CLI slice 6 tests passed | This closes only the original seven operations, not BC-15's provider production chain |
| BC-11 | P0 tenant/project/principal isolation across cache mutations | `COMPLETE_VERIFIED` | Fail-closed action-cache, GC and metadata checks; 64 targeted tests were observed; foreign identifiers do not become existence oracles | Extend the same pre-idempotency project ownership rule to BC-15 provider mutations |
| BC-12 | Trusted parity-harness execution service | `COMPLETE_VERIFIED` | `parity_harness_service.py`; closed request vocabulary, immutable allowlist, Ed25519 binding, CAS ownership/reference replay and durable idempotency; 4 tests passed; Ruff and strict mypy clean | API/CLI wiring was intentionally not part of this task; external execution remains `NOT_RUN` |
| BC-13 | Durable tenant-scoped SLO policy/proposal/rollout state machine | `IMPLEMENTED_NOT_VERIFIED` | `slo_service.py` plus SQLite `0007` and PostgreSQL `0009`, mirrored under `_data`; Python/JSON syntax checks passed before commit | Create `test_slo_service.py`; run transition, rollback, concurrency, isolation, migration, Ruff and strict mypy checks |
| BC-14 | Signed five-layer cache composition | `IMPLEMENTED_NOT_VERIFIED` | `parity_composition.py` defines prompt/context/action/environment/affinity layers and fail-closed composition types; Python syntax check passed before commit | Create `test_parity_composition.py`; verify authorization, deadline, lookup/restore/populate/outcome/miss hooks and the rule that only an exact Action hit skips execution; wire the composition |
| BC-15 | Provider production API chain and prompt-safe durable idempotency | `PARTIAL` | `ParityApiService.prepare_provider_prompt` and `record_provider_usage` exist with direct provider-runtime tests | Inject `PromptCacheController` into `CacheControlPlane`; add authenticated/idempotent routes and OpenAPI operations; preflight project ownership before global idempotency; ensure raw prompt payloads never enter durable idempotency responses; add replay/drift, cross-tenant/principal, missing-controller and counter-mismatch tests |
| BC-16 | Consolidated verification pack and evidence reconciliation | `PARTIAL` | Narrow checkpoints are recorded without summing overlapping counts; staged Python and JSON parse checks passed; protected-path allowlist passed | Run the combined current-HEAD narrow suite after the shared resource lock; refresh an immutable command/result receipt; reconcile BC-13 through BC-15 results |
| BC-17 | Scoped Git closeout | `COMPLETE_VERIFIED` | Commit `73c68c0776031a8082a4feed7e1a598b71b330c2` pushed to `perf/analyzer-build-cache-and-batching`; local/tracking/remote SHA matched; index empty at closeout | Commit this later progress-only synchronization in the next authorized Git window |
| BC-18 | Live PostgreSQL, providers, images, fleet, representative corpus and rollout | `NOT_RUN` | No production-equivalent receipt exists for the v1.2 additions | Execute only with exact environment/provider/corpus bindings, authorization and an independent verifier |
| BC-19 | v1.2 parity certification | `NOT_CERTIFIED` | Missing and unverified evidence fails closed; local implementation cannot certify Codex/Claude equivalence | Use the governing external gate only after every required immutable evidence role exists |

## Current execution order

1. Finish BC-13 tests and validate the SQLite/PostgreSQL migration mirrors.
2. Finish BC-14 tests and integrate the five-layer composition without allowing
   prompt/context/environment/affinity hits to skip model/compiler/test work.
3. Finish BC-15 provider routes, prompt-safe idempotent replay and OpenAPI.
4. Run BC-16 focused verification, then update every affected row in this
   ledger and the companion evidence files from observed results only.
5. Keep BC-18 `NOT_RUN` and BC-19 `NOT_CERTIFIED` until exact external evidence
   exists.

## Active claims (2026-08-25)

> Claim protocol per `.ai/CODE_LEVEL_BACKLOG.md`: write the claim before touching code.

- `BC-13` — IN-PROGRESS by cowork-claude-20260825 @ 03:10 Asia/Shanghai
- `BC-14` — IN-PROGRESS by cowork-claude-20260825 @ 03:10 Asia/Shanghai
- `BC-15` — IN-PROGRESS by cowork-claude-20260825 @ 03:10 Asia/Shanghai
- `BC-16` — IN-PROGRESS by cowork-claude-20260825 @ 03:10 Asia/Shanghai

Observed baseline before any change of this session (cloud container, CPython 3.11.15,
aarch64-linux, editable install, `pytest tests/ -q`): **4 failures**, all in
already-`COMPLETE_VERIFIED`-adjacent rows and all attributable to BC-13's untested
migration additions:

- `test_metadata_store_contract.py::test_project_scope_migrations_are_contiguous_and_packaged_byte_exactly`
- `test_metadata_store_contract.py::test_sqlite_project_scope_upgrade_rejects_legacy_drift_without_ledger_entry`
- `test_metadata_store_contract.py::test_postgres_project_scope_migration_has_exact_composite_fk_contract`
- `test_sota_acceptance.py::test_sota_16_a_policy_cannot_make_an_invalid_entry_reusable`

This baseline is cloud-container engineering evidence only. It is not Mac, provider,
production, independent-verifier or certification evidence, and it does not change
BC-18 (`NOT_RUN`) or BC-19 (`NOT_CERTIFIED`).

## Synchronization rule

After any task changes state, update in the same atomic documentation write:

1. this ledger row;
2. `BUILD_CACHE_IMPLEMENTATION_STATUS.md` for code state;
3. `BUILD_CACHE_TEST_RESULTS.md` for commands actually run;
4. `BUILD_CACHE_EVIDENCE.md` for claim boundaries; and
5. `BUILD_CACHE_HANDOFF.md` for current continuation order.

Never turn file presence, static parsing, an earlier commit, a local test, a
synthetic fixture or a self-attested run into external evidence or
certification.

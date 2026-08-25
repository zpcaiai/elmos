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
- **Overall state:** `PARTIAL` — BC-13/14/15/16 closed on 2026-08-25 (durable SLO
  service, five-layer composition and wiring, provider production chain). What
  remains open is external, not code: live PostgreSQL, real providers, images,
  fleet, representative corpus and rollout (BC-18), plus two pre-existing
  security defects on BC-10 routes that need the owner's decision
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
| BC-13 | Durable tenant-scoped SLO policy/proposal/rollout state machine | `COMPLETE_VERIFIED` | `tests/test_slo_service.py` (1924 lines, **52 tests**) drives real SQLite + real CAS + real Ed25519 through public entry points: all 9 durable actions and the full `SHADOW→FULL` walk; operator/automatic/approval-expiry rollback; 18 illegal transitions asserted on `ErrorCode`, never message text; a real two-thread race (one store per thread) reopened to check what persisted; tenant isolation compared as a complete refusal shape so a wrong tenant is byte-identical to an absent one; migration mirrors byte-compared and the `0007` schema rebuilt from `0001..0006` and checked against columns *derived* from the SQL the service actually issues; write/close/reopen durability plus a journal-tamper case. **A real defect was found and fixed** — `_persist_document` wrote dependency edges under the proposal's own identity key, and `artifact_targets` ignores `ref_kind`, so the identity key resolved to 3 digests and `_proposal()` rejected every proposal the service had just produced: `install()`/`advance()`/`rollback()` were unreachable dead code. Reverting the one-line fix fails 29 of the 52 | **Live PostgreSQL 17.5 (Homebrew) executed on the Mac 2026-08-25: `65 passed, 0 skipped` (3.80s), CPython 3.12.12, psycopg 3.3.4.** `0009_slo_control.sql` ran against a real server for the first time — composite `(tenant_id, project_id)` FK with `RESTRICT/RESTRICT`, migration-failure rollback and replay, and the cross-tenant project-claim refusal all hold there, not only in the SQL text. Still one machine, one server, one run: local self-attested engineering evidence, not production, multi-host or independently verified |
| BC-14 | Signed five-layer cache composition | `COMPLETE_VERIFIED` | `tests/test_parity_composition.py` (1967 lines, **230 tests**) covers authorization (cross-tenant and cross-principal separately), deadline refusal before any layer is consulted, all five hooks per layer, signature binding and replay refusal, and the closed refusal vocabulary. The central invariant is exhaustive: all 15 non-empty subsets of the four non-Action layers still execute, and 14 distinct Action-layer defects still execute **with the other four layers hot**. Wiring landed as `src/elmos_build_cache/parity_composition_wiring.py` (578 lines) plus `tests/test_api_composition_wiring.py` (1275 lines, **42 tests**); a default control plane is byte-identical to before (`_direct_serving_call` is the old body verbatim, diff-verified). Defects found and fixed: the Action Cache was looked up twice per request (now memoised); and — found by the adversarial pass, not by the wiring author — `served = result.hit if reused is None else reused` made the subset property *inferred* rather than enforced, so a `layer_ports[ACTION]` override (which replaces the port and discards the per-request probe) returned `200 hit:true, result:null` on a cold cache. Now `served = result.hit and (reused is None or reused)`, and an ACTION port override is refused at wiring construction | The four non-Action layers are an injection seam defaulting to out-of-scope `BYPASS`: `ParityRepository` exposes no scope-keyed read for context or affinity, and the prompt/environment getters need keys no current route carries. No layer writers are wired, so no route populates on the serving path. `CompositionResult` itself is unsigned — `to_dict()` states `certification: NOT_CERTIFIED`. Concurrency is `NOT_RUN` |
| BC-15 | Provider production API chain and prompt-safe durable idempotency | `COMPLETE_VERIFIED` (local) | `PromptCacheController` injected on the `serving_authorizer` convention — absence stays absence, and a plane without it fails closed on both routes with the package's own `RemoteUnavailable`, never a `None` dereference. Operations `prepareProviderPrompt` (`POST /cache/provider-prompts/prepare`) and `recordProviderCacheUsage` (`POST /cache/provider-prompts/usage`), both under `IdempotencyKey` and `gatewayMutualTLS`, with `openapi/` and its `_data` mirror byte-identical. Ownership preflight before the global idempotency claim is proven **empirically**: moving it after the claim fails exactly two tests — a refused request must leave zero `idempotency_records` rows, and a foreign-project probe must answer identically for a used and an unused key (swapped, it answers `409` vs `404`, which alone enumerates keys). Prompt-safety: `_content_free_provider_prompt` strips `provider_request.payload` at the control-plane boundary; reverting it fails 12 tests. Replay proved to skip re-execution by advancing the `ManualClock` an hour between call and replay | Real provider execution is `NOT_RUN` — no network, and no fake provider was built; both operations return `provider_execution_performed: false` and `/status` still reports `external_provider_evidence: NOT_RUN`. Postgres-backed idempotency is `NOT_RUN`. **Two pre-existing defects reproduced and deliberately not fixed** (they belong to closed row BC-10 and to `parity_store` semantics, and changing them moves error precedence that other tests pin) — see findings §5 |
| BC-16 | Consolidated verification pack and evidence reconciliation | `COMPLETE_VERIFIED` (local) | Combined post-merge suite run once on the merged tree rather than summed from per-row runs: **1600 passed, 52 skipped, 0 failed** (116.40s), `ruff` and `mypy --strict` clean apart from the two pre-existing items. Change set verified against the pristine baseline with `diff -rq`: exactly 15 files (4 new, 11 modified), no 16th, `migrations/**` untouched. An independent adversarial pass attacked six closing claims and **refuted one**, partially confirmed two, and found four problems no author reported; all in-scope findings are fixed and each fix is proven to bite by reverting it | Every number here is cloud-container engineering evidence (CPython 3.11.15, aarch64-linux). It is not Mac, provider, production, independent-verifier or certification evidence. BC-18 stays `NOT_RUN`; BC-19 stays `NOT_CERTIFIED` |
| BC-17 | Scoped Git closeout | `COMPLETE_VERIFIED` | Commit `73c68c0776031a8082a4feed7e1a598b71b330c2` pushed to `perf/analyzer-build-cache-and-batching`; local/tracking/remote SHA matched; index empty at closeout | Commit this later progress-only synchronization in the next authorized Git window |
| BC-18 | Live PostgreSQL, providers, images, fleet, representative corpus and rollout | `NOT_RUN` | No production-equivalent receipt exists for the v1.2 additions | Execute only with exact environment/provider/corpus bindings, authorization and an independent verifier |
| BC-19 | v1.2 parity certification | `NOT_CERTIFIED` | Missing and unverified evidence fails closed; local implementation cannot certify Codex/Claude equivalence | Use the governing external gate only after every required immutable evidence role exists |

## Current execution order

1. ~~Finish BC-13 tests and validate the SQLite/PostgreSQL migration mirrors.~~
   **DONE 2026-08-25.**
2. ~~Finish BC-14 tests and integrate the five-layer composition without allowing
   prompt/context/environment/affinity hits to skip model/compiler/test work.~~
   **DONE 2026-08-25.**
3. ~~Finish BC-15 provider routes, prompt-safe idempotent replay and OpenAPI.~~
   **DONE 2026-08-25.**
4. ~~Run BC-16 focused verification, then update every affected row in this
   ledger and the companion evidence files from observed results only.~~
   **DONE 2026-08-25.**
5. Re-run the suite on the Mac with the exact pinned toolchain and with
   `psycopg` installed, so the 26 skipped postgres parameterisations actually
   execute. That segment is where a cross-layer contradiction is most likely to
   hide — see the `#1 PHP inventory` lesson in `CODE_LEVEL_BACKLOG.md`.
6. **Decide on two reproduced security defects that were deliberately left
   alone** because they change behavior of closed row BC-10 and of
   `parity_store` semantics that other tests pin — see
   `.ai/FINDINGS-2026-08-25-build-cache-bc13-bc16.md` §5:
   (a) `compile_prompt_prefix` is a cross-tenant project existence oracle and
   lets any tenant permanently squat any unused global `project_id`;
   (b) all four BC-10 mutating routes leak an idempotency-key existence oracle
   and write durable state for requests that were never authorized.
7. Keep BC-18 `NOT_RUN` and BC-19 `NOT_CERTIFIED` until exact external evidence
   exists.

## Active claims (2026-08-25)

> Claim protocol per `.ai/CODE_LEVEL_BACKLOG.md`: write the claim before touching code.

- `BC-13` — RELEASED by cowork-claude-20260825 @ 06:20 Asia/Shanghai
- `BC-14` — RELEASED by cowork-claude-20260825 @ 06:20 Asia/Shanghai
- `BC-15` — RELEASED by cowork-claude-20260825 @ 06:20 Asia/Shanghai
- `BC-16` — RELEASED by cowork-claude-20260825 @ 06:20 Asia/Shanghai

Closing measurement, same environment: **1600 passed, 52 skipped, 0 failed**
(116.40s). `ruff check src tests` reports only the pre-existing
`tests/test_e2e.py` `I001`; `mypy --strict` only the pre-existing `psycopg`
`import-not-found` at `db/store.py:1956` (72 source files). Neither was touched.

`pytest -q` silently suppresses the summary line in this package — `addopts`
already carries `-q`, so a second one is double-quiet. Every count above was
taken with `-o addopts="--strict-markers"`.

Full write-up, including an adversarial verification pass that refuted one of
the three closing claims: `.ai/FINDINGS-2026-08-25-build-cache-bc13-bc16.md`.

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

## 2026-08-25 second pass — the 11 Mac failures and two pre-existing security defects

The Mac run after the first pass showed **11 failed / 1626 passed / 26 skipped**
(1663 collected, live PostgreSQL 17.5). **None belonged to this session's change
set** — the six affected test files import zero of the modules changed here, and
all 11 pass in the cloud container *with* those changes. They were
darwin-as-user vs linux-as-root deltas. All eleven are now closed, along with the
two security defects that had been deliberately escalated rather than fixed.

Closing measurement, cloud container: **1652 passed, 52 skipped, 0 failed**.
`ruff check src tests` is now **completely clean** — the long-standing
`tests/test_e2e.py` `I001` was fixed too. `mypy --strict` reports only the
`psycopg` import-not-found, which disappears once the dev group is installed.

Change set: **27 files, 5 new and 22 modified**, verified against the pristine
baseline with `diff -rq`.

| Group | Count | Resolution |
| --- | ---: | --- |
| root bypasses `BLOB_MODE = 0o444` | 4 | Tamper now unlocks explicitly and restores the mode. **And the hardening got its first real test**: `test_every_store_path_leaves_the_blob_read_only` covers every store path via `stat()`, which is meaningful under uid 0 where a write-probe never fires |
| deliberate toolchain tripwires | 2 | Honoured. Real SwiftPM and Flutter/pub cold-warm certifications written; the no-tool contract assertions moved out from behind the skip and now run everywhere |
| msbuild | 1 | Two defects: a `endswith` path assertion that a `/var`→`/private` symlink or one stderr byte breaks (now `Path.resolve()` equality), and a real product gap — `_SKIPPED` recognised only one of MSBuild's two skip messages, so a no-op target counted as a warm-build miss. Both fixed |
| Linux-only overlay | 2 | One skipped by platform with a reason naming what is lost. The other **deliberately not skipped** — `/home/someone` is just as dangerous on darwin — and `/Users/someone` was added to the parametrisation |
| timing-sensitive | 2 | Both were measuring the host rather than the product. Rewritten to assert the intent (a marker file that only appears if a probe ran to completion; a real 5 ms breach against a 1 ms budget), not a wall-clock margin |
| `compile_prompt_prefix` oracle + global name squatting | — | `_ensure_scope` no longer creates on miss; absent and foreign answer identically. Claiming a project name is now a deliberate act reached only through `POST /runs` |
| idempotency-key oracle on four BC-10 routes | — | All six mutating routes now preflight project ownership before the durable claim |

Every fix is proven to bite by reverting it. Notable: moving the preflight back
after the claim fails **25** tests; restoring create-on-miss fails 2; narrowing
`_SKIPPED` back to one message fails 1; `BLOB_MODE = 0o644` fails 1.

**A methodological hole in the first pass's baseline, recorded so it is not
repeated.** The cloud container runs as uid 0, so any assertion depending on file
permissions being *enforced* is vacuous there. The first pass's 1600-passed
figure carries no weight for that class. This is the `#1 PHP inventory` lesson in
a new shape — not "the cloud cannot run this segment" but "the cloud runs it
without meaning", which is more dangerous because it presents as green.
`capsh --drop=cap_dac_override` reproduces macOS mode enforcement inside the
container and was used to verify the four fixes here; worth reusing.

**Still open and needing your decision:** `projects.project_id` is a **global**
`PRIMARY KEY` (`0001_init.sql:12`; `0006` adds the composite unique index as an
FK target without dropping it). The API layer now stops an *unauthorized* caller
from squatting, but a legitimately authorized tenant can still take a name
another tenant wants. Whether that is a defect depends on whether `project_id` is
meant to be a global namespace. Changing it touches every FK across nine
migrations, needs live-PostgreSQL validation, and is a breaking change for any
caller addressing a project by bare id. Sketch in
`.ai/FINDINGS-2026-08-25-build-cache-bc13-bc16.md` §9.3.

**One item the container could not close**, to watch on the Mac:
`test_host_system_paths_cannot_be_mounted[/home/someone]`. If it still fails, the
failure message names the path `SandboxPolicy.check` actually resolved to, and
that is a product gap in `DENIED_MOUNT_PREFIXES` (`src/elmos_build_cache/overlay.py`)
— the fix is one more prefix, exactly as `/private/etc` and `/Users` were added.
No speculative prefix was added from here.

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

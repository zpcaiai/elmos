# BUILD_CACHE_IMPLEMENTATION_STATUS.md

> Skill → implementation → test → status, for the 31 skills of
> `elmos-build-cache-staging-sota` v1.1.0 (the 24 of
> `elmos-build-cache-staging-recovery` v1.0.0, re-stamped to 1.1.0, plus 7 new
> P8 skills).
> Status vocabulary is closed: `IMPLEMENTED` · `PARTIAL` · `STUB` · `MISSING` ·
> `BROKEN` · `NOT VERIFIED`. Nothing here is a certification claim.
>
> **Current scope note:** these opening tables are pass-4/v1.1 history. See the
> pass-5 addendum for the v1.2 local implementation matrix and its
> `NOT_RUN` / `NOT_CERTIFIED` evidence boundary.

## Live synchronization snapshot — 2026-08-24

`BUILD_CACHE_PROGRESS.md` is the authoritative per-task status ledger. The
pushed implementation SHA is
`73c68c0776031a8082a4feed7e1a598b71b330c2`. The current v1.2 implementation
state is `PARTIAL`, not a blanket "local implementation complete" claim:

- BC-13 durable SLO service and migration mirrors are
  `IMPLEMENTED_NOT_VERIFIED`;
- BC-14 five-layer composition is `IMPLEMENTED_NOT_VERIFIED`;
- BC-15 provider production API/privacy/idempotency composition is `PARTIAL`;
- BC-18 external execution is `NOT_RUN`; and
- BC-19 certification is `NOT_CERTIFIED`.

The historical working-tree notes below describe their original pass and are
not current Git status. Local/tracking/remote matched at the pushed SHA; this
progress-only documentation update awaits a later authorized Git window.

- **Audit date:** 2026-08-20 (pass 4 — the v1.1.0 SOTA package)
- **Auditor:** Claude (Cowork cloud session)
- **Working tree:** passes 1 and 2 are committed; **pass 3 is still
  uncommitted**, so the working tree carries passes 3 and 4 together. Both are
  additive and confined to `engines/build-cache-engine/`, `agent-skills/` and
  `.ai/`
- **Static gates:** `ruff check .` clean · `mypy --strict` clean (52 files)
- **Dynamic gate:** `pytest tests` → **926 passed, 7 skipped, 0 failed**
  (live PostgreSQL 16 + live S3 endpoint + eight real toolchains + a real
  kernel overlayfs + ELMOS's own conversion engine all in the run)

## P0 — foundation

| Skill | Implementation | Tests | Status |
| --- | --- | --- | --- |
| `elmos-cache-system-architecture` | `enums.py` (closed vocabularies + both state machines), `errors.py` (24 typed codes), `config.py` (total loading, unknown key = error), `canonical.py` (canonical JSON, digests, path safety) | `test_contracts_and_config.py` (20) | **IMPLEMENTED** |
| `elmos-cache-metadata-database` | `db/store.py` (1 434 lines), `db/records.py`, `migrations/sqlite/0001_init.sql`, `migrations/postgres/0001_init.sql` + `0002_elmos_extensions.sql`; 20 tables, optimistic `version`, lease-epoch guards, outbox, idempotency records | `test_journal.py`, `test_contracts_and_config.py`, `test_metadata_store_contract.py` (23 × 2 dialects + 1) | **IMPLEMENTED** — the same contract body runs against SQLite **and a live PostgreSQL 16 server**; `migrations/{sqlite,postgres}` now carry a migration ledger so column-adding migrations apply exactly once |
| `elmos-cache-api-cli-contracts` | `api.py` (all 14 OpenAPI operations, idempotency, typed errors, cursor pagination, WSGI adapter), `cli.py` (17 commands) | `test_api.py` (16), `test_cli.py` (11) | **IMPLEMENTED** |

## P1 — local cache

| Skill | Implementation | Tests | Status |
| --- | --- | --- | --- |
| `elmos-project-snapshot-merkle` | `snapshot.py` — 7-way classification, raw/normalised/semantic digests kept separate, bottom-up directory + module Merkle, rename detection by content identity, lockfile and submodule roots, symlinks recorded not followed, **logical paths composed to NFC** (a decomposed macOS spelling no longer moves the digest), plus `portability_findings` predicting case collisions, normalisation folds, Windows-hostile names, over-long paths and symlinks from any host | `test_snapshot.py` (7), `test_snapshot_portability.py` (21), `tools/cross_platform_snapshot.py` | **IMPLEMENTED** — one fixture, identical root digest on Linux **and on a real macOS APFS volume**; a native Darwin run and a Windows run are recorded as not captured and skip loudly |
| `elmos-content-addressable-storage` | `cas.py` — sharded paths, streaming put/get, sidecar metadata, compression, create-if-absent convergence via `os.link`, scrub, corruption quarantine, replica repair, restore-cost estimation, read-only blobs | `test_cas.py` (12) | **IMPLEMENTED** |
| `elmos-cache-key-fingerprinting` | `fingerprint.py` — `StageFingerprintSpec` with required/optional/excluded/secret dimensions, canonical flags and maps, explainable fingerprint document, per-dimension miss attribution, hermeticity audit | `test_fingerprint.py` (18) | **IMPLEMENTED** |
| `elmos-action-cache` | `action_cache.py` — policy-checked lookup (tenant, trust, provenance, expiry, revocation, validation floor, artifact presence, restore cost), CAS commit, nondeterminism quarantine that survives the caller's rollback, bounded negative cache, five cache modes, non-authoritative hot index | `test_action_cache.py` (19) | **IMPLEMENTED** |

## P2 — staging

| Skill | Implementation | Tests | Status |
| --- | --- | --- | --- |
| `elmos-project-generation-file-staging` | `staging.py` (808 lines) — full workspace contract, five file classes, eight-state lifecycle, transactional path reservation, undeclared-output quarantine, recovery planner and executor that converges | `test_staging.py` (27) | **IMPLEMENTED** |
| `elmos-atomic-file-write-promotion` | `atomic.py` (exclusive `O_NOFOLLOW` temp, streaming digest, fsync-before-rename, cross-device copy-verify fallback), `publish.py` (complete-tree materialisation, atomic pointer switch, retention, rollback) | `test_staging.py`, `test_publish.py` (11) | **IMPLEMENTED** |
| `elmos-sandbox-overlay-workspaces` | `overlay.py` — reflink / hardlink-CoW / copy strategy detection, read-only source materialisation, copy-on-write break on first write, mount allowlist denying home and credential paths, quotas, declared-output export | `test_overlay.py` (36) | **IMPLEMENTED** — copy-on-write is verified by reading back inode numbers and link counts, the whole lifecycle is re-run **on a real kernel overlayfs mount**, and the hazard the API prevents (writing through a shared link corrupts the base) is demonstrated rather than asserted |
| `elmos-intermediate-artifact-manifest` | `manifests.py` — artifact / file-tree / action-result / checkpoint / evidence / source-map envelopes, content-addressed identity, schema validation before storage, required-vs-optional outputs | `test_publish.py`, `test_contracts_and_config.py` | **IMPLEMENTED** |

## P3 — incremental

| Skill | Implementation | Tests | Status |
| --- | --- | --- | --- |
| `elmos-stage-contract-registry` | `stage_contract.py` — schema, loader, 13-stage default pipeline, capability edges, runtime guard, generated documentation, 13 lint rules | `test_stage_contract.py` (22) | **IMPLEMENTED** |
| `elmos-semantic-interface-hashing` | `interface_hash.py` (1 039 lines) + `treesitter_hash.py` (847 lines) — API / ABI / body / surface / semantic digests; **exact for all 13 languages**: Python via `ast`, the other twelve via pinned `tree-sitter` grammars, with the line scanner kept as a fallback. Confidence degrades to `HEURISTIC` on any grammar error node, and the extractor's identity and grammar version are bound into `semantic_digest` | `test_interface_hash.py` (20), `test_treesitter_hash.py` (103) | **IMPLEMENTED** |
| `elmos-incremental-conversion-dag` | `dag.py` — 9 granularities, 10 edge kinds with interface-vs-behaviour propagation, minimal affected closure with reasons, deterministic critical-path scheduling, output arbitration, plan-versus-actual record | `test_dag.py` (14) | **IMPLEMENTED** |

## P4 — recovery

| Skill | Implementation | Tests | Status |
| --- | --- | --- | --- |
| `elmos-run-journal-state-machine` | `journal.py` — fsynced append-only NDJSON with sequence and payload-digest checks, torn-tail tolerance, lease claim/heartbeat/expiry/reclaim, retry budget and poison handling, pause/resume/cancel, journal↔database reconciliation, state rebuild from the journal alone | `test_journal.py` (13) | **IMPLEMENTED** |
| `elmos-checkpoint-resume` | `checkpoint.py` — flush-then-commit ordering, CAS-stored manifests, atomic attach under the current lease epoch, compatibility profile with per-field rejection reasons, chain bounding, side-effect receipts | `test_checkpoint.py` (15) | **IMPLEMENTED** |
| `elmos-generation-conflict-merge` | `merge.py` — five ownership classes, protected-region splice, line-level three-way merge, deterministic dependency/registration/config mergers, all three sides preserved in CAS, replayable resolution rules | `test_merge.py` (17) | **IMPLEMENTED** |

## P5 — distributed

| Skill | Implementation | Tests | Status |
| --- | --- | --- | --- |
| `elmos-remote-shared-cache` | `remote.py` — filesystem and S3 backends, read-through / write-through / write-behind, bounded queue and retry budget, multipart with parts-before-object ordering, end-to-end digest verification independent of transport, miss leases, offline sync that never overwrites a canonical entry, replicas, scrub/repair, bandwidth budget | `test_remote.py` (15), `test_remote_s3.py` (12) | **IMPLEMENTED** — filesystem backend plus a **live HTTP S3 endpoint**: conditional creation refused by the service with `412 PreconditionFailed`, a genuine multipart create/upload-part/complete cycle, and an aborted upload proven to leave nothing discoverable |
| `elmos-native-build-cache-adapters` | `native_adapters.py` — **9** adapters (Gradle/Maven, MSBuild/NuGet, Cargo/sccache, CMake/ccache, TS/pnpm/Vite, pip/uv, Xcode/Swift, Flutter/pub, **Go build cache**), sandbox path redirection with escape detection, per-toolchain and per-trust-domain isolation, diagnostics parsing rewritten against real tool output, CAS import, clean-room comparison, safe degradation | `test_native_adapters.py` (15), `test_native_toolchains.py` (13) | **PARTIAL** — seven adapters certified against the **real** tool (Gradle 8.14.3, .NET SDK 8.0.130, Cargo 1.95, ccache 4.9.1 + CMake, tsc 6.0.3 + npm, pip 24.0, Go 1.24.7): cold build, destroyed outputs, warm build the tool itself reports as a hit. Maven's local-repository redirection is now certified against Maven itself (`MAVEN_OPTS=-Dmaven.repo.local=…`, and Maven prints the sandbox path in its own repository list); a full Maven build still needs a reachable Central. Swift and Flutter are not installable on this platform, and for both the adapter contract that does *not* need the tool is asserted so the residue is one specific thing |

## P6 — assurance

| Skill | Implementation | Tests | Status |
| --- | --- | --- | --- |
| `elmos-cache-security-provenance` | `security.py` — 11 secret rules with placeholder allowlist, no-follow file ops, archive bomb/traversal/symlink inspection, signed provenance binding digest+producer+key+level+scope+time, tenant-isolated authorization with no existence leak, revocation reverse-closure, per-tenant envelope encryption, telemetry redaction | `test_security.py` (15), `test_provenance_crypto.py` (24) | **IMPLEMENTED** — `Ed25519ProvenanceSigner` (algorithm and key id signed *inside* the payload, so a downgrade or key substitution is a forgery) and an AES-256-GCM `EnvelopeCipher` with the tenant identity as AAD. `SecurityConfig.require_asymmetric_provenance` defaults on, and `CertificationService` refuses a symmetric signer; the HMAC signer survives for offline development only |
| `elmos-cache-retention-gc` | `gc.py` — root set from active runs, checkpoints, pins, published trees, valid certificates and legal holds; transitive reachability; multi-factor eviction scoring; two-phase dry-run → grace → apply with receipts; protection re-derived at apply time; orphan reconciliation both directions | `test_gc.py` (11) | **IMPLEMENTED** |
| `elmos-cache-observability-performance` | `observability.py` — 11 fixed span names, allowlisted low-cardinality labels, per-stage hit accounting with avoided CPU/wall/compiler/token work, incident counters, Prometheus exposition, 10 benchmark scenarios, 9 SLOs with a pass/fail gate, measurement-driven tuning advice | `test_observability.py` (11) | **IMPLEMENTED** (benchmark *harness* implemented; real ELMOS workload numbers **NOT VERIFIED**) |
| `elmos-cache-chaos-certification` | `chaos.py` — 17 kill points × 13 fault kinds, deterministic seeded injection with a replayable reproduce block, invariant checks (no partial publication, recovery converges, at-most-once effects, no orphan metadata), cross-mode digest comparison, certificate issue/verify/revoke, regression corpus | `test_chaos.py` (12), `test_chaos_process.py` (17) | **IMPLEMENTED** — `KillMode.SIGKILL` kills a real child process at 8 kill points and the parent asserts the invariants over what survived on disk; disk-full and inode exhaustion run against a **real tmpfs mount** (1 MiB / 96 inodes) rather than a simulated quota |
| `elmos-cache-rollout-end-to-end` | `pipeline.py` — snapshot → plan → resolve → allocate → generate into staging → seal → promote → assemble → evidence → publish, with justification required for every skipped node, tree-reachability enforcement, six rollout phases, kill switch, shadow comparison | `test_e2e.py` (10), `test_e2e_real_stages.py` (9), `test_elmos_route_stages.py` (16) | **IMPLEMENTED** — `elmos_route_stages.py` registers **ELMOS's own conversion engine** (`engines/polyglot-route-engine`) against these contracts: its analyzer produces the semantic IR, its emitter produces the target file, and generation is keyed by the IR digest, so a comment-only source edit re-emits nothing while an emitter edit invalidates everything. `TEST_VERIFIED` is earned by compiling the emitted Java and running it against the Python original; a deliberately sabotaged translation is caught and refused reuse |

## P8 — the SOTA policy plane

New in v1.1.0. The rule these seven skills share: **the policy plane decides
what is kept, fetched early and let in; it never decides what is valid.** Every
one of them is a separate module with its own tests, and the boundary is
asserted, not assumed (`SOTA-16`).

| Skill | Implementation | Tests | Status |
| --- | --- | --- | --- |
| `elmos-sota-cache-policy-portfolio` | `cache_policy.py` (1 090 lines) — one SPI (`access`/`put`/`forget`/`resize`/`snapshot`/`restore`/`explain`) behind six policies: **LRU** (mandatory baseline), **SIEVE** (NSDI'24), **S3-FIFO** (SOSP'23, small/main/ghost), **W-TinyLFU** (Count-Min sketch + doorkeeper + halving), **size-aware TinyLFU** (frequency per byte), **GDSF** (frequency × cost ÷ size with clock inflation). Protected roots are registered before any decision and are never victims — when only protected objects remain, admission is *refused*. `state_digest()` deliberately excludes counters so a snapshot/restore round trip is bit-identical. Object size is immutable per key: a size change is a `ContractViolation`, not a silent update | `test_cache_policy.py` (74), `test_policy_integration.py` (41) | **IMPLEMENTED** |
| `elmos-cache-trace-replay-simulator` | `cache_trace.py` (790 lines) — `CacheTraceEvent` schema 1.1.0, `TraceRecorder` with HMAC tenant pseudonyms, key-deterministic sampling and per-tenant budgets, positive-rule `assert_privacy`, `TraceCorpus` with time-separated splits (warmup/train/validation/test/drift/adversarial) validated non-overlapping, leakage and drift detection, sample-size floors, JSONL round trip, and ten workload generators. `cache_simulator.py` — `replay()`, five objective profiles, `weighted_value`, `BenchmarkGates`, `benchmark()` emitting a report valid against `cache-benchmark-report.schema.json` | `test_cache_trace.py` (33), `test_cache_simulator.py` (24) | **IMPLEMENTED** — replay is deterministic to the byte (`SOTA-01`), every arm is bound to one capacity, warm-up and request sequence (`SOTA-15`) |
| `elmos-cost-aware-cache-admission` | `cache_admission.py` — `CacheValue = P(reuse) × (avoided work + critical path + validation value) − storage − restore − pollution − trust risk`, with cost provenance (`OBSERVED`/`PREDICTED`/`FALLBACK`), per-tenant quotas, and the bypass rule that an object costing more to restore than to rebuild is not admitted at all | `test_cache_admission.py` (16) | **IMPLEMENTED** |
| `elmos-dag-aware-cache-prefetch` | `dag_prefetch.py` — `FutureUseIndex.from_dag` builds the next-use index from the **real** `ConversionDag`, Belady within the planned window, prefetch budgets and cancellation, precision accounting, restore-vs-recompute bypass, locality-aware placement with fairness slack | `test_dag_prefetch.py` (23) | **IMPLEMENTED** |
| `elmos-adaptive-cache-policy-orchestrator` | `policy_orchestrator.py` — `RuleSelector` over workload fingerprints (readable branches, each returning its own evidence), schema-bound `PolicyEpoch`, hysteresis and minimum dwell, shadow policies, and a **pinned** fixed fallback (SIEVE) for insufficient sample, out-of-distribution input or low confidence | `test_policy_orchestrator.py` (22) | **IMPLEMENTED** — off by default (`policy.adaptive_selection: false`) |
| `elmos-learning-augmented-cache-control` | `learned_control.py` — off-path bounded parameter tuning, ridge regression by Gaussian elimination, **clipping to certified bounds as the safety property** (not model accuracy), signed model registry with activate/verify/rollback, OOD/drift/stale/low-confidence fallback, canary fractions and automatic rollback | `test_learned_control.py` (23) | **IMPLEMENTED** — off by default, and shadow-only when on; the configuration loader refuses a canary fraction while `learned_shadow_only` is true |
| `elmos-cache-autotuning-certification` | `policy_certification.py` — the benchmark matrix, Pareto frontier, parameter search on train/validation with the test window untouched, `CertificationContext` binding commit + policy digest + configuration digest + capacity + objective + protected-root rules + hardware profile, an Ed25519-signed `CachePolicyCertificate`, `expired_reasons()`, and the rollout ladder `SIMULATOR → SHADOW → RECOMMENDATION → CANARY → PROGRESSIVE → FULL` | `test_sota_acceptance.py` (36), `test_policy_integration.py` | **IMPLEMENTED** — the gates genuinely refuse: on 8 of 30 matrix cells no candidate clears the threshold and `selected` is `None`; certification without shadow or rollback evidence is refused with those exact reason codes |

### Where the policy plane is actually wired in

The package is explicit that a prototype does not count. It is reachable from
three real places:

| Seam | What it does | Off switch |
| --- | --- | --- |
| `config.PolicyConfig` | typed, total configuration section; unknown policy names, unknown objectives and out-of-range fractions all fail to load rather than defaulting. Shipped in `config/elmos-cache.yaml`, so it is reviewable in git | `policy.enabled: false` |
| `policy_plane.PolicyPlane` | the single object that turns configuration into behaviour, held by `ConversionPipeline`. `trace_capture` records the run's own lookups at `plan()`'s probe; `admission_enabled` is consulted immediately before `ActionCache.commit`; `prefetch_enabled` plans against the real DAG at each wave boundary; `adaptive_selection` and `learned_tuning` produce an end-of-run recommendation in `RunReport.policy`. With everything off the plane is inert and `RunReport.policy` is `None` | each switch individually |
| `action_cache.HotIndex` | the in-process action-cache accelerator now runs the configured L0 policy; `HotIndex.from_config` builds it, and `pipeline.ConversionPipeline` and the CLI both use it. Chosen first *because* the index is never authoritative — the worst a policy bug costs here is one database read | `policy.enabled: false` → the original built-in LRU |
| `gc.GarbageCollector.replacement` | orders deletion candidates by the configured L2 policy. Membership of the candidate list is still decided entirely by the root set, which is declared to the policy first | pass `replacement=None` |

Two invariants that fell out of doing this properly:

- **`CachePolicy.forget()`** — a revocation or quarantine removes an entry
  without being counted as an eviction, and is accounted separately
  (`counters.invalidations`). Without it the correctness plane would have had
  to lie to the policy.
- **A switch that reports itself on must do something.** The five capability
  switches shipped inert at first — their only reader was the `policy show`
  display, so `admission_enabled: true` did nothing. That is worse than not
  having the switch, and `SOTA-24` now pins each one to its own capability.
- **A half-empty cache must admit.** W-TinyLFU originally ran its frequency
  contest against a main-region incumbent that was not competing for the slot,
  so a cold cache never warmed. Fixed, and pinned by a test that runs against
  all six policies (`SOTA-20`).

## Aggregate

| Status | Count | Change |
| --- | --- | --- |
| `IMPLEMENTED` | 30 | +7 |
| `PARTIAL` | 1 | — |
| `STUB` / `MISSING` / `BROKEN` | 0 | — |

One `PARTIAL` row remains, and exactly what is missing from it:

| Skill | What is missing | Why it is not closed here |
| --- | --- | --- |
| `elmos-native-build-cache-adapters` | Xcode/Swift and Flutter/pub against their real tools; a full Maven build | Neither toolchain exists for Linux and neither is obtainable from this sandbox's network allowlist; Maven Central is unreachable. Everything about those adapters that does not need the tool is asserted, and the three gaps skip with their reason printed. |

Three things that are **not** counted as gaps in a skill, but are worth
stating plainly:

- The policy corpora are **synthetic**. They are shaped after ELMOS conversion
  patterns and they are enough to show that no single policy dominates and to
  refuse a policy that regresses — but a certificate issued against them binds
  to them, and `expired_reasons()` says so. `TraceRecorder` is the path to real
  traces and capture is off by default.

- No native-Darwin and no Windows snapshot capture exists. The fixture agrees
  on Linux and on a real macOS APFS volume; `portability_findings` covers the
  general question from any host; `tools/cross_platform_snapshot.py` produces
  the missing entries in one command.
- The route-engine bridge refuses to run when the host does not match the
  engine's pinned toolchain tree. That refusal is tested, not worked around.

Every `PARTIAL` is explained in the row above and carries an entry in
`BUILD_CACHE_HANDOFF.md`. No skill is claimed complete on the strength of a
happy-path demo, and nothing that this environment could not prove is recorded
as proven.

## Pass 5 addendum — v1.2 Codex/Claude cache parity

This addendum is the current status for the v1.2 scope. The v1.1 tables above
are retained as historical evidence; their `CERTIFIED_IN_SANDBOX` language is
not a parity decision.

### Package migration

| Check | Current result |
| --- | --- |
| Source archive | pinned to SHA-256 `dde312b55a95cbc7af6753ec88f07833e93ffa296b782ddcf3ef1a6470b73cb7` |
| Retained work | 31 v1.1 Skill bodies detected as unchanged; only v1.2 frontmatter/provenance is refreshed |
| New work | 11 v1.2 Skills imported and implemented locally |
| Installed total | 42 Skills, byte-identical across four install roots |
| Import behavior | inventory/checksum/schema/DAG validation; package scripts are not executed |
| External evidence | `NOT_RUN` |
| Certification | `NOT_CERTIFIED` |

### New Skill implementation matrix

| Skill | Production-code surface | Local implementation status | Evidence boundary |
| --- | --- | --- | --- |
| `elmos-provider-prompt-cache-adapters` | `prompt_cache.py` | **IMPLEMENTED** | Real provider/SDK/model calls `NOT_RUN` |
| `elmos-canonical-prompt-prefix-layout` | `prompt_cache.py`, `prompt_tools.py` | **IMPLEMENTED** | Provider-side hit ratios `NOT_RUN` |
| `elmos-append-only-repository-context-ledger` | `context_ledger.py`, both-dialect ledger migrations | **IMPLEMENTED** | New PostgreSQL migration live run `NOT_RUN` |
| `elmos-cache-preserving-context-compaction` | `context_compaction.py` | **IMPLEMENTED** | Long-session representative corpus `NOT_RUN` |
| `elmos-environment-snapshot-cache` | `environment_cache.py`, `environment_service.py`, CAS and parity metadata | **IMPLEMENTED** | Real image/toolchain warm restore `NOT_RUN` |
| `elmos-cache-affinity-routing` | `affinity.py` | **IMPLEMENTED** | Production scheduler/fleet routing `NOT_RUN` |
| `elmos-multi-layer-cache-coordinator` | `coordinator.py` | **IMPLEMENTED** | Distributed contention/scale `NOT_RUN` |
| `elmos-cache-miss-diagnostics` | `miss_diagnostics.py`, `parity_runtime.py` | **IMPLEMENTED** | Production miss budget `NOT_RUN` |
| `elmos-codex-claude-parity-benchmark` | `parity.py`, `parity_harness.py` | **IMPLEMENTED** | Independent real parity corpus `NOT_RUN` |
| `elmos-cache-hit-slo-autotuning` | `slo_autotune.py` | **IMPLEMENTED** | Canary/progressive production rollout `NOT_RUN` |
| `elmos-codex-claude-cache-parity-rollout` | `parity_api.py`, `parity_store.py`, `api.py`, `cli.py`, `pipeline.py` | **IMPLEMENTED** | External gate and production rollout `NOT_RUN` |

### Durable and public surfaces

- SQLite migrations `0003_context_ledger.sql` and `0004_cache_parity.sql`, and
  PostgreSQL migrations `0005_context_ledger.sql` and `0006_cache_parity.sql`,
  are mirrored byte-for-byte under `_data/migrations/`.
- `parity_store.ParityMetadataRepository` stores tenant/project-scoped prompt
  manifests, provider usage, immutable environment manifests plus append-only
  status, outcome events, affinity decisions and immutable parity reports. It
  rejects raw prompt/source/secret fields and detects idempotency drift.
- `cache-parity-control-plane.openapi.yaml` defines seven operations, all
  implemented by `ParityApiService` and wired into `CacheControlPlane`.
- The CLI exposes `cache explain`, `prompt compile/diff`, `environment
  inspect`, `affinity decide`, and `parity status/evaluate/report`. Persistence
  is explicit and requires an idempotency key.
- `ConversionPipeline` emits optional `RunReport.parity` observations from the
  real Action Cache lookup path. A telemetry-store failure degrades observation
  only; it cannot change the action result or publication path.

The local maximum remains `READY_FOR_EXTERNAL_GATE`, and only after every
required scenario has immutable raw evidence, replay metadata, authorization
and an independent verifier. The current repository state does not meet that
condition and remains `NOT_CERTIFIED`.

## 2026-08-25 — BC-13 / BC-14 / BC-15 code state

Fifteen files changed: 4 new, 11 modified. Verified against the pristine
baseline with `diff -rq` — exactly this set, no sixteenth file. `migrations/**`
was **not** touched (all 16 files were already byte-identical to their packaged
mirrors; confirmed with `cmp`).

**New**

| File | Lines | What it is |
| --- | ---: | --- |
| `src/elmos_build_cache/parity_composition_wiring.py` | 578 | The adapters binding the composition to real collaborators. Kept out of both `api.py` and `parity_composition.py`: the composition is deliberately dependency-free (it imports only `canonical`, `errors`, `security`), and `api.py` is routing/idempotency/error-mapping only. A sibling module named after the seam keeps both pure and lets a non-HTTP driver reuse the adapters |
| `tests/test_slo_service.py` | 1924 | 52 tests, BC-13 |
| `tests/test_parity_composition.py` | 1967 | 230 tests, BC-14 composition |
| `tests/test_api_composition_wiring.py` | 1275 | 42 tests, BC-14 wiring |

**Modified**

- `src/elmos_build_cache/slo_service.py` — dependency reference edges moved to a
  derived namespace `f"{source_kind}-dependency"`. Before this, the proposal's
  identity key resolved to three digests (because `artifact_targets` selects on
  `(tenant_id, source_kind, source_id)` and ignores `ref_kind`), so `_proposal()`
  rejected every proposal the service had just produced and the whole
  install/advance/rollback path was unreachable. Plus one pre-existing `I001`
  import-order fix in the same file.
- `src/elmos_build_cache/api.py` — `PromptCacheController` injected into
  `CacheControlPlane`; two new authenticated + idempotent provider routes with
  ownership preflight ahead of the global idempotency claim; the composition
  reachable from `lookup_action` and `_serving_call`, with `_direct_serving_call`
  holding the old body verbatim for the unwired path; `served = result.hit and
  (reused is None or reused)` so `reused` can only ever subtract; and a corrected
  comment on why serving routes cannot skip their operation (the old one gave a
  false reason — see `BUILD_CACHE_EVIDENCE.md`).
- `src/elmos_build_cache/parity_api.py` — `_enum` and `_strict_object` no longer
  echo caller-supplied text. They report shape instead: the closed server-owned
  `permitted` / `allowed` set, a bounded `unknown_count`, and `missing` as a
  subset of the server's own `required`. None of the three is an echo, and a
  caller can still name its offending keys by subtracting `allowed` from its own
  request.
- `openapi/cache-parity-control-plane.openapi.yaml` and its packaged mirror
  `src/elmos_build_cache/_data/openapi/…` — two operations added, kept
  byte-identical to each other.
- `tests/test_api.py`, `tests/test_metadata_store_contract.py`,
  `tests/test_parity_api.py`, `tests/test_parity_contract_assets.py`,
  `tests/test_provider_prompt_runtime.py`, `tests/test_sota_acceptance.py`.

**Not touched:** `parity_composition.py`, `prompt_cache.py`, `cli.py`,
`migrations/**`, `tests/test_e2e.py`.

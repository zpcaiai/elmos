# BUILD_CACHE_IMPLEMENTATION_STATUS.md

> Skill → implementation → test → status, for the 24 skills of
> `elmos-build-cache-staging-recovery` v1.0.0.
> Status vocabulary is closed: `IMPLEMENTED` · `PARTIAL` · `STUB` · `MISSING` ·
> `BROKEN` · `NOT VERIFIED`. Nothing here is a certification claim.

- **Audit date:** 2026-08-19 (pass 2 — the seven `PARTIAL` rows)
- **Auditor:** Claude (Cowork cloud session)
- **Working tree:** pass 1 is committed; this pass is a second, additive change
  under `engines/build-cache-engine/` and `.ai/` only
- **Static gates:** `ruff check src tests` clean · `mypy --strict` clean (42 files)
- **Dynamic gate:** `pytest tests` → **550 passed, 5 skipped, 0 failed**
  (live PostgreSQL 16 + live S3 endpoint + real toolchains all in the run)

## P0 — foundation

| Skill | Implementation | Tests | Status |
| --- | --- | --- | --- |
| `elmos-cache-system-architecture` | `enums.py` (closed vocabularies + both state machines), `errors.py` (24 typed codes), `config.py` (total loading, unknown key = error), `canonical.py` (canonical JSON, digests, path safety) | `test_contracts_and_config.py` (20) | **IMPLEMENTED** |
| `elmos-cache-metadata-database` | `db/store.py` (1 434 lines), `db/records.py`, `migrations/sqlite/0001_init.sql`, `migrations/postgres/0001_init.sql` + `0002_elmos_extensions.sql`; 20 tables, optimistic `version`, lease-epoch guards, outbox, idempotency records | `test_journal.py`, `test_contracts_and_config.py`, `test_metadata_store_contract.py` (23 × 2 dialects + 1) | **IMPLEMENTED** — the same contract body runs against SQLite **and a live PostgreSQL 16 server**; `migrations/{sqlite,postgres}` now carry a migration ledger so column-adding migrations apply exactly once |
| `elmos-cache-api-cli-contracts` | `api.py` (all 14 OpenAPI operations, idempotency, typed errors, cursor pagination, WSGI adapter), `cli.py` (17 commands) | `test_api.py` (16), `test_cli.py` (11) | **IMPLEMENTED** |

## P1 — local cache

| Skill | Implementation | Tests | Status |
| --- | --- | --- | --- |
| `elmos-project-snapshot-merkle` | `snapshot.py` — 7-way classification, raw/normalised/semantic digests kept separate, bottom-up directory + module Merkle, rename detection by content identity, lockfile and submodule roots, symlinks recorded not followed | `test_snapshot.py` (7) | **IMPLEMENTED**; cross-platform fixtures **PARTIAL** (Linux only) |
| `elmos-content-addressable-storage` | `cas.py` — sharded paths, streaming put/get, sidecar metadata, compression, create-if-absent convergence via `os.link`, scrub, corruption quarantine, replica repair, restore-cost estimation, read-only blobs | `test_cas.py` (12) | **IMPLEMENTED** |
| `elmos-cache-key-fingerprinting` | `fingerprint.py` — `StageFingerprintSpec` with required/optional/excluded/secret dimensions, canonical flags and maps, explainable fingerprint document, per-dimension miss attribution, hermeticity audit | `test_fingerprint.py` (18) | **IMPLEMENTED** |
| `elmos-action-cache` | `action_cache.py` — policy-checked lookup (tenant, trust, provenance, expiry, revocation, validation floor, artifact presence, restore cost), CAS commit, nondeterminism quarantine that survives the caller's rollback, bounded negative cache, five cache modes, non-authoritative hot index | `test_action_cache.py` (19) | **IMPLEMENTED** |

## P2 — staging

| Skill | Implementation | Tests | Status |
| --- | --- | --- | --- |
| `elmos-project-generation-file-staging` | `staging.py` (808 lines) — full workspace contract, five file classes, eight-state lifecycle, transactional path reservation, undeclared-output quarantine, recovery planner and executor that converges | `test_staging.py` (27) | **IMPLEMENTED** |
| `elmos-atomic-file-write-promotion` | `atomic.py` (exclusive `O_NOFOLLOW` temp, streaming digest, fsync-before-rename, cross-device copy-verify fallback), `publish.py` (complete-tree materialisation, atomic pointer switch, retention, rollback) | `test_staging.py`, `test_publish.py` (11) | **IMPLEMENTED** |
| `elmos-sandbox-overlay-workspaces` | `overlay.py` — reflink / hardlink-CoW / copy strategy detection, read-only source materialisation, copy-on-write break on first write, mount allowlist denying home and credential paths, quotas, declared-output export | `test_e2e.py`, exercised via `staging` | **PARTIAL** — implemented and self-tested during development, but has **no dedicated test file**; platform-specific isolation tests (overlayfs, macOS APFS) not written |
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
| `elmos-native-build-cache-adapters` | `native_adapters.py` — **9** adapters (Gradle/Maven, MSBuild/NuGet, Cargo/sccache, CMake/ccache, TS/pnpm/Vite, pip/uv, Xcode/Swift, Flutter/pub, **Go build cache**), sandbox path redirection with escape detection, per-toolchain and per-trust-domain isolation, diagnostics parsing rewritten against real tool output, CAS import, clean-room comparison, safe degradation | `test_native_adapters.py` (15), `test_native_toolchains.py` (12) | **PARTIAL** — seven adapters certified against the **real** tool (Gradle 8.14.3, .NET SDK 8.0.130, Cargo 1.95, ccache 4.9.1 + CMake, tsc 6.0.3 + npm, pip 24.0, Go 1.24.7): cold build, destroyed outputs, warm build the tool itself reports as a hit. Xcode/Swift, Flutter/pub and Maven Central are unavailable in this environment and **skip loudly** rather than passing |

## P6 — assurance

| Skill | Implementation | Tests | Status |
| --- | --- | --- | --- |
| `elmos-cache-security-provenance` | `security.py` — 11 secret rules with placeholder allowlist, no-follow file ops, archive bomb/traversal/symlink inspection, signed provenance binding digest+producer+key+level+scope+time, tenant-isolated authorization with no existence leak, revocation reverse-closure, per-tenant envelope encryption, telemetry redaction | `test_security.py` (15), `test_provenance_crypto.py` (24) | **IMPLEMENTED** — `Ed25519ProvenanceSigner` (algorithm and key id signed *inside* the payload, so a downgrade or key substitution is a forgery) and an AES-256-GCM `EnvelopeCipher` with the tenant identity as AAD. `SecurityConfig.require_asymmetric_provenance` defaults on, and `CertificationService` refuses a symmetric signer; the HMAC signer survives for offline development only |
| `elmos-cache-retention-gc` | `gc.py` — root set from active runs, checkpoints, pins, published trees, valid certificates and legal holds; transitive reachability; multi-factor eviction scoring; two-phase dry-run → grace → apply with receipts; protection re-derived at apply time; orphan reconciliation both directions | `test_gc.py` (11) | **IMPLEMENTED** |
| `elmos-cache-observability-performance` | `observability.py` — 11 fixed span names, allowlisted low-cardinality labels, per-stage hit accounting with avoided CPU/wall/compiler/token work, incident counters, Prometheus exposition, 10 benchmark scenarios, 9 SLOs with a pass/fail gate, measurement-driven tuning advice | `test_observability.py` (11) | **IMPLEMENTED** (benchmark *harness* implemented; real ELMOS workload numbers **NOT VERIFIED**) |
| `elmos-cache-chaos-certification` | `chaos.py` — 17 kill points × 13 fault kinds, deterministic seeded injection with a replayable reproduce block, invariant checks (no partial publication, recovery converges, at-most-once effects, no orphan metadata), cross-mode digest comparison, certificate issue/verify/revoke, regression corpus | `test_chaos.py` (12), `test_chaos_process.py` (17) | **IMPLEMENTED** — `KillMode.SIGKILL` kills a real child process at 8 kill points and the parent asserts the invariants over what survived on disk; disk-full and inode exhaustion run against a **real tmpfs mount** (1 MiB / 96 inodes) rather than a simulated quota |
| `elmos-cache-rollout-end-to-end` | `pipeline.py` — snapshot → plan → resolve → allocate → generate into staging → seal → promote → assemble → evidence → publish, with justification required for every skipped node, tree-reachability enforcement, six rollout phases, kill switch, shadow comparison | `test_e2e.py` (10), `test_e2e_real_stages.py` (9) | **PARTIAL** — the orchestration contract is now certified against **real** stages: a real `javac` invocation and a real tree-sitter-driven Java→C# translation whose output is parsed back with the C# grammar and compared against the Java source's public surface. A private-body edit restores the dependent from cache; a public-interface edit retranslates it. Residual gap: ELMOS's own **model-driven** conversion stage still has to be registered by the orchestrator |

## Aggregate

| Status | Count | Change |
| --- | --- | --- |
| `IMPLEMENTED` | 20 | +3 |
| `PARTIAL` | 4 | −3 |
| `STUB` / `MISSING` / `BROKEN` | 0 | — |

The four remaining `PARTIAL` rows and exactly what is missing from each:

| Skill | What is missing | Why it is not closed here |
| --- | --- | --- |
| `elmos-project-snapshot-merkle` | Golden root digests captured on macOS and Windows | Linux-only sandbox |
| `elmos-sandbox-overlay-workspaces` | A dedicated test file with platform-specific isolation | overlayfs/APFS behaviour cannot be exercised meaningfully here |
| `elmos-native-build-cache-adapters` | Xcode/Swift, Flutter/pub, and the Maven half of `gradle-maven` | no Swift or Flutter toolchain; Maven Central unreachable |
| `elmos-cache-rollout-end-to-end` | ELMOS's model-driven conversion stage | lives in the orchestrator, not in this engine |

Every `PARTIAL` is explained in the row above and carries an entry in
`BUILD_CACHE_HANDOFF.md`. No skill is claimed complete on the strength of a
happy-path demo, and nothing that this environment could not prove is recorded
as proven.

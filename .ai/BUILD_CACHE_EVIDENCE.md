# BUILD_CACHE_EVIDENCE.md

> Acceptance row → required result → implementing symbol → test → executed
> verdict. Source of the rows:
> `agent-skills/packages/elmos-build-cache-staging-sota/tests/acceptance/cache-staging-acceptance-matrix.md`
> (the `SOTA-` rows come from the v1.1.0 package's own matrix).
>
> Every row below was re-executed on 2026-08-20 (pass 4), Linux x86_64,
> Python 3.12.3, `pytest tests` → **926 passed, 7 skipped**, with a live
> PostgreSQL 16 server, a live HTTP S3 endpoint, eight real build toolchains, a
> real kernel overlayfs, a real macOS APFS volume and ELMOS's own conversion
> engine in the run. A row without an executed command is marked
> `NOT EXECUTED`. Nothing here is a certification claim beyond what the
> commands showed.
>
> **Current scope note:** the paragraph above and the acceptance rows below are
> pass-4/v1.1 history. The v1.2 parity decision is in the final section of this
> file: external evidence is `NOT_RUN` and certification is `NOT_CERTIFIED`.

| ID | Required result | Implementation | Test | Verdict |
| --- | --- | --- | --- | --- |
| SNAP-001 | Same logical repository → same canonical root digest | `snapshot.take_snapshot` (path-independent, **logical paths composed to NFC**, sorted Merkle) + `portability_findings` | `test_snap_001_same_repository_different_absolute_paths`, `test_snap_001_windows_style_separators_normalise`, `test_this_host_agrees_with_every_platform_ever_recorded`, `test_a_decomposed_filename_snapshots_as_the_composed_one` | **PASS** — one fixture, identical root digest on Linux/ext4 and on a real macOS APFS volume; native Darwin and Windows captures `NOT EXECUTED` and named in a skip |
| SNAP-002 | Whitespace-only edit: raw digest changes, semantic follows policy | `FileEntry.raw_digest` vs `normalized_digest`, `normalize_text` | `test_snap_002_formatting_only_change` | **PASS** |
| SNAP-003 | Rename recognised; unrelated subtrees unchanged | `diff_snapshots` content-identity rename matching | `test_snap_003_rename_detected_and_unrelated_subtrees_stable` | **PASS** |
| KEY-001 | Irrelevant temporary path leaves the ActionKey unchanged | `EXCLUDED_DIMENSIONS`, declared-environment filtering, `canonical_flags` | `test_key_001_irrelevant_inputs_do_not_move_the_key`, `test_key_001_flag_order_and_duplicates_are_canonical` | **PASS** |
| KEY-002 | Rule pack / compiler / SDK / prompt / model / public interface change → key changes | `build_action_key` over 20 declared dimensions | `test_key_002_result_affecting_inputs_move_the_key` (9 parameterisations) | **PASS** |
| KEY-003 | Undeclared environment value: key unchanged, hermeticity audit records the exclusion | `StageFingerprintSpec.audit_environment`, `RuntimeGuard.check_environment` | `test_key_003_undeclared_environment_is_excluded_and_audited`, `test_guard_fails_a_deterministic_stage_that_reads_hidden_environment` | **PASS** |
| CAS-001 | Two concurrent identical writers → one object, same digest | `ContentAddressableStore._link_commit` (create-if-absent) | `test_cas_001_concurrent_identical_writers_converge` (8 threads) | **PASS** |
| CAS-002 | Kill during blob write → no visible partial object | `put_stream` staging + `finally` unlink | `test_cas_002_interrupted_write_leaves_no_visible_object` | **PASS** |
| CAS-003 | Corrupt bytes: read rejects; object quarantined or repaired | `get_bytes` verify → `quarantine`; `repair_from` | `test_cas_003_corruption_is_rejected_and_quarantined`, `test_cas_003_repair_from_verified_replica` | **PASS** |
| CACHE-001 | Repeated exact deterministic action → outputs restored without execution | `ActionCache.lookup` + `pipeline._restore` | `test_cache_001_exact_repeat_restores_without_execution`, `test_e2e_003_…` | **PASS** |
| CACHE-002 | Lower validation than the consumer minimum → `VALIDATION_TOO_LOW` | `ValidationLevel.satisfies`, `_policy_reasons` | `test_cache_002_validation_floor_is_enforced` | **PASS** |
| CACHE-003 | Same ActionKey, different result digest → both quarantined, alert | `_quarantine_nondeterminism` (durable before raise) | `test_cache_003_nondeterminism_quarantines_both_results` | **PASS** |
| STAGE-001 | Kill after reservation → safe reclaim, nothing published | `Workspace.plan_recovery` `RELEASE_OR_REASSIGN` | `test_stage_001_kill_after_reservation_reclaims_without_publishing` | **PASS** |
| STAGE-002 | Kill during write → partial deleted/quarantined, never sealed | `write_and_seal` except-path + durable `ABORTED` | `test_stage_002_kill_during_write_never_seals` | **PASS** |
| STAGE-003 | Kill after fsync before metadata commit → converges, no duplicate | rename-then-CAS ordering + `recover()` | `test_stage_003_kill_after_seal_before_metadata_converges` | **PASS** |
| STAGE-004 | Kill after seal before CAS promotion → verify and promote idempotently | `Workspace.promote` early-return on `CAS_PROMOTED` | `test_stage_004_promotion_is_idempotent` | **PASS** |
| STAGE-005 | Undeclared generator output → quarantined, excluded from the tree | `scan_undeclared` / `handle_undeclared` | `test_stage_005_undeclared_output_is_quarantined` | **PASS** |
| STAGE-006 | Traversal / reserved name / case collision / symlink escape → rejected before write | `normalize_logical_path`, `resolve_within`, case-fold reservation check | `test_stage_006_unsafe_paths_are_rejected_before_any_write` (10 params), `…_case_collision_is_rejected`, `…_symlink_on_the_write_path_is_refused` | **PASS** |
| STAGE-007 | Stale worker attempts seal → rejected by lease epoch / version | `Workspace._assert_lease` + `update_staged_file` CAS | `test_stage_007_stale_worker_cannot_seal` | **PASS** |
| PUB-001 | Kill while materialising a candidate → active tree unchanged | staging dir + `os.replace`, `shutil.rmtree` on failure | `test_pub_001_failed_materialisation_leaves_the_active_tree_untouched` | **PASS** |
| PUB-002 | Atomic pointer/rename switch → readers see old or new complete tree only | `TreePublisher.publish` symlink/pointer-file replace | `test_pub_002_pointer_switch_exposes_only_complete_trees` | **PASS** |
| PUB-003 | Evidence bound to a different tree digest → publication blocked | `TreePublisher.check_evidence` | `test_pub_003_evidence_bound_to_another_tree_blocks_publication` | **PASS** |
| DAG-001 | Private method-body change → unrelated dependents stay cached | `BEHAVIOR_EDGES` vs `INTERFACE_EDGES` in `affected_closure` | `test_dag_001_private_body_change_leaves_unrelated_dependents_cached`, `test_private_body_change_reuses_the_unaffected_module` | **PASS** |
| DAG-002 | Public route/schema/event change → affected dependents invalidated | interface-edge propagation + `interface_hash.surface_digest` | `test_dag_002_public_interface_change_invalidates_dependents`, `test_route_change_propagates_even_without_a_signature_change` | **PASS** |
| DAG-003 | Rule-pack upgrade with compatible IR schema → hits retained where safe | per-node `ProbeResult`; restore wins over "upstream re-executes" | `test_dag_003_unaffected_nodes_are_restored_from_cache` | **PASS** |
| CHECK-001 | Resume after worker crash → same sealed output digest as a clean run | `CheckpointService.commit`/`evaluate`, `remaining_partitions` | `test_check_001_resume_recovers_completed_work`, `test_e2e_003_…` (same tree digest) | **PASS** |
| CHECK-002 | Relevant source/toolchain/rule change → checkpoint rejected with the exact reason | `CompatibilityProfile.incompatibilities` | `test_check_002_incompatible_checkpoint_is_rejected_with_a_reason` (5 params) | **PASS** |
| CHECK-003 | Side effect committed before a crash → retry does not duplicate it | `claim_side_effect` insert-if-absent receipts | `test_check_003_side_effect_is_not_duplicated_on_retry` | **PASS** |
| JOURNAL-001 | Duplicate event delivery → materialised state unchanged | `MetadataStore.append_event` unique `(run_id, sequence)` + digest check | `test_journal_001_duplicate_delivery_is_idempotent` | **PASS** |
| LEASE-001 | Stale worker commits after recovery → rejected | monotonic `lease_epoch` bumped on recovery claim | `test_lease_001_stale_worker_cannot_commit` | **PASS** |
| REMOTE-001 | Network loss during multipart upload → no discoverable incomplete entry | blobs-then-manifest-then-entry ordering, durability re-check, `S3RemoteBackend.put_multipart` with abort-on-failure | `test_remote_001_outage_leaves_nothing_discoverable`, `test_an_aborted_multipart_upload_leaves_nothing_discoverable` (live S3, 12 MiB) | **PASS** — against a real S3 service: no readable object, no in-flight upload, retry succeeds |
| REMOTE-002 | Offline execution, later sync → local succeeds; sync is idempotent | write-behind queue, `synchronize` create-if-absent, `IfNoneMatch: "*"` | `test_remote_002_offline_then_synchronise_is_idempotent`, `test_conditional_creation_is_enforced_by_the_service` | **PASS** — the *service* returns `412 PreconditionFailed`, not just the client pre-check |
| REMOTE-003 | Untrusted fork result cannot satisfy an official namespace | per-namespace key space + `TrustNamespace.satisfies` | `test_remote_003_fork_result_cannot_satisfy_official`, `test_trust_namespaces_are_separate_key_spaces` (live S3 key inspection) | **PASS** |
| SEC-001 | Cross-tenant digest lookup denied without a useful existence leak | `AccessController.authorize_read`; lookup returns `NO_ENTRY` either way | `test_sec_001_cross_tenant_access_is_denied_without_an_existence_signal`, `test_cross_tenant_lookup_reveals_nothing` | **PASS** |
| SEC-002 | Secret in a generated file → shared upload and publication blocked | `SecretScanner` + `SecurityGate` on both paths | `test_sec_002_secret_in_generated_output_blocks_upload_and_publish` | **PASS** |
| SEC-003 | Forged provenance or elevated validation claim → rejected and audited | **Ed25519** over the whole canonical statement with algorithm + key id inside the signed payload; `check_promotion`; `require_asymmetric` | `test_sec_003_forged_provenance_is_rejected`, `test_producer_cannot_self_certify`, `test_provenance_crypto.py` (24: per-field tamper ×6, algorithm downgrade, key substitution, rotation, domain separation, verifier holds no forging material) | **PASS** |
| GC-001 | Artifact reachable from an active checkpoint → not deleted | `live_roots` + `reachable` transitive closure | `test_gc_001_checkpoint_referenced_artifact_is_protected`, `test_published_tree_and_pins_are_protected` | **PASS** |
| GC-002 | Interrupted deletion pass → resumes idempotently with receipts | receipts table + protection re-derived at apply time | `test_gc_002_interrupted_pass_resumes_idempotently`, `test_artifact_that_becomes_reachable_after_planning_is_spared` | **PASS** |
| OBS-001 | Cache miss shows the exact changed fingerprint dimensions | `explain_miss` + `DIMENSION_MISS_REASON` + per-stage accounting | `test_obs_001_miss_reasons_are_attributed_per_stage`, `test_key_002_…` | **PASS** |
| OBS-002 | Failure trace: run/node/artifact/staged-file/checkpoint IDs correlate | `correlation_fields` as span attributes, never metric labels | `test_obs_002_failure_traces_correlate_every_identifier` | **PASS** |
| PERF-001 | No-change full-project rerun meets the declared budgets | `PerformanceGate` + `BenchmarkResult`; E2E hit rate 1.0 | `test_perf_001_no_change_rerun_meets_the_budget`, `test_a_no_change_rerun_reruns_neither_the_compiler_nor_the_translator` (real `javac` + real translator invoked **0** times, `saved.compiler_ms ≥ 1100`) | **PASS** on the harness and on the real-stage rerun; ELMOS-workload budgets `NOT EXECUTED` |
| PERF-002 | Single independent method change meets the partial-hit budget | same gate, `private-body` scenario | `test_perf_002_a_reuse_regression_fails_the_gate`, `test_private_body_change_reuses_the_unaffected_module` | **PASS** on the harness; real-workload numbers `NOT EXECUTED` |
| CHAOS-001 | Kill at each file-write boundary → no partial publication; recovery converges | `FaultInjector` at 10 boundaries + `KillMode.SIGKILL` (`run_until_kill`) + `check_no_partial_publication` + `check_recovery_converges` | `test_chaos_001_kill_at_every_write_boundary_never_publishes_partially`, `test_chaos_process.py` (8 real kill points) | **PASS** — a real child process is `SIGKILL`ed and a separate parent asserts the invariants over what survived on disk |
| CHAOS-002 | Disk full / inode exhaustion → controlled failure, no corrupt canonical state | `QuotaExceeded` at the write kill point; `bounded_filesystem()` mounts a real tmpfs via `libc.mount` | `test_chaos_002_disk_full_is_a_controlled_failure`, `test_chaos_002_real_enospc_is_a_controlled_failure`, `test_chaos_002_real_inode_exhaustion_is_bounded` | **PASS** — real `ENOSPC` on a 1 MiB tmpfs and real inode exhaustion at 96 inodes |
| CERT-001 | Expired / revoked / scope-mismatched certificate → production reuse rejected | `CertificationService.verify` | `test_cert_001_expired_revoked_and_scope_mismatch_are_rejected`, `test_certificate_revocation_blocks_reuse` | **PASS** |
| E2E-001 | Java/Spring → C#/ASP.NET complete project: staged, validated, atomically published | `ConversionPipeline` + `TreePublisher`, driven by a real `javac` stage, a real tree-sitter-driven translator, and — through `elmos_route_stages` — **ELMOS's own `polyglot-route-engine`** | `test_e2e_001_complete_project_is_staged_validated_and_published`, `test_e2e_001_real_stages_compile_translate_and_publish`, `test_the_pipeline_publishes_what_the_route_engine_emitted` | **PASS** — the route engine's analyzer, IR and emitter run inside the pipeline; the emitted Java compiles and is executed against the Python original |
| E2E-002 | Service restart during generation → resume without duplicate side effects or partial output | lease reclaim + workspace recovery | `test_e2e_002_restart_during_generation_resumes_without_duplicates` | **PASS** |
| E2E-003 | No-change rerun → same final tree digest, model/compiler work avoided | ActionKey stability + restore-from-cache staging | `test_e2e_003_no_change_rerun_reproduces_the_tree_without_model_work` | **PASS** (identical `root_digest`, generator invoked 0 times, hit rate 1.0) |

## Release gates (spec §21)

| Gate | Verdict |
| --- | --- |
| 1. Cross-platform deterministic snapshot fixtures | **PASS on two filesystems** — identical root digest on Linux/ext4 and real macOS APFS, plus a from-any-host hazard audit; native Darwin and Windows captures `NOT EXECUTED` |
| 2. CAS concurrent-write, interruption, corruption | **PASS** |
| 3. ActionKey dimension tests | **PASS** |
| 4. Staged-file kill-point tests at all critical boundaries | **PASS** — in-process injection at 10 boundaries **and** real `SIGKILL` at 8 |
| 5. No partial final file exposed | **PASS** |
| 6. Checkpoint resume matches clean-run output digest | **PASS** for the deterministic fixture |
| 7. Stale-worker and duplicate-message tests | **PASS** |
| 8. Tenant isolation, secret leakage, cache poisoning | **PASS** |
| 9. No-change and small-change benchmark budgets | **PARTIAL** — gate implemented and exercised, including against real compiler, translator and route-engine work; the budget *numbers* are still engineering estimates |
| 10. Production certificate bound to exact artifacts, scope, expiry, fresh evidence | **PASS** for issue/verify/revoke, now with Ed25519 signatures and a policy that refuses a symmetric signer; **no certificate issued** for a real ELMOS output tree |

**Overall: `CERTIFIED_IN_SANDBOX`.** Every gate that can be decided from this
host passes against real services, real tools and ELMOS's own conversion
engine. What remains is bounded and named: budget *numbers* (gate 9), a
certificate over a real ELMOS output tree (gate 10), and captures on hosts this
session cannot reach — a native Darwin run, a Windows run, and the Swift and
Flutter toolchains. The ordered work is in `BUILD_CACHE_HANDOFF.md` §3.

## Pass-2 rows added

| ID | Required result | Implementation | Test | Verdict |
| --- | --- | --- | --- | --- |
| STORE-001 | The orchestration contract holds identically on the production dialect | `PostgresMetadataStore`, `paramstyle`/`returning_clause` abstraction, `migrations/postgres/0003`,`0004` | `test_metadata_store_contract.py` × `postgres` (23) + `test_dialect_is_actually_exercised` | **PASS** against PostgreSQL 16.10 |
| STORE-002 | A column-adding migration applies exactly once across reopens | `SQLITE_MIGRATIONS` + `schema_migrations` ledger | `test_sqlite_migrations_are_applied_exactly_once` | **PASS** |
| SEC-004 | Envelope encryption binds the tenant; every header byte is authenticated | `EnvelopeCipher` (AES-256-GCM, AAD = version + tenant + key id) | `test_provenance_crypto.py` (round trip, tenant binding, byte-flip, nonce uniqueness, rotation, truncation, unknown key) | **PASS** |
| HASH-001 | Public-interface extraction is exact, not heuristic, in every language | `treesitter_hash.py` (12 grammars) + `interface_hash._extract_python` | `test_treesitter_hash.py` (103) | **PASS** — 13/13 languages |
| HASH-002 | A body-only edit does not cross a module boundary, in every language | `ModuleInterface.body_digest` vs `api_digest`; `compare_interfaces` | `test_a_body_only_edit_does_not_propagate` (13 parameterisations) | **PASS** |
| HASH-003 | Extractor identity and grammar version are part of the digest | `ModuleInterface.extractor` folded into `semantic_digest` | `test_extraction_is_deterministic`, pinned versions in `pyproject.toml` | **PASS** |
| NATIVE-001 | The adapter's environment really redirects each tool's cache | `NativeBuildCacheAdapter.environment` + `assert_sandboxed` | `test_native_toolchains.py` (7 toolchains, each asserting the tool's default cache location was never created) | **PASS** for Gradle, MSBuild, Cargo, ccache, tsc/npm, pip, Go |
| NATIVE-002 | The adapter reads its tool's real hit/miss reporting | `parse_diagnostics` per adapter | same file, cold-build vs warm-build assertions on genuine logs | **PASS** |
| NATIVE-003 | A different trust domain starts from a cold native cache | per-trust-domain adapter root | `test_a_second_trust_domain_starts_from_a_cold_go_cache` | **PASS** |
| E2E-004 | A conversion's target preserves the source's public surface | tree-sitter Java reader + C# emitter + C# grammar re-parse | `test_the_generated_csharp_preserves_the_public_surface`, `test_a_dropped_method_would_fail_verification` | **PASS** |
| OBS-003 | A restored node reports the compiler time it saved | `saved_compiler_ms` through record → store → action cache → accounting | `test_action_cache_entry_round_trip` (both dialects), `test_a_no_change_rerun_…` | **PASS** — previously reported `0` for every restore |

## Pass-3 rows added

| ID | Required result | Implementation | Test | Verdict |
| --- | --- | --- | --- | --- |
| SNAP-004 | A decomposed (NFD) filename snapshots as the composed one | `snapshot._logical` | `test_a_decomposed_filename_snapshots_as_the_composed_one` | **PASS** — this was a real defect: before pass 3 the same checkout produced two root digests |
| SNAP-005 | A repository that cannot round-trip elsewhere says so from here | `snapshot.portability_findings` | `test_snapshot_portability.py` (case collisions, normalisation folds, 10 Windows-hostile names, symlinks, over-long paths) | **PASS** |
| OVL-001 | Projection shares storage; the first write breaks the sharing | `OverlayWorkspace.populate_overlay` / `open_for_write` | `test_projection_shares_storage_and_the_first_write_breaks_it` (inode + link-count evidence) | **PASS** |
| OVL-002 | The source layer cannot be edited by the stage that reads it | `materialize_source` + `_protect` | `test_the_materialised_source_is_read_only_on_disk` | **PASS** (mode asserted; the write attempt skips under root) |
| OVL-003 | A stage sees only declared mounts; credentials and host paths are refused | `SandboxPolicy.check`, `assert_writable` | 7 + 9 parameterised cases in `test_overlay.py` | **PASS** |
| OVL-004 | The workspace behaves on the filesystem a containerised runner actually has | the whole lifecycle | `test_the_workspace_works_on_top_of_a_kernel_overlayfs` (real `mount -t overlay`) | **PASS** |
| ROUTE-001 | The cache drives ELMOS's own conversion engine | `elmos_route_stages.RouteStages` | `test_the_real_analyzer_produces_a_semantic_ir`, `test_the_real_emitter_produces_overflow_checked_java`, `test_the_pipeline_publishes_what_the_route_engine_emitted` | **PASS** |
| ROUTE-002 | Generation is keyed by the IR, so a comment-only edit re-emits nothing | `RouteStages.generation_fingerprint` | `test_a_comment_only_edit_does_not_re_emit` | **PASS** — emitter invoked 0 times, same tree digest |
| ROUTE-003 | `TEST_VERIFIED` is earned by execution, not asserted | `RouteStages.differential_check` | `test_the_emitted_java_compiles_with_a_real_compiler`, `test_a_wrong_translation_cannot_claim_test_verified` | **PASS** — a sabotaged translation is caught and refused reuse |
| ROUTE-004 | A toolchain identity is never invented | `RouteStages.toolchain_identity`, `require`-style refusal | `test_strict_mode_refuses_an_unpinned_toolchain`, `test_an_unpinned_identity_cannot_collide_with_a_pinned_one` | **PASS** |
| NATIVE-004 | Maven reads the sandboxed local repository | `GradleMavenAdapter.derived_environment` (`-Dmaven.repo.local`) | `test_maven_reads_the_sandboxed_local_repository` | **PASS** — Maven's own repository list names the sandbox path |

## SOTA rows (v1.1.0, pass 4)

| ID | Required result | Implementation | Test | Verdict |
| --- | --- | --- | --- | --- |
| SOTA-01 | Same trace, capacity and seed twice → identical decisions and state | `CachePolicy.snapshot`/`restore`/`state_digest` (counters excluded on purpose), `cache_simulator.replay` | `test_sota_01_replay_is_deterministic`, `test_state_digest_survives_a_snapshot_restore_round_trip` | **PASS** — byte-identical decision sequence and state digest |
| SOTA-02 | LRU is always measured; a candidate that does not beat it is not selected | `benchmark(baseline="LRU")` forces LRU into the arm set; `BenchmarkGates.minimum_weighted_improvement` | `test_sota_02_lru_is_always_in_the_comparison`, `test_a_candidate_that_does_not_improve_is_not_selected` | **PASS** — on `multi-tenant-burst` and `large-binaries` at 5 % capacity, `selected` is `None` |
| SOTA-03 | One-hit scan: scan-resistant policies keep the hot set | `SievePolicy`, `S3FifoPolicy`, `WTinyLfuPolicy` | `test_sota_03_scan_does_not_flush_the_hot_set` | **PASS** — ACR at 5 %: LRU 0.000, S3-FIFO 0.216, W-TinyLFU 0.346 |
| SOTA-04 | High temporal reuse: cost/frequency policies beat LRU | `GdsfPolicy`, `WTinyLfuPolicy` | `test_sota_04_high_reuse_favours_frequency_and_cost` | **PASS** — `identical-rerun` at 5 %: LRU 0.000, GDSF 0.581 |
| SOTA-05 | Heterogeneous sizes: one large object may not evict many small hot ones | `SizeAwareTinyLfuPolicy._score` (frequency ÷ bytes) | `test_sota_05_size_aware_keeps_the_denser_object`, `test_size_aware_tinylfu_prefers_the_denser_object` | **PASS** |
| SOTA-06 | Expensive, sparsely reused objects are kept | `GdsfPolicy` priority `clock + freq × saved ÷ size`; `AdmissionController.evaluate` | `test_sota_06_expensive_sparse_objects_survive` | **PASS** |
| SOTA-07 | DAG known future: prefetch precision above the floor, budget respected | `FutureUseIndex.from_dag` over the real `ConversionDag`, `PrefetchPlanner` | `test_sota_07_known_future_is_prefetched_within_budget`, `test_dag_prefetch.py` (23) | **PASS** — cancellation and unused-prefetch accounting included |
| SOTA-08 | Restore slower than recompute → bypass, not admit | `AdmissionReason.BYPASS_RESTORE_SLOWER_THAN_RECOMPUTE`, `restore_or_recompute` | `test_sota_08_restore_slower_than_recompute_is_bypassed` | **PASS** |
| SOTA-09 | Regime shift: switch only past the margin and the dwell | `PolicyOrchestrator.evaluate` (hysteresis + `minimum_dwell_events`) | `test_sota_09_regime_shift_switches_only_past_the_margin` | **PASS** — a shift inside the dwell window does not switch |
| SOTA-10 | Out-of-distribution or drifted features → pinned fallback with a reason | `RuleSelector.out_of_distribution`, `PINNED_FALLBACK = SIEVE`, `detect_drift` | `test_sota_10_out_of_distribution_falls_back_and_says_so` | **PASS** — reason codes `OUT_OF_DISTRIBUTION`, `STRONG_FIXED_FALLBACK` |
| SOTA-11 | Model missing/stale/unsigned/low-confidence → fixed parameters, never an unbounded value | `LearningAugmentedController._fallback_proposal`, `LearnedModel.predict` clipping, `ModelRegistry.verify` | `test_sota_11_missing_or_untrusted_model_uses_fixed_parameters`, `test_learned_control.py` (23) | **PASS** — clipping is the safety property; an unsigned model is refused |
| SOTA-12 | Multi-tenant burst: quota holds, fairness above the gate | `TenantQuota`, `SimulationResult.tenant_fairness` | `test_sota_12_one_tenant_cannot_take_the_whole_cache` | **PASS** |
| SOTA-13 | Snapshot/restore across a restart → matching state digest | `snapshot()`/`restore()`/`state_digest()` on all six policies | `test_sota_13_policy_state_survives_a_restart` (parameterised over all policies) | **PASS** |
| SOTA-14 | Captured trace contains no path, prompt, source or tenant name | `assert_privacy` (positive rule: only allowed shapes pass), HMAC `namespace_hash`, closed vocabularies | `test_sota_14_a_trace_carries_no_identifying_content`, `test_cache_trace.py` (33) | **PASS** — the check allows a listed shape rather than blocking a listed pattern, so a new field is refused by default |
| SOTA-15 | Full matrix: no single policy wins every cell, equal capacity per arm | `benchmark_matrix` (10 workloads × 3 capacities) | `test_sota_15_no_single_policy_wins_everything` | **PASS** — `no_single_winner = True`; wins GDSF 14, W-TinyLFU 8, size-aware 4, SIEVE 2, LRU 1, S3-FIFO 1 |
| SOTA-16 | A policy decision never changes validity, freshness or reuse eligibility | separate modules; `ActionCache` policy checks are untouched by `cache_policy` | `test_sota_16_policy_never_decides_correctness` | **PASS** — the same lookup returns the same verdict under all six policies (`test_sota_21_action_cache_lookup_still_works_under_every_policy`) |
| SOTA-17 | Crash during staging with the policy plane active → staging invariants unchanged | `staging.Workspace` (unchanged), policy plane not on the staging path | `test_sota_17_staging_invariants_hold_with_the_policy_plane_active` | **PASS** |
| SOTA-18 | Regression after promotion → automatic rollback, certificate expires | `RolloutPlan.rollback` (straight to `SIMULATOR`, not one step down), `expired_reasons` | `test_sota_18_a_regression_rolls_back_to_the_pinned_fallback` | **PASS** |
| SOTA-19 | Unknown policy / bad objective / out-of-range fraction fails to load | `config.PolicyConfig` + `_validate_policy` (enum members read from the real enums, not duplicated) | `test_sota_19_bad_policy_configuration_is_refused` (10 params), `test_sota_19_shipped_configuration_carries_the_policy_section` | **PASS** — including the cross-field rule that a canary fraction requires `learned_shadow_only: false` |
| SOTA-20 | Invalidation is removal, not eviction; a half-empty cache admits | `CachePolicy.forget`, `PolicyCounters.invalidations`; W-TinyLFU main-region room check | `test_sota_20_forget_is_accounted_separately_from_eviction`, `test_sota_20_a_half_empty_cache_admits` (both × 6 policies) | **PASS** — the second test is what caught the W-TinyLFU cold-start bug |
| SOTA-21 | Policy-backed hot index never drifts from its policy | `HotIndex(policy=…)` reconciling on `decision.evicted` and refused admissions; `invalidate` → `forget` | `test_sota_21_hot_index_never_drifts_from_its_policy` (× 6), `…_invalidation_reaches_the_policy`, `…_disabled_policy_gives_back_the_built_in_lru` | **PASS** — index membership equals policy residency exactly, under all six |
| SOTA-22 | GC ordering changes; protected roots never become candidates | `GarbageCollector._order_by_replacement_policy` (roots declared to the policy first) | `test_sota_22_replacement_policy_orders_but_never_protects`, `…_protected_roots_are_fed_to_the_policy_first` | **PASS** — same candidate set and same reclaimable bytes as without a policy; only the order moves |
| SOTA-23 | Operator surface emits evidence and refuses without it | `cli` `policy show/benchmark/matrix/select/certify`, `trace generate/verify/workloads` | `test_sota_23_*` (6 tests) | **PASS** — certification refused with `NO_ROLLBACK_EXERCISE`/`NO_SHADOW_EVIDENCE`, granted and Ed25519-signed once the three evidence files exist |
| SOTA-24 | Each configuration switch activates exactly its own capability | `policy_plane.PolicyPlane` — the single place configuration becomes behaviour | `test_sota_24_each_switch_turns_on_exactly_its_own_capability` (4 params), `…_every_switch_is_off_by_default_and_the_plane_is_inert`, `…_admission_refuses_an_entry_that_is_not_worth_recording`, `…_learned_tuning_without_a_signer_is_refused`, `…_a_trace_captured_here_is_usable_downstream`, `…_recommends_but_never_switches_a_live_policy` | **PASS** — this row exists because the five switches were previously read *only* by `policy show`; setting one did nothing |
| SOTA-25 | The plane acts on the real pipeline path, and opting out is inert | `ConversionPipeline.policy_plane`: trace at `plan()`'s probe, admission before `action_cache.commit`, prefetch at each wave boundary, recommendation in `RunReport.policy` | `test_sota_25_a_run_captures_a_trace_from_the_real_lookup_path`, `…_the_report_is_unchanged_when_nothing_is_switched_on`, `…_admission_can_refuse_to_record_without_losing_an_output` | **PASS** — with everything off `RunReport.policy` is `None`; with admission on the published tree digest is *identical* and every published path still comes from a sealed staged record |

## Transfer verification (cloud → Mac), pass 2

29 files were written into `engines/build-cache-engine/` and 5 into `.ai/`.
Aggregate digest over the engine tree — `sha256` of the sorted
`path sha256` listing of every `.py`, `.md`, `.sql`, `.json`, `.yaml` and
`.toml` file (excluding `.venv`, `__pycache__`, `.mypy_cache`, `.pytest_cache`
and `*.egg-info`) — computed independently on both sides:

```text
d7fa735067e55c39b2a5e54e1e2f26f6ca29ae70dd86b2f5edb93499e4fceb1b   (106 files)
```

Identical, so the tree on the Mac is byte-for-byte the tree that produced the
550 passing tests above.

The engine's own tests were **not** re-run on the Mac: its system Python is
3.10 and the engine requires 3.11+. `BUILD_CACHE_HANDOFF.md` §2 has the 3.12
recipe, including the two optional extras and the PostgreSQL DSN.

## Transfer verification (cloud → Mac), pass 3

10 files were written into `engines/build-cache-engine/` (5 new, 5 changed) and
5 into `.ai/`. Aggregate digest over the engine tree — `sha256` of the sorted
`path sha256` listing of every `.py`, `.md`, `.sql`, `.json`, `.yaml` and
`.toml` file (excluding `.venv`, `__pycache__`, `.mypy_cache`, `.pytest_cache`
and `*.egg-info`) — computed independently on both sides:

```text
7831339ac222d1a36578eb14a6238ba9941ee1025361938a0af54ca8c16020fa   (112 files)
```

Identical, so the tree on the Mac is byte-for-byte the tree that produced the
622 passing tests above.

The cross-platform capture left two scratch directories on the Mac. The bridge
cannot delete, so they were moved to
`~/DevProjects/AIProjects/elmos/.ai-tmp/_to_delete/{xplat-probe,xplat-fixture}`
for removal.

## Transfer verification (cloud → Mac), pass 4

33 files were written into `engines/build-cache-engine/` (23 new, 10 changed),
5 into `.ai/`, and the v1.1.0 skills package was vendored at
`agent-skills/packages/elmos-build-cache-staging-sota/` with its 31 `SKILL.md`
files installed into `agent-skills/runtime/` (7 of them new). Aggregate digest
over the engine tree — `sha256` of the sorted `path sha256` listing of every
`.py`, `.md`, `.sql`, `.json`, `.yaml` and `.toml` file (excluding `.venv`,
`__pycache__`, `.mypy_cache`, `.pytest_cache` and `*.egg-info`) — computed
independently on both sides:

```text
15d4a7077138aac8f670dc2301c7e5516f9fd58665efa287327200400cc3528a   (135 files)
```

Identical, so the tree on the Mac is byte-for-byte the tree that produced the
914 passing tests above.

The skills package was additionally validated **on the Mac**, not only in the
sandbox:

```text
$ agent-skills/packages/elmos-build-cache-staging-sota/validate.sh
package structure and checksums OK: 31 skills
Python compilation OK
reference implementation tests OK        (20 tests)
```

The transfer tarball cannot be deleted from here; it was moved to
`agent-skills/packages/_to_delete/elmos-build-cache-staging-sota-v1.1.0.tar.gz`
for removal.

## Transfer verification (cloud → Mac), pass 4b — the switch wiring

A follow-up within pass 4. The five `policy` switches (`adaptive_selection`,
`learned_tuning`, `admission_enabled`, `trace_capture`, `prefetch_enabled`) and
`prefetch_horizon` were **declared but inert**: their only reader was the
`policy show` CLI display. `src/elmos_build_cache/policy_plane.py` now turns
each of them into behaviour on a real call path, and 7 files were rewritten:

```text
2ea9f4d5b6a9c5682d59ae01d7452e40a0584b7280dbcb8d25dccbdf70bdd88d   (136 files)
```

Identical on both sides, and the tree that produced **926 passed, 7 skipped**,
`ruff` clean, `mypy --strict` clean across 52 files.

Where each switch now takes effect:

| Switch | Call path it drives |
| --- | --- |
| `trace_capture` | `ConversionPipeline.plan()`'s cache probe — the run's own lookups, not a replay |
| `admission_enabled` | consulted immediately before `ActionCache.commit`, *after* the artifact is sealed, promoted and in the tree |
| `prefetch_enabled` / `prefetch_horizon` | `ConversionPipeline.execute()` at each wave boundary, against the real `ConversionDag` order |
| `adaptive_selection` | end-of-run recommendation in `RunReport.policy.recommendation.selection` |
| `learned_tuning` | end-of-run bounded parameter proposal; refuses to construct at all without a provenance signer |

With every switch off, `PolicyPlane.active` is `False` and `RunReport.policy`
is `None` — a report from a deployment that has not opted in is byte-identical
to one produced before the plane existed.

## Pass 5 evidence ledger — v1.2 parity

The v1.2 source archive is immutable and identified by
`sha256:dde312b55a95cbc7af6753ec88f07833e93ffa296b782ddcf3ef1a6470b73cb7`.
The importer inspected its inventory, checksums and contracts without executing
package scripts. The vendored tree and
`docs/build-cache-staging-parity/installed-manifest.json` record 42 Skills: 31
retained v1.1 bodies plus 11 new v1.2 contracts. The installed files are
byte-identical across all four supported roots.

### Local engineering evidence

| Evidence item | Evidence location | Result and limit |
| --- | --- | --- |
| Delta-aware import | `tooling/import_build_cache_parity_skills.py`, `tests/build-cache-staging-parity/test_import_build_cache_parity_skills.py` | **PASS** locally; proves structure/provenance/idempotent import, not runtime behavior |
| Contract assets | 19 files under `schemas/` and `_data/schemas/`; parity OpenAPI under `openapi/` and `_data/openapi/` | Root/packaged copies are exact. The engine OpenAPI is a documented production overlay; the canonical ZIP remains unchanged |
| Append-only context | `context_ledger.py`, `context_compaction.py`, SQLite 0003, PostgreSQL 0005 | Local SQLite/narrow tests **PASS**; live v1.2 PostgreSQL path `NOT_RUN` |
| Durable parity metadata | `parity_store.py`, SQLite 0004, PostgreSQL 0006 | Local SQLite/reopen/idempotency/tenant checks **PASS**; live v1.2 PostgreSQL path `NOT_RUN` |
| Provider prefix | `prompt_cache.py`, `prompt_tools.py` | Compiler, volatility, exact-profile and content-free accounting tests **PASS**; provider calls and provider-reported hit ratios `NOT_RUN` |
| Environment snapshots | `environment_cache.py`, `environment_service.py` | 9 local SQLite/CAS service tests **PASS**; remote/distributed CAS, runner inventory and real rebuild/restore `NOT_RUN` |
| Affinity/coordinator/diagnostics | `affinity.py`, `coordinator.py`, `miss_diagnostics.py`, `parity_runtime.py` | Pure/local and pipeline-observation behavior covered; production scheduler/fleet and scale `NOT_RUN` |
| Parity corpus/evaluator | `parity.py`, `parity_harness.py` | Exact 20-scenario/16-metric shape and fail-closed evidence rules covered; independent real corpus `NOT_RUN` |
| Rollout | `slo_autotune.py`, `config/elmos-cache.yaml` | Shadow/canary/progressive/rollback state logic covered; field rollout `NOT_RUN` |
| Public surface | `parity_api.py`, `api.py`, `cli.py`, parity OpenAPI | Seven API operations and new CLI commands covered locally; no external control-plane deployment |

The source package's OpenAPI description was not copied blindly into the
production surface. The engine overlay adds the missing mutation idempotency
headers and an append-context payload that matches the implemented event
contract. This is an intentional, tested overlay stored only under the engine;
the canonical ZIP is left byte-for-byte intact.

### Claim boundary

| Claim | Current state |
| --- | --- |
| Source package imported without overwriting completed v1.1 behavior | local engineering evidence available |
| All 11 new contracts have concrete engine modules and narrow tests | local engineering evidence available |
| Real provider prompt-prefix reuse | `NOT_RUN` |
| Real environment warm-start reuse | `NOT_RUN` |
| Real long-session compaction/restart behavior | `NOT_RUN` |
| Independent representative parity corpus | `NOT_RUN` |
| Production PostgreSQL/fleet/rollout evidence | `NOT_RUN` |
| Package numerical parity thresholds achieved | no claim |
| v1.2 certification | `NOT_CERTIFIED` |

Local tests may support implementation readiness, but they cannot produce a
Codex/Claude-equivalence claim. A future report must bind the exact source,
configuration, provider/model/tool profile, date, platform, corpus, raw
evidence, replay command, authorization, executor and separate verifier.

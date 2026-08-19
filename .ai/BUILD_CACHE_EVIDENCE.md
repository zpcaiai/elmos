# BUILD_CACHE_EVIDENCE.md

> Acceptance row → required result → implementing symbol → test → executed
> verdict. Source of the rows:
> `agent-skills/packages/elmos-build-cache-staging-recovery/tests/acceptance/cache-staging-acceptance-matrix.md`.
>
> Every row below was executed on 2026-08-19 (pass 2), Linux x86_64,
> Python 3.12.3, `pytest tests` → **550 passed, 5 skipped**, with a live
> PostgreSQL 16 server, a live HTTP S3 endpoint and seven real build toolchains
> in the run. A row without an executed command is marked `NOT EXECUTED`.
> Nothing here is a certification claim beyond what the commands showed.

| ID | Required result | Implementation | Test | Verdict |
| --- | --- | --- | --- | --- |
| SNAP-001 | Same logical repository → same canonical root digest | `snapshot.take_snapshot` (path-independent, NFC, sorted Merkle) | `test_snap_001_same_repository_different_absolute_paths`, `test_snap_001_windows_style_separators_normalise` | **PASS**, cross-OS fixtures `NOT EXECUTED` |
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
| E2E-001 | Java/Spring → C#/ASP.NET complete project: staged, validated, atomically published | `ConversionPipeline` + `TreePublisher`, driven by a real `javac` stage and a real tree-sitter-driven translator | `test_e2e_001_complete_project_is_staged_validated_and_published`, `test_e2e_001_real_stages_compile_translate_and_publish`, `test_the_generated_csharp_preserves_the_public_surface` | **PASS** for the orchestration over real artifacts; **`NOT EXECUTED`** for ELMOS's own model-driven stage, which is registered by the orchestrator and not by this engine |
| E2E-002 | Service restart during generation → resume without duplicate side effects or partial output | lease reclaim + workspace recovery | `test_e2e_002_restart_during_generation_resumes_without_duplicates` | **PASS** |
| E2E-003 | No-change rerun → same final tree digest, model/compiler work avoided | ActionKey stability + restore-from-cache staging | `test_e2e_003_no_change_rerun_reproduces_the_tree_without_model_work` | **PASS** (identical `root_digest`, generator invoked 0 times, hit rate 1.0) |

## Release gates (spec §21)

| Gate | Verdict |
| --- | --- |
| 1. Cross-platform deterministic snapshot fixtures | **PARTIAL** — deterministic and path-independent on Linux; macOS/Windows fixtures `NOT EXECUTED` |
| 2. CAS concurrent-write, interruption, corruption | **PASS** |
| 3. ActionKey dimension tests | **PASS** |
| 4. Staged-file kill-point tests at all critical boundaries | **PASS** — in-process injection at 10 boundaries **and** real `SIGKILL` at 8 |
| 5. No partial final file exposed | **PASS** |
| 6. Checkpoint resume matches clean-run output digest | **PASS** for the deterministic fixture |
| 7. Stale-worker and duplicate-message tests | **PASS** |
| 8. Tenant isolation, secret leakage, cache poisoning | **PASS** |
| 9. No-change and small-change benchmark budgets | **PARTIAL** — gate implemented and exercised, including against real compiler and translator work; the budget *numbers* are still engineering estimates |
| 10. Production certificate bound to exact artifacts, scope, expiry, fresh evidence | **PASS** for issue/verify/revoke, now with Ed25519 signatures and a policy that refuses a symmetric signer; **no certificate issued** for a real ELMOS output tree |

**Overall: `CERTIFIED_IN_SANDBOX`.** Every gate that can be decided without
ELMOS's own conversion workload passes against real services and real tools.
Gates 1, 9 and 10 remain open for the reasons stated, and only for those
reasons; the ordered work is in `BUILD_CACHE_HANDOFF.md` §3.

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

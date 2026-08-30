# Production Metrics

## Correctness
- semantic_conversion_pass_rate
- compile_pass_rate
- reference_integrity_rate
- behavior_equivalence_pass_rate
- certification_pass_rate
- unresolved_p0_p1

## Agent effectiveness
- first_pass_edit_success
- repairs_per_transaction
- agent_task_success_rate
- merge_conflict_rate
- stale_patch_rejection_rate
- reviewer_blocker_rate
- human_intervention_rate

## Runtime
- job_wall_clock_seconds
- phase_wall_clock_seconds
- critical_path_seconds
- restart_recovery_seconds
- idempotency_replay_count

## Cost
- tokens_input/output/cache
- provider_cost
- tool_compute_cost
- storage_cost
- project_total_cost
- cost_per_kloc
- cost_per_successful_route
- gross_margin_estimate

## Model / harness
- fallback_rate
- quota_failure_rate
- tool_selection_accuracy
- LSP_vs_text_fallback_rate
- prompt_variant_success
- context_compaction_count
- context_rebuild_count

## Skill learning
- candidate_skill_count
- promotion_rate
- regression_failure_rate
- skill_rollback_rate
- fixture_coverage
- golden_route_coverage

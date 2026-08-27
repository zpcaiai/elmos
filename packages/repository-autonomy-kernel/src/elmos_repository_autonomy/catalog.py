"""Exact v2 catalog; the dispatcher is intentionally closed-world."""

from __future__ import annotations

from dataclasses import dataclass

PACKAGE_ID = "elmos-repository-autonomy-kernel-v2.0.0"
PACKAGE_VERSION = "2.0.0"


@dataclass(frozen=True, slots=True)
class SkillSpec:
    name: str
    priority: str
    pack: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    side_effects: bool = True


def _s(name: str, priority: str, pack: str, inputs: str, outputs: str, side_effects: bool = True) -> SkillSpec:
    return SkillSpec(name, priority, pack, tuple(inputs.split()), tuple(outputs.split()), side_effects)


_SPECS = (
    _s("task-spec-delta-compiler", "P0", "P03", "requirements repository_snapshot previous_task_spec policy_profile", "task_spec spec_delta acceptance_criteria ambiguity_register affected_node_set"),
    _s("durable-run-orchestrator", "P0", "P01", "task_spec workflow_definition repository_snapshot budget policy_snapshot", "run step_runs run_events checkpoints rollback_plan progress_snapshot"),
    _s("execution-authority-kernel", "P0", "P01", "environment workspace permission_profile tool_request fencing_token", "execution_authority authority_snapshot authorization_decision audit_event"),
    _s("typed-tool-runtime", "P0", "P01", "tool_descriptor tool_call_request execution_authority policy_snapshot", "tool_call_record typed_result structured_error side_effect_record compensation_record"),
    _s("policy-hook-kernel", "P0", "P01", "hook_event policy_layers run_context tool_or_step_context", "policy_decision modified_input approval_request policy_evidence audit_event"),
    _s("two-phase-secretless-sandbox", "P0", "P01", "repository_snapshot workspace_profile network_policy secret_binding_plan", "analysis_environment execution_environment secret_lease sandbox_attestation cleanup_report"),
    _s("workspace-lease-fencing", "P0", "P01", "workspace worker_identity lease_policy checkpoint side_effect_ledger", "lease fencing_token heartbeat takeover_event recovery_plan"),
    _s("artifact-evidence-protocol", "P0", "P02", "producer_step content repo_snapshot task_spec_version security_label", "artifact evidence provenance_edge retention_decision integrity_record"),
    _s("repository-census", "P0", "P02", "immutable_repository_snapshot build_files optional_runtime_traces coverage api_schemas", "repository_profile module_graph build_graph entrypoint_map data_flow_map risk_map"),
    _s("incremental-semantic-index", "P0", "P02", "repository_snapshot previous_index change_set compiler_metadata", "semantic_index symbol_graph call_graph dependency_graph test_impact_map invalidation_set"),
    _s("semantic-ir-compiler", "P0", "P03", "repository_semantic_index task_spec source_framework_profile target_profile", "semantic_ir rule_dsl mutation_dsl scenario_dsl evidence_dsl source_map"),
    _s("changegraph-vcs", "P0", "P03", "task_spec repository_snapshot patches artifact_lineage validation_results", "change_graph change_node change_edge merge_plan revert_plan provenance_commit"),
    _s("validation-dag", "P0", "P04", "task_spec change_graph repository_profile risk_profile test_catalog", "validation_plan validation_dag critical_path coverage_map validation_budget"),
    _s("independent-verification-mesh", "P0", "P04", "change_set validation_dag task_spec repository_snapshot policies", "verification_run findings finding_validations coverage_report release_recommendation"),
    _s("evidence-release-gate", "P0", "P05", "completion_claim acceptance_criteria validation_results artifacts approvals deployment_results", "acceptance_decision gate_results release_bundle rollback_bundle deployment_complete_attestation"),
    _s("contract-compatibility-engine", "P0", "P03", "baseline_contracts candidate_contracts consumer_inventory compatibility_policy", "compatibility_report breaking_changes adapter_plan migration_plan rollback_contract"),
    _s("prefix-stable-context-planner", "P1", "P02", "task_spec repository_index current_step skill_metadata token_budget previous_ledger", "context_plan context_bundle context_ledger retrieval_trace compaction_snapshot"),
    _s("lazy-tool-loader", "P1", "P02", "step_requirements tool_catalog agent_contract execution_authority policy_snapshot", "tool_load_plan loaded_tool_set tool_schema_bundle denied_tool_set load_metrics"),
    _s("model-state-continuity", "P1", "P01", "context_ledger run_state agent_state tool_results open_findings provider_event", "model_state_snapshot continuation_prompt resume_cursor state_diff continuity_report"),
    _s("multi-agent-worktree-coordinator", "P1", "P04", "task_dag agent_contracts workspace_topology budget artifact_contracts", "agent_assignments agent_runs artifact_handoffs conflict_report merge_plan"),
    _s("phase-aware-model-router", "P1", "P06", "step_profile model_capability_profiles risk_profile budget provider_policy recent_evals", "routing_decision fallback_chain escalation_plan estimated_cost usage_record"),
    _s("layered-cache-fabric", "P1", "P06", "snapshot_hash task_spec_hash workflow_version skill_versions policy_hash tool_schema_versions model_profile", "cache_key cache_entry hit_miss invalidation_set provenance cache_metrics"),
    _s("cost-eta-observability", "P1", "P06", "run_events historical_runs repo_features model_tool_usage cache_metrics pricing_profile", "progress_snapshot eta_distribution critical_path cost_breakdown billing_record slo_metrics"),
    _s("tiered-security-assurance", "P1", "P05", "tool_or_file_change diff semantic_index security_policy deployment_artifact", "security_findings threat_model_delta security_gate sbom_references waiver"),
    _s("session-time-travel", "P1", "P01", "run_event_stream checkpoints context_ledgers change_graph artifacts", "session_snapshot forked_run replay_report state_comparison rollback_plan"),
    _s("capability-package-registry", "P1", "P07", "package_manifest components dependency_lock signature test_results", "registered_package component_catalog install_plan permission_review upgrade_plan"),
    _s("demonstration-to-skill", "P2", "P07", "validated_demonstration run_artifacts expert_annotations privacy_policy", "skill_draft trigger_examples reusable_scripts references regression_fixtures"),
    _s("auto-improvement-inbox-and-skill-curator", "P2", "P07", "run_incidents user_corrections findings telemetry benchmark_results", "improvement_candidate failure_cluster reproducer regression_test curation_decision"),
    _s("agent-arena", "P2", "P07", "arena_task_set agent_candidates fixed_environments budgets evaluation_protocol", "arena_runs pairwise_results quality_cost_frontier failure_analysis promotion_candidate"),
    _s("repository-model-elo", "P2", "P07", "arena_results production_evals task_taxonomy model_cost_latency", "elo_ratings confidence_intervals segment_ratings routing_recommendations drift_alerts"),
    _s("repository-gym-golden-routes", "P2", "P07", "benchmark_repositories golden_task_specs fixed_images expected_contracts chaos_scenarios", "gym_runs golden_artifacts scorecards regression_trends commercial_readiness"),
)

SKILL_SPECS = {item.name: item for item in _SPECS}
SKILL_NAMES = tuple(item.name for item in _SPECS)

if len(SKILL_NAMES) != 31 or len(SKILL_SPECS) != 31:
    raise RuntimeError("repository autonomy catalog must contain exactly 31 unique Skills")

"""Unit and contract tests for all 22 Batch 42 Governed Agent Factory skills."""

import pytest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts/batch42"))

from b42_skill_runtime import B42SkillRuntime


@pytest.fixture
def runtime():
    return B42SkillRuntime()


def test_runtime_skill_enumeration(runtime):
    assert len(runtime.SKILLS) == 22
    for s in runtime.SKILLS:
        assert s.startswith("b42-")


def test_b42_agent_migration_factory(runtime):
    res = runtime.dispatch("b42-agent-migration-factory", "init", {})
    assert res["status"] == "AGENT_FACTORY_ONLINE"
    assert res["ready"] is True
    assert "supervisor" in res["agent_roles"]


def test_b42_agent_team_topology(runtime):
    res = runtime.dispatch("b42-agent-team-topology", "configure", {})
    assert res["status"] == "TOPOLOGY_CONFIGURED"
    assert res["supervisor_node"] == "agent-supervisor-01"


def test_b42_supervisor_coordination_agent(runtime):
    res = runtime.dispatch("b42-supervisor-coordination-agent", "supervise", {"task_id": "task-01"})
    assert res["status"] == "COORDINATION_SUPERVISED"
    assert "lease-fence" in res["lease_fencing_token"]


def test_b42_migration_planner_agent(runtime):
    res = runtime.dispatch("b42-migration-planner-agent", "plan", {})
    assert res["status"] == "PLAN_FINALIZED"
    assert len(res["migration_waves"]) == 3


def test_b42_language_framework_specialist_agent(runtime):
    res = runtime.dispatch("b42-language-framework-specialist-agent", "engage", {})
    assert res["status"] == "SPECIALIST_ENGAGED"
    assert res["type_conversions_verified"] is True


def test_b42_recipe_candidate_agent(runtime):
    res = runtime.dispatch("b42-recipe-candidate-agent", "synthesize", {})
    assert res["status"] == "CANDIDATE_RECIPE_GENERATED"
    assert res["generalizability_score"] >= 0.90


def test_b42_deterministic_execution_agent(runtime):
    res = runtime.dispatch("b42-deterministic-execution-agent", "execute", {"patch_id": "p-10"})
    assert res["status"] == "DETERMINISTIC_EXECUTION_COMPLETED"
    assert res["exit_code"] == 0
    assert res["patch_hash"].startswith("sha256:")


def test_b42_verification_agent(runtime):
    res = runtime.dispatch("b42-verification-agent", "verify", {"failures_count": 0})
    assert res["status"] == "VERIFICATION_COMPLETED"
    assert res["verification_decision"] == "PASSED"

    res_fail = runtime.dispatch("b42-verification-agent", "verify", {"failures_count": 2})
    assert res_fail["verification_decision"] == "FAILED"


def test_b42_policy_enforcement_agent(runtime):
    res = runtime.dispatch("b42-policy-enforcement-agent", "enforce", {"violations_count": 0})
    assert res["status"] == "POLICY_ENFORCED"
    assert res["policy_decision"] == "ALLOW"

    res_deny = runtime.dispatch("b42-policy-enforcement-agent", "enforce", {"violations_count": 1})
    assert res_deny["policy_decision"] == "DENY"


def test_b42_agent_tool_permissions(runtime):
    res = runtime.dispatch("b42-agent-tool-permissions", "scope", {"agent_role": "executor"})
    assert res["status"] == "PERMISSIONS_SCOPED"
    assert "delete_repo" in res["forbidden_tools"]


def test_b42_agent_autonomy_levels(runtime):
    res = runtime.dispatch("b42-agent-autonomy-levels", "set_level", {"autonomy_level": "L3_CONDITIONAL_AUTONOMY"})
    assert res["status"] == "AUTONOMY_LEVEL_APPLIED"
    assert res["human_override_available"] is True


def test_b42_agent_budget_resource_limits(runtime):
    res = runtime.dispatch("b42-agent-budget-resource-limits", "check", {"max_turns": 50})
    assert res["status"] == "RESOURCE_BUDGET_NORMAL"
    assert res["budget_exhausted"] is False


def test_b42_agent_memory_state_governance(runtime):
    res = runtime.dispatch("b42-agent-memory-state-governance", "compact", {"session_id": "s-1"})
    assert res["status"] == "MEMORY_GOVERNED"
    assert res["poisoning_audit_clean"] is True


def test_b42_multiagent_consensus_arbitration(runtime):
    res = runtime.dispatch("b42-multiagent-consensus-arbitration", "arbitrate", {})
    assert res["status"] == "CONSENSUS_REACHED"
    assert res["arbitrated_decision"] == "PROCEED"


def test_b42_model_routing_provider_failover(runtime):
    res = runtime.dispatch("b42-model-routing-provider-failover", "route", {})
    assert res["status"] == "FAILOVER_ROUTED"
    assert res["routed_provider"] == "anthropic-bedrock"


def test_b42_minimal_context_evidence(runtime):
    res = runtime.dispatch("b42-minimal-context-evidence", "compile", {"context_tokens": 8000})
    assert res["status"] == "MINIMAL_CONTEXT_COMPILED"
    assert res["evidence_retention_ratio"] == 1.0


def test_b42_agent_shadow_canary(runtime):
    res = runtime.dispatch("b42-agent-shadow-canary", "evaluate", {})
    assert res["status"] == "SHADOW_CANARY_EVALUATED"
    assert res["canary_passed"] is True


def test_b42_agent_eval_benchmark(runtime):
    res = runtime.dispatch("b42-agent-eval-benchmark", "run_bench", {})
    assert res["status"] == "BENCHMARK_EVAL_COMPLETED"
    assert res["eval_pass_rate"] == 1.0


def test_b42_agent_red_team(runtime):
    res = runtime.dispatch("b42-agent-red-team", "execute_attacks", {})
    assert res["status"] == "RED_TEAM_PASSED"
    assert res["breaches_detected"] == 0


def test_b42_human_approval_takeover(runtime):
    res = runtime.dispatch("b42-human-approval-takeover", "trigger_pause", {})
    assert res["status"] == "HUMAN_TAKEOVER_READY"
    assert res["agent_state_paused"] is True


def test_b42_agent_incident_killswitch_rollback(runtime):
    res = runtime.dispatch("b42-agent-incident-killswitch-rollback", "kill", {})
    assert res["status"] == "KILLSWITCH_EXECUTED_SAFELY"
    assert res["killswitch_pass_rate"] == 1.0


def test_b42_agent_factory_gate(runtime):
    res = runtime.dispatch("b42-agent-factory-gate", "evaluate", {
        "agentEvalPassRate": 1.0,
        "policyViolationCount": 0.0,
        "killSwitchPassRate": 1.0,
    })
    assert res["passed"] is True
    assert res["status"] == "GATE_PASSED"

    res_fail = runtime.dispatch("b42-agent-factory-gate", "evaluate", {
        "agentEvalPassRate": 0.95,
        "policyViolationCount": 1.0,
        "killSwitchPassRate": 1.0,
    })
    assert res_fail["passed"] is False
    assert res_fail["status"] == "GATE_REJECTED"


def test_unknown_skill_raises(runtime):
    with pytest.raises(KeyError):
        runtime.dispatch("b42-non-existent-skill", "check")

"""Unit and contract tests for all 22 Batch 39 Global SRE & Production Operations skills."""

import pytest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts/batch39"))

from b39_skill_runtime import B39SkillRuntime


@pytest.fixture
def runtime():
    return B39SkillRuntime()


def test_runtime_skill_enumeration(runtime):
    assert len(runtime.SKILLS) == 22
    for s in runtime.SKILLS:
        assert s.startswith("b39-")


def test_b39_global_sre_operations_factory(runtime):
    res = runtime.dispatch("b39-global-sre-operations-factory", "init", {"factory_id": "fac-global"})
    assert res["status"] == "SRE_FACTORY_ONLINE"
    assert res["ready"] is True
    assert "sli-slo" in res["core_subsystems"]


def test_b39_service_catalog_sli_slo(runtime):
    res = runtime.dispatch("b39-service-catalog-sli-slo", "check", {"service_name": "payments-api"})
    assert res["status"] == "SLO_HEALTHY"
    assert "availability" in res["sli_definitions"]
    assert res["slo_targets"]["availability"] == 0.9995


def test_b39_error_budget_governance(runtime):
    res = runtime.dispatch("b39-error-budget-governance", "evaluate", {"budget_remaining_percent": 85.0})
    assert res["status"] == "BUDGET_ACTIVE"
    assert res["policy_decision"] == "PROCEED"

    res_frozen = runtime.dispatch("b39-error-budget-governance", "evaluate", {"budget_remaining_percent": 5.0})
    assert res_frozen["policy_decision"] == "FREEZE_DEPLOYMENTS"


def test_b39_global_observability_telemetry(runtime):
    res = runtime.dispatch("b39-global-observability-telemetry", "ingest", {"events_per_sec": 50000})
    assert res["status"] == "TELEMETRY_PIPELINE_ACTIVE"
    assert "otlp-grpc" in res["protocols"]


def test_b39_autoscaling_capacity_control(runtime):
    res = runtime.dispatch("b39-autoscaling-capacity-control", "tune", {"cluster_id": "k8s-prod-1"})
    assert res["status"] == "CAPACITY_GOVERNED"
    assert res["warm_pool_headroom_percent"] == 15


def test_b39_incident_command(runtime):
    res = runtime.dispatch("b39-incident-command", "declare", {"incident_id": "INC-100", "severity": "SEV-1"})
    assert res["status"] == "MITIGATED"
    assert res["incident_commander"] == "oncall-lead-apac"


def test_b39_oncall_follow_the_sun(runtime):
    res = runtime.dispatch("b39-oncall-follow-the-sun", "query_shift", {"active_region": "EMEA"})
    assert res["status"] == "ROTATION_ACTIVE"
    assert res["shift_details"]["primary"] == "sre-emea-01"


def test_b39_problem_root_cause_loop(runtime):
    res = runtime.dispatch("b39-problem-root-cause-loop", "postmortem", {"incident_id": "INC-100"})
    assert res["status"] == "POSTMORTEM_APPROVED"
    assert res["five_whys_completed"] is True
    assert len(res["remediation_actions"]) == 2


def test_b39_chaos_resilience_fault_injection(runtime):
    res = runtime.dispatch("b39-chaos-resilience-fault-injection", "inject", {"experiment_name": "kill-broker"})
    assert res["status"] == "CHAOS_EXPERIMENT_PASSED"
    assert res["steady_state_hypothesis_verified"] is True


def test_b39_multiregion_failover(runtime):
    res = runtime.dispatch("b39-multiregion-failover", "test_failover", {"replication_lag_seconds": 0.5})
    assert res["status"] == "MULTILOCATION_FAILOVER_VALIDATED"
    assert res["failover_ready"] is True


def test_b39_backup_restore_recovery(runtime):
    res = runtime.dispatch("b39-backup-restore-recovery", "restore", {"target_timestamp": "2026-09-10T12:00:00Z"})
    assert res["status"] == "BACKUP_RESTORE_SUCCESSFUL"
    assert res["checksum_validation"] == "PASSED"


def test_b39_scheduled_restore_dr_exercise(runtime):
    res = runtime.dispatch("b39-scheduled-restore-dr-exercise", "exercise", {"cycle": "MONTHLY_DR_DRILL"})
    assert res["status"] == "DR_EXERCISE_CERTIFIED"
    assert res["data_checksum_match"] is True


def test_b39_job_fairness_tenant_isolation(runtime):
    res = runtime.dispatch("b39-job-fairness-tenant-isolation", "admit", {"tenant_id": "t-001"})
    assert res["status"] == "TENANT_FAIRNESS_ENFORCED"
    assert res["admission_decision"] == "ADMITTED"


def test_b39_platform_cost_anomaly_monitoring(runtime):
    res = runtime.dispatch("b39-platform-cost-anomaly-monitoring", "scan", {"current_spend_usd": 1260.0})
    assert res["status"] == "COST_NORMAL"
    assert res["anomaly_detected"] is False

    res_anom = runtime.dispatch("b39-platform-cost-anomaly-monitoring", "scan", {"current_spend_usd": 2000.0})
    assert res_anom["status"] == "COST_ANOMALY_FLAGGED"
    assert res_anom["anomaly_detected"] is True


def test_b39_change_management_freeze(runtime):
    res_allowed = runtime.dispatch("b39-change-management-freeze", "check", {"freeze_window_active": False})
    assert res_allowed["change_permitted"] is True

    res_blocked = runtime.dispatch("b39-change-management-freeze", "check", {"freeze_window_active": True, "change_class": "STANDARD"})
    assert res_blocked["change_permitted"] is False


def test_b39_production_readiness_review(runtime):
    res = runtime.dispatch("b39-production-readiness-review", "review", {"service_name": "worker-1"})
    assert res["status"] == "PRR_COMPLETED"
    assert res["prr_status"] == "APPROVED_FOR_PRODUCTION"


def test_b39_tenant_project_migration_health(runtime):
    res = runtime.dispatch("b39-tenant-project-migration-health", "probe", {"error_count": 0})
    assert res["status"] == "MIGRATION_HEALTHY"
    assert res["health_score"] == 1.0


def test_b39_customer_status_communication(runtime):
    res = runtime.dispatch("b39-customer-status-communication", "publish", {"message": "Operational"})
    assert res["status"] == "STATUS_BROADCAST_COMPLETED"
    assert res["subscribers_notified"] == 420


def test_b39_enterprise_support_sla(runtime):
    res = runtime.dispatch("b39-enterprise-support-sla", "track", {"priority": "P1_URGENT", "first_response_minutes": 10})
    assert res["status"] == "SUPPORT_SLA_COMPLIANT"
    assert res["sla_met"] is True


def test_b39_sla_service_credit_governance(runtime):
    res = runtime.dispatch("b39-sla-service-credit-governance", "calculate", {"monthly_uptime_percent": 99.99})
    assert res["service_credit_applicable"] is False
    assert res["credit_percentage_owed"] == 0.0


def test_b39_operations_evidence_reporting(runtime):
    res = runtime.dispatch("b39-operations-evidence-reporting", "generate", {"period": "2026-08"})
    assert res["status"] == "OPERATIONS_REPORT_GENERATED"
    assert res["evidence_digest"].startswith("sha256:")


def test_b39_global_operations_gate(runtime):
    res = runtime.dispatch("b39-global-operations-gate", "evaluate", {
        "sloPassRate": 1.0,
        "restorePassRate": 1.0,
        "incidentExercisePassRate": 1.0,
    })
    assert res["passed"] is True
    assert res["status"] == "GATE_PASSED"

    res_fail = runtime.dispatch("b39-global-operations-gate", "evaluate", {
        "sloPassRate": 0.98,
        "restorePassRate": 1.0,
        "incidentExercisePassRate": 1.0,
    })
    assert res_fail["passed"] is False
    assert res_fail["status"] == "GATE_REJECTED"


def test_unknown_skill_raises(runtime):
    with pytest.raises(KeyError):
        runtime.dispatch("b39-non-existent-skill", "check")

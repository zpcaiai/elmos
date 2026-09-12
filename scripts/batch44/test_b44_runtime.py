"""Unit and contract tests for all 20 Batch 44 FinOps & Unit Economics skills."""

import pytest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts/batch44"))

from b44_skill_runtime import B44SkillRuntime


@pytest.fixture
def runtime():
    return B44SkillRuntime()


def test_runtime_skill_enumeration(runtime):
    assert len(runtime.SKILLS) == 20
    for s in runtime.SKILLS:
        assert s.startswith("b44-")


def test_b44_migration_finops_factory(runtime):
    res = runtime.dispatch("b44-migration-finops-factory", "init", {})
    assert res["status"] == "FINOPS_FACTORY_INITIALIZED"
    assert res["ready"] is True
    assert "model_tokens" in res["cost_dimensions"]


def test_b44_cost_taxonomy_economic_model(runtime):
    res = runtime.dispatch("b44-cost-taxonomy-economic-model", "taxonomy", {})
    assert res["status"] == "TAXONOMY_ESTABLISHED"
    assert "COGS_MODEL_INFERENCE" in res["categories"]


def test_b44_resource_metering(runtime):
    res = runtime.dispatch("b44-resource-metering", "meter", {"input_tokens": 1000})
    assert res["status"] == "USAGE_METERED"
    assert res["metered_metrics"]["input_tokens"] == 1000


def test_b44_usage_billing_reconciliation(runtime):
    res = runtime.dispatch("b44-usage-billing-reconciliation", "reconcile", {"metered_usd": 100.0, "billed_usd": 100.0})
    assert res["status"] == "RECONCILIATION_SUCCESS"
    assert res["reconciled"] is True

    res_fail = runtime.dispatch("b44-usage-billing-reconciliation", "reconcile", {"metered_usd": 100.0, "billed_usd": 110.0})
    assert res_fail["status"] == "DISCREPANCY_DETECTED"
    assert res_fail["reconciled"] is False


def test_b44_model_agent_economics(runtime):
    res = runtime.dispatch("b44-model-agent-economics", "calculate", {"prompt_tokens": 1000000, "completion_tokens": 200000})
    assert res["status"] == "MODEL_ECONOMICS_COMPUTED"
    assert res["blended_cost_usd"] == 6.0


def test_b44_runner_fleet_economics(runtime):
    res = runtime.dispatch("b44-runner-fleet-economics", "compute", {"runner_hours": 100.0, "hourly_rate_usd": 0.10})
    assert res["status"] == "FLEET_ECONOMICS_RECORDED"
    assert res["fleet_cost_usd"] == 10.0


def test_b44_human_expert_cost(runtime):
    res = runtime.dispatch("b44-human-expert-cost", "record", {"expert_hours": 2.0, "rate_usd_per_hour": 150.0})
    assert res["status"] == "EXPERT_COST_RECORDED"
    assert res["cost_usd"] == 300.0


def test_b44_support_hypercare_operations_cost(runtime):
    res = runtime.dispatch("b44-support-hypercare-operations-cost", "allocate", {"days": 10, "daily_cost_usd": 500.0})
    assert res["status"] == "HYPERCARE_COST_ALLOCATED"
    assert res["total_hypercare_usd"] == 5000.0


def test_b44_artifact_retention_egress_economics(runtime):
    res = runtime.dispatch("b44-artifact-retention-egress-economics", "optimize", {"gb_months": 1000, "egress_gb": 100})
    assert res["status"] == "STORAGE_ECONOMICS_OPTIMIZED"
    assert res["cost_usd"] == 25.0


def test_b44_cache_incremental_cost_optimization(runtime):
    res = runtime.dispatch("b44-cache-incremental-cost-optimization", "record", {"cached_tokens": 1000000})
    assert res["status"] == "CACHE_SAVINGS_RECORDED"
    assert res["net_savings_usd"] == 2.80


def test_b44_verified_workload_unit_cost(runtime):
    res = runtime.dispatch("b44-verified-workload-unit-cost", "calculate", {"kloc_migrated": 10.0, "total_cost_usd": 100.0})
    assert res["status"] == "UNIT_COST_VERIFIED"
    assert res["cost_per_kloc_usd"] == 10.0
    assert res["within_target"] is True


def test_b44_customer_route_edition_margin(runtime):
    res = runtime.dispatch("b44-customer-route-edition-margin", "evaluate", {"contract_value_usd": 10000.0, "delivery_cost_usd": 2000.0})
    assert res["status"] == "MARGIN_TARGET_MET"
    assert res["gross_margin_percent"] == 80.0


def test_b44_budget_quota_cost_guardrail(runtime):
    res = runtime.dispatch("b44-budget-quota-cost-guardrail", "check", {"budget_usd": 500.0, "spent_usd": 200.0})
    assert res["status"] == "GUARDRAILS_PASSED"
    assert res["budget_guardrail_pass"] is True

    res_exceeded = runtime.dispatch("b44-budget-quota-cost-guardrail", "check", {"budget_usd": 500.0, "spent_usd": 600.0})
    assert res_exceeded["status"] == "BUDGET_EXCEEDED_HALT"
    assert res_exceeded["budget_guardrail_pass"] is False


def test_b44_showback_chargeback(runtime):
    res = runtime.dispatch("b44-showback-chargeback", "invoice", {"department": "Engineering"})
    assert res["status"] == "CHARGEBACK_INVOICE_GENERATED"
    assert res["total_chargeback_usd"] > 0


def test_b44_cost_scenario_forecast(runtime):
    res = runtime.dispatch("b44-cost-scenario-forecast", "forecast", {"repo_count": 50, "avg_kloc": 20})
    assert res["status"] == "COST_FORECAST_COMPILED"
    assert res["total_kloc"] == 1000


def test_b44_packaging_pricing_model(runtime):
    res = runtime.dispatch("b44-packaging-pricing-model", "get_tier", {"tier": "ENTERPRISE_PLATINUM"})
    assert res["status"] == "PRICING_MODEL_DEFINED"
    assert res["base_monthly_usd"] == 5000.0


def test_b44_assessment_poc_project_quote(runtime):
    res = runtime.dispatch("b44-assessment-poc-project-quote", "quote", {"client_name": "TestCorp"})
    assert res["status"] == "QUOTE_GENERATED"
    assert res["fixed_poc_fee_usd"] == 25000.0


def test_b44_customer_roi_tco_value(runtime):
    res = runtime.dispatch("b44-customer-roi-tco-value", "compute", {"manual_cost_usd": 200000.0, "elmos_cost_usd": 50000.0})
    assert res["status"] == "ROI_CALCULATED"
    assert res["net_savings_usd"] == 150000.0
    assert res["roi_percent"] == 300.0


def test_b44_provider_resource_routing(runtime):
    res = runtime.dispatch("b44-provider-resource-routing", "route", {"task_complexity": "LOW_BOILERPLATE"})
    assert res["status"] == "OPTIMAL_RESOURCE_ROUTED"
    assert res["routed_tier"] == "lightweight-draft-model"


def test_b44_economics_maturity_gate(runtime):
    res = runtime.dispatch("b44-economics-maturity-gate", "evaluate", {
        "meteringReconciliationRate": 1.0,
        "budgetGuardrailPassRate": 1.0,
        "grossMarginEvidenceCoverageRate": 0.98,
    })
    assert res["passed"] is True
    assert res["status"] == "GATE_PASSED"

    res_fail = runtime.dispatch("b44-economics-maturity-gate", "evaluate", {
        "meteringReconciliationRate": 0.95,
        "budgetGuardrailPassRate": 1.0,
        "grossMarginEvidenceCoverageRate": 0.90,
    })
    assert res_fail["passed"] is False
    assert res_fail["status"] == "GATE_REJECTED"


def test_unknown_skill_raises(runtime):
    with pytest.raises(KeyError):
        runtime.dispatch("b44-non-existent-skill", "check")

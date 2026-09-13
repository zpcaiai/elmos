import unittest
from elmos_mature_platform.types import ModelPricing, ModelProvider, AgentInvocation, AgentCostType
from elmos_mature_platform.model_agent_economics_engine import ModelAgentEconomicsEngine

class TestModelAgentEconomicsEngine(unittest.TestCase):
    def setUp(self):
        self.engine = ModelAgentEconomicsEngine()
        self.gpt4 = ModelPricing(
            model_id="gpt-4",
            provider=ModelProvider.OPENAI,
            input_cost_per_1k_tokens=0.03,
            output_cost_per_1k_tokens=0.06
        )
        self.claude = ModelPricing(
            model_id="claude-3",
            provider=ModelProvider.ANTHROPIC,
            input_cost_per_1k_tokens=0.015,
            output_cost_per_1k_tokens=0.075
        )
        self.engine.register_model_pricing(self.gpt4)
        self.engine.register_model_pricing(self.claude)

    def test_register_model_pricing(self):
        self.assertIn("gpt-4", self.engine._pricing)
        self.assertEqual(self.engine._pricing["gpt-4"].input_cost_per_1k_tokens, 0.03)

    def test_compute_invocation_cost_basic(self):
        inv = AgentInvocation(
            invocation_id="i1", agent_id="a1", model_id="gpt-4",
            input_tokens=1000, output_tokens=1000,
            tool_cost=0.0, human_review_cost=0.0
        )
        cost = self.engine.compute_invocation_cost(inv)
        self.assertAlmostEqual(cost, 0.09)

    def test_compute_invocation_cost_unregistered(self):
        inv = AgentInvocation(
            invocation_id="i1", agent_id="a1", model_id="unknown",
            input_tokens=1000, output_tokens=1000
        )
        with self.assertRaises(ValueError):
            self.engine.compute_invocation_cost(inv)

    def test_compute_invocation_cost_with_tools(self):
        inv = AgentInvocation(
            invocation_id="i1", agent_id="a1", model_id="gpt-4",
            input_tokens=1000, output_tokens=1000,
            tool_cost=0.5, human_review_cost=1.0
        )
        cost = self.engine.compute_invocation_cost(inv)
        self.assertAlmostEqual(cost, 1.59)

    def test_record_invocation(self):
        inv = AgentInvocation(
            invocation_id="i1", agent_id="a1", model_id="gpt-4",
            input_tokens=1000, output_tokens=1000
        )
        self.engine.record_invocation(inv)
        self.assertEqual(len(self.engine._invocations), 1)

    def test_record_invocation_unregistered(self):
        inv = AgentInvocation(
            invocation_id="i1", agent_id="a1", model_id="unknown",
            input_tokens=1000, output_tokens=1000
        )
        with self.assertRaises(ValueError):
            self.engine.record_invocation(inv)

    def test_get_agent_costs_empty(self):
        costs = self.engine.get_agent_costs("a1")
        self.assertEqual(costs[AgentCostType.MODEL_INFERENCE], 0.0)

    def test_get_agent_costs_populated(self):
        inv = AgentInvocation(
            invocation_id="i1", agent_id="a1", model_id="gpt-4",
            input_tokens=1000, output_tokens=1000,
            tool_cost=0.5, human_review_cost=1.0
        )
        self.engine.record_invocation(inv)
        costs = self.engine.get_agent_costs("a1")
        self.assertAlmostEqual(costs[AgentCostType.MODEL_INFERENCE], 0.09)
        self.assertAlmostEqual(costs[AgentCostType.TOOL_EXECUTION], 0.5)
        self.assertAlmostEqual(costs[AgentCostType.HUMAN_REVIEW], 1.0)

    def test_get_agent_costs_multiple(self):
        self.engine.record_invocation(AgentInvocation("i1", "a1", "gpt-4", 1000, 1000, tool_cost=1.0))
        self.engine.record_invocation(AgentInvocation("i2", "a1", "gpt-4", 2000, 2000, tool_cost=2.0))
        costs = self.engine.get_agent_costs("a1")
        self.assertAlmostEqual(costs[AgentCostType.MODEL_INFERENCE], 0.27)
        self.assertAlmostEqual(costs[AgentCostType.TOOL_EXECUTION], 3.0)

    def test_get_tenant_costs_empty(self):
        self.assertEqual(self.engine.get_tenant_costs("t1"), {})

    def test_get_tenant_costs_single(self):
        self.engine.record_invocation(AgentInvocation("i1", "a1", "gpt-4", 1000, 1000, tenant_id="t1"))
        costs = self.engine.get_tenant_costs("t1")
        self.assertAlmostEqual(costs["a1"], 0.09)

    def test_get_tenant_costs_multiple(self):
        self.engine.record_invocation(AgentInvocation("i1", "a1", "gpt-4", 1000, 1000, tenant_id="t1"))
        self.engine.record_invocation(AgentInvocation("i2", "a2", "gpt-4", 2000, 2000, tenant_id="t1"))
        costs = self.engine.get_tenant_costs("t1")
        self.assertAlmostEqual(costs["a1"], 0.09)
        self.assertAlmostEqual(costs["a2"], 0.18)

    def test_get_tenant_costs_mixed(self):
        self.engine.record_invocation(AgentInvocation("i1", "a1", "gpt-4", 1000, 1000, tenant_id="t1"))
        self.engine.record_invocation(AgentInvocation("i2", "a1", "gpt-4", 1000, 1000, tenant_id="t2"))
        costs = self.engine.get_tenant_costs("t1")
        self.assertEqual(len(costs), 1)

    def test_compute_agent_roi_no_invocations(self):
        roi = self.engine.compute_agent_roi("a1", 10.0)
        self.assertEqual(roi.total_cost, 0.0)
        self.assertEqual(roi.roi_percentage, 0.0)

    def test_compute_agent_roi_all_success(self):
        self.engine.record_invocation(AgentInvocation("i1", "a1", "gpt-4", 1000, 1000, success=True))
        roi = self.engine.compute_agent_roi("a1", 1.0)
        self.assertAlmostEqual(roi.total_cost, 0.09)
        self.assertAlmostEqual(roi.total_value_generated, 1.0)
        self.assertAlmostEqual(roi.roi_percentage, (1.0 - 0.09) / 0.09 * 100.0)

    def test_compute_agent_roi_mixed_success(self):
        self.engine.record_invocation(AgentInvocation("i1", "a1", "gpt-4", 1000, 1000, success=True))
        self.engine.record_invocation(AgentInvocation("i2", "a1", "gpt-4", 1000, 1000, success=False))
        roi = self.engine.compute_agent_roi("a1", 1.0)
        self.assertAlmostEqual(roi.total_cost, 0.18)
        self.assertAlmostEqual(roi.total_value_generated, 1.0)
        self.assertAlmostEqual(roi.roi_percentage, (1.0 - 0.18) / 0.18 * 100.0)

    def test_forecast_costs_empty(self):
        forecast = self.engine.forecast_costs("a1", 30)
        self.assertEqual(forecast.projected_cost, 0.0)

    def test_forecast_costs_populated(self):
        self.engine.record_invocation(AgentInvocation("i1", "a1", "gpt-4", 1000, 1000))
        self.engine.record_invocation(AgentInvocation("i2", "a1", "gpt-4", 1000, 1000))
        forecast = self.engine.forecast_costs("a1", 30)
        self.assertAlmostEqual(forecast.projected_cost, 0.18 * 30)

    def test_get_model_comparison_empty(self):
        comp = self.engine.get_model_comparison()
        self.assertEqual(len(comp), 0)

    def test_get_model_comparison_single(self):
        self.engine.record_invocation(AgentInvocation("i1", "a1", "gpt-4", 1000, 1000))
        comp = self.engine.get_model_comparison()
        self.assertEqual(len(comp), 1)
        self.assertEqual(comp[0]["model_id"], "gpt-4")
        self.assertAlmostEqual(comp[0]["total_cost"], 0.09)
        self.assertAlmostEqual(comp[0]["cost_per_1k_success_tokens"], 0.045)

    def test_get_model_comparison_multiple(self):
        self.engine.record_invocation(AgentInvocation("i1", "a1", "gpt-4", 1000, 1000))
        self.engine.record_invocation(AgentInvocation("i2", "a2", "claude-3", 1000, 1000))
        comp = self.engine.get_model_comparison()
        self.assertEqual(len(comp), 2)
        # Claude cost: 0.015 + 0.075 = 0.09. Same cost!

    def test_get_model_comparison_failed_invocations(self):
        self.engine.record_invocation(AgentInvocation("i1", "a1", "gpt-4", 1000, 1000, success=False))
        comp = self.engine.get_model_comparison()
        self.assertEqual(comp[0]["cost_per_1k_success_tokens"], 0.0)

    def test_detect_cost_anomalies_empty(self):
        anomalies = self.engine.detect_cost_anomalies("a1")
        self.assertEqual(len(anomalies), 0)

    def test_detect_cost_anomalies_no_variance(self):
        self.engine.record_invocation(AgentInvocation("i1", "a1", "gpt-4", 1000, 1000))
        self.engine.record_invocation(AgentInvocation("i2", "a1", "gpt-4", 1000, 1000))
        anomalies = self.engine.detect_cost_anomalies("a1")
        self.assertEqual(len(anomalies), 0)

    def test_detect_cost_anomalies_detected(self):
        self.engine.record_invocation(AgentInvocation("i1", "a1", "gpt-4", 1000, 1000)) # 0.09
        self.engine.record_invocation(AgentInvocation("i2", "a1", "gpt-4", 1000, 1000)) # 0.09
        self.engine.record_invocation(AgentInvocation("i3", "a1", "gpt-4", 1000, 1000)) # 0.09
        self.engine.record_invocation(AgentInvocation("i4", "a1", "gpt-4", 100000, 100000)) # 9.0
        anomalies = self.engine.detect_cost_anomalies("a1", threshold_multiplier=1.0)
        self.assertEqual(len(anomalies), 1)
        self.assertEqual(anomalies[0].invocation_id, "i4")

    def test_get_economics_report(self):
        self.engine.record_invocation(AgentInvocation("i1", "a1", "gpt-4", 1000, 1000, tenant_id="t1"))
        report = self.engine.get_economics_report()
        self.assertAlmostEqual(report["total_spend"], 0.09)
        self.assertAlmostEqual(report["spend_by_model"]["gpt-4"], 0.09)
        self.assertAlmostEqual(report["spend_by_agent"]["a1"], 0.09)
        self.assertAlmostEqual(report["spend_by_tenant"]["t1"], 0.09)

    def test_recommend_model_no_invocations(self):
        with self.assertRaises(ValueError):
            self.engine.recommend_model("a1")

    def test_recommend_model_basic(self):
        self.engine.record_invocation(AgentInvocation("i1", "a1", "gpt-4", 1000, 1000)) # success
        # Claude is same cost here, let's make gpt-4 cheaper to test sorting properly
        cheaper_gpt = ModelPricing("cheap-gpt", ModelProvider.OPENAI, 0.001, 0.002)
        self.engine.register_model_pricing(cheaper_gpt)
        self.engine.record_invocation(AgentInvocation("i2", "a2", "cheap-gpt", 1000, 1000)) # success
        
        rec = self.engine.recommend_model("a1")
        self.assertEqual(rec, "cheap-gpt")

    def test_recommend_model_considers_success_rate(self):
        cheap_model = ModelPricing("cheap", ModelProvider.OPENAI, 0.001, 0.001)
        self.engine.register_model_pricing(cheap_model)
        
        # Agent uses gpt-4, 100% success
        self.engine.record_invocation(AgentInvocation("i1", "a1", "gpt-4", 1000, 1000, success=True))
        
        # Cheap model has 0% success globally
        self.engine.record_invocation(AgentInvocation("i2", "a2", "cheap", 1000, 1000, success=False))
        
        rec = self.engine.recommend_model("a1")
        self.assertEqual(rec, "gpt-4") # cheap model fails target success rate

    def test_recommend_model_fallback(self):
        self.engine.record_invocation(AgentInvocation("i1", "a1", "gpt-4", 1000, 1000, success=False))
        # Since target is 0, any model works. It will pick the cheapest one.
        rec = self.engine.recommend_model("a1")
        self.assertEqual(rec, "gpt-4")

    def test_roi_zero_cost(self):
        # Register a free model
        self.engine.register_model_pricing(ModelPricing("free", ModelProvider.OPENAI, 0.0, 0.0))
        self.engine.record_invocation(AgentInvocation("i1", "a1", "free", 1000, 1000, success=True))
        roi = self.engine.compute_agent_roi("a1", 5.0)
        self.assertEqual(roi.total_cost, 0.0)
        self.assertEqual(roi.roi_percentage, 0.0)

    def test_get_economics_report_empty(self):
        report = self.engine.get_economics_report()
        self.assertEqual(report["total_spend"], 0.0)

    def test_detect_anomalies_no_threshold(self):
        self.engine.record_invocation(AgentInvocation("i1", "a1", "gpt-4", 1000, 1000))
        self.engine.record_invocation(AgentInvocation("i2", "a1", "gpt-4", 1000, 1000))
        anomalies = self.engine.detect_cost_anomalies("a1", threshold_multiplier=0.0)
        # All points are at mean, so cost > threshold is False
        self.assertEqual(len(anomalies), 0)

if __name__ == "__main__":
    unittest.main()

import unittest
from elmos_mature_platform.types import (
    ForecastCostCategory as CostCategory,
    ScenarioType,
    ForecastCostLineItem as CostLineItem,
    CostScenario,
)
from elmos_mature_platform.cost_scenario_forecast_engine import CostScenarioForecastEngine

class TestCostScenarioForecastEngine(unittest.TestCase):
    def setUp(self):
        self.engine = CostScenarioForecastEngine()
        
    def test_add_line_item(self):
        item = CostLineItem(item_id="1", category=CostCategory.COMPUTE, name="EC2", monthly_cost=100.0)
        self.engine.add_line_item(item)
        self.assertIn("1", self.engine.line_items)

    def test_add_line_item_calculates_monthly(self):
        item = CostLineItem(item_id="2", category=CostCategory.COMPUTE, name="EC2", unit_cost=10.0, quantity=5.0)
        self.engine.add_line_item(item)
        self.assertEqual(self.engine.line_items["2"].monthly_cost, 50.0)

    def test_create_scenario(self):
        scenario = CostScenario(scenario_id="s1", name="Base")
        self.engine.create_scenario(scenario)
        self.assertIn("s1", self.engine.scenarios)
        self.assertNotEqual(self.engine.scenarios["s1"].created_at, "")

    def test_add_item_to_scenario(self):
        item = CostLineItem(item_id="i1", category=CostCategory.COMPUTE, name="EC2", monthly_cost=100.0)
        self.engine.add_line_item(item)
        scenario = CostScenario(scenario_id="s1", name="Base")
        self.engine.create_scenario(scenario)
        self.engine.add_item_to_scenario("s1", "i1")
        self.assertIn("i1", self.engine.scenarios["s1"].line_items)

    def test_add_item_to_scenario_updates_total(self):
        item = CostLineItem(item_id="i1", category=CostCategory.COMPUTE, name="EC2", monthly_cost=100.0)
        self.engine.add_line_item(item)
        scenario = CostScenario(scenario_id="s1", name="Base")
        self.engine.create_scenario(scenario)
        self.engine.add_item_to_scenario("s1", "i1")
        self.assertEqual(self.engine.scenarios["s1"].total_monthly, 100.0)
        self.assertEqual(self.engine.scenarios["s1"].total_annual, 1200.0)

    def test_add_item_to_scenario_not_found(self):
        scenario = CostScenario(scenario_id="s1", name="Base")
        self.engine.create_scenario(scenario)
        with self.assertRaises(ValueError):
            self.engine.add_item_to_scenario("s2", "i1")

    def test_add_item_to_scenario_item_not_found(self):
        scenario = CostScenario(scenario_id="s1", name="Base")
        self.engine.create_scenario(scenario)
        with self.assertRaises(ValueError):
            self.engine.add_item_to_scenario("s1", "i1")

    def test_forecast(self):
        item = CostLineItem(item_id="i1", category=CostCategory.COMPUTE, name="EC2", monthly_cost=100.0, growth_rate_pct=10.0)
        self.engine.add_line_item(item)
        scenario = CostScenario(scenario_id="s1", name="Base")
        self.engine.create_scenario(scenario)
        self.engine.add_item_to_scenario("s1", "i1")
        forecast = self.engine.forecast("s1", 2)
        self.assertEqual(len(forecast), 2)
        self.assertEqual(forecast[0]["month"], 1)
        self.assertAlmostEqual(forecast[0]["total_cost"], 110.0)
        self.assertEqual(forecast[1]["month"], 2)
        self.assertAlmostEqual(forecast[1]["total_cost"], 121.0)

    def test_forecast_scenario_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.forecast("s1")

    def test_get_total_cost(self):
        item = CostLineItem(item_id="i1", category=CostCategory.COMPUTE, name="EC2", monthly_cost=100.0)
        self.engine.add_line_item(item)
        scenario = CostScenario(scenario_id="s1", name="Base")
        self.engine.create_scenario(scenario)
        self.engine.add_item_to_scenario("s1", "i1")
        self.assertEqual(self.engine.get_total_cost("s1"), 100.0)

    def test_get_total_cost_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.get_total_cost("s1")

    def test_compare_scenarios(self):
        i1 = CostLineItem(item_id="i1", category=CostCategory.COMPUTE, name="EC2", monthly_cost=100.0)
        i2 = CostLineItem(item_id="i2", category=CostCategory.COMPUTE, name="EC2", monthly_cost=50.0)
        self.engine.add_line_item(i1)
        self.engine.add_line_item(i2)
        s1 = CostScenario(scenario_id="s1", name="Base")
        s2 = CostScenario(scenario_id="s2", name="Opt")
        self.engine.create_scenario(s1)
        self.engine.create_scenario(s2)
        self.engine.add_item_to_scenario("s1", "i1")
        self.engine.add_item_to_scenario("s2", "i2")
        comparison = self.engine.compare_scenarios(["s1", "s2"])
        self.assertEqual(comparison["s1"]["total_monthly"], 100.0)
        self.assertEqual(comparison["s2"]["total_monthly"], 50.0)

    def test_get_cost_by_category(self):
        i1 = CostLineItem(item_id="i1", category=CostCategory.COMPUTE, name="EC2", monthly_cost=100.0)
        i2 = CostLineItem(item_id="i2", category=CostCategory.STORAGE, name="S3", monthly_cost=50.0)
        self.engine.add_line_item(i1)
        self.engine.add_line_item(i2)
        s1 = CostScenario(scenario_id="s1", name="Base")
        self.engine.create_scenario(s1)
        self.engine.add_item_to_scenario("s1", "i1")
        self.engine.add_item_to_scenario("s1", "i2")
        breakdown = self.engine.get_cost_by_category("s1")
        self.assertEqual(breakdown[CostCategory.COMPUTE.value], 100.0)
        self.assertEqual(breakdown[CostCategory.STORAGE.value], 50.0)
        self.assertEqual(breakdown[CostCategory.NETWORK.value], 0.0)

    def test_get_cost_by_category_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.get_cost_by_category("s1")

    def test_get_savings_from_optimization(self):
        i1 = CostLineItem(item_id="i1", category=CostCategory.COMPUTE, name="EC2", monthly_cost=100.0)
        i2 = CostLineItem(item_id="i2", category=CostCategory.COMPUTE, name="EC2", monthly_cost=50.0)
        self.engine.add_line_item(i1)
        self.engine.add_line_item(i2)
        s1 = CostScenario(scenario_id="s1", name="Base")
        s2 = CostScenario(scenario_id="s2", name="Opt")
        self.engine.create_scenario(s1)
        self.engine.create_scenario(s2)
        self.engine.add_item_to_scenario("s1", "i1")
        self.engine.add_item_to_scenario("s2", "i2")
        savings = self.engine.get_savings_from_optimization("s1", "s2")
        self.assertEqual(savings["baseline_monthly"], 100.0)
        self.assertEqual(savings["optimized_monthly"], 50.0)
        self.assertEqual(savings["monthly_savings"], 50.0)
        self.assertEqual(savings["annual_savings"], 600.0)
        self.assertEqual(savings["savings_pct"], 50.0)

    def test_get_savings_from_optimization_baseline_not_found(self):
        s2 = CostScenario(scenario_id="s2", name="Opt")
        self.engine.create_scenario(s2)
        with self.assertRaises(ValueError):
            self.engine.get_savings_from_optimization("s1", "s2")

    def test_get_savings_from_optimization_optimized_not_found(self):
        s1 = CostScenario(scenario_id="s1", name="Base")
        self.engine.create_scenario(s1)
        with self.assertRaises(ValueError):
            self.engine.get_savings_from_optimization("s1", "s2")

    def test_get_top_cost_drivers(self):
        i1 = CostLineItem(item_id="i1", category=CostCategory.COMPUTE, name="EC2", monthly_cost=100.0)
        i2 = CostLineItem(item_id="i2", category=CostCategory.STORAGE, name="S3", monthly_cost=200.0)
        i3 = CostLineItem(item_id="i3", category=CostCategory.NETWORK, name="NAT", monthly_cost=50.0)
        self.engine.add_line_item(i1)
        self.engine.add_line_item(i2)
        self.engine.add_line_item(i3)
        s1 = CostScenario(scenario_id="s1", name="Base")
        self.engine.create_scenario(s1)
        self.engine.add_item_to_scenario("s1", "i1")
        self.engine.add_item_to_scenario("s1", "i2")
        self.engine.add_item_to_scenario("s1", "i3")
        drivers = self.engine.get_top_cost_drivers("s1", 2)
        self.assertEqual(len(drivers), 2)
        self.assertEqual(drivers[0].item_id, "i2")
        self.assertEqual(drivers[1].item_id, "i1")

    def test_get_top_cost_drivers_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.get_top_cost_drivers("s1")

    def test_project_break_even(self):
        i1 = CostLineItem(item_id="i1", category=CostCategory.COMPUTE, name="EC2", monthly_cost=100.0, growth_rate_pct=10.0)
        i2 = CostLineItem(item_id="i2", category=CostCategory.COMPUTE, name="EC2_Opt", monthly_cost=120.0, growth_rate_pct=2.0)
        self.engine.add_line_item(i1)
        self.engine.add_line_item(i2)
        s1 = CostScenario(scenario_id="s1", name="Base")
        s2 = CostScenario(scenario_id="s2", name="Opt")
        self.engine.create_scenario(s1)
        self.engine.create_scenario(s2)
        self.engine.add_item_to_scenario("s1", "i1")
        self.engine.add_item_to_scenario("s2", "i2")
        # Month 1: s1 = 110, s2 = 122.4 -> s2 is not cheaper
        # Month 2: s1 = 121, s2 = 124.848 -> s2 is not cheaper
        # Month 3: s1 = 133.1, s2 = 127.34 -> s2 is cheaper!
        break_even = self.engine.project_break_even("s1", "s2")
        self.assertEqual(break_even, 3)

    def test_project_break_even_never(self):
        i1 = CostLineItem(item_id="i1", category=CostCategory.COMPUTE, name="EC2", monthly_cost=100.0, growth_rate_pct=2.0)
        i2 = CostLineItem(item_id="i2", category=CostCategory.COMPUTE, name="EC2_Opt", monthly_cost=120.0, growth_rate_pct=10.0)
        self.engine.add_line_item(i1)
        self.engine.add_line_item(i2)
        s1 = CostScenario(scenario_id="s1", name="Base")
        s2 = CostScenario(scenario_id="s2", name="Opt")
        self.engine.create_scenario(s1)
        self.engine.create_scenario(s2)
        self.engine.add_item_to_scenario("s1", "i1")
        self.engine.add_item_to_scenario("s2", "i2")
        break_even = self.engine.project_break_even("s1", "s2")
        self.assertIsNone(break_even)

    def test_project_break_even_not_found(self):
        s1 = CostScenario(scenario_id="s1", name="Base")
        self.engine.create_scenario(s1)
        with self.assertRaises(ValueError):
            self.engine.project_break_even("s1", "s2")

    def test_get_forecast_report(self):
        i1 = CostLineItem(item_id="i1", category=CostCategory.COMPUTE, name="EC2", monthly_cost=100.0, growth_rate_pct=1.0)
        self.engine.add_line_item(i1)
        s1 = CostScenario(scenario_id="s1", name="Base", scenario_type=ScenarioType.BASELINE)
        self.engine.create_scenario(s1)
        self.engine.add_item_to_scenario("s1", "i1")
        report = self.engine.get_forecast_report("s1")
        self.assertEqual(report["scenario_id"], "s1")
        self.assertEqual(report["name"], "Base")
        self.assertEqual(report["type"], ScenarioType.BASELINE.value)
        self.assertEqual(report["total_monthly"], 100.0)
        self.assertEqual(report["total_annual"], 1200.0)
        self.assertIn(CostCategory.COMPUTE.value, report["cost_by_category"])
        self.assertEqual(len(report["top_cost_drivers"]), 1)
        self.assertEqual(report["top_cost_drivers"][0], "i1")
        self.assertEqual(len(report["forecast_12m"]), 12)

    def test_get_forecast_report_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.get_forecast_report("s1")

    def test_compare_empty_scenarios(self):
        s1 = CostScenario(scenario_id="s1", name="Base")
        self.engine.create_scenario(s1)
        comparison = self.engine.compare_scenarios(["s1", "s2"])
        self.assertIn("s1", comparison)
        self.assertNotIn("s2", comparison)

    def test_savings_pct_zero_baseline(self):
        i1 = CostLineItem(item_id="i1", category=CostCategory.COMPUTE, name="EC2", monthly_cost=0.0)
        i2 = CostLineItem(item_id="i2", category=CostCategory.COMPUTE, name="EC2", monthly_cost=50.0)
        self.engine.add_line_item(i1)
        self.engine.add_line_item(i2)
        s1 = CostScenario(scenario_id="s1", name="Base")
        s2 = CostScenario(scenario_id="s2", name="Opt")
        self.engine.create_scenario(s1)
        self.engine.create_scenario(s2)
        self.engine.add_item_to_scenario("s1", "i1")
        self.engine.add_item_to_scenario("s2", "i2")
        savings = self.engine.get_savings_from_optimization("s1", "s2")
        self.assertEqual(savings["savings_pct"], 0.0)

    def test_forecast_zero_growth(self):
        item = CostLineItem(item_id="i1", category=CostCategory.COMPUTE, name="EC2", monthly_cost=100.0, growth_rate_pct=0.0)
        self.engine.add_line_item(item)
        scenario = CostScenario(scenario_id="s1", name="Base")
        self.engine.create_scenario(scenario)
        self.engine.add_item_to_scenario("s1", "i1")
        forecast = self.engine.forecast("s1", 2)
        self.assertEqual(forecast[0]["total_cost"], 100.0)
        self.assertEqual(forecast[1]["total_cost"], 100.0)

    def test_forecast_negative_growth(self):
        item = CostLineItem(item_id="i1", category=CostCategory.COMPUTE, name="EC2", monthly_cost=100.0, growth_rate_pct=-10.0)
        self.engine.add_line_item(item)
        scenario = CostScenario(scenario_id="s1", name="Base")
        self.engine.create_scenario(scenario)
        self.engine.add_item_to_scenario("s1", "i1")
        forecast = self.engine.forecast("s1", 2)
        self.assertAlmostEqual(forecast[0]["total_cost"], 90.0)
        self.assertAlmostEqual(forecast[1]["total_cost"], 81.0)
        
    def test_duplicate_add_item_to_scenario(self):
        item = CostLineItem(item_id="i1", category=CostCategory.COMPUTE, name="EC2", monthly_cost=100.0)
        self.engine.add_line_item(item)
        scenario = CostScenario(scenario_id="s1", name="Base")
        self.engine.create_scenario(scenario)
        self.engine.add_item_to_scenario("s1", "i1")
        self.engine.add_item_to_scenario("s1", "i1")
        self.assertEqual(len(self.engine.scenarios["s1"].line_items), 1)

if __name__ == "__main__":
    unittest.main()

"""Comprehensive tests for PackagingPricingModelEngine."""

import unittest
from datetime import datetime, timezone
from elmos_mature_platform.packaging_pricing_model_engine import PackagingPricingModelEngine
from elmos_mature_platform.types import (
    PricingModel,
    PackageTier,
    PricingPlan,
    PricingSubscription,
    PricingSimulation
)

class TestPackagingPricingModelEngine(unittest.TestCase):
    def setUp(self):
        self.engine = PackagingPricingModelEngine()
        
        self.free_plan = PricingPlan(
            plan_id="plan_free",
            name="Free Tier",
            tier=PackageTier.FREE,
            pricing_model=PricingModel.FREEMIUM,
            max_seats=5,
            features=["basic"]
        )
        self.engine.create_plan(self.free_plan)
        
        self.starter_plan = PricingPlan(
            plan_id="plan_starter",
            name="Starter",
            tier=PackageTier.STARTER,
            pricing_model=PricingModel.PER_SEAT,
            base_price_monthly=0.0,
            per_seat_price=10.0,
            max_seats=10,
            features=["basic", "standard"]
        )
        self.engine.create_plan(self.starter_plan)

        self.pro_plan = PricingPlan(
            plan_id="plan_pro",
            name="Professional",
            tier=PackageTier.PROFESSIONAL,
            pricing_model=PricingModel.HYBRID,
            base_price_monthly=50.0,
            per_seat_price=20.0,
            included_units=1000,
            overage_price_per_unit=0.05,
            features=["basic", "standard", "pro"]
        )
        self.engine.create_plan(self.pro_plan)
        
    def test_create_plan_success(self):
        plan = PricingPlan("p1", "P1", PackageTier.ENTERPRISE, PricingModel.FLAT_RATE, 1000.0)
        pid = self.engine.create_plan(plan)
        self.assertEqual(pid, "p1")
        
    def test_create_plan_free_tier_invalid(self):
        plan = PricingPlan("p1", "P1", PackageTier.FREE, PricingModel.FREEMIUM, 10.0)
        with self.assertRaises(ValueError):
            self.engine.create_plan(plan)
            
    def test_create_plan_free_tier_invalid_per_seat(self):
        plan = PricingPlan("p1", "P1", PackageTier.FREE, PricingModel.FREEMIUM, 0.0, 5.0)
        with self.assertRaises(ValueError):
            self.engine.create_plan(plan)

    def test_create_subscription_success(self):
        sub = PricingSubscription("sub1", "cust1", "plan_starter", seats=3)
        sid = self.engine.create_subscription(sub)
        self.assertEqual(sid, "sub1")
        self.assertEqual(self.engine._subscriptions["sub1"].monthly_total, 30.0)

    def test_create_subscription_plan_not_found(self):
        sub = PricingSubscription("sub1", "cust1", "plan_fake")
        with self.assertRaises(ValueError):
            self.engine.create_subscription(sub)
            
    def test_create_subscription_exceeds_max_seats(self):
        sub = PricingSubscription("sub1", "cust1", "plan_free", seats=10)
        with self.assertRaises(ValueError):
            self.engine.create_subscription(sub)

    def test_calculate_monthly_cost_base(self):
        sub = PricingSubscription("sub1", "cust1", "plan_pro", seats=2)
        self.engine.create_subscription(sub)
        # 50 + 2*20 = 90
        self.assertEqual(self.engine.calculate_monthly_cost("sub1"), 90.0)
        
    def test_calculate_monthly_cost_with_usage(self):
        sub = PricingSubscription("sub1", "cust1", "plan_pro", seats=2, usage_units=1200)
        self.engine.create_subscription(sub)
        # 50 + 40 + (200*0.05) = 90 + 10 = 100
        self.assertEqual(self.engine.calculate_monthly_cost("sub1"), 100.0)

    def test_calculate_monthly_cost_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.calculate_monthly_cost("fake")

    def test_record_usage(self):
        sub = PricingSubscription("sub1", "cust1", "plan_pro", seats=2, usage_units=900)
        self.engine.create_subscription(sub)
        self.engine.record_usage("sub1", 200)
        self.assertEqual(self.engine._subscriptions["sub1"].usage_units, 1100)
        self.assertEqual(self.engine.calculate_monthly_cost("sub1"), 95.0)

    def test_record_usage_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.record_usage("fake", 100)
            
    def test_simulate_pricing_basic(self):
        sim = self.engine.simulate_pricing("plan_starter", 5, 0)
        self.assertEqual(sim.monthly_cost, 50.0)
        self.assertEqual(sim.annual_cost, 600.0)
        self.assertEqual(sim.cost_per_seat, 10.0)
        
    def test_simulate_pricing_with_overage(self):
        sim = self.engine.simulate_pricing("plan_pro", 2, 1100)
        # base: 50, seats: 40, overage(100): 5 -> 95
        self.assertEqual(sim.monthly_cost, 95.0)

    def test_simulate_pricing_with_discount(self):
        sim = self.engine.simulate_pricing("plan_starter", 5, 0, discount_pct=10)
        self.assertEqual(sim.monthly_cost, 45.0)
        
    def test_simulate_pricing_plan_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.simulate_pricing("fake", 1, 0)

    def test_simulate_pricing_exceeds_max_seats(self):
        with self.assertRaises(ValueError):
            self.engine.simulate_pricing("plan_free", 10, 0)

    def test_upgrade_plan_success(self):
        sub = PricingSubscription("sub1", "cust1", "plan_starter", seats=3)
        self.engine.create_subscription(sub)
        self.engine.upgrade_plan("sub1", "plan_pro")
        self.assertEqual(self.engine._subscriptions["sub1"].plan_id, "plan_pro")
        self.assertEqual(self.engine._subscriptions["sub1"].monthly_total, 110.0) # 50 + 60

    def test_upgrade_plan_same_tier(self):
        sub = PricingSubscription("sub1", "cust1", "plan_starter", seats=3)
        self.engine.create_subscription(sub)
        with self.assertRaises(ValueError):
            self.engine.upgrade_plan("sub1", "plan_starter")

    def test_upgrade_plan_lower_tier(self):
        sub = PricingSubscription("sub1", "cust1", "plan_starter", seats=3)
        self.engine.create_subscription(sub)
        with self.assertRaises(ValueError):
            self.engine.upgrade_plan("sub1", "plan_free")

    def test_upgrade_plan_exceeds_max_seats(self):
        sub = PricingSubscription("sub1", "cust1", "plan_starter", seats=8)
        self.engine.create_subscription(sub)
        ent_plan = PricingPlan("plan_ent", "Ent", PackageTier.ENTERPRISE, PricingModel.FLAT_RATE, max_seats=5)
        self.engine.create_plan(ent_plan)
        with self.assertRaises(ValueError):
            self.engine.upgrade_plan("sub1", "plan_ent")

    def test_upgrade_plan_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.upgrade_plan("fake", "plan_pro")

    def test_downgrade_plan_success(self):
        sub = PricingSubscription("sub1", "cust1", "plan_pro", seats=3)
        self.engine.create_subscription(sub)
        self.engine.downgrade_plan("sub1", "plan_starter")
        self.assertEqual(self.engine._subscriptions["sub1"].plan_id, "plan_starter")

    def test_downgrade_plan_higher_tier(self):
        sub = PricingSubscription("sub1", "cust1", "plan_starter", seats=3)
        self.engine.create_subscription(sub)
        with self.assertRaises(ValueError):
            self.engine.downgrade_plan("sub1", "plan_pro")

    def test_get_revenue_report_empty(self):
        report = self.engine.get_revenue_report()
        self.assertEqual(report["total_mrr"], 0.0)
        self.assertEqual(report["total_arr"], 0.0)

    def test_get_revenue_report_with_data(self):
        self.engine.create_subscription(PricingSubscription("s1", "c1", "plan_starter", seats=2)) # 20
        self.engine.create_subscription(PricingSubscription("s2", "c2", "plan_pro", seats=1, usage_units=1100)) # 70 + 5 = 75
        
        report = self.engine.get_revenue_report()
        self.assertEqual(report["total_mrr"], 95.0)
        self.assertEqual(report["total_arr"], 1140.0)
        self.assertEqual(report["avg_revenue_per_customer"], 47.5)
        self.assertEqual(report["mrr_by_tier"]["starter"], 20.0)
        self.assertEqual(report["mrr_by_tier"]["professional"], 75.0)
        
    def test_compare_plans(self):
        matrix = self.engine.compare_plans(["plan_starter", "plan_pro"])
        self.assertIn("plan_starter", matrix)
        self.assertIn("plan_pro", matrix)
        
        self.assertTrue(matrix["plan_pro"]["feature_support"]["pro"])
        self.assertFalse(matrix["plan_starter"]["feature_support"]["pro"])

    def test_get_plan_recommendations(self):
        recs = self.engine.get_plan_recommendations(3, 500)
        self.assertEqual(len(recs), 3)
        # Expected costs: Free (0), Starter (30), Pro (50 + 60 = 110)
        self.assertEqual(recs[0]["plan_id"], "plan_free")
        self.assertEqual(recs[1]["plan_id"], "plan_starter")
        self.assertEqual(recs[2]["plan_id"], "plan_pro")
        
    def test_get_plan_recommendations_filters_seats(self):
        recs = self.engine.get_plan_recommendations(8, 500)
        # Free max is 5, so it should be excluded
        self.assertEqual(len(recs), 2)
        self.assertEqual(recs[0]["plan_id"], "plan_starter")

    def test_apply_discount(self):
        sub = PricingSubscription("sub1", "cust1", "plan_starter", seats=10) # 100
        self.engine.create_subscription(sub)
        self.engine.apply_discount("sub1", 15.0)
        self.assertEqual(self.engine._subscriptions["sub1"].discount_pct, 15.0)
        self.assertEqual(self.engine._subscriptions["sub1"].monthly_total, 85.0)
        
    def test_apply_discount_invalid_pct(self):
        sub = PricingSubscription("sub1", "cust1", "plan_starter", seats=10)
        self.engine.create_subscription(sub)
        with self.assertRaises(ValueError):
            self.engine.apply_discount("sub1", 105.0)
        with self.assertRaises(ValueError):
            self.engine.apply_discount("sub1", -10.0)

if __name__ == '__main__':
    unittest.main()

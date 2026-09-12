import datetime
from typing import Dict, List, Optional
from elmos_mature_platform.types import (
    ForecastCostCategory as CostCategory,
    ScenarioType,
    ForecastCostLineItem as CostLineItem,
    CostScenario,
    ForecastCostCategory,
    ForecastCostLineItem,
)

class CostScenarioForecastEngine:
    """Engine for forecasting cost scenarios and analyzing cloud spend."""
    
    def __init__(self) -> None:
        self.line_items: Dict[str, CostLineItem] = {}
        self.scenarios: Dict[str, CostScenario] = {}

    def add_line_item(self, item: CostLineItem) -> str:
        """Add a cost line item to the engine."""
        if item.monthly_cost == 0.0:
            item.monthly_cost = item.unit_cost * item.quantity
        self.line_items[item.item_id] = item
        return item.item_id

    def create_scenario(self, scenario: CostScenario) -> str:
        """Create a new cost scenario."""
        if not scenario.created_at:
            scenario.created_at = datetime.datetime.utcnow().isoformat()
        
        self.scenarios[scenario.scenario_id] = scenario
        self._update_scenario_totals(scenario.scenario_id)
        return scenario.scenario_id

    def add_item_to_scenario(self, scenario_id: str, item_id: str) -> CostScenario:
        """Add a cost line item to a scenario."""
        if scenario_id not in self.scenarios:
            raise ValueError("Scenario not found")
        if item_id not in self.line_items:
            raise ValueError("Item not found")
            
        scenario = self.scenarios[scenario_id]
        if item_id not in scenario.line_items:
            scenario.line_items.append(item_id)
            self._update_scenario_totals(scenario_id)
        return scenario

    def _update_scenario_totals(self, scenario_id: str) -> None:
        """Update total monthly and annual costs for a scenario."""
        scenario = self.scenarios[scenario_id]
        total_monthly = 0.0
        for item_id in scenario.line_items:
            if item_id in self.line_items:
                total_monthly += self.line_items[item_id].monthly_cost
        
        scenario.total_monthly = total_monthly
        scenario.total_annual = total_monthly * 12

    def forecast(self, scenario_id: str, months: int = 12) -> List[Dict]:
        """Generate a monthly forecast for a scenario over a given number of months."""
        if scenario_id not in self.scenarios:
            raise ValueError("Scenario not found")
            
        scenario = self.scenarios[scenario_id]
        forecast_data = []
        
        for month in range(1, months + 1):
            month_cost = 0.0
            for item_id in scenario.line_items:
                if item_id in self.line_items:
                    item = self.line_items[item_id]
                    growth = (1 + item.growth_rate_pct / 100) ** month
                    month_cost += item.monthly_cost * growth
            forecast_data.append({
                "month": month,
                "total_cost": month_cost
            })
            
        return forecast_data

    def get_total_cost(self, scenario_id: str) -> float:
        """Get the total monthly cost for a scenario."""
        if scenario_id not in self.scenarios:
            raise ValueError("Scenario not found")
        scenario = self.scenarios[scenario_id]
        return scenario.total_monthly

    def compare_scenarios(self, scenario_ids: List[str]) -> Dict:
        """Compare multiple scenarios side-by-side."""
        comparison = {}
        for s_id in scenario_ids:
            if s_id in self.scenarios:
                scenario = self.scenarios[s_id]
                comparison[s_id] = {
                    "total_monthly": scenario.total_monthly,
                    "total_annual": scenario.total_annual
                }
        return comparison

    def get_cost_by_category(self, scenario_id: str) -> Dict[str, float]:
        """Get a breakdown of costs by category for a scenario."""
        if scenario_id not in self.scenarios:
            raise ValueError("Scenario not found")
            
        scenario = self.scenarios[scenario_id]
        breakdown = {category.value: 0.0 for category in CostCategory}
        
        for item_id in scenario.line_items:
            if item_id in self.line_items:
                item = self.line_items[item_id]
                if item.category.value not in breakdown:
                    breakdown[item.category.value] = 0.0
                breakdown[item.category.value] += item.monthly_cost
                
        return breakdown

    def get_savings_from_optimization(self, baseline_id: str, optimized_id: str) -> Dict:
        """Calculate savings from an optimized scenario compared to a baseline."""
        if baseline_id not in self.scenarios or optimized_id not in self.scenarios:
            raise ValueError("Scenario not found")
            
        baseline_cost = self.scenarios[baseline_id].total_monthly
        optimized_cost = self.scenarios[optimized_id].total_monthly
        
        diff = baseline_cost - optimized_cost
        pct = (diff / baseline_cost * 100) if baseline_cost > 0 else 0.0
        
        return {
            "baseline_monthly": baseline_cost,
            "optimized_monthly": optimized_cost,
            "monthly_savings": diff,
            "annual_savings": diff * 12,
            "savings_pct": pct
        }

    def get_top_cost_drivers(self, scenario_id: str, top_n: int = 5) -> List[CostLineItem]:
        """Get the highest cost items in a scenario."""
        if scenario_id not in self.scenarios:
            raise ValueError("Scenario not found")
            
        scenario = self.scenarios[scenario_id]
        items = []
        for item_id in scenario.line_items:
            if item_id in self.line_items:
                items.append(self.line_items[item_id])
                
        items.sort(key=lambda x: x.monthly_cost, reverse=True)
        return items[:top_n]

    def project_break_even(self, scenario_a: str, scenario_b: str) -> Optional[int]:
        """Project the month where scenario B becomes cheaper than scenario A."""
        if scenario_a not in self.scenarios or scenario_b not in self.scenarios:
            raise ValueError("Scenario not found")
            
        MAX_MONTHS = 120
        for month in range(1, MAX_MONTHS + 1):
            cost_a = 0.0
            for item_id in self.scenarios[scenario_a].line_items:
                if item_id in self.line_items:
                    item = self.line_items[item_id]
                    cost_a += item.monthly_cost * ((1 + item.growth_rate_pct / 100) ** month)
                    
            cost_b = 0.0
            for item_id in self.scenarios[scenario_b].line_items:
                if item_id in self.line_items:
                    item = self.line_items[item_id]
                    cost_b += item.monthly_cost * ((1 + item.growth_rate_pct / 100) ** month)
                    
            if cost_b < cost_a:
                return month
                
        return None

    def get_forecast_report(self, scenario_id: str) -> Dict:
        """Generate a full forecast report for a scenario."""
        if scenario_id not in self.scenarios:
            raise ValueError("Scenario not found")
            
        scenario = self.scenarios[scenario_id]
        return {
            "scenario_id": scenario.scenario_id,
            "name": scenario.name,
            "type": scenario.scenario_type.value,
            "total_monthly": scenario.total_monthly,
            "total_annual": scenario.total_annual,
            "cost_by_category": self.get_cost_by_category(scenario_id),
            "top_cost_drivers": [item.item_id for item in self.get_top_cost_drivers(scenario_id)],
            "forecast_12m": self.forecast(scenario_id, months=12)
        }

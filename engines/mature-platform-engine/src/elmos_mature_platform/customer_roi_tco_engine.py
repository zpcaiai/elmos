import datetime
from typing import Dict, List, Optional
from elmos_mature_platform.types import (
    RoiAnalysis, TcoCostItem, ValueItem, TcoComparison, CostDriver, ValueDriver
)

class CustomerRoiTcoEngine:
    """
    Engine for calculating Customer Return on Investment (ROI) and Total Cost of Ownership (TCO).
    """

    def __init__(self):
        self._analyses: Dict[str, RoiAnalysis] = {}
        self._cost_items: Dict[str, List[TcoCostItem]] = {}
        self._value_items: Dict[str, List[ValueItem]] = {}

    def create_analysis(self, analysis: RoiAnalysis) -> str:
        """Create a new ROI analysis."""
        if not analysis.analysis_id:
            raise ValueError("analysis_id is required")
        if not analysis.created_at:
            analysis.created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        self._analyses[analysis.analysis_id] = analysis
        self._cost_items[analysis.analysis_id] = []
        self._value_items[analysis.analysis_id] = []
        return analysis.analysis_id

    def add_cost_item(self, analysis_id: str, item: TcoCostItem) -> None:
        """Add a cost item to the analysis."""
        if analysis_id not in self._analyses:
            raise KeyError(f"Analysis {analysis_id} not found")
        self._cost_items[analysis_id].append(item)

    def add_value_item(self, analysis_id: str, item: ValueItem) -> None:
        """Add a value item to the analysis."""
        if analysis_id not in self._analyses:
            raise KeyError(f"Analysis {analysis_id} not found")
        self._value_items[analysis_id].append(item)

    def compute_tco(self, analysis_id: str) -> float:
        """Compute the Total Cost of Ownership."""
        if analysis_id not in self._analyses:
            raise KeyError(f"Analysis {analysis_id} not found")
        
        analysis = self._analyses[analysis_id]
        total_cost = 0.0
        
        for item in self._cost_items[analysis_id]:
            if item.recurring:
                total_cost += item.amount * analysis.period_years
            else:
                total_cost += item.amount
                
        analysis.total_cost = total_cost
        return total_cost

    def compute_roi(self, analysis_id: str) -> RoiAnalysis:
        """Compute ROI and populate the analysis object."""
        if analysis_id not in self._analyses:
            raise KeyError(f"Analysis {analysis_id} not found")
            
        analysis = self._analyses[analysis_id]
        
        total_cost = self.compute_tco(analysis_id)
        
        total_value = 0.0
        for item in self._value_items[analysis_id]:
            # Simple assumption: full annual value for the period
            total_value += item.annual_value * analysis.period_years
            
        analysis.total_value = total_value
        analysis.net_value = total_value - total_cost
        
        if total_cost > 0:
            analysis.roi_percentage = (analysis.net_value / total_cost) * 100.0
        else:
            analysis.roi_percentage = 0.0
            
        analysis.payback_months = self.compute_payback_period(analysis_id)
        analysis.npv = self.compute_npv(analysis_id)
        analysis.risk_adjusted_roi = self.compute_risk_adjusted_roi(analysis_id)
        
        return analysis

    def compute_risk_adjusted_roi(self, analysis_id: str) -> float:
        """Compute ROI with value item confidence levels applied."""
        if analysis_id not in self._analyses:
            raise KeyError(f"Analysis {analysis_id} not found")
            
        analysis = self._analyses[analysis_id]
        total_cost = self.compute_tco(analysis_id)
        
        risk_adjusted_value = 0.0
        for item in self._value_items[analysis_id]:
            risk_adjusted_value += (item.annual_value * item.confidence) * analysis.period_years
            
        if total_cost > 0:
            return ((risk_adjusted_value - total_cost) / total_cost) * 100.0
        return 0.0

    def compute_payback_period(self, analysis_id: str) -> float:
        """Compute payback period in months."""
        if analysis_id not in self._analyses:
            raise KeyError(f"Analysis {analysis_id} not found")
            
        total_cost = self.compute_tco(analysis_id)
        
        annual_value = 0.0
        for item in self._value_items[analysis_id]:
            annual_value += item.annual_value
            
        if annual_value > 0:
            return total_cost / (annual_value / 12.0)
        return float('inf')

    def compute_npv(self, analysis_id: str, discount_rate: float = 0.1) -> float:
        """Compute Net Present Value."""
        if analysis_id not in self._analyses:
            raise KeyError(f"Analysis {analysis_id} not found")
            
        analysis = self._analyses[analysis_id]
        npv = 0.0
        
        # Initial year (0) cash flows (one-time costs)
        year_0_cash_flow = 0.0
        for item in self._cost_items[analysis_id]:
            if not item.recurring:
                year_0_cash_flow -= item.amount
        npv += year_0_cash_flow
        
        # Subsequent years cash flows
        for year in range(1, analysis.period_years + 1):
            yearly_cash_flow = 0.0
            
            # Recurring costs
            for cost_item in self._cost_items[analysis_id]:
                if cost_item.recurring:
                    yearly_cash_flow -= cost_item.amount
                    
            # Value realized
            for value_item in self._value_items[analysis_id]:
                # Factor in realization month. If realization > year*12, 0 value.
                # Simplistic implementation: full value if year > realization_month/12
                # But let's simplify and just assume annual value for simplicity 
                # or partial for the first year.
                if value_item.realization_month <= year * 12:
                    yearly_cash_flow += value_item.annual_value
                    
            npv += yearly_cash_flow / ((1 + discount_rate) ** year)
            
        return npv

    def compare_tco(self, analysis_id: str, current_costs: List[TcoCostItem]) -> TcoComparison:
        """Compare current costs vs proposed (elmos) costs."""
        if analysis_id not in self._analyses:
            raise KeyError(f"Analysis {analysis_id} not found")
            
        analysis = self._analyses[analysis_id]
        proposed_tco = self.compute_tco(analysis_id)
        
        current_tco = 0.0
        for item in current_costs:
            if item.recurring:
                current_tco += item.amount * analysis.period_years
            else:
                current_tco += item.amount
                
        savings = current_tco - proposed_tco
        savings_perc = (savings / current_tco * 100.0) if current_tco > 0 else 0.0
        
        return TcoComparison(
            current_state="current",
            proposed_state="elmos",
            current_tco=current_tco,
            proposed_tco=proposed_tco,
            savings=savings,
            savings_percentage=savings_perc
        )

    def get_cost_breakdown(self, analysis_id: str) -> Dict[str, float]:
        """Get cost breakdown by driver."""
        if analysis_id not in self._analyses:
            raise KeyError(f"Analysis {analysis_id} not found")
            
        analysis = self._analyses[analysis_id]
        breakdown = {driver.value: 0.0 for driver in CostDriver}
        
        for item in self._cost_items[analysis_id]:
            amount = item.amount * analysis.period_years if item.recurring else item.amount
            breakdown[item.driver.value] += amount
            
        return {k: v for k, v in breakdown.items() if v > 0}

    def get_value_breakdown(self, analysis_id: str) -> Dict[str, float]:
        """Get value breakdown by driver."""
        if analysis_id not in self._analyses:
            raise KeyError(f"Analysis {analysis_id} not found")
            
        analysis = self._analyses[analysis_id]
        breakdown = {driver.value: 0.0 for driver in ValueDriver}
        
        for item in self._value_items[analysis_id]:
            breakdown[item.driver.value] += item.annual_value * analysis.period_years
            
        return {k: v for k, v in breakdown.items() if v > 0}

    def get_executive_summary(self, analysis_id: str) -> Dict:
        """Get executive summary for presentation."""
        if analysis_id not in self._analyses:
            raise KeyError(f"Analysis {analysis_id} not found")
            
        analysis = self.compute_roi(analysis_id)
        
        return {
            "customer_name": analysis.customer_name,
            "period_years": analysis.period_years,
            "total_tco": analysis.total_cost,
            "total_value": analysis.total_value,
            "net_value": analysis.net_value,
            "roi_percentage": analysis.roi_percentage,
            "risk_adjusted_roi": analysis.risk_adjusted_roi,
            "payback_months": analysis.payback_months,
            "npv": analysis.npv,
            "cost_breakdown": self.get_cost_breakdown(analysis_id),
            "value_breakdown": self.get_value_breakdown(analysis_id)
        }

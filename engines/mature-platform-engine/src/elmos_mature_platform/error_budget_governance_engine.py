import time
from typing import Dict, List, Optional
from datetime import datetime, timedelta

from elmos_mature_platform.types import (
    ErrorBudgetSlo,
    BurnRateAlert,
    BurnRateWindow,
    ReleaseFreezeDecision,
    ReleaseFreezeAction,
    ErrorBudgetWaiver
)

class ErrorBudgetGovernanceEngine:
    """
    Error Budget Governance Engine for managing SLOs, computing burn rates, 
    evaluating release gates, and managing emergency waivers.
    """
    def __init__(self):
        self._slos: Dict[str, ErrorBudgetSlo] = {}
        self._waivers: Dict[str, ErrorBudgetWaiver] = {}
        # Stores (timestamp, error_count, total_requests)
        self._events: Dict[str, List[tuple]] = {}
    
    def register_slo(self, slo: ErrorBudgetSlo):
        """Registers an SLO for a service."""
        self._slos[slo.slo_id] = slo
        if slo.slo_id not in self._events:
            self._events[slo.slo_id] = []
            
    def record_error_event(self, slo_id: str, error_count: int, total_requests: int):
        """Records error events and updates budget consumption."""
        if slo_id not in self._slos:
            raise ValueError(f"SLO {slo_id} not found")
        
        if total_requests < error_count:
            raise ValueError("total_requests cannot be less than error_count")
            
        self._events[slo_id].append((time.time(), error_count, total_requests))
        
        # Simplistic budget update based on events
        slo = self._slos[slo_id]
        error_budget_total = (100.0 - slo.target) / 100.0
        
        # Total errors and requests in the window
        # In a real system, we would prune old events outside window_days
        total_err = sum(e for _, e, _ in self._events[slo_id])
        total_req = sum(t for _, _, t in self._events[slo_id])
        
        if total_req > 0:
            current_error_rate = total_err / total_req
            # How much of the error budget have we consumed?
            consumed_ratio = current_error_rate / error_budget_total
            slo.consumed_budget_pct = min(100.0, consumed_ratio * 100.0)
            slo.budget_remaining_pct = max(0.0, 100.0 - slo.consumed_budget_pct)
            
    def _get_window_seconds(self, window: BurnRateWindow) -> float:
        mapping = {
            BurnRateWindow.ONE_HOUR: 3600,
            BurnRateWindow.SIX_HOURS: 3600 * 6,
            BurnRateWindow.ONE_DAY: 86400,
            BurnRateWindow.SEVEN_DAYS: 86400 * 7,
            BurnRateWindow.THIRTY_DAYS: 86400 * 30
        }
        return mapping[window]
        
    def compute_burn_rate(self, slo_id: str, window: BurnRateWindow) -> BurnRateAlert:
        """Calculates burn rate in specified window."""
        if slo_id not in self._slos:
            raise ValueError(f"SLO {slo_id} not found")
            
        slo = self._slos[slo_id]
        window_sec = self._get_window_seconds(window)
        now = time.time()
        
        window_events = [e for e in self._events[slo_id] if now - e[0] <= window_sec]
        
        total_err = sum(e for _, e, _ in window_events)
        total_req = sum(t for _, _, t in window_events)
        
        error_budget_total = (100.0 - slo.target) / 100.0
        
        if total_req == 0 or error_budget_total == 0:
            burn_rate = 0.0
        else:
            actual_error_rate = total_err / total_req
            # Burn rate is how fast we are consuming budget compared to allowed rate
            burn_rate = actual_error_rate / error_budget_total
            
        severity = "log"
        if window == BurnRateWindow.ONE_HOUR and burn_rate > 14.4:
            severity = "page"
        elif burn_rate > 6.0:
            severity = "ticket"
            
        proj_hours = 0.0
        if burn_rate > 0:
            remaining_ratio = slo.budget_remaining_pct / 100.0
            window_hours = window_sec / 3600
            total_budget_exhaustion_time = window_hours / burn_rate
            proj_hours = remaining_ratio * (slo.window_days * 24) / burn_rate
            
        return BurnRateAlert(
            slo_id=slo_id,
            window=window,
            burn_rate=burn_rate,
            remaining_budget_pct=slo.budget_remaining_pct,
            alert_severity=severity,
            projected_exhaustion_hours=proj_hours
        )
        
    def get_remaining_budget(self, slo_id: str) -> float:
        """Remaining budget percentage."""
        if slo_id not in self._slos:
            raise ValueError(f"SLO {slo_id} not found")
        return self._slos[slo_id].budget_remaining_pct
        
    def evaluate_release_gate(self, service_name: str) -> ReleaseFreezeDecision:
        """FREEZE if budget < 10%, WARN if < 30%, ALLOW otherwise."""
        # Find minimum budget across all SLOs for this service
        service_slos = [s for s in self._slos.values() if s.service_name == service_name]
        if not service_slos:
            return ReleaseFreezeDecision(
                service_name=service_name,
                action=ReleaseFreezeAction.ALLOW,
                reason="No SLOs found, releasing allowed",
                remaining_budget_pct=100.0
            )
            
        min_budget = min(s.budget_remaining_pct for s in service_slos)
        
        # Check active waivers
        active_waiver = None
        now_str = datetime.utcnow().isoformat()
        for w in self._waivers.values():
            if w.service_name == service_name and w.expires_at > now_str and w.deploys_used < w.max_deploys:
                active_waiver = w.waiver_id
                break
                
        if min_budget < 10.0:
            if active_waiver:
                return ReleaseFreezeDecision(
                    service_name=service_name,
                    action=ReleaseFreezeAction.ALLOW,
                    reason="Budget exhausted but active waiver found",
                    remaining_budget_pct=min_budget,
                    override_allowed=True,
                    waiver_id=active_waiver
                )
            return ReleaseFreezeDecision(
                service_name=service_name,
                action=ReleaseFreezeAction.FREEZE,
                reason="Budget remaining < 10%, mandatory freeze",
                remaining_budget_pct=min_budget
            )
        elif min_budget < 30.0:
            return ReleaseFreezeDecision(
                service_name=service_name,
                action=ReleaseFreezeAction.WARN,
                reason="Budget remaining < 30%, proceed with caution",
                remaining_budget_pct=min_budget
            )
            
        return ReleaseFreezeDecision(
            service_name=service_name,
            action=ReleaseFreezeAction.ALLOW,
            reason="Sufficient budget remaining",
            remaining_budget_pct=min_budget
        )
        
    def grant_waiver(self, waiver: ErrorBudgetWaiver):
        """Emergency waiver allowing deploy despite budget exhaustion."""
        now_str = datetime.utcnow().isoformat()
        if waiver.expires_at <= now_str:
            raise ValueError("Cannot grant expired waiver")
        self._waivers[waiver.waiver_id] = waiver
        
    def use_waiver(self, service_name: str) -> bool:
        """Consume one deploy from waiver, fail if no valid waiver or all used."""
        now_str = datetime.utcnow().isoformat()
        valid_waivers = [w for w in self._waivers.values() 
                         if w.service_name == service_name 
                         and w.expires_at > now_str 
                         and w.deploys_used < w.max_deploys]
                         
        if not valid_waivers:
            return False
            
        # Use the first valid waiver
        valid_waivers[0].deploys_used += 1
        return True
        
    def get_multi_window_burn_rates(self, slo_id: str) -> List[BurnRateAlert]:
        """Burn rates across all windows."""
        return [self.compute_burn_rate(slo_id, w) for w in BurnRateWindow]
        
    def get_budget_forecast(self, slo_id: str, days_ahead: int) -> Dict:
        """Project when budget will exhaust at current rate."""
        if slo_id not in self._slos:
            raise ValueError(f"SLO {slo_id} not found")
            
        # Use 1d burn rate for forecasting
        alert = self.compute_burn_rate(slo_id, BurnRateWindow.ONE_DAY)
        exhausts_in_hours = alert.projected_exhaustion_hours
        
        will_exhaust = exhausts_in_hours > 0 and exhausts_in_hours < (days_ahead * 24)
        
        return {
            "slo_id": slo_id,
            "current_remaining_pct": alert.remaining_budget_pct,
            "1d_burn_rate": alert.burn_rate,
            "projected_exhaustion_hours": exhausts_in_hours,
            "exhausts_within_forecast": will_exhaust
        }
        
    def get_governance_report(self) -> Dict:
        """Summary: services, budgets, frozen services, active waivers."""
        services = set(s.service_name for s in self._slos.values())
        
        budgets = {s_id: s.budget_remaining_pct for s_id, s in self._slos.items()}
        
        frozen_services = []
        for svc in services:
            decision = self.evaluate_release_gate(svc)
            if decision.action == ReleaseFreezeAction.FREEZE:
                frozen_services.append(svc)
                
        now_str = datetime.utcnow().isoformat()
        active_waivers = [w.waiver_id for w in self._waivers.values() 
                          if w.expires_at > now_str and w.deploys_used < w.max_deploys]
                          
        return {
            "services_tracked": list(services),
            "budgets_remaining_pct": budgets,
            "frozen_services": frozen_services,
            "active_waivers": active_waivers
        }

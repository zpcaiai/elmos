from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Set

from elmos_mature_platform.types import (
    IncidentSeverity, IncidentStatus, EscalationTier, OnCallShift,
    OnCallEngineer, IncidentRecord, StatusPageUpdate, ServiceCatalogEntry,
    ChangeFreeze, CapacityPlan, RegionId
)

class IncidentCommandEngine:
    def __init__(self):
        self.incidents: Dict[str, IncidentRecord] = {}
        self.roster: List[OnCallEngineer] = []
        self.catalog: Dict[str, ServiceCatalogEntry] = {}
        self.change_freezes: Dict[str, ChangeFreeze] = {}
        self.capacity_plans: Dict[str, CapacityPlan] = {}

    def register_oncall_engineer(self, engineer: OnCallEngineer) -> None:
        """Add an engineer to the on-call roster."""
        self.roster.append(engineer)

    def get_active_oncall(self, shift: OnCallShift, tier: EscalationTier) -> Optional[OnCallEngineer]:
        """Find an available engineer for the given shift and tier."""
        for engineer in self.roster:
            if engineer.shift == shift and engineer.tier == tier and engineer.is_available:
                if engineer.current_incident_count < engineer.max_concurrent_incidents:
                    return engineer
        return None

    def declare_incident(
        self, incident_id: str, title: str, severity: IncidentSeverity,
        declaring_user: str, tenant_id: str, affected_regions: List[RegionId]
    ) -> IncidentRecord:
        """Create an incident, auto-assign a commander, and record an initial status update."""
        declared_at = datetime.now(timezone.utc).isoformat()
        
        hour = datetime.now(timezone.utc).hour
        if 0 <= hour < 8:
            current_shift = OnCallShift.APAC
        elif 8 <= hour < 16:
            current_shift = OnCallShift.EMEA
        else:
            current_shift = OnCallShift.AMERICAS
            
        commander = self.get_active_oncall(current_shift, EscalationTier.TIER_1)
        commander_id = commander.engineer_id if commander else None
        if commander:
            commander.current_incident_count += 1
            
        incident = IncidentRecord(
            incident_id=incident_id,
            title=title,
            severity=severity,
            status=IncidentStatus.DECLARED,
            declared_at=declared_at,
            declaring_user=declaring_user,
            tenant_id=tenant_id,
            affected_regions=affected_regions,
            assigned_commander=commander_id,
        )
        incident.status_updates.append({
            "timestamp": declared_at,
            "status": IncidentStatus.DECLARED.value,
            "message": "Incident declared"
        })
        self.incidents[incident_id] = incident
        return incident

    def escalate_incident(self, incident_id: str, reason: str) -> EscalationTier:
        """Escalate an incident to the next tier."""
        incident = self.incidents[incident_id]
        
        if incident.assigned_commander:
            current_commander = next((e for e in self.roster if e.engineer_id == incident.assigned_commander), None)
            if current_commander:
                current_commander.current_incident_count -= 1
                current_tier = current_commander.tier
                current_shift = current_commander.shift
            else:
                current_tier = EscalationTier.TIER_1
                current_shift = OnCallShift.APAC
        else:
            current_tier = EscalationTier.TIER_1
            current_shift = OnCallShift.APAC
            
        if current_tier == EscalationTier.TIER_1:
            next_tier = EscalationTier.TIER_2
        elif current_tier == EscalationTier.TIER_2:
            next_tier = EscalationTier.TIER_3
        elif current_tier == EscalationTier.TIER_3:
            next_tier = EscalationTier.MANAGEMENT
        else:
            raise ValueError("Cannot escalate past MANAGEMENT tier")
            
        new_commander = self.get_active_oncall(current_shift, next_tier)
        new_commander_id = new_commander.engineer_id if new_commander else None
        if new_commander:
            new_commander.current_incident_count += 1
            
        incident.assigned_commander = new_commander_id
        timestamp = datetime.now(timezone.utc).isoformat()
        incident.escalation_log.append({
            "timestamp": timestamp,
            "from_tier": current_tier.value,
            "to_tier": next_tier.value,
            "reason": reason
        })
        return next_tier

    def update_incident_status(self, incident_id: str, new_status: IncidentStatus, message: str) -> IncidentRecord:
        """Transition the status of an incident with validation."""
        incident = self.incidents[incident_id]
        
        valid_transitions = {
            IncidentStatus.DECLARED: [IncidentStatus.TRIAGING],
            IncidentStatus.TRIAGING: [IncidentStatus.MITIGATING],
            IncidentStatus.MITIGATING: [IncidentStatus.RESOLVED],
            IncidentStatus.RESOLVED: [IncidentStatus.POST_MORTEM, IncidentStatus.CLOSED],
            IncidentStatus.POST_MORTEM: [IncidentStatus.CLOSED],
            IncidentStatus.CLOSED: []
        }
        
        if new_status not in valid_transitions.get(incident.status, []):
            raise ValueError(f"Invalid transition from {incident.status} to {new_status}")
            
        incident.status = new_status
        timestamp = datetime.now(timezone.utc).isoformat()
        incident.status_updates.append({
            "timestamp": timestamp,
            "status": new_status.value,
            "message": message
        })
        return incident

    def resolve_incident(self, incident_id: str, root_cause: str) -> IncidentRecord:
        """Resolve an incident and set its root cause."""
        incident = self.incidents[incident_id]
        incident.status = IncidentStatus.RESOLVED
        timestamp = datetime.now(timezone.utc).isoformat()
        incident.resolved_at = timestamp
        incident.root_cause = root_cause
        incident.status_updates.append({
            "timestamp": timestamp,
            "status": IncidentStatus.RESOLVED.value,
            "message": "Incident resolved"
        })
        
        if incident.assigned_commander:
            current_commander = next((e for e in self.roster if e.engineer_id == incident.assigned_commander), None)
            if current_commander:
                current_commander.current_incident_count -= 1
                
        return incident

    def generate_status_page_update(self, incident_id: str, component: str, message: str) -> StatusPageUpdate:
        """Create a customer-facing update and mark communication as sent."""
        incident = self.incidents[incident_id]
        incident.customer_communication_sent = True
        
        status_map = {
            IncidentStatus.DECLARED: "major_outage",
            IncidentStatus.TRIAGING: "major_outage",
            IncidentStatus.MITIGATING: "degraded_performance",
            IncidentStatus.RESOLVED: "operational",
            IncidentStatus.POST_MORTEM: "operational",
            IncidentStatus.CLOSED: "operational"
        }
        
        return StatusPageUpdate(
            update_id=f"upd_{int(datetime.now(timezone.utc).timestamp())}",
            incident_id=incident_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            component=component,
            status=status_map.get(incident.status, "operational"),
            message=message
        )

    def register_service(self, entry: ServiceCatalogEntry) -> None:
        """Register a service in the catalog."""
        self.catalog[entry.service_id] = entry

    def get_service_dependencies(self, service_id: str) -> List[str]:
        """Return the transitive dependency graph (BFS) of a service."""
        visited = set()
        queue = [service_id]
        
        while queue:
            current = queue.pop(0)
            if current not in visited:
                visited.add(current)
                if current in self.catalog:
                    queue.extend(self.catalog[current].dependencies)
                    
        if service_id in visited:
            visited.remove(service_id)
        return list(visited)

    def create_change_freeze(self, freeze_id: str, reason: str, duration_hours: int, scope: str, approved_by: str) -> ChangeFreeze:
        """Create and register a change freeze."""
        start = datetime.now(timezone.utc)
        end = start + timedelta(hours=duration_hours)
        
        freeze = ChangeFreeze(
            freeze_id=freeze_id,
            reason=reason,
            started_at=start.isoformat(),
            ends_at=end.isoformat(),
            scope=scope,
            approved_by=approved_by,
        )
        self.change_freezes[freeze_id] = freeze
        return freeze

    def is_change_allowed(self, service_id: str) -> Tuple[bool, Optional[str]]:
        """Check if any active freeze blocks changes for this service."""
        for freeze_id, freeze in self.change_freezes.items():
            if not freeze.is_active:
                continue
            if freeze.scope == "global" or freeze.scope == service_id:
                if service_id not in freeze.exceptions:
                    return False, freeze_id
        return True, None

    def create_capacity_plan(self, plan: CapacityPlan) -> None:
        """Register a capacity plan."""
        self.capacity_plans[plan.plan_id] = plan

    def evaluate_autoscale(self, service_id: str, region: RegionId, current_cpu: float, current_memory: float) -> Tuple[str, int]:
        """Return autoscale decision based on thresholds."""
        for plan in self.capacity_plans.values():
            if plan.service_id == service_id and plan.region == region:
                if current_cpu > plan.target_cpu_percent:
                    new_count = min(plan.current_replicas + 1, plan.max_replicas)
                    if new_count != plan.current_replicas:
                        plan.current_replicas = new_count
                        return 'scale_up', new_count
                elif current_cpu < plan.target_cpu_percent * 0.5:
                    new_count = max(plan.current_replicas - 1, plan.min_replicas)
                    if new_count != plan.current_replicas:
                        plan.current_replicas = new_count
                        return 'scale_down', new_count
                return 'no_change', plan.current_replicas
        return 'no_change', 0

    def get_incident_timeline(self, incident_id: str) -> List[Dict[str, str]]:
        """Return chronological list of all status updates + escalation events."""
        incident = self.incidents[incident_id]
        events = []
        for update in incident.status_updates:
            e = dict(update)
            e["type"] = "status_update"
            events.append(e)
        for esc in incident.escalation_log:
            e = dict(esc)
            e["type"] = "escalation"
            events.append(e)
            
        events.sort(key=lambda x: x["timestamp"])
        return events

    def compute_mttr(self) -> Dict[str, float]:
        """Mean time to resolve by severity for RESOLVED/CLOSED incidents."""
        mttr_by_sev = {}
        counts = {}
        
        for inc in self.incidents.values():
            if inc.status in [IncidentStatus.RESOLVED, IncidentStatus.CLOSED] and inc.resolved_at:
                start = datetime.fromisoformat(inc.declared_at)
                end = datetime.fromisoformat(inc.resolved_at)
                diff_seconds = (end - start).total_seconds()
                sev = inc.severity.value
                mttr_by_sev[sev] = mttr_by_sev.get(sev, 0.0) + diff_seconds
                counts[sev] = counts.get(sev, 0) + 1
                
        for sev in mttr_by_sev:
            mttr_by_sev[sev] /= counts[sev]
            
        return mttr_by_sev

    def get_active_incidents(self) -> List[IncidentRecord]:
        """Return all non-CLOSED incidents."""
        return [inc for inc in self.incidents.values() if inc.status != IncidentStatus.CLOSED]

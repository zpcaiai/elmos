import uuid
import datetime
from typing import Dict, List, Optional
from elmos_mature_platform.physical.cloud_vendor import CloudVendorControlPlaneDriver
from elmos_mature_platform.types import (
    RegionConfig,
    RegionHealthStatus,
    FailoverEvent,
    FailoverTrigger,
    TrafficShift,
    FailoverMode
)

class MultiregionFailoverEngine:
    """Engine for managing multiregion failover and traffic shifting."""
    
    def __init__(
        self,
        replication_lag_threshold_ms: float = 1000.0,
        cloud_driver: Optional[CloudVendorControlPlaneDriver] = None,
    ):
        self._regions: Dict[str, RegionConfig] = {}
        self._failover_events: Dict[str, FailoverEvent] = {}
        self._traffic_shifts: Dict[str, TrafficShift] = {}
        self._replication_lag_threshold_ms = replication_lag_threshold_ms
        self._cloud = cloud_driver or CloudVendorControlPlaneDriver.from_env()
        self._physical_receipts: List[Dict] = []

    def register_region(self, config: RegionConfig) -> None:
        """Register a region in the mesh."""
        self._regions[config.region_id] = config

    def update_health(self, region_id: str, status: RegionHealthStatus, replication_lag_ms: float) -> None:
        """Update region health."""
        if region_id not in self._regions:
            raise ValueError(f"Region {region_id} not found")
        self._regions[region_id].health_status = status
        self._regions[region_id].replication_lag_ms = replication_lag_ms
        self._regions[region_id].last_health_check = datetime.datetime.now(datetime.timezone.utc).isoformat()

    def get_region_status(self, region_id: str) -> RegionConfig:
        """Get current region state."""
        if region_id not in self._regions:
            raise ValueError(f"Region {region_id} not found")
        return self._regions[region_id]

    def initiate_failover(self, source: str, target: str, trigger: FailoverTrigger) -> FailoverEvent:
        """Start failover, validate target is healthy, shift traffic, track RTO."""
        if source not in self._regions or target not in self._regions:
            raise ValueError("Source or target region not found")
        
        target_region = self._regions[target]
        source_region = self._regions[source]
        
        if target_region.health_status not in [RegionHealthStatus.HEALTHY, RegionHealthStatus.DEGRADED]:
            raise ValueError(f"Cannot failover to region with status {target_region.health_status}")
            
        if target_region.data_residency_zone != source_region.data_residency_zone:
             raise ValueError("Data residency zone mismatch blocks cross-zone failover")
             
        if trigger == FailoverTrigger.AUTOMATIC and target_region.replication_lag_ms > self._replication_lag_threshold_ms:
            raise ValueError(f"Replication lag {target_region.replication_lag_ms} exceeds threshold {self._replication_lag_threshold_ms}")

        event_id = str(uuid.uuid4())
        event = FailoverEvent(
            event_id=event_id,
            source_region=source,
            target_region=target,
            trigger=trigger,
            started_at=datetime.datetime.now(datetime.timezone.utc).isoformat()
        )
        self._failover_events[event_id] = event
        
        # Shift all traffic from source to target
        target_region.traffic_weight += source_region.traffic_weight
        source_region.traffic_weight = 0.0
        shift = self._cloud.shift_traffic(source_region=source, target_region=target)
        self._physical_receipts.append(shift.to_dict())
        event.dns_propagation_complete = shift.applied
        
        return event

    def complete_failover(self, event_id: str, success: bool, rpo_bytes: int) -> FailoverEvent:
        """Complete failover, update primary/traffic weights."""
        if event_id not in self._failover_events:
            raise ValueError("Event not found")
            
        event = self._failover_events[event_id]
        event.completed_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        event.success = success
        event.rpo_data_loss_bytes = rpo_bytes
        
        # Calculate mock RTO
        started = datetime.datetime.fromisoformat(event.started_at)
        completed = datetime.datetime.fromisoformat(event.completed_at)
        event.rto_seconds = (completed - started).total_seconds()
        
        if success:
             self._regions[event.source_region].is_primary = False
             self._regions[event.target_region].is_primary = True
             event.dns_propagation_complete = True
             
        self._normalize_weights()
        
        return event

    def rollback_failover(self, event_id: str) -> FailoverEvent:
        """Rollback to original primary."""
        if event_id not in self._failover_events:
            raise ValueError("Event not found")
            
        event = self._failover_events[event_id]
        if not event.rollback_available:
            raise ValueError("Rollback not available for this event")
            
        source = self._regions[event.source_region]
        target = self._regions[event.target_region]
        
        source.is_primary = True
        target.is_primary = False
        
        source.traffic_weight += target.traffic_weight
        target.traffic_weight = 0.0
        
        event.success = False
        event.rollback_available = False
        
        self._normalize_weights()
        
        return event

    def shift_traffic(self, from_region: str, to_region: str, percentage: float) -> TrafficShift:
        """Gradual traffic shifting for canary failover."""
        if from_region not in self._regions or to_region not in self._regions:
             raise ValueError("Regions not found")
             
        if percentage < 0 or percentage > 100:
             raise ValueError("Percentage must be between 0 and 100")
             
        source = self._regions[from_region]
        target = self._regions[to_region]
        
        amount_to_shift = (percentage / 100.0) * source.traffic_weight
        source.traffic_weight -= amount_to_shift
        target.traffic_weight += amount_to_shift
        
        self._normalize_weights()
        
        shift_id = str(uuid.uuid4())
        shift = TrafficShift(
             shift_id=shift_id,
             from_region=from_region,
             to_region=to_region,
             percentage=percentage,
             reason="manual shift",
             started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
             completed=True
        )
        self._traffic_shifts[shift_id] = shift
        return shift

    def get_active_regions(self) -> List[RegionConfig]:
        """All healthy/degraded regions."""
        return [
             r for r in self._regions.values() 
             if r.health_status in (RegionHealthStatus.HEALTHY, RegionHealthStatus.DEGRADED)
        ]

    def validate_failover_readiness(self, source: str, target: str) -> Dict:
        """Check replication lag, health, data residency compatibility."""
        if source not in self._regions or target not in self._regions:
             raise ValueError("Regions not found")
             
        s_reg = self._regions[source]
        t_reg = self._regions[target]
        
        is_healthy = t_reg.health_status in (RegionHealthStatus.HEALTHY, RegionHealthStatus.DEGRADED)
        lag_ok = t_reg.replication_lag_ms <= self._replication_lag_threshold_ms
        residency_ok = s_reg.data_residency_zone == t_reg.data_residency_zone
        
        return {
             "ready": is_healthy and lag_ok and residency_ok,
             "target_health": t_reg.health_status,
             "replication_lag_ok": lag_ok,
             "data_residency_match": residency_ok
        }

    def run_dr_drill(self, source: str, target: str) -> FailoverEvent:
        """Execute DR drill with automatic rollback."""
        event = self.initiate_failover(source, target, FailoverTrigger.DR_DRILL)
        self.complete_failover(event.event_id, success=True, rpo_bytes=0)
        return self.rollback_failover(event.event_id)

    def get_failover_history(self) -> List[FailoverEvent]:
        """All failover events."""
        return list(self._failover_events.values())

    def get_rto_rpo_report(self) -> Dict:
        """RTO/RPO metrics across all failover events."""
        total_rto = 0.0
        total_rpo = 0
        count = 0
        for ev in self._failover_events.values():
             if ev.completed_at:
                  total_rto += ev.rto_seconds
                  total_rpo += ev.rpo_data_loss_bytes
                  count += 1
                  
        return {
             "average_rto_seconds": total_rto / count if count > 0 else 0.0,
             "average_rpo_bytes": total_rpo / count if count > 0 else 0.0,
             "total_events": count
        }
        
    def _normalize_weights(self) -> None:
         """Ensure traffic weights sum to 100."""
         total = sum(r.traffic_weight for r in self._regions.values())
         if total > 0:
              for r in self._regions.values():
                   r.traffic_weight = (r.traffic_weight / total) * 100.0
         elif self._regions:
              primaries = [r for r in self._regions.values() if r.is_primary]
              if primaries:
                  primaries[0].traffic_weight = 100.0

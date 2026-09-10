import datetime
from typing import Dict, List, Optional
from elmos_mature_platform.types import (
    StatusPageState,
    CommunicationType,
    ServiceStatus,
    StatusCommunication,
    MaintenanceWindow
)

class CustomerStatusCommunicationEngine:
    def __init__(self) -> None:
        self._services: Dict[str, ServiceStatus] = {}
        self._communications: Dict[str, StatusCommunication] = {}
        self._maintenance_windows: Dict[str, MaintenanceWindow] = {}
        # Track time intervals to estimate uptime: (service_id, state, timestamp)
        self._state_history: List[Dict] = []

    def _now(self) -> str:
        return datetime.datetime.now(datetime.timezone.utc).isoformat()

    def register_service(self, service: ServiceStatus) -> None:
        """Register a new service for status tracking."""
        service.updated_at = self._now()
        self._services[service.service_id] = service
        self._state_history.append({
            "service_id": service.service_id,
            "state": service.state,
            "timestamp": service.updated_at
        })

    def update_service_state(self, service_id: str, state: StatusPageState, message: str) -> ServiceStatus:
        """Update the state of a registered service."""
        if service_id not in self._services:
            raise ValueError(f"Service {service_id} not found.")
        
        svc = self._services[service_id]
        svc.state = state
        svc.message = message
        svc.updated_at = self._now()
        
        self._state_history.append({
            "service_id": svc.service_id,
            "state": svc.state,
            "timestamp": svc.updated_at
        })
        return svc

    def create_communication(self, comm: StatusCommunication) -> str:
        """Create a new communication item."""
        if not comm.comm_id:
            raise ValueError("Communication ID is required.")
        if comm.comm_id in self._communications:
            raise ValueError(f"Communication {comm.comm_id} already exists.")
        
        self._communications[comm.comm_id] = comm
        return comm.comm_id

    def publish_communication(self, comm_id: str) -> StatusCommunication:
        """Publish a drafted communication."""
        if comm_id not in self._communications:
            raise ValueError(f"Communication {comm_id} not found.")
        
        comm = self._communications[comm_id]
        if comm.published:
            return comm
            
        comm.published = True
        comm.published_at = self._now()
        return comm

    def schedule_maintenance(self, window: MaintenanceWindow) -> str:
        """Schedule a maintenance window."""
        if not window.window_id:
            raise ValueError("Window ID is required.")
        if window.window_id in self._maintenance_windows:
            raise ValueError(f"Window {window.window_id} already exists.")
            
        window.status = "scheduled"
        self._maintenance_windows[window.window_id] = window
        return window.window_id

    def start_maintenance(self, window_id: str) -> MaintenanceWindow:
        """Start a maintenance window and set associated services to MAINTENANCE state."""
        if window_id not in self._maintenance_windows:
            raise ValueError(f"Window {window_id} not found.")
            
        window = self._maintenance_windows[window_id]
        if window.status != "scheduled":
            raise ValueError(f"Cannot start window with status {window.status}.")
            
        window.status = "in_progress"
        window.actual_start = self._now()
        
        for svc_id in window.service_ids:
            if svc_id in self._services:
                self.update_service_state(
                    service_id=svc_id,
                    state=StatusPageState.MAINTENANCE,
                    message=f"Maintenance {window.title} in progress"
                )
        return window

    def complete_maintenance(self, window_id: str) -> MaintenanceWindow:
        """Complete a maintenance window and restore associated services to OPERATIONAL state."""
        if window_id not in self._maintenance_windows:
            raise ValueError(f"Window {window_id} not found.")
            
        window = self._maintenance_windows[window_id]
        if window.status != "in_progress":
            raise ValueError(f"Cannot complete window with status {window.status}.")
            
        window.status = "completed"
        window.actual_end = self._now()
        
        for svc_id in window.service_ids:
            if svc_id in self._services:
                self.update_service_state(
                    service_id=svc_id,
                    state=StatusPageState.OPERATIONAL,
                    message=f"Maintenance {window.title} completed"
                )
        return window

    def cancel_maintenance(self, window_id: str) -> MaintenanceWindow:
        """Cancel a scheduled maintenance window."""
        if window_id not in self._maintenance_windows:
            raise ValueError(f"Window {window_id} not found.")
            
        window = self._maintenance_windows[window_id]
        if window.status != "scheduled":
            raise ValueError(f"Cannot cancel window with status {window.status}.")
            
        window.status = "cancelled"
        return window

    def get_status_page(self) -> Dict:
        """Get the current status of all services."""
        return {
            "services": [
                {
                    "service_id": svc.service_id,
                    "service_name": svc.service_name,
                    "state": svc.state.value,
                    "message": svc.message,
                    "updated_at": svc.updated_at
                }
                for svc in self._services.values()
            ],
            "active_maintenance": [
                {
                    "window_id": w.window_id,
                    "title": w.title,
                    "status": w.status
                }
                for w in self._maintenance_windows.values()
                if w.status == "in_progress"
            ]
        }

    def get_communication_history(self, service_id: Optional[str] = None) -> List[StatusCommunication]:
        """Get history of communications, optionally filtered by service_id."""
        published_comms = [c for c in self._communications.values() if c.published]
        
        if service_id:
            filtered = [
                c for c in published_comms
                if not c.affected_services or service_id in c.affected_services
            ]
            return sorted(filtered, key=lambda x: x.published_at, reverse=True)
            
        return sorted(published_comms, key=lambda x: x.published_at, reverse=True)

    def get_uptime_summary(self) -> Dict:
        """Get operational vs non-operational time ratio per service."""
        # Simple simulated uptime summary based on state history frequency
        # For a real implementation, we would use intervals between timestamps.
        
        summary = {}
        for svc_id in self._services:
            events = [e for e in self._state_history if e["service_id"] == svc_id]
            if not events:
                summary[svc_id] = {"uptime_percentage": 100.0, "total_events": 0}
                continue
                
            op_events = sum(1 for e in events if e["state"] == StatusPageState.OPERATIONAL)
            total = len(events)
            
            # Simple heuristic: treat states as durations if we don't have true timing simulation
            uptime_percentage = (op_events / total) * 100.0 if total > 0 else 100.0
            
            summary[svc_id] = {
                "uptime_percentage": round(uptime_percentage, 2),
                "total_events": total,
                "current_state": self._services[svc_id].state.value
            }
            
        return summary

from typing import List, Dict, Optional
from datetime import datetime
from elmos_mature_platform.types import (
    ChangeRequest, ChangeFreezeWindow, ChangeAuditEntry,
    ChangeRiskLevel, ChangeStatus, FreezeScope
)

class ChangeManagementEngine:
    def __init__(self):
        self.changes: Dict[str, ChangeRequest] = {}
        self.freezes: Dict[str, ChangeFreezeWindow] = {}
        self.audits: Dict[str, List[ChangeAuditEntry]] = {}

    def _record_audit(self, change_id: str, action: str, actor: str, details: str = ""):
        if change_id not in self.audits:
            self.audits[change_id] = []
        entry = ChangeAuditEntry(
            change_id=change_id,
            action=action,
            actor=actor,
            timestamp=datetime.utcnow().isoformat() + "Z",
            details=details
        )
        self.audits[change_id].append(entry)

    def submit_change(self, change: ChangeRequest) -> ChangeRequest:
        """Submit a change request for review."""
        if change.risk_level in [ChangeRiskLevel.HIGH, ChangeRiskLevel.CRITICAL]:
            if not change.rollback_plan:
                raise ValueError("HIGH and CRITICAL changes require a rollback_plan")
        
        change.status = ChangeStatus.SUBMITTED
        self.changes[change.change_id] = change
        self._record_audit(change.change_id, "SUBMIT", change.requester, "Change submitted for review")
        return change

    def approve_change(self, change_id: str, approver: str) -> ChangeRequest:
        """Approve a change request."""
        if change_id not in self.changes:
            raise KeyError(f"Change {change_id} not found")
            
        change = self.changes[change_id]
        
        if change.status != ChangeStatus.SUBMITTED:
            raise ValueError(f"Cannot approve change in {change.status} status")
            
        if change.requester == approver:
            raise PermissionError("Self-approval is not allowed")
            
        change.status = ChangeStatus.APPROVED
        change.approver = approver
        self._record_audit(change_id, "APPROVE", approver, "Change approved")
        return change

    def reject_change(self, change_id: str, approver: str, reason: str) -> ChangeRequest:
        """Reject a change request."""
        if change_id not in self.changes:
            raise KeyError(f"Change {change_id} not found")
            
        change = self.changes[change_id]
        
        if change.status != ChangeStatus.SUBMITTED:
            raise ValueError(f"Cannot reject change in {change.status} status")
            
        if change.requester == approver:
            raise PermissionError("Self-rejection is not allowed")
            
        change.status = ChangeStatus.REJECTED
        change.approver = approver
        self._record_audit(change_id, "REJECT", approver, f"Change rejected: {reason}")
        return change

    def start_change(self, change_id: str) -> ChangeRequest:
        """Begin executing an approved change."""
        if change_id not in self.changes:
            raise KeyError(f"Change {change_id} not found")
            
        change = self.changes[change_id]
        
        if change.status != ChangeStatus.APPROVED:
            raise ValueError(f"Cannot start change in {change.status} status")

        # Check for active freezes
        current_time = datetime.utcnow().isoformat() + "Z"
        if self.is_frozen(change.service_name, change.region, current_time):
            # Check exceptions
            exempt = False
            for freeze in self.freezes.values():
                if freeze.is_active and self._matches_freeze(freeze, change.service_name, change.region, current_time):
                    if change_id in freeze.exceptions:
                        exempt = True
                        break
            if not exempt:
                raise PermissionError("Cannot start change during active freeze")

        change.status = ChangeStatus.IN_PROGRESS
        change.started_at = current_time
        self._record_audit(change_id, "START", change.requester, "Change execution started")
        return change

    def complete_change(self, change_id: str, success: bool) -> ChangeRequest:
        """Mark a change as completed or failed."""
        if change_id not in self.changes:
            raise KeyError(f"Change {change_id} not found")
            
        change = self.changes[change_id]
        
        if change.status != ChangeStatus.IN_PROGRESS:
            raise ValueError(f"Cannot complete change in {change.status} status")

        current_time = datetime.utcnow().isoformat() + "Z"
        change.status = ChangeStatus.COMPLETED if success else ChangeStatus.FAILED
        change.completed_at = current_time
        self._record_audit(change_id, "COMPLETE" if success else "FAIL", change.requester, f"Change finished with success={success}")
        return change

    def rollback_change(self, change_id: str) -> ChangeRequest:
        """Rollback a failed or in-progress change."""
        if change_id not in self.changes:
            raise KeyError(f"Change {change_id} not found")
            
        change = self.changes[change_id]
        
        if change.status not in [ChangeStatus.IN_PROGRESS, ChangeStatus.FAILED, ChangeStatus.COMPLETED]:
            raise ValueError(f"Cannot rollback change in {change.status} status")
            
        change.status = ChangeStatus.ROLLED_BACK
        self._record_audit(change_id, "ROLLBACK", change.requester, "Change rolled back")
        return change

    def create_freeze(self, freeze: ChangeFreezeWindow):
        """Create a change freeze window."""
        self.freezes[freeze.freeze_id] = freeze

    def _matches_freeze(self, freeze: ChangeFreezeWindow, service_name: str, region: str, current_time: str) -> bool:
        if freeze.starts_at and current_time < freeze.starts_at:
            return False
        if freeze.ends_at and current_time > freeze.ends_at:
            return False
            
        if freeze.scope == FreezeScope.GLOBAL:
            return True
        elif freeze.scope == FreezeScope.REGION and freeze.scope_value == region:
            return True
        elif freeze.scope == FreezeScope.SERVICE and freeze.scope_value == service_name:
            return True
        elif freeze.scope == FreezeScope.TENANT:
            return False  # Assuming tenant isn't supported for service checks directly, though possible
        return False

    def is_frozen(self, service_name: str, region: str, current_time: str) -> bool:
        """Check if a service or region is currently frozen."""
        for freeze in self.freezes.values():
            if freeze.is_active and self._matches_freeze(freeze, service_name, region, current_time):
                return True
        return False

    def add_freeze_exception(self, freeze_id: str, change_id: str):
        """Exempt a specific change from a freeze."""
        if freeze_id not in self.freezes:
            raise KeyError(f"Freeze {freeze_id} not found")
        freeze = self.freezes[freeze_id]
        if change_id not in freeze.exceptions:
            freeze.exceptions.append(change_id)

    def get_pending_approvals(self) -> List[ChangeRequest]:
        """Get all changes awaiting approval."""
        return [c for c in self.changes.values() if c.status == ChangeStatus.SUBMITTED]

    def get_change_audit(self, change_id: str) -> List[ChangeAuditEntry]:
        """Get the audit trail for a change."""
        return self.audits.get(change_id, [])

    def get_change_metrics(self) -> Dict:
        """Get a summary of change metrics."""
        metrics = {
            "status_counts": {s.value: 0 for s in ChangeStatus},
            "risk_counts": {r.value: 0 for r in ChangeRiskLevel},
            "average_approval_time_seconds": 0.0,
            "total_changes": len(self.changes)
        }
        
        approval_times = []
        
        for change in self.changes.values():
            metrics["status_counts"][change.status.value] += 1
            metrics["risk_counts"][change.risk_level.value] += 1
            
            audits = self.audits.get(change.change_id, [])
            submit_time = None
            approve_time = None
            
            for entry in audits:
                if entry.action == "SUBMIT":
                    submit_time = entry.timestamp
                elif entry.action == "APPROVE":
                    approve_time = entry.timestamp
                    
            if submit_time and approve_time:
                try:
                    submit_dt = datetime.fromisoformat(submit_time.replace("Z", "+00:00"))
                    approve_dt = datetime.fromisoformat(approve_time.replace("Z", "+00:00"))
                    approval_times.append((approve_dt - submit_dt).total_seconds())
                except ValueError:
                    pass
                    
        if approval_times:
            metrics["average_approval_time_seconds"] = sum(approval_times) / len(approval_times)
            
        return metrics

    def check_change_conflicts(self, change_id: str) -> List[str]:
        """Find overlapping changes on the same service."""
        if change_id not in self.changes:
            raise KeyError(f"Change {change_id} not found")
            
        target_change = self.changes[change_id]
        conflicts = []
        
        # Consider a conflict if another change is IN_PROGRESS on the same service
        # or impacts the same service.
        target_services = set([target_change.service_name] + target_change.impact_services)
        
        for cid, change in self.changes.items():
            if cid == change_id:
                continue
            if change.status in [ChangeStatus.IN_PROGRESS, ChangeStatus.APPROVED]:
                other_services = set([change.service_name] + change.impact_services)
                if target_services.intersection(other_services):
                    conflicts.append(cid)
                    
        return conflicts

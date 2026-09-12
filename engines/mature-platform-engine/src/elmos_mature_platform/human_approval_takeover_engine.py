from typing import List, Dict, Any, Optional
from datetime import datetime
from elmos_mature_platform.types import (
    ApprovalRequest,
    ApprovalStatus,
    TakeoverEvent,
    TakeoverReason
)

class HumanApprovalTakeoverEngine:
    """Engine for managing human approvals and agent takeover control."""
    
    def __init__(self) -> None:
        self._approvals: Dict[str, ApprovalRequest] = {}
        self._takeovers: Dict[str, TakeoverEvent] = {}
        
        self._risk_levels = {
            "low": 0,
            "medium": 1,
            "high": 2,
            "critical": 3
        }

    def _get_current_time(self) -> str:
        return datetime.utcnow().isoformat()
        
    def _is_risk_auto_approvable(self, risk_level: str, threshold: str) -> bool:
        """Check if risk level is <= threshold."""
        risk_val = self._risk_levels.get(risk_level, 1)  # Default medium
        thresh_val = self._risk_levels.get(threshold, 0) # Default low
        return risk_val <= thresh_val

    def submit_approval(self, request: ApprovalRequest) -> str:
        """Submit for approval, auto-approve if risk <= threshold."""
        if not request.created_at:
            request.created_at = self._get_current_time()
            
        if self._is_risk_auto_approvable(request.risk_level, request.auto_approve_threshold):
            request.status = ApprovalStatus.AUTO_APPROVED
            request.decided_at = self._get_current_time()
            request.decision_reason = "Auto-approved based on risk threshold"
            
        self._approvals[request.request_id] = request
        return request.request_id

    def approve(self, request_id: str, approver: str, reason: str) -> ApprovalRequest:
        """Approve a pending request."""
        if request_id not in self._approvals:
            raise ValueError(f"Request {request_id} not found")
            
        req = self._approvals[request_id]
        if req.status != ApprovalStatus.PENDING:
            raise ValueError(f"Cannot approve request with status {req.status}")
            
        req.status = ApprovalStatus.APPROVED
        req.approver = approver
        req.decision_reason = reason
        req.decided_at = self._get_current_time()
        return req

    def reject(self, request_id: str, approver: str, reason: str) -> ApprovalRequest:
        """Reject a pending request."""
        if request_id not in self._approvals:
            raise ValueError(f"Request {request_id} not found")
            
        req = self._approvals[request_id]
        if req.status != ApprovalStatus.PENDING:
            raise ValueError(f"Cannot reject request with status {req.status}")
            
        req.status = ApprovalStatus.REJECTED
        req.approver = approver
        req.decision_reason = reason
        req.decided_at = self._get_current_time()
        return req

    def escalate(self, request_id: str, reason: str) -> ApprovalRequest:
        """Escalate a pending request to a higher authority."""
        if request_id not in self._approvals:
            raise ValueError(f"Request {request_id} not found")
            
        req = self._approvals[request_id]
        if req.status != ApprovalStatus.PENDING:
            raise ValueError(f"Cannot escalate request with status {req.status}")
            
        req.status = ApprovalStatus.ESCALATED
        req.decision_reason = reason
        req.decided_at = self._get_current_time()
        return req

    def check_expiry(self) -> List[str]:
        """Expire pending requests past expires_at."""
        expired_ids = []
        current_time = self._get_current_time()
        
        for req_id, req in self._approvals.items():
            if req.status == ApprovalStatus.PENDING and req.expires_at and current_time > req.expires_at:
                req.status = ApprovalStatus.EXPIRED
                req.decision_reason = "Expired automatically"
                req.decided_at = current_time
                expired_ids.append(req_id)
                
        return expired_ids

    def initiate_takeover(self, event: TakeoverEvent) -> str:
        """Start human takeover of agent."""
        if not event.agent_id:
            raise ValueError("Takeover must reference a valid agent")
            
        if not event.started_at:
            event.started_at = self._get_current_time()
            
        self._takeovers[event.event_id] = event
        return event.event_id

    def end_takeover(self, event_id: str, outcome: str) -> TakeoverEvent:
        """End takeover."""
        if event_id not in self._takeovers:
            raise ValueError(f"Takeover {event_id} not found")
            
        event = self._takeovers[event_id]
        if event.ended_at:
            raise ValueError(f"Takeover {event_id} already ended")
            
        event.ended_at = self._get_current_time()
        event.outcome = outcome
        return event

    def record_takeover_action(self, event_id: str, action: str) -> None:
        """Log action during takeover."""
        if event_id not in self._takeovers:
            raise ValueError(f"Takeover {event_id} not found")
            
        event = self._takeovers[event_id]
        if event.ended_at:
            raise ValueError(f"Cannot record action, takeover {event_id} already ended")
            
        event.actions_taken.append(action)

    def get_pending_approvals(self, risk_level: str = "") -> List[ApprovalRequest]:
        """Get pending approvals optionally filtered by risk level."""
        pending = [r for r in self._approvals.values() if r.status == ApprovalStatus.PENDING]
        if risk_level:
            pending = [r for r in pending if r.risk_level == risk_level]
        return pending

    def get_approval_stats(self) -> Dict[str, Any]:
        """By status, avg decision time, auto vs manual."""
        stats: Dict[str, Any] = {
            "by_status": {},
            "avg_decision_time_sec": 0.0,
            "auto_vs_manual": {
                "auto": 0,
                "manual": 0
            }
        }
        
        total_decision_time = 0.0
        decided_count = 0
        
        for status in ApprovalStatus:
            stats["by_status"][status.value] = 0
            
        for req in self._approvals.values():
            stats["by_status"][req.status.value] += 1
            
            if req.status == ApprovalStatus.AUTO_APPROVED:
                stats["auto_vs_manual"]["auto"] += 1
            elif req.status in [ApprovalStatus.APPROVED, ApprovalStatus.REJECTED]:
                stats["auto_vs_manual"]["manual"] += 1
                
            if req.created_at and req.decided_at:
                try:
                    created = datetime.fromisoformat(req.created_at)
                    decided = datetime.fromisoformat(req.decided_at)
                    diff = (decided - created).total_seconds()
                    total_decision_time += diff
                    decided_count += 1
                except ValueError:
                    pass
                    
        if decided_count > 0:
            stats["avg_decision_time_sec"] = total_decision_time / decided_count
            
        return stats

    def get_takeover_history(self) -> List[TakeoverEvent]:
        """All takeover events."""
        return list(self._takeovers.values())

    def get_approval_audit_trail(self, request_id: str) -> Dict[str, Any]:
        """Full audit: request, decision, who, when."""
        if request_id not in self._approvals:
            raise ValueError(f"Request {request_id} not found")
            
        req = self._approvals[request_id]
        
        return {
            "request_id": req.request_id,
            "action_description": req.action_description,
            "requester": req.requester,
            "status": req.status.value,
            "risk_level": req.risk_level,
            "created_at": req.created_at,
            "decided_at": req.decided_at,
            "approver": req.approver,
            "decision_reason": req.decision_reason,
            "context": req.context
        }

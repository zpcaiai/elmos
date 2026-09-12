from typing import Dict, List, Optional
from datetime import datetime, timezone

from elmos_mature_platform.types import (
    SecurityFix,
    BackportRecord,
    BackportPriority,
    BackportStatus,
)

class SecurityFixBackportEngine:
    """Engine for managing security fix backports across platform versions."""
    
    def __init__(self):
        self._fixes: Dict[str, SecurityFix] = {}
        self._backports: Dict[str, BackportRecord] = {}

    def _now_iso(self) -> str:
        """Get current time in ISO format."""
        return datetime.now(timezone.utc).isoformat()

    def register_fix(self, fix: SecurityFix) -> str:
        """Register a new security fix."""
        if not fix.created_at:
            fix.created_at = self._now_iso()
        self._fixes[fix.fix_id] = fix
        return fix.fix_id

    def create_backport(self, backport: BackportRecord) -> str:
        """Create a new backport task for an existing fix."""
        if backport.fix_id not in self._fixes:
            raise ValueError(f"Fix {backport.fix_id} not found")
        if backport.backport_id in self._backports:
            raise ValueError(f"Backport {backport.backport_id} already exists")
        
        backport.status = BackportStatus.PENDING
        self._backports[backport.backport_id] = backport
        return backport.backport_id

    def start_backport(self, backport_id: str) -> BackportRecord:
        """Move backport from PENDING to IN_PROGRESS."""
        backport = self._backports.get(backport_id)
        if not backport:
            raise ValueError(f"Backport {backport_id} not found")
        if backport.status != BackportStatus.PENDING:
            raise ValueError(f"Cannot start backport from status {backport.status}")
            
        backport.status = BackportStatus.IN_PROGRESS
        return backport

    def apply_backport(self, backport_id: str) -> BackportRecord:
        """Mark a backport as APPLIED."""
        backport = self._backports.get(backport_id)
        if not backport:
            raise ValueError(f"Backport {backport_id} not found")
        if backport.status != BackportStatus.IN_PROGRESS:
            raise ValueError(f"Cannot apply backport from status {backport.status}")
            
        backport.status = BackportStatus.APPLIED
        backport.applied_at = self._now_iso()
        return backport

    def verify_backport(self, backport_id: str, verifier: str, test_passed: bool) -> BackportRecord:
        """Verify backport. If test passes -> VERIFIED, else FAILED."""
        backport = self._backports.get(backport_id)
        if not backport:
            raise ValueError(f"Backport {backport_id} not found")
        if backport.status != BackportStatus.APPLIED:
            raise ValueError(f"Cannot verify backport from status {backport.status}")
            
        backport.verified_by = verifier
        backport.verified_at = self._now_iso()
        backport.test_passed = test_passed
        if test_passed:
            backport.status = BackportStatus.VERIFIED
        else:
            backport.status = BackportStatus.FAILED
            backport.failure_reason = "Test failed during verification"
            
        return backport

    def skip_backport(self, backport_id: str, reason: str) -> BackportRecord:
        """Skip a backport with a reason."""
        backport = self._backports.get(backport_id)
        if not backport:
            raise ValueError(f"Backport {backport_id} not found")
            
        if backport.status in (BackportStatus.VERIFIED, BackportStatus.FAILED, BackportStatus.SKIPPED):
            raise ValueError(f"Cannot skip backport that is already finished ({backport.status})")
            
        backport.status = BackportStatus.SKIPPED
        backport.skip_reason = reason
        return backport

    def get_pending_backports(self, priority: Optional[BackportPriority] = None) -> List[BackportRecord]:
        """Get pending backports, optionally filtered by priority."""
        pending = [b for b in self._backports.values() if b.status == BackportStatus.PENDING]
        if priority:
            pending = [b for b in pending if self._fixes[b.fix_id].priority == priority]
        return pending

    def get_fix_coverage(self, fix_id: str) -> Dict:
        """Get backport status per target version for a fix."""
        if fix_id not in self._fixes:
            raise ValueError(f"Fix {fix_id} not found")
            
        coverage = {}
        total = 0
        verified = 0
        for b in self._backports.values():
            if b.fix_id == fix_id:
                coverage[b.target_version] = b.status.value
                total += 1
                if b.status == BackportStatus.VERIFIED:
                    verified += 1
                    
        pct = (verified / total * 100.0) if total > 0 else 0.0
        return {
            "versions": coverage,
            "verified_percentage": pct
        }

    def get_overdue_backports(self, max_age_hours: int = 48) -> List[BackportRecord]:
        """Get pending backports older than max_age_hours."""
        overdue = []
        now = datetime.now(timezone.utc)
        
        for b in self._backports.values():
            if b.status == BackportStatus.PENDING:
                fix = self._fixes[b.fix_id]
                if fix.created_at:
                    try:
                        created = datetime.fromisoformat(fix.created_at)
                        age_hours = (now - created).total_seconds() / 3600.0
                        if age_hours > max_age_hours:
                            overdue.append(b)
                    except ValueError:
                        pass
        return overdue

    def get_version_security_status(self, version: str) -> Dict:
        """Get security status for a specific version."""
        status_counts = {
            "pending": 0,
            "in_progress": 0,
            "applied": 0,
            "verified": 0,
            "failed": 0,
            "skipped": 0
        }
        backports_list = []
        
        for b in self._backports.values():
            if b.target_version == version:
                status_counts[b.status.value] += 1
                backports_list.append(b.backport_id)
                
        return {
            "version": version,
            "backports": backports_list,
            "status_counts": status_counts
        }

    def get_backport_report(self) -> Dict:
        """Generate an overall report of backports."""
        by_priority = {}
        by_status = {}
        total_time_verified = 0.0
        verified_count = 0
        
        for p in BackportPriority:
            by_priority[p.value] = 0
        for s in BackportStatus:
            by_status[s.value] = 0
            
        for b in self._backports.values():
            fix = self._fixes[b.fix_id]
            by_priority[fix.priority.value] += 1
            by_status[b.status.value] += 1
            
            if b.status == BackportStatus.VERIFIED and b.applied_at and b.verified_at:
                try:
                    applied = datetime.fromisoformat(b.applied_at)
                    verified = datetime.fromisoformat(b.verified_at)
                    hours = (verified - applied).total_seconds() / 3600.0
                    if hours >= 0:
                        total_time_verified += hours
                        verified_count += 1
                except ValueError:
                    pass
                    
        avg_time = (total_time_verified / verified_count) if verified_count > 0 else 0.0
        total = len(self._backports)
        coverage = (by_status[BackportStatus.VERIFIED.value] / total * 100.0) if total > 0 else 0.0
        
        return {
            "by_priority": by_priority,
            "by_status": by_status,
            "avg_time_to_verify_hours": avg_time,
            "verified_coverage_percentage": coverage
        }

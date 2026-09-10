"""Engine for managing backups, restores, and disaster recovery drills."""

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from .types import (
    BackupType,
    RestoreVerdict,
    BackupRecord,
    RestoreRequest,
    RestoreResult,
    DrDrillResult
)

class BackupRestoreEngine:
    def __init__(self) -> None:
        # In-memory storage for backups: backup_id -> BackupRecord
        self._backups: Dict[str, BackupRecord] = {}
        # Simulated backup payload storage for integrity verification
        self._payloads: Dict[str, bytes] = {}

    def _generate_checksum(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def create_backup(self, source_name: str, backup_type: BackupType, data: bytes, kms_key_id: str, region: str, retention_days: int = 90, parent_backup_id: Optional[str] = None) -> BackupRecord:
        """Create a backup with checksum."""
        
        if backup_type == BackupType.INCREMENTAL and not parent_backup_id:
            raise ValueError("Incremental backup requires a parent backup ID.")
            
        if parent_backup_id and parent_backup_id not in self._backups:
            raise ValueError(f"Parent backup {parent_backup_id} not found.")

        backup_id = f"bck-{uuid.uuid4().hex[:8]}"
        checksum = self._generate_checksum(data)
        
        record = BackupRecord(
            backup_id=backup_id,
            backup_type=backup_type,
            source_name=source_name,
            size_bytes=len(data),
            checksum_sha256=checksum,
            created_at=datetime.now(timezone.utc).isoformat(),
            retention_days=retention_days,
            encrypted=bool(kms_key_id),
            kms_key_id=kms_key_id,
            region=region,
            parent_backup_id=parent_backup_id
        )
        
        self._backups[backup_id] = record
        self._payloads[backup_id] = data
        return record

    def list_backups(self, source_name: str) -> List[BackupRecord]:
        """List backups for source."""
        return [b for b in self._backups.values() if b.source_name == source_name]

    def get_backup(self, backup_id: str) -> BackupRecord:
        """Get backup by ID."""
        if backup_id not in self._backups:
            raise KeyError(f"Backup {backup_id} not found")
        return self._backups[backup_id]

    def restore_backup(self, request: RestoreRequest) -> RestoreResult:
        """Restore from backup, verify checksum integrity."""
        if not request.isolated_environment:
            raise PermissionError("Restoring to non-isolated environment must be explicitly opted in.")

        backup = self.get_backup(request.backup_id)
        payload = self._payloads.get(request.backup_id, b"")
        
        # Verify integrity
        checksum_verified = self.verify_backup_integrity(request.backup_id, payload)
        
        restore_id = f"rst-{uuid.uuid4().hex[:8]}"
        
        if not checksum_verified:
            return RestoreResult(
                restore_id=restore_id,
                verdict=RestoreVerdict.INTEGRITY_MISMATCH,
                checksum_verified=False,
                integrity_errors=["Checksum verification failed."]
            )
            
        # Simulate restore
        restored_rows = backup.size_bytes // 100  # Fake rows calculation
        
        return RestoreResult(
            restore_id=restore_id,
            verdict=RestoreVerdict.SUCCESS,
            restored_rows=restored_rows,
            elapsed_seconds=1.5,
            checksum_verified=True,
            integrity_errors=[]
        )

    def verify_backup_integrity(self, backup_id: str, data: bytes) -> bool:
        """Re-verify checksum."""
        backup = self.get_backup(backup_id)
        current_checksum = self._generate_checksum(data)
        return backup.checksum_sha256 == current_checksum

    def run_restore_drill(self, drill_type: str, backup_id: str, target_rto: float, target_rpo: float, simulated_restore_time: float, simulated_data_lag: float) -> DrDrillResult:
        """Execute DR drill with RTO/RPO assertion."""
        # Check backup exists
        self.get_backup(backup_id)
        
        rto_met = simulated_restore_time <= target_rto
        rpo_met = simulated_data_lag <= target_rpo
        passed = rto_met and rpo_met
        
        findings = []
        if not rto_met:
            findings.append(f"RTO missed: target {target_rto}s, actual {simulated_restore_time}s")
        if not rpo_met:
            findings.append(f"RPO missed: target {target_rpo}s, actual {simulated_data_lag}s")
            
        return DrDrillResult(
            drill_id=f"drill-{uuid.uuid4().hex[:8]}",
            drill_type=drill_type,
            target_rto_seconds=target_rto,
            target_rpo_seconds=target_rpo,
            actual_rto_seconds=simulated_restore_time,
            actual_rpo_seconds=simulated_data_lag,
            rto_met=rto_met,
            rpo_met=rpo_met,
            passed=passed,
            findings=findings
        )

    def enforce_retention(self, cutoff_date: str) -> List[str]:
        """Delete expired backups, return deleted IDs."""
        deleted_ids = []
        # Parse cutoff_date safely
        cutoff_dt = datetime.fromisoformat(cutoff_date.replace("Z", "+00:00"))
        
        for b_id, record in list(self._backups.items()):
            created_dt = datetime.fromisoformat(record.created_at.replace("Z", "+00:00"))
            # calculate age in days
            age = (cutoff_dt - created_dt).days
            if age > record.retention_days:
                deleted_ids.append(b_id)
                del self._backups[b_id]
                self._payloads.pop(b_id, None)
                
        return deleted_ids

    def get_backup_chain(self, backup_id: str) -> List[BackupRecord]:
        """Full/incremental chain for restore."""
        chain = []
        current_id = backup_id
        while current_id:
            record = self.get_backup(current_id)
            chain.append(record)
            current_id = record.parent_backup_id
        return list(reversed(chain))

    def validate_pitr_range(self, source_name: str, target_time: str) -> bool:
        """Check if PITR target is within available backup range."""
        backups = self.list_backups(source_name)
        if not backups:
            return False
            
        target_dt = datetime.fromisoformat(target_time.replace("Z", "+00:00"))
        
        # We need the earliest and latest backup times
        times = [datetime.fromisoformat(b.created_at.replace("Z", "+00:00")) for b in backups]
        min_time = min(times)
        max_time = max(times)
        
        return min_time <= target_dt <= max_time

    def get_backup_report(self) -> Dict[str, Any]:
        """Total backups, total size, oldest/newest, retention compliance."""
        total_backups = len(self._backups)
        total_size = sum(b.size_bytes for b in self._backups.values())
        
        if not self._backups:
            return {
                "total_backups": 0,
                "total_size_bytes": 0,
                "oldest_backup": None,
                "newest_backup": None,
                "retention_compliant": True
            }
            
        sorted_backups = sorted(
            self._backups.values(),
            key=lambda x: datetime.fromisoformat(x.created_at.replace("Z", "+00:00"))
        )
        
        return {
            "total_backups": total_backups,
            "total_size_bytes": total_size,
            "oldest_backup": sorted_backups[0].created_at,
            "newest_backup": sorted_backups[-1].created_at,
            "retention_compliant": True
        }

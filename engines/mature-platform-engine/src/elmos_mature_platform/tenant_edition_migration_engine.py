from typing import Dict, List, Optional
from datetime import datetime, timezone

from .types import (
    TenantEditionMapping,
    MigrationPrecheck,
    MigrationWave,
    TenantMigrationStatus,
)

class TenantEditionMigrationEngine:
    """
    Engine for managing tenant migrations between editions.
    """
    def __init__(self):
        self._mappings: Dict[str, TenantEditionMapping] = {}
        self._waves: Dict[str, MigrationWave] = {}

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def create_mapping(self, mapping: TenantEditionMapping) -> str:
        """Create a new migration mapping."""
        if mapping.mapping_id in self._mappings:
            raise ValueError(f"Mapping {mapping.mapping_id} already exists.")
        if mapping.source_edition == mapping.target_edition:
            raise ValueError("Source and target editions must be different.")
        
        self._mappings[mapping.mapping_id] = mapping
        return mapping.mapping_id

    def precheck(self, mapping_id: str) -> MigrationPrecheck:
        """Run pre-migration checks."""
        if mapping_id not in self._mappings:
            raise KeyError(f"Mapping {mapping_id} not found.")
        
        mapping = self._mappings[mapping_id]
        
        # Simple simulated checks based on mapping data
        edition_compatible = True  # Assuming compatible unless configured otherwise in a more complex setup
        data_exportable = True
        features_available = len(mapping.feature_gaps) == 0
        capacity_sufficient = mapping.data_size_gb < 1000.0  # arbitrary limit for the sake of example
        
        blockers = []
        if not features_available:
            blockers.append("Feature gaps exist: " + ", ".join(mapping.feature_gaps))
        if not capacity_sufficient:
            blockers.append(f"Data size {mapping.data_size_gb}GB exceeds capacity.")

        overall_ready = edition_compatible and data_exportable and features_available and capacity_sufficient
        
        precheck = MigrationPrecheck(
            mapping_id=mapping_id,
            edition_compatible=edition_compatible,
            data_exportable=data_exportable,
            features_available=features_available,
            capacity_sufficient=capacity_sufficient,
            overall_ready=overall_ready,
            blockers=blockers
        )
        
        if overall_ready:
            mapping.validation_passed = True
            mapping.status = TenantMigrationStatus.VALIDATING
            
        return precheck

    def start_migration(self, mapping_id: str) -> TenantEditionMapping:
        """Start migration (must pass precheck)."""
        if mapping_id not in self._mappings:
            raise KeyError(f"Mapping {mapping_id} not found.")
            
        mapping = self._mappings[mapping_id]
        
        if not mapping.validation_passed or len(mapping.feature_gaps) > 0:
            raise ValueError(f"Mapping {mapping_id} must pass precheck and have no feature gaps before starting.")
            
        if mapping.status not in (TenantMigrationStatus.PLANNED, TenantMigrationStatus.VALIDATING):
            raise ValueError(f"Cannot start migration in status {mapping.status}")
            
        mapping.status = TenantMigrationStatus.MIGRATING
        mapping.started_at = self._now()
        
        return mapping

    def complete_migration(self, mapping_id: str) -> TenantEditionMapping:
        """Mark as completed."""
        if mapping_id not in self._mappings:
            raise KeyError(f"Mapping {mapping_id} not found.")
            
        mapping = self._mappings[mapping_id]
        
        if mapping.status not in (TenantMigrationStatus.MIGRATING, TenantMigrationStatus.VERIFYING):
            raise ValueError(f"Cannot complete migration from status {mapping.status}")
            
        mapping.status = TenantMigrationStatus.COMPLETED
        mapping.completed_at = self._now()
        
        return mapping

    def rollback_migration(self, mapping_id: str) -> TenantEditionMapping:
        """Rollback (must be within deadline)."""
        if mapping_id not in self._mappings:
            raise KeyError(f"Mapping {mapping_id} not found.")
            
        mapping = self._mappings[mapping_id]
        
        if mapping.status not in (TenantMigrationStatus.MIGRATING, TenantMigrationStatus.VERIFYING):
            raise ValueError(f"Cannot rollback migration from status {mapping.status}")
            
        if mapping.rollback_deadline:
            deadline = datetime.fromisoformat(mapping.rollback_deadline)
            now = datetime.now(timezone.utc)
            if now > deadline:
                raise ValueError("Rollback deadline exceeded.")
                
        mapping.status = TenantMigrationStatus.ROLLED_BACK
        mapping.completed_at = self._now()
        
        return mapping

    def fail_migration(self, mapping_id: str, error: str) -> TenantEditionMapping:
        """Mark as failed."""
        if mapping_id not in self._mappings:
            raise KeyError(f"Mapping {mapping_id} not found.")
            
        mapping = self._mappings[mapping_id]
        mapping.status = TenantMigrationStatus.FAILED
        mapping.completed_at = self._now()
        # In a real system, we'd log or store the error
        
        return mapping

    def create_wave(self, wave: MigrationWave) -> str:
        """Create migration wave."""
        if wave.wave_id in self._waves:
            raise ValueError(f"Wave {wave.wave_id} already exists.")
            
        for m_id in wave.mappings:
            if m_id not in self._mappings:
                raise ValueError(f"Mapping {m_id} referenced in wave not found.")
                
        self._waves[wave.wave_id] = wave
        return wave.wave_id

    def execute_wave(self, wave_id: str) -> MigrationWave:
        """Execute wave (respecting max_parallel)."""
        if wave_id not in self._waves:
            raise KeyError(f"Wave {wave_id} not found.")
            
        wave = self._waves[wave_id]
        wave.started_at = self._now()
        
        in_progress = 0
        for m_id in wave.mappings:
            mapping = self._mappings[m_id]
            if mapping.status in (TenantMigrationStatus.MIGRATING, TenantMigrationStatus.VERIFYING):
                in_progress += 1
                
        for m_id in wave.mappings:
            mapping = self._mappings[m_id]
            if in_progress >= wave.max_parallel:
                break
                
            if mapping.status in (TenantMigrationStatus.PLANNED, TenantMigrationStatus.VALIDATING):
                if mapping.validation_passed:
                    self.start_migration(m_id)
                    in_progress += 1
                    
        return wave

    def get_migration_status(self, mapping_id: str) -> TenantEditionMapping:
        """Get status."""
        if mapping_id not in self._mappings:
            raise KeyError(f"Mapping {mapping_id} not found.")
        return self._mappings[mapping_id]

    def get_wave_progress(self, wave_id: str) -> Dict:
        """Wave progress: completed, in-progress, remaining."""
        if wave_id not in self._waves:
            raise KeyError(f"Wave {wave_id} not found.")
            
        wave = self._waves[wave_id]
        completed = 0
        in_progress = 0
        remaining = 0
        
        for m_id in wave.mappings:
            status = self._mappings[m_id].status
            if status in (TenantMigrationStatus.COMPLETED, TenantMigrationStatus.ROLLED_BACK, TenantMigrationStatus.FAILED):
                completed += 1
            elif status in (TenantMigrationStatus.MIGRATING, TenantMigrationStatus.VERIFYING):
                in_progress += 1
            else:
                remaining += 1
                
        return {
            "completed": completed,
            "in_progress": in_progress,
            "remaining": remaining,
            "total": len(wave.mappings)
        }

    def get_migration_report(self) -> Dict:
        """Summary: by status, by edition pair, completion rate."""
        total = len(self._mappings)
        if total == 0:
            return {}
            
        by_status = {}
        by_pair = {}
        completed = 0
        
        for m in self._mappings.values():
            by_status[m.status.value] = by_status.get(m.status.value, 0) + 1
            pair = f"{m.source_edition}->{m.target_edition}"
            by_pair[pair] = by_pair.get(pair, 0) + 1
            if m.status == TenantMigrationStatus.COMPLETED:
                completed += 1
                
        return {
            "total": total,
            "by_status": by_status,
            "by_edition_pair": by_pair,
            "completion_rate": completed / total
        }

from typing import List, Dict, Optional
import time
from elmos_mature_platform.types import (
    DbMigrationPhase,
    SchemaChangeType,
    SchemaChange,
    ExpandContractPlan,
    SchemaValidation
)

class DatabaseExpandContractEngine:
    """
    Engine to manage database schema upgrades using the Expand-Contract pattern.
    Supports safe lifecycle management: PENDING -> EXPAND -> MIGRATE -> CONTRACT -> COMPLETED
    """

    def __init__(self):
        self._plans: Dict[str, ExpandContractPlan] = {}

    def create_plan(self, plan: ExpandContractPlan) -> str:
        """Create a new database expand-contract plan."""
        if plan.plan_id in self._plans:
            raise ValueError(f"Plan {plan.plan_id} already exists.")
        
        plan.phase = DbMigrationPhase.PENDING
        plan.created_at = str(time.time())
        self._plans[plan.plan_id] = plan
        return plan.plan_id

    def validate_plan(self, plan_id: str) -> SchemaValidation:
        """
        Validate plan for breaking changes.
        Rules:
        - DROP_COLUMN/DROP_TABLE without contract phase is a breaking change
        - Non-nullable ADD_COLUMN without default is a breaking change
        """
        if plan_id not in self._plans:
            raise ValueError(f"Plan {plan_id} not found.")
            
        plan = self._plans[plan_id]
        validation = SchemaValidation(
            plan_id=plan_id,
            valid=True,
            breaking_changes=[],
            warnings=[],
            estimated_downtime_seconds=0
        )

        # Validate Expand changes
        for change in plan.expand_changes:
            if change.change_type in (SchemaChangeType.DROP_COLUMN, SchemaChangeType.DROP_TABLE):
                validation.breaking_changes.append(
                    f"DROP operations ({change.change_type.value}) must happen in CONTRACT phase, not EXPAND."
                )
                validation.valid = False
            
            if change.change_type == SchemaChangeType.ADD_COLUMN and not change.nullable and not change.default_value:
                validation.breaking_changes.append(
                    f"Adding non-nullable column '{change.column_name}' without default value is a breaking change."
                )
                validation.valid = False
                
        # Validate Contract changes
        for change in plan.contract_changes:
            if change.change_type in (SchemaChangeType.ADD_COLUMN, SchemaChangeType.ADD_TABLE):
                validation.warnings.append(
                    f"ADD operations ({change.change_type.value}) typically belong in EXPAND phase."
                )

        if not validation.valid:
            validation.estimated_downtime_seconds = 300 # arbitrary downtime for breaking changes
            
        return validation

    def check_phase_transition(self, plan_id: str, target_phase: DbMigrationPhase) -> bool:
        """Validate phase transition order."""
        plan = self.get_plan(plan_id)
        
        transitions = {
            DbMigrationPhase.PENDING: [DbMigrationPhase.EXPAND, DbMigrationPhase.ROLLED_BACK],
            DbMigrationPhase.EXPAND: [DbMigrationPhase.MIGRATE, DbMigrationPhase.ROLLED_BACK],
            DbMigrationPhase.MIGRATE: [DbMigrationPhase.MIGRATE, DbMigrationPhase.CONTRACT, DbMigrationPhase.ROLLED_BACK],
            DbMigrationPhase.CONTRACT: [DbMigrationPhase.COMPLETED, DbMigrationPhase.ROLLED_BACK],
            DbMigrationPhase.COMPLETED: [],
            DbMigrationPhase.ROLLED_BACK: []
        }
        
        return target_phase in transitions[plan.phase]

    def start_expand(self, plan_id: str) -> ExpandContractPlan:
        """Transition to EXPAND phase, block if breaking changes."""
        plan = self.get_plan(plan_id)
        
        if not self.check_phase_transition(plan_id, DbMigrationPhase.EXPAND):
            raise ValueError(f"Invalid transition from {plan.phase} to EXPAND.")
            
        validation = self.validate_plan(plan_id)
        if not validation.valid:
            raise ValueError(f"Cannot start expand: plan has breaking changes: {validation.breaking_changes}")
            
        plan.phase = DbMigrationPhase.EXPAND
        plan.started_at = str(time.time())
        return plan

    def start_migrate(self, plan_id: str, rows_migrated: int) -> ExpandContractPlan:
        """Transition to MIGRATE phase."""
        plan = self.get_plan(plan_id)
        
        if not self.check_phase_transition(plan_id, DbMigrationPhase.MIGRATE):
            raise ValueError(f"Invalid transition from {plan.phase} to MIGRATE.")
            
        plan.phase = DbMigrationPhase.MIGRATE
        plan.rows_migrated += rows_migrated
        return plan

    def start_contract(self, plan_id: str) -> ExpandContractPlan:
        """Transition to CONTRACT phase."""
        plan = self.get_plan(plan_id)
        
        if not self.check_phase_transition(plan_id, DbMigrationPhase.CONTRACT):
            raise ValueError(f"Invalid transition from {plan.phase} to CONTRACT.")
            
        plan.phase = DbMigrationPhase.CONTRACT
        return plan

    def complete_plan(self, plan_id: str) -> ExpandContractPlan:
        """Transition to COMPLETED phase."""
        plan = self.get_plan(plan_id)
        
        if not self.check_phase_transition(plan_id, DbMigrationPhase.COMPLETED):
            raise ValueError(f"Invalid transition from {plan.phase} to COMPLETED.")
            
        plan.phase = DbMigrationPhase.COMPLETED
        plan.completed_at = str(time.time())
        return plan

    def rollback_plan(self, plan_id: str) -> ExpandContractPlan:
        """Rollback plan if not completed."""
        plan = self.get_plan(plan_id)
        
        if plan.phase == DbMigrationPhase.COMPLETED:
            raise ValueError("Cannot rollback a completed plan.")
            
        if plan.phase == DbMigrationPhase.ROLLED_BACK:
            return plan # Already rolled back
            
        plan.phase = DbMigrationPhase.ROLLED_BACK
        plan.completed_at = str(time.time())
        return plan

    def get_plan(self, plan_id: str) -> ExpandContractPlan:
        """Get plan details."""
        if plan_id not in self._plans:
            raise ValueError(f"Plan {plan_id} not found.")
        return self._plans[plan_id]

    def list_plans(self, phase: Optional[DbMigrationPhase] = None) -> List[ExpandContractPlan]:
        """List plans, optionally filtered by phase."""
        if phase:
            return [p for p in self._plans.values() if p.phase == phase]
        return list(self._plans.values())

    def get_migration_report(self) -> Dict:
        """Summary report of migrations."""
        plans_by_phase = {p.value: 0 for p in DbMigrationPhase}
        total_rows_migrated = 0
        total_breaking_changes = 0
        
        for plan in self._plans.values():
            plans_by_phase[plan.phase.value] += 1
            total_rows_migrated += plan.rows_migrated
            
            validation = self.validate_plan(plan.plan_id)
            total_breaking_changes += len(validation.breaking_changes)
            
        return {
            "plans_by_phase": plans_by_phase,
            "total_rows_migrated": total_rows_migrated,
            "total_breaking_changes_detected": total_breaking_changes,
            "total_plans": len(self._plans)
        }

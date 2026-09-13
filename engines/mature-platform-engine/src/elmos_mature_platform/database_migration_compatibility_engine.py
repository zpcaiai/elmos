from typing import Dict, List
from datetime import datetime
from elmos_mature_platform.types import (
    MigrationCompatLevel,
    MigrationSchemaChangeType,
    MigrationSchemaChange,
    DbMigrationScript,
)

class DatabaseMigrationCompatibilityEngine:
    """
    Engine to validate, classify, and manage database migration compatibilities.
    """

    def __init__(self):
        self.changes: Dict[str, MigrationSchemaChange] = {}
        self.scripts: Dict[str, DbMigrationScript] = {}

    def register_change(self, change: MigrationSchemaChange) -> str:
        """Register a schema change."""
        self.changes[change.change_id] = change
        return change.change_id

    def classify_change(self, change_id: str) -> MigrationCompatLevel:
        """Auto-classify a change and return the compat level."""
        if change_id not in self.changes:
            raise ValueError(f"Change {change_id} not found.")

        change = self.changes[change_id]
        ctype = change.change_type

        # Default fallback
        level = MigrationCompatLevel.UNKNOWN

        if ctype == MigrationSchemaChangeType.ADD_COLUMN:
            if change.nullable or change.has_default:
                level = MigrationCompatLevel.FULLY_COMPATIBLE
            else:
                level = MigrationCompatLevel.BREAKING
        elif ctype in (MigrationSchemaChangeType.DROP_COLUMN, MigrationSchemaChangeType.DROP_TABLE):
            level = MigrationCompatLevel.BREAKING
        elif ctype in (MigrationSchemaChangeType.ADD_TABLE, MigrationSchemaChangeType.ADD_INDEX):
            level = MigrationCompatLevel.FULLY_COMPATIBLE
        elif ctype == MigrationSchemaChangeType.DROP_INDEX:
            level = MigrationCompatLevel.BACKWARD_COMPATIBLE
        elif ctype == MigrationSchemaChangeType.MODIFY_COLUMN:
            if change.old_type != change.new_type:
                level = MigrationCompatLevel.BREAKING
            else:
                level = MigrationCompatLevel.BACKWARD_COMPATIBLE
        elif ctype == MigrationSchemaChangeType.RENAME:
            level = MigrationCompatLevel.BREAKING
        elif ctype in (MigrationSchemaChangeType.ADD_CONSTRAINT, MigrationSchemaChangeType.DROP_CONSTRAINT):
            level = MigrationCompatLevel.BREAKING  # General assumption for constraint unless specified

        change.compatibility = level
        return level

    def create_migration(self, script: DbMigrationScript) -> str:
        """Create a new migration script."""
        self.scripts[script.script_id] = script
        return script.script_id

    def validate_migration_order(self, script_ids: List[str]) -> Dict:
        """
        Validate: versions in order, no gaps, all changes covered.
        Returns a validation result dictionary.
        """
        if not script_ids:
            return {"valid": True, "errors": []}

        errors = []
        last_version = None

        for sid in script_ids:
            if sid not in self.scripts:
                errors.append(f"Script {sid} not found.")
                continue

            script = self.scripts[sid]
            
            # Simple version string comparison (or convert to tuples if we assume semantic versioning, 
            # but standard string comparison works if zero-padded or uniform)
            if last_version is not None:
                # To handle versions correctly, let's try splitting by '.' if they look like semver
                # If they are just "1", "2", convert to float for comparison.
                try:
                    v_curr = [int(x) for x in script.version.split('.')]
                    v_prev = [int(x) for x in last_version.split('.')]
                    if v_curr <= v_prev:
                        errors.append(f"Version ordering issue: {script.version} is not > {last_version}.")
                except ValueError:
                    # fallback to string comparison
                    if script.version <= last_version:
                        errors.append(f"Version ordering issue: {script.version} is not > {last_version}.")

            last_version = script.version

            # Check if changes exist
            for cid in script.changes:
                if cid not in self.changes:
                    errors.append(f"Change {cid} referenced in {sid} does not exist.")

        return {
            "valid": len(errors) == 0,
            "errors": errors
        }

    def check_compatibility(self, script_id: str) -> Dict:
        """
        Check if all changes in a script are compatible.
        Identifies any breaking changes.
        """
        if script_id not in self.scripts:
            raise ValueError(f"Script {script_id} not found.")
        
        script = self.scripts[script_id]
        is_fully_compatible = True
        has_breaking = False
        breaking_details = []

        for cid in script.changes:
            change = self.changes.get(cid)
            if not change:
                continue

            if change.compatibility == MigrationCompatLevel.UNKNOWN:
                self.classify_change(cid)

            if change.compatibility == MigrationCompatLevel.BREAKING:
                is_fully_compatible = False
                has_breaking = True
                breaking_details.append(cid)
            elif change.compatibility != MigrationCompatLevel.FULLY_COMPATIBLE:
                is_fully_compatible = False

        if has_breaking and not script.requires_downtime:
            return {
                "compatible": False,
                "has_breaking": True,
                "breaking_changes": breaking_details,
                "error": "Migration has breaking changes but requires_downtime is False."
            }

        return {
            "compatible": not has_breaking,
            "has_breaking": has_breaking,
            "breaking_changes": breaking_details,
            "error": ""
        }

    def mark_reviewed(self, script_id: str, reviewer: str) -> DbMigrationScript:
        """Mark a script as reviewed."""
        if script_id not in self.scripts:
            raise ValueError(f"Script {script_id} not found.")
        script = self.scripts[script_id]
        script.reviewed = True
        return script

    def apply_migration(self, script_id: str) -> DbMigrationScript:
        """Apply a migration (must be reviewed)."""
        if script_id not in self.scripts:
            raise ValueError(f"Script {script_id} not found.")
        
        script = self.scripts[script_id]
        if not script.reviewed:
            raise ValueError(f"Script {script_id} cannot be applied: unreviewed.")

        script.applied = True
        script.applied_at = datetime.utcnow().isoformat()
        return script

    def rollback_migration(self, script_id: str) -> DbMigrationScript:
        """Rollback an applied migration (must have down_sql)."""
        if script_id not in self.scripts:
            raise ValueError(f"Script {script_id} not found.")
        
        script = self.scripts[script_id]
        if not script.applied:
            raise ValueError(f"Script {script_id} cannot be rolled back: not applied.")
        if not script.down_sql:
            raise ValueError(f"Script {script_id} cannot be rolled back: missing down_sql.")

        script.applied = False
        script.applied_at = ""
        return script

    def test_rollback(self, script_id: str) -> bool:
        """Verify down_sql exists and mark rollback_tested."""
        if script_id not in self.scripts:
            raise ValueError(f"Script {script_id} not found.")
        
        script = self.scripts[script_id]
        if not script.down_sql:
            raise ValueError(f"Script {script_id} missing down_sql for testing.")
        
        script.rollback_tested = True
        return True

    def get_migration_plan(self, script_ids: List[str]) -> Dict:
        """
        Ordered plan: estimated time, downtime required, breaking changes.
        """
        plan = []
        total_duration = 0
        any_downtime = False
        all_breaking = []

        # Assuming script_ids are correctly ordered before calling this
        for sid in script_ids:
            if sid not in self.scripts:
                continue
            script = self.scripts[sid]
            comp = self.check_compatibility(sid)

            plan.append({
                "script_id": sid,
                "version": script.version,
                "duration": script.estimated_duration_seconds,
                "downtime": script.requires_downtime,
                "breaking": comp["has_breaking"]
            })

            total_duration += script.estimated_duration_seconds
            if script.requires_downtime:
                any_downtime = True
            all_breaking.extend(comp["breaking_changes"])

        return {
            "plan_steps": plan,
            "total_estimated_duration_seconds": total_duration,
            "requires_downtime": any_downtime,
            "total_breaking_changes": len(all_breaking),
            "breaking_change_ids": all_breaking
        }

    def get_compatibility_report(self) -> Dict:
        """
        Summary: by compatibility level, breaking changes, coverage.
        """
        counts = {
            MigrationCompatLevel.FULLY_COMPATIBLE: 0,
            MigrationCompatLevel.BACKWARD_COMPATIBLE: 0,
            MigrationCompatLevel.BREAKING: 0,
            MigrationCompatLevel.UNKNOWN: 0
        }

        breaking_list = []
        for cid, change in self.changes.items():
            level = change.compatibility
            if level == MigrationCompatLevel.UNKNOWN:
                level = self.classify_change(cid)
            
            counts[level] += 1
            if level == MigrationCompatLevel.BREAKING:
                breaking_list.append(cid)

        total_changes = len(self.changes)
        
        # calculate coverage: changes that are part of at least one script
        covered_changes = set()
        for s in self.scripts.values():
            for c in s.changes:
                covered_changes.add(c)
        
        coverage_pct = 0.0
        if total_changes > 0:
            coverage_pct = (len(covered_changes.intersection(self.changes.keys())) / total_changes) * 100.0

        return {
            "total_changes": total_changes,
            "compatibility_counts": {k.value: v for k, v in counts.items()},
            "breaking_changes": breaking_list,
            "coverage_percentage": coverage_pct
        }

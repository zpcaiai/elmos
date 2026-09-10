from typing import Dict, List, Optional
from datetime import datetime, timezone
import copy

from elmos_mature_platform.types import (
    UpgradePlaybook,
    UpgradeStep,
    UpgradeToolStatus,
    UpgradeToolAction
)

class AutomatedUpgradeToolingEngine:
    """
    Engine for managing automated upgrade tooling for Batch 43.
    """
    def __init__(self):
        self._playbooks: Dict[str, UpgradePlaybook] = {}
        self._steps: Dict[str, Dict[str, UpgradeStep]] = {}  # playbook_id -> step_id -> step

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def create_playbook(self, playbook: UpgradePlaybook) -> str:
        """Create a new upgrade playbook."""
        if playbook.playbook_id in self._playbooks:
            raise ValueError(f"Playbook {playbook.playbook_id} already exists")
        self._playbooks[playbook.playbook_id] = copy.deepcopy(playbook)
        self._steps[playbook.playbook_id] = {}
        return playbook.playbook_id

    def add_step(self, playbook_id: str, step: UpgradeStep) -> UpgradePlaybook:
        """Add a step to the playbook, ensuring proper ordering."""
        if playbook_id not in self._playbooks:
            raise ValueError(f"Playbook {playbook_id} not found")
        
        playbook = self._playbooks[playbook_id]
        if playbook.status != UpgradeToolStatus.PENDING:
            raise ValueError("Can only add steps to PENDING playbooks")
            
        step_dict = self._steps[playbook_id]
        if step.step_id in step_dict:
            raise ValueError(f"Step {step.step_id} already exists in playbook {playbook_id}")

        # Add step
        step_dict[step.step_id] = copy.deepcopy(step)
        
        # Keep steps list in order of their 'order' field
        all_steps = list(step_dict.values())
        all_steps.sort(key=lambda x: x.order)
        playbook.steps = [s.step_id for s in all_steps]
        
        return copy.deepcopy(playbook)

    def validate_playbook(self, playbook_id: str) -> Dict:
        """
        Validate playbook: check preconditions, rollback steps, and circular dependencies.
        """
        if playbook_id not in self._playbooks:
            raise ValueError(f"Playbook {playbook_id} not found")
            
        step_dict = self._steps[playbook_id]
        valid = True
        errors = []
        
        # Check preconditions exist and are before the current step
        # Check rollback steps exist if specified
        # Check circular dependencies
        for step_id, step in step_dict.items():
            if step.rollback_step_id and step.rollback_step_id not in step_dict:
                valid = False
                errors.append(f"Step {step_id} refers to non-existent rollback step {step.rollback_step_id}")
                
            for pre in step.preconditions:
                if pre not in step_dict:
                    valid = False
                    errors.append(f"Step {step_id} has non-existent precondition {pre}")
                else:
                    pre_step = step_dict[pre]
                    if pre_step.order >= step.order:
                        valid = False
                        errors.append(f"Step {step_id} has precondition {pre} with order >= its own order")

        return {
            "valid": valid,
            "errors": errors
        }

    def start_playbook(self, playbook_id: str) -> UpgradePlaybook:
        """Start the execution of the playbook."""
        if playbook_id not in self._playbooks:
            raise ValueError(f"Playbook {playbook_id} not found")
            
        playbook = self._playbooks[playbook_id]
        if playbook.status != UpgradeToolStatus.PENDING:
            raise ValueError(f"Cannot start playbook in status {playbook.status}")
            
        validation = self.validate_playbook(playbook_id)
        if not validation["valid"]:
            raise ValueError(f"Playbook is invalid: {validation['errors']}")
            
        playbook.status = UpgradeToolStatus.RUNNING
        playbook.started_at = self._now()
        playbook.current_step_index = 0
        return copy.deepcopy(playbook)

    def execute_step(self, playbook_id: str, step_id: str) -> UpgradeStep:
        """Execute a step, checking preconditions."""
        if playbook_id not in self._playbooks:
            raise ValueError(f"Playbook {playbook_id} not found")
            
        playbook = self._playbooks[playbook_id]
        if playbook.status != UpgradeToolStatus.RUNNING:
            raise ValueError("Playbook is not RUNNING")
            
        step_dict = self._steps[playbook_id]
        if step_id not in step_dict:
            raise ValueError(f"Step {step_id} not found")
            
        step = step_dict[step_id]
        
        if step.status == UpgradeToolStatus.SUCCESS:
            return copy.deepcopy(step)
            
        # Check preconditions
        for pre in step.preconditions:
            pre_step = step_dict[pre]
            if pre_step.status != UpgradeToolStatus.SUCCESS:
                raise ValueError(f"Precondition {pre} for step {step_id} is not SUCCESS")
                
        # Update current index if this is in the main sequence
        if step_id in playbook.steps:
            playbook.current_step_index = playbook.steps.index(step_id)
            
        step.status = UpgradeToolStatus.SUCCESS
        step.duration_seconds = 10.0  # Simulated duration
        playbook.total_duration_seconds += step.duration_seconds
        
        return copy.deepcopy(step)

    def fail_step(self, playbook_id: str, step_id: str, error: str) -> UpgradeStep:
        """Mark a step as failed and potentially trigger auto rollback."""
        if playbook_id not in self._playbooks:
            raise ValueError(f"Playbook {playbook_id} not found")
            
        playbook = self._playbooks[playbook_id]
        if playbook.status != UpgradeToolStatus.RUNNING:
            raise ValueError("Playbook is not RUNNING")
            
        step_dict = self._steps[playbook_id]
        if step_id not in step_dict:
            raise ValueError(f"Step {step_id} not found")
            
        step = step_dict[step_id]
        step.status = UpgradeToolStatus.FAILED
        step.error_message = error
        playbook.status = UpgradeToolStatus.FAILED
        playbook.completed_at = self._now()
        
        if playbook.auto_rollback:
            self.auto_rollback_playbook(playbook_id)
            
        return copy.deepcopy(step)

    def auto_rollback_playbook(self, playbook_id: str) -> Dict:
        """Rollback all completed steps in reverse order."""
        if playbook_id not in self._playbooks:
            raise ValueError(f"Playbook {playbook_id} not found")
            
        playbook = self._playbooks[playbook_id]
        step_dict = self._steps[playbook_id]
        
        playbook.status = UpgradeToolStatus.ROLLED_BACK
        
        rollback_actions = []
        # Go through steps in reverse order
        reversed_steps = reversed(playbook.steps)
        for s_id in reversed_steps:
            step = step_dict[s_id]
            if step.status == UpgradeToolStatus.SUCCESS:
                if step.rollback_step_id and step.rollback_step_id in step_dict:
                    rollback_step = step_dict[step.rollback_step_id]
                    # execute rollback step
                    rollback_step.status = UpgradeToolStatus.SUCCESS
                    rollback_step.duration_seconds = 5.0
                    playbook.total_duration_seconds += rollback_step.duration_seconds
                    rollback_actions.append(rollback_step.step_id)
                step.status = UpgradeToolStatus.ROLLED_BACK
                
        return {
            "status": "rolled_back",
            "actions_executed": rollback_actions
        }

    def skip_step(self, playbook_id: str, step_id: str, reason: str) -> UpgradeStep:
        """Skip a non-critical step."""
        if playbook_id not in self._playbooks:
            raise ValueError(f"Playbook {playbook_id} not found")
            
        playbook = self._playbooks[playbook_id]
        step_dict = self._steps[playbook_id]
        
        if step_id not in step_dict:
            raise ValueError(f"Step {step_id} not found")
            
        step = step_dict[step_id]
        step.status = UpgradeToolStatus.SKIPPED
        step.error_message = reason
        
        if step_id in playbook.steps:
            playbook.current_step_index = playbook.steps.index(step_id)
            
        return copy.deepcopy(step)

    def get_playbook_progress(self, playbook_id: str) -> Dict:
        """Get the progress of a playbook."""
        if playbook_id not in self._playbooks:
            raise ValueError(f"Playbook {playbook_id} not found")
            
        playbook = self._playbooks[playbook_id]
        step_dict = self._steps[playbook_id]
        
        total = len(playbook.steps)
        completed = sum(1 for s_id in playbook.steps if step_dict[s_id].status in (UpgradeToolStatus.SUCCESS, UpgradeToolStatus.SKIPPED))
        
        current_step_id = playbook.steps[playbook.current_step_index] if playbook.steps and playbook.current_step_index < total else None
        
        return {
            "total_steps": total,
            "completed_steps": completed,
            "current_step_id": current_step_id,
            "total_duration_seconds": playbook.total_duration_seconds,
            "status": playbook.status.value
        }

    def complete_playbook(self, playbook_id: str) -> UpgradePlaybook:
        """Mark playbook as completed if all steps are SUCCESS or SKIPPED."""
        if playbook_id not in self._playbooks:
            raise ValueError(f"Playbook {playbook_id} not found")
            
        playbook = self._playbooks[playbook_id]
        step_dict = self._steps[playbook_id]
        
        for s_id in playbook.steps:
            s = step_dict[s_id]
            if s.status not in (UpgradeToolStatus.SUCCESS, UpgradeToolStatus.SKIPPED):
                raise ValueError(f"Cannot complete: step {s_id} is in status {s.status}")
                
        playbook.status = UpgradeToolStatus.SUCCESS
        playbook.completed_at = self._now()
        
        return copy.deepcopy(playbook)

    def dry_run(self, playbook_id: str) -> Dict:
        """Simulate execution returning projected timeline."""
        if playbook_id not in self._playbooks:
            raise ValueError(f"Playbook {playbook_id} not found")
            
        validation = self.validate_playbook(playbook_id)
        if not validation["valid"]:
            return {"status": "error", "errors": validation["errors"]}
            
        playbook = self._playbooks[playbook_id]
        step_dict = self._steps[playbook_id]
        
        timeline = []
        total_time = 0.0
        
        for s_id in playbook.steps:
            step = step_dict[s_id]
            timeline.append({
                "step_id": s_id,
                "projected_start": total_time,
                "projected_duration": 10.0,
                "action": step.action.value
            })
            total_time += 10.0
            
        return {
            "status": "success",
            "projected_total_duration": total_time,
            "timeline": timeline
        }

    def get_upgrade_report(self) -> Dict:
        """Get aggregate report across all playbooks."""
        by_status = {}
        total_duration = 0.0
        success_count = 0
        total = len(self._playbooks)
        
        for p in self._playbooks.values():
            status_val = p.status.value
            by_status[status_val] = by_status.get(status_val, 0) + 1
            if p.status == UpgradeToolStatus.SUCCESS:
                success_count += 1
                total_duration += p.total_duration_seconds
                
        avg_duration = (total_duration / success_count) if success_count > 0 else 0.0
        success_rate = (success_count / total * 100.0) if total > 0 else 0.0
        
        return {
            "total_playbooks": total,
            "by_status": by_status,
            "avg_duration_successful_seconds": avg_duration,
            "success_rate_percentage": success_rate
        }

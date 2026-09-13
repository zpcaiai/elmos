import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from elmos_mature_platform.types import (
    WorkflowState,
    CheckpointType,
    WorkflowCheckpoint,
    WorkflowExecution,
    RecoveryPlan
)


class WorkflowVersionRecoveryEngine:
    """
    Engine for managing long-running workflow version recovery, checkpoints, and idempotency.
    """

    def __init__(self):
        # In-memory storage for workflows and checkpoints
        self._workflows: Dict[str, WorkflowExecution] = {}
        self._checkpoints: Dict[str, WorkflowCheckpoint] = {}
        self._idempotency_map: Dict[str, str] = {}  # idempotency_key -> workflow_id

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _generate_checksum(self, state: Dict[str, Any]) -> str:
        state_str = json.dumps(state, sort_keys=True)
        return hashlib.sha256(state_str.encode("utf-8")).hexdigest()

    def create_workflow(self, execution: WorkflowExecution) -> str:
        """Create a new workflow execution or return existing one if idempotency_key matches."""
        if execution.idempotency_key:
            existing = self.check_idempotency(execution.idempotency_key)
            if existing:
                return existing.workflow_id
            
        workflow_id = execution.workflow_id or str(uuid.uuid4())
        execution.workflow_id = workflow_id
        execution.state = WorkflowState.RUNNING
        execution.started_at = self._now()
        
        self._workflows[workflow_id] = execution
        
        if execution.idempotency_key:
            self._idempotency_map[execution.idempotency_key] = workflow_id
            
        return workflow_id

    def advance_step(self, workflow_id: str) -> WorkflowExecution:
        """Advance workflow to next step. Auto-checkpoint every 5 steps."""
        if workflow_id not in self._workflows:
            raise ValueError(f"Workflow {workflow_id} not found")
            
        workflow = self._workflows[workflow_id]
        if workflow.state != WorkflowState.RUNNING:
            raise ValueError(f"Workflow {workflow_id} is not in RUNNING state (current state: {workflow.state})")
            
        if workflow.current_step >= workflow.total_steps:
            workflow.state = WorkflowState.COMPLETED
            workflow.completed_at = self._now()
            return workflow
            
        workflow.current_step += 1
        
        # Auto-checkpoint every 5 steps
        if workflow.current_step % 5 == 0 and workflow.current_step < workflow.total_steps:
            self.create_checkpoint(
                workflow_id=workflow_id,
                checkpoint_type=CheckpointType.AUTOMATIC,
                state={"step": workflow.current_step, "auto": True}
            )
            
        if workflow.current_step == workflow.total_steps:
            workflow.state = WorkflowState.COMPLETED
            workflow.completed_at = self._now()
            
        return workflow

    def create_checkpoint(self, workflow_id: str, checkpoint_type: CheckpointType, state: Dict[str, Any]) -> WorkflowCheckpoint:
        """Create a checkpoint for a RUNNING workflow with SHA-256 checksum."""
        if workflow_id not in self._workflows:
            raise ValueError(f"Workflow {workflow_id} not found")
            
        workflow = self._workflows[workflow_id]
        if workflow.state != WorkflowState.RUNNING:
            raise ValueError(f"Workflow {workflow_id} is not RUNNING")
            
        checkpoint_id = str(uuid.uuid4())
        checksum = self._generate_checksum(state)
        
        checkpoint = WorkflowCheckpoint(
            checkpoint_id=checkpoint_id,
            workflow_id=workflow_id,
            step_index=workflow.current_step,
            checkpoint_type=checkpoint_type,
            state_snapshot=state,
            created_at=self._now(),
            version=workflow.version,
            checksum=checksum
        )
        
        self._checkpoints[checkpoint_id] = checkpoint
        workflow.checkpoints.append(checkpoint_id)
        
        return checkpoint

    def pause_workflow(self, workflow_id: str) -> WorkflowExecution:
        """Pause a running workflow."""
        if workflow_id not in self._workflows:
            raise ValueError(f"Workflow {workflow_id} not found")
            
        workflow = self._workflows[workflow_id]
        if workflow.state != WorkflowState.RUNNING:
            raise ValueError(f"Only RUNNING workflows can be paused")
            
        workflow.state = WorkflowState.PAUSED
        return workflow

    def resume_workflow(self, workflow_id: str) -> WorkflowExecution:
        """Resume a paused workflow."""
        if workflow_id not in self._workflows:
            raise ValueError(f"Workflow {workflow_id} not found")
            
        workflow = self._workflows[workflow_id]
        if workflow.state != WorkflowState.PAUSED:
            raise ValueError(f"Only PAUSED workflows can be resumed")
            
        workflow.state = WorkflowState.RUNNING
        return workflow

    def fail_workflow(self, workflow_id: str, error: str) -> WorkflowExecution:
        """Mark a workflow as failed."""
        if workflow_id not in self._workflows:
            raise ValueError(f"Workflow {workflow_id} not found")
            
        workflow = self._workflows[workflow_id]
        workflow.state = WorkflowState.FAILED
        workflow.error_message = error
        workflow.completed_at = self._now()
        return workflow

    def plan_recovery(self, workflow_id: str) -> RecoveryPlan:
        """Find latest checkpoint and plan recovery."""
        if workflow_id not in self._workflows:
            raise ValueError(f"Workflow {workflow_id} not found")
            
        workflow = self._workflows[workflow_id]
        
        if not workflow.checkpoints:
            raise ValueError(f"No checkpoints found for workflow {workflow_id}")
            
        # Get the latest checkpoint
        latest_checkpoint_id = workflow.checkpoints[-1]
        latest_checkpoint = self._checkpoints[latest_checkpoint_id]
        
        return RecoveryPlan(
            workflow_id=workflow_id,
            from_checkpoint_id=latest_checkpoint_id,
            resume_step=latest_checkpoint.step_index,
            version_compatible=True,
            migration_needed=False,
            estimated_steps_remaining=workflow.total_steps - latest_checkpoint.step_index
        )

    def recover_workflow(self, workflow_id: str) -> WorkflowExecution:
        """Recover from latest checkpoint, increment retry_count."""
        if workflow_id not in self._workflows:
            raise ValueError(f"Workflow {workflow_id} not found")
            
        workflow = self._workflows[workflow_id]
        if workflow.state != WorkflowState.FAILED:
            raise ValueError(f"Only FAILED workflows can be recovered")
            
        if workflow.retry_count >= workflow.max_retries:
            raise RuntimeError(f"Max retries ({workflow.max_retries}) exceeded for workflow {workflow_id}")
            
        workflow.retry_count += 1
        workflow.state = WorkflowState.RECOVERING
        
        plan = self.plan_recovery(workflow_id)
        
        # Reset to checkpoint step
        workflow.current_step = plan.resume_step
        workflow.state = WorkflowState.RUNNING
        workflow.error_message = ""
        workflow.completed_at = ""
        
        return workflow

    def cancel_workflow(self, workflow_id: str) -> WorkflowExecution:
        """Cancel workflow."""
        if workflow_id not in self._workflows:
            raise ValueError(f"Workflow {workflow_id} not found")
            
        workflow = self._workflows[workflow_id]
        workflow.state = WorkflowState.CANCELLED
        workflow.completed_at = self._now()
        return workflow

    def check_version_compatibility(self, workflow_id: str, new_version: str) -> bool:
        """Check if workflow can resume under new version."""
        if workflow_id not in self._workflows:
            raise ValueError(f"Workflow {workflow_id} not found")
            
        workflow = self._workflows[workflow_id]
        # In a real system, this would check a compatibility matrix
        # For this implementation, we'll assume matching major versions are compatible
        def get_major(v): return v.split('.')[0] if '.' in v else v
        
        return get_major(workflow.version) == get_major(new_version)

    def get_workflow_report(self) -> Dict[str, Any]:
        """Summary: by state, checkpoints, recovery stats"""
        report = {
            "total_workflows": len(self._workflows),
            "by_state": {},
            "total_checkpoints": len(self._checkpoints),
            "total_retries": 0,
            "failed_permanently": 0
        }
        
        for state in WorkflowState:
            report["by_state"][state.value] = 0
            
        for workflow in self._workflows.values():
            report["by_state"][workflow.state.value] += 1
            report["total_retries"] += workflow.retry_count
            if workflow.state == WorkflowState.FAILED and workflow.retry_count >= workflow.max_retries:
                report["failed_permanently"] += 1
                
        return report

    def check_idempotency(self, idempotency_key: str) -> Optional[WorkflowExecution]:
        """Return existing workflow if key matches."""
        if idempotency_key in self._idempotency_map:
            workflow_id = self._idempotency_map[idempotency_key]
            return self._workflows.get(workflow_id)
        return None

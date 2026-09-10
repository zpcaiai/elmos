from typing import List, Dict, Optional
from datetime import datetime, timezone
import uuid

from elmos_mature_platform.types import (
    ExecutionMode,
    StepOutcome,
    ExecutionStep,
    DeterministicExecution,
    ReplayVerification
)

class DeterministicExecutionEngine:
    def __init__(self):
        self._executions: Dict[str, DeterministicExecution] = {}
        self._steps: Dict[str, List[ExecutionStep]] = {}

    def create_execution(self, execution: DeterministicExecution) -> str:
        if not execution.execution_id:
            execution.execution_id = str(uuid.uuid4())
        if not execution.started_at:
            execution.started_at = datetime.now(timezone.utc).isoformat()
        
        self._executions[execution.execution_id] = execution
        self._steps[execution.execution_id] = []
        return execution.execution_id

    def record_step(self, step: ExecutionStep) -> None:
        if step.execution_id not in self._executions:
            raise ValueError(f"Execution {step.execution_id} not found")
            
        execution = self._executions[step.execution_id]
        steps = self._steps[step.execution_id]
        
        if step.step_index != len(steps):
            raise ValueError(f"Step index {step.step_index} is not sequential, expected {len(steps)}")
            
        if not step.timestamp:
            step.timestamp = datetime.now(timezone.utc).isoformat()
            
        steps.append(step)
        execution.total_steps = len(steps)
        if step.outcome == StepOutcome.SUCCESS:
            execution.completed_steps += 1
            
        execution.determinism_score = self.compute_determinism_score(step.execution_id)

    def get_steps(self, execution_id: str) -> List[ExecutionStep]:
        if execution_id not in self._steps:
            raise ValueError(f"Execution {execution_id} not found")
        return self._steps[execution_id].copy()

    def compute_determinism_score(self, execution_id: str) -> float:
        steps = self.get_steps(execution_id)
        if not steps:
            return 1.0
        deterministic_count = sum(1 for s in steps if s.deterministic)
        return deterministic_count / len(steps)

    def start_replay(self, execution_id: str) -> DeterministicExecution:
        if execution_id not in self._executions:
            raise ValueError(f"Execution {execution_id} not found")
            
        original = self._executions[execution_id]
        
        replay_id = str(uuid.uuid4())
        replay = DeterministicExecution(
            execution_id=replay_id,
            agent_id=original.agent_id,
            mode=ExecutionMode.REPLAY,
            seed=original.seed,
            replay_source_id=execution_id,
            started_at=datetime.now(timezone.utc).isoformat()
        )
        self.create_execution(replay)
        return replay

    def verify_replay(self, original_id: str, replay_id: str) -> ReplayVerification:
        if original_id not in self._executions or replay_id not in self._executions:
            raise ValueError("Execution not found")
            
        orig_steps = self.get_steps(original_id)
        replay_steps = self.get_steps(replay_id)
        
        verification = ReplayVerification(
            execution_id=original_id,
            replay_id=replay_id
        )
        
        for i, replay_step in enumerate(replay_steps):
            if i >= len(orig_steps):
                break
                
            orig_step = orig_steps[i]
            if orig_step.input_hash == replay_step.input_hash and orig_step.output_hash == replay_step.output_hash:
                verification.steps_matched += 1
            else:
                verification.steps_diverged += 1
                verification.divergence_points.append(i)
                
        verification.fully_deterministic = (verification.steps_diverged == 0 and len(replay_steps) == len(orig_steps))
        return verification

    def get_divergence_report(self, original_id: str, replay_id: str) -> Dict:
        verification = self.verify_replay(original_id, replay_id)
        orig_steps = self.get_steps(original_id)
        replay_steps = self.get_steps(replay_id)
        
        details = []
        for point in verification.divergence_points:
            details.append({
                "step_index": point,
                "original": {
                    "input_hash": orig_steps[point].input_hash,
                    "output_hash": orig_steps[point].output_hash
                },
                "replay": {
                    "input_hash": replay_steps[point].input_hash,
                    "output_hash": replay_steps[point].output_hash
                }
            })
            
        return {
            "execution_id": original_id,
            "replay_id": replay_id,
            "fully_deterministic": verification.fully_deterministic,
            "divergence_details": details
        }

    def set_deterministic_seed(self, execution_id: str, seed: int) -> None:
        if execution_id not in self._executions:
            raise ValueError(f"Execution {execution_id} not found")
            
        if len(self._steps[execution_id]) > 0:
            raise ValueError("Cannot change seed after steps have been recorded")
            
        self._executions[execution_id].seed = seed

    def mark_step_nondeterministic(self, step_id: str) -> ExecutionStep:
        for execution_id, steps in self._steps.items():
            for step in steps:
                if step.step_id == step_id:
                    step.deterministic = False
                    self._executions[execution_id].determinism_score = self.compute_determinism_score(execution_id)
                    return step
        raise ValueError(f"Step {step_id} not found")

    def get_execution_trace(self, execution_id: str) -> Dict:
        if execution_id not in self._executions:
            raise ValueError(f"Execution {execution_id} not found")
            
        execution = self._executions[execution_id]
        steps = self.get_steps(execution_id)
        
        return {
            "execution_id": execution.execution_id,
            "agent_id": execution.agent_id,
            "mode": execution.mode,
            "seed": execution.seed,
            "determinism_score": execution.determinism_score,
            "steps": [
                {
                    "step_id": s.step_id,
                    "index": s.step_index,
                    "action": s.action,
                    "input_hash": s.input_hash,
                    "output_hash": s.output_hash,
                    "outcome": s.outcome,
                    "deterministic": s.deterministic
                } for s in steps
            ]
        }

    def get_execution_report(self) -> Dict:
        total_executions = len(self._executions)
        if total_executions == 0:
            return {
                "total_executions": 0,
                "average_determinism_score": 1.0,
                "total_replays": 0,
                "overall_divergence_rate": 0.0
            }
            
        total_score = sum(e.determinism_score for e in self._executions.values())
        replays = [e for e in self._executions.values() if e.mode == ExecutionMode.REPLAY]
        
        total_replay_steps = 0
        total_diverged_steps = 0
        
        for replay in replays:
            original_id = replay.replay_source_id
            if original_id in self._executions:
                orig_steps = self.get_steps(original_id)
                replay_steps = self.get_steps(replay.execution_id)
                
                total_replay_steps += min(len(orig_steps), len(replay_steps))
                
                for i in range(min(len(orig_steps), len(replay_steps))):
                    if orig_steps[i].input_hash != replay_steps[i].input_hash or orig_steps[i].output_hash != replay_steps[i].output_hash:
                        total_diverged_steps += 1
                        
        divergence_rate = total_diverged_steps / total_replay_steps if total_replay_steps > 0 else 0.0
        
        return {
            "total_executions": total_executions,
            "average_determinism_score": total_score / total_executions,
            "total_replays": len(replays),
            "overall_divergence_rate": divergence_rate
        }

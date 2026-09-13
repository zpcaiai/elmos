from typing import List, Dict, Optional
from datetime import datetime

from elmos_mature_platform.types import (
    DrExerciseType,
    DrExerciseStatus,
    DrExercise,
    DrSchedule
)

class ScheduledRestoreDrExerciseEngine:
    """Engine for scheduling, running, and tracking Disaster Recovery (DR) exercises."""

    def __init__(self):
        self._schedules: Dict[str, DrSchedule] = {}
        self._exercises: Dict[str, DrExercise] = {}

    def create_schedule(self, schedule: DrSchedule) -> str:
        """Create a new DR exercise schedule."""
        self._schedules[schedule.schedule_id] = schedule
        return schedule.schedule_id

    def create_exercise(self, exercise: DrExercise) -> str:
        """Create a new DR exercise."""
        self._exercises[exercise.exercise_id] = exercise
        return exercise.exercise_id

    def start_exercise(self, exercise_id: str) -> DrExercise:
        """Move an exercise to IN_PROGRESS status."""
        if exercise_id not in self._exercises:
            raise ValueError(f"Exercise {exercise_id} not found")
        
        exercise = self._exercises[exercise_id]
        if exercise.status != DrExerciseStatus.SCHEDULED:
            raise ValueError(f"Exercise {exercise_id} cannot be started from status {exercise.status}")

        exercise.status = DrExerciseStatus.IN_PROGRESS
        exercise.started_at = datetime.utcnow().isoformat()
        return exercise

    def complete_exercise(self, exercise_id: str, actual_rto: int, actual_rpo: int, findings: List[str]) -> DrExercise:
        """Record results and check pass/fail."""
        if exercise_id not in self._exercises:
            raise ValueError(f"Exercise {exercise_id} not found")
        
        exercise = self._exercises[exercise_id]
        if exercise.status != DrExerciseStatus.IN_PROGRESS:
            raise ValueError(f"Exercise {exercise_id} cannot be completed from status {exercise.status}")

        exercise.status = DrExerciseStatus.COMPLETED
        exercise.completed_at = datetime.utcnow().isoformat()
        exercise.actual_rto_minutes = actual_rto
        exercise.actual_rpo_minutes = actual_rpo
        exercise.findings.extend(findings)

        # Check pass/fail (pass if actual <= target for both)
        if actual_rto <= exercise.target_rto_minutes and actual_rpo <= exercise.target_rpo_minutes:
            exercise.passed = True
        else:
            exercise.passed = False

        # Update last_executed on the schedule if we can find one matching the type
        # For simplicity, we just find any schedule of this type and update its last_executed
        for schedule in self._schedules.values():
            if schedule.exercise_type == exercise.exercise_type:
                schedule.last_executed = exercise.completed_at
                # Could update next_scheduled here based on frequency_days

        return exercise

    def fail_exercise(self, exercise_id: str, reason: str) -> DrExercise:
        """Mark an exercise as failed."""
        if exercise_id not in self._exercises:
            raise ValueError(f"Exercise {exercise_id} not found")
        
        exercise = self._exercises[exercise_id]
        exercise.status = DrExerciseStatus.FAILED
        exercise.findings.append(f"Failed: {reason}")
        exercise.passed = False
        return exercise

    def cancel_exercise(self, exercise_id: str) -> DrExercise:
        """Cancel a scheduled exercise."""
        if exercise_id not in self._exercises:
            raise ValueError(f"Exercise {exercise_id} not found")
        
        exercise = self._exercises[exercise_id]
        if exercise.status not in [DrExerciseStatus.SCHEDULED, DrExerciseStatus.IN_PROGRESS]:
            raise ValueError(f"Exercise {exercise_id} cannot be cancelled from status {exercise.status}")

        exercise.status = DrExerciseStatus.CANCELLED
        return exercise

    def get_overdue_exercises(self) -> List[DrSchedule]:
        """Get schedules past their next_scheduled date."""
        overdue = []
        now = datetime.utcnow().isoformat()
        for schedule in self._schedules.values():
            if schedule.next_scheduled and schedule.next_scheduled < now:
                overdue.append(schedule)
        return overdue

    def get_exercise_history(self, exercise_type: Optional[DrExerciseType] = None) -> List[DrExercise]:
        """Get history of exercises, optionally filtered by type."""
        history = list(self._exercises.values())
        if exercise_type:
            history = [e for e in history if e.exercise_type == exercise_type]
        return history

    def get_rto_rpo_trends(self) -> Dict:
        """Calculate average actual RTO/RPO over time to show improving/degrading trends."""
        trends = {
            "avg_rto_minutes": 0.0,
            "avg_rpo_minutes": 0.0,
            "trend": "unknown"
        }
        
        completed = [e for e in self._exercises.values() if e.status == DrExerciseStatus.COMPLETED]
        if not completed:
            return trends
            
        total_rto = sum(e.actual_rto_minutes for e in completed)
        total_rpo = sum(e.actual_rpo_minutes for e in completed)
        
        trends["avg_rto_minutes"] = total_rto / len(completed)
        trends["avg_rpo_minutes"] = total_rpo / len(completed)
        
        # Simple trend calc: compare first half to second half
        completed.sort(key=lambda e: e.completed_at)
        mid = len(completed) // 2
        if mid > 0:
            first_half = completed[:mid]
            second_half = completed[mid:]
            
            avg_rto_first = sum(e.actual_rto_minutes for e in first_half) / len(first_half)
            avg_rto_second = sum(e.actual_rto_minutes for e in second_half) / len(second_half)
            
            if avg_rto_second < avg_rto_first:
                trends["trend"] = "improving"
            elif avg_rto_second > avg_rto_first:
                trends["trend"] = "degrading"
            else:
                trends["trend"] = "stable"
                
        return trends

    def get_compliance_status(self) -> Dict:
        """Get compliance status for all schedules."""
        status = {
            "on_time_percent": 0.0,
            "overdue_count": len(self.get_overdue_exercises()),
            "schedules": {}
        }
        
        if not self._schedules:
            return status
            
        on_time = len(self._schedules) - status["overdue_count"]
        status["on_time_percent"] = (on_time / len(self._schedules)) * 100
        
        for schedule_id, schedule in self._schedules.items():
            # Find the last completed exercise for this type
            history = [e for e in self._exercises.values() if e.exercise_type == schedule.exercise_type and e.status == DrExerciseStatus.COMPLETED]
            history.sort(key=lambda e: e.completed_at, reverse=True)
            
            last_passed = False
            if history:
                last_passed = history[0].passed
                
            is_overdue = schedule.next_scheduled and schedule.next_scheduled < datetime.utcnow().isoformat()
            
            status["schedules"][schedule_id] = {
                "is_overdue": bool(is_overdue),
                "last_passed": last_passed
            }
            
        return status

    def get_dr_report(self) -> Dict:
        """Get a comprehensive report of DR exercises."""
        report = {
            "by_type": {},
            "overall_pass_rate": 0.0,
            "total_findings": 0,
            "coverage": list(self._schedules.keys())
        }
        
        completed = [e for e in self._exercises.values() if e.status == DrExerciseStatus.COMPLETED]
        if not completed:
            return report
            
        passes = sum(1 for e in completed if e.passed)
        report["overall_pass_rate"] = (passes / len(completed)) * 100
        
        for exercise in self._exercises.values():
            report["total_findings"] += len(exercise.findings)
            
            t = exercise.exercise_type.value
            if t not in report["by_type"]:
                report["by_type"][t] = {
                    "count": 0,
                    "passes": 0,
                    "avg_rto": 0.0,
                    "avg_rpo": 0.0
                }
                
            report["by_type"][t]["count"] += 1
            if exercise.passed:
                report["by_type"][t]["passes"] += 1
                
        # Calculate averages
        for t, data in report["by_type"].items():
            type_completed = [e for e in completed if e.exercise_type.value == t]
            if type_completed:
                data["avg_rto"] = sum(e.actual_rto_minutes for e in type_completed) / len(type_completed)
                data["avg_rpo"] = sum(e.actual_rpo_minutes for e in type_completed) / len(type_completed)
                
        return report

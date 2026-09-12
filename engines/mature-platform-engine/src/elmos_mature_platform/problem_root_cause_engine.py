from typing import Dict, List, Optional
from datetime import datetime
from elmos_mature_platform.types import (
    ProblemRecord, ProblemStatus, ProblemPriority,
    RcaFinding, CorrectiveAction
)

class ProblemRootCauseEngine:
    """Engine for performing problem root cause analysis and management."""

    def __init__(self):
        self.problems: Dict[str, ProblemRecord] = {}
        self.findings: Dict[str, List[RcaFinding]] = {}
        self.actions: Dict[str, List[CorrectiveAction]] = {}
        self._current_time_fn = lambda: datetime.utcnow().isoformat()

    def set_time_fn(self, time_fn):
        """Set a custom time provider function (mainly for testing)."""
        self._current_time_fn = time_fn

    def create_problem(self, record: ProblemRecord) -> str:
        """Create a new problem record."""
        if not record.created_at:
            record.created_at = self._current_time_fn()
        self.problems[record.problem_id] = record
        self.findings[record.problem_id] = []
        self.actions[record.problem_id] = []
        return record.problem_id

    def start_investigation(self, problem_id: str) -> ProblemRecord:
        """Move problem status to INVESTIGATING."""
        if problem_id not in self.problems:
            raise ValueError(f"Problem {problem_id} not found")
        
        prob = self.problems[problem_id]
        if prob.status not in (ProblemStatus.OPEN, ProblemStatus.INVESTIGATING):
            raise ValueError(f"Cannot start investigation from status {prob.status}")
        
        prob.status = ProblemStatus.INVESTIGATING
        return prob

    def add_finding(self, finding: RcaFinding):
        """Add an RCA finding to a problem."""
        if finding.problem_id not in self.problems:
            raise ValueError(f"Problem {finding.problem_id} not found")
            
        prob = self.problems[finding.problem_id]
        if prob.status == ProblemStatus.OPEN:
            raise ValueError("Must start investigation before adding findings")
            
        self.findings[finding.problem_id].append(finding)

    def identify_root_cause(self, problem_id: str, root_cause: str) -> ProblemRecord:
        """Set root cause and move to ROOT_CAUSE_IDENTIFIED."""
        if problem_id not in self.problems:
            raise ValueError(f"Problem {problem_id} not found")
            
        prob = self.problems[problem_id]
        if prob.status != ProblemStatus.INVESTIGATING:
            raise ValueError("Problem must be INVESTIGATING to identify root cause")
            
        prob.root_cause = root_cause
        prob.status = ProblemStatus.ROOT_CAUSE_IDENTIFIED
        return prob

    def add_corrective_action(self, action: CorrectiveAction):
        """Add a corrective action to a problem."""
        if action.problem_id not in self.problems:
            raise ValueError(f"Problem {action.problem_id} not found")
            
        prob = self.problems[action.problem_id]
        if prob.status not in (ProblemStatus.ROOT_CAUSE_IDENTIFIED, ProblemStatus.FIX_IN_PROGRESS):
            raise ValueError("Root cause must be identified before adding corrective actions")
            
        self.actions[action.problem_id].append(action)
        prob.status = ProblemStatus.FIX_IN_PROGRESS

    def complete_action(self, action_id: str) -> CorrectiveAction:
        """Mark a corrective action as completed."""
        for actions_list in self.actions.values():
            for action in actions_list:
                if action.action_id == action_id:
                    action.completed = True
                    return action
        raise ValueError(f"Action {action_id} not found")

    def verify_action(self, action_id: str, effectiveness: float) -> CorrectiveAction:
        """Verify action effectiveness."""
        for actions_list in self.actions.values():
            for action in actions_list:
                if action.action_id == action_id:
                    if not action.completed:
                        raise ValueError(f"Action {action_id} must be completed before verification")
                    action.verified = True
                    action.effectiveness_score = max(0.0, min(1.0, effectiveness))
                    return action
        raise ValueError(f"Action {action_id} not found")

    def resolve_problem(self, problem_id: str, fix_description: str) -> ProblemRecord:
        """Resolve problem, requires all actions to be complete."""
        if problem_id not in self.problems:
            raise ValueError(f"Problem {problem_id} not found")
            
        prob = self.problems[problem_id]
        if prob.status not in (ProblemStatus.ROOT_CAUSE_IDENTIFIED, ProblemStatus.FIX_IN_PROGRESS):
            raise ValueError("Cannot resolve without root cause identification and fixes")
            
        # Check all actions are completed
        actions_list = self.actions.get(problem_id, [])
        for action in actions_list:
            if not action.completed:
                raise ValueError("All corrective actions must be completed before resolving")
                
        prob.fix_description = fix_description
        prob.status = ProblemStatus.RESOLVED
        prob.resolved_at = self._current_time_fn()
        return prob

    def link_incident(self, problem_id: str, incident_id: str):
        """Link an incident to the problem."""
        if problem_id not in self.problems:
            raise ValueError(f"Problem {problem_id} not found")
        prob = self.problems[problem_id]
        if incident_id not in prob.related_incidents:
            prob.related_incidents.append(incident_id)

    def detect_recurrence(self, problem_id: str) -> bool:
        """Check if same root cause appeared in other problems. Increments recurrence count if so."""
        if problem_id not in self.problems:
            raise ValueError(f"Problem {problem_id} not found")
            
        prob = self.problems[problem_id]
        if not prob.root_cause:
            return False
            
        count = 0
        for p_id, p in self.problems.items():
            if p_id != problem_id and p.root_cause == prob.root_cause:
                count += 1
                
        if count > 0:
            prob.recurrence_count = count
            return True
        return False

    def get_problem_report(self) -> Dict:
        """Get summary report of problems."""
        status_counts = {s.value: 0 for s in ProblemStatus}
        priority_counts = {p.value: 0 for p in ProblemPriority}
        top_root_causes = {}
        
        total_resolve_time = 0.0
        resolved_count = 0
        
        for prob in self.problems.values():
            status_counts[prob.status.value] += 1
            priority_counts[prob.priority.value] += 1
            
            if prob.root_cause:
                top_root_causes[prob.root_cause] = top_root_causes.get(prob.root_cause, 0) + 1
                
            if prob.status == ProblemStatus.RESOLVED and prob.created_at and prob.resolved_at:
                try:
                    c_time = datetime.fromisoformat(prob.created_at)
                    r_time = datetime.fromisoformat(prob.resolved_at)
                    total_resolve_time += (r_time - c_time).total_seconds()
                    resolved_count += 1
                except ValueError:
                    pass

        avg_time = (total_resolve_time / resolved_count) if resolved_count > 0 else 0.0
        
        sorted_causes = sorted(top_root_causes.items(), key=lambda x: x[1], reverse=True)[:5]
        
        return {
            "by_status": status_counts,
            "by_priority": priority_counts,
            "avg_resolve_time_seconds": avg_time,
            "top_root_causes": dict(sorted_causes),
            "total_problems": len(self.problems)
        }

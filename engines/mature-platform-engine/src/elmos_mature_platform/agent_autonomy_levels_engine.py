import time
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from elmos_mature_platform.types import (
    AgentAutonomyLevel,
    AutonomyReviewDecision,
    AgentAutonomyProfile,
    AutonomyLevelTransition,
    AutonomyEnforcementGate
)

class AgentAutonomyLevelsEngine:
    """Engine for managing agent autonomy levels and governance."""

    def __init__(self):
        self._profiles: Dict[str, AgentAutonomyProfile] = {}
        self._transitions: Dict[str, List[AutonomyLevelTransition]] = {}
        
        self._tier_order = {
            AgentAutonomyLevel.L0_MANUAL: 0,
            AgentAutonomyLevel.L1_SUGGESTION: 1,
            AgentAutonomyLevel.L2_SUPERVISED: 2,
            AgentAutonomyLevel.L3_BOUNDED_AUTONOMOUS: 3,
            AgentAutonomyLevel.L4_FULL_AUTONOMOUS: 4
        }
        self._order_to_tier = {v: k for k, v in self._tier_order.items()}

    def register_agent(self, profile: AgentAutonomyProfile) -> str:
        """Register a new agent profile."""
        if profile.agent_id in self._profiles:
            raise ValueError(f"Agent {profile.agent_id} already exists")
        self._profiles[profile.agent_id] = profile
        self._transitions[profile.agent_id] = []
        return profile.agent_id

    def record_run_result(self, agent_id: str, success: bool, had_policy_violation: bool = False) -> AgentAutonomyProfile:
        """Record the result of an agent run and update metrics."""
        profile = self.get_agent_profile(agent_id)
        if not profile:
            raise ValueError(f"Agent {agent_id} not found")

        if success:
            profile.successful_runs += 1
            profile.consecutive_successes += 1
            profile.evaluation_score = min(100.0, profile.evaluation_score + 1.0)
        else:
            profile.failed_runs += 1
            profile.consecutive_successes = 0
            profile.evaluation_score = max(0.0, profile.evaluation_score - 5.0)

        if had_policy_violation:
            profile.policy_violations += 1
            profile.evaluation_score = max(0.0, profile.evaluation_score - 20.0)

        return profile

    def evaluate_autonomy_level(self, agent_id: str, reviewer: str = "system") -> AutonomyLevelTransition:
        """Evaluate and potentially adjust the agent's autonomy level."""
        profile = self.get_agent_profile(agent_id)
        if not profile:
            raise ValueError(f"Agent {agent_id} not found")

        current_val = self._tier_order[profile.current_tier]
        max_val = self._tier_order[profile.max_permitted_tier]
        
        new_tier = profile.current_tier
        decision = AutonomyReviewDecision.MAINTAINED
        reason = "Performance within normal bounds"

        if profile.policy_violations > 0 or profile.evaluation_score < 60:
            if profile.policy_violations > 2:
                new_tier = AgentAutonomyLevel.L0_MANUAL
                reason = "Excessive policy violations"
            else:
                new_tier = self._order_to_tier[max(0, current_val - 1)]
                reason = "Poor performance or policy violation"
            decision = AutonomyReviewDecision.DEMOTED
        elif profile.consecutive_successes >= 10 and profile.evaluation_score >= 90:
            if current_val < max_val:
                new_tier = self._order_to_tier[current_val + 1]
                reason = "Excellent performance and high reliability"
                decision = AutonomyReviewDecision.PROMOTED
            else:
                reason = "Excellent performance but at max permitted tier"

        transition = AutonomyLevelTransition(
            transition_id=str(uuid.uuid4()),
            agent_id=agent_id,
            from_tier=profile.current_tier,
            to_tier=new_tier,
            decision=decision,
            reason=reason,
            reviewer=reviewer,
            evaluated_at=datetime.now(timezone.utc).isoformat(),
            audit_receipt=f"audit-{uuid.uuid4()}"
        )

        profile.current_tier = new_tier
        profile.last_evaluated_at = transition.evaluated_at
        self._transitions[agent_id].append(transition)

        return transition

    def request_tier_elevation(self, agent_id: str, target_tier: AgentAutonomyLevel, justification: str, approver: str) -> AutonomyLevelTransition:
        """Manually override and elevate an agent's max permitted and current tier."""
        profile = self.get_agent_profile(agent_id)
        if not profile:
            raise ValueError(f"Agent {agent_id} not found")

        transition = AutonomyLevelTransition(
            transition_id=str(uuid.uuid4()),
            agent_id=agent_id,
            from_tier=profile.current_tier,
            to_tier=target_tier,
            decision=AutonomyReviewDecision.PROMOTED,
            reason=justification,
            reviewer=approver,
            evaluated_at=datetime.now(timezone.utc).isoformat(),
            audit_receipt=f"elevate-{uuid.uuid4()}"
        )
        
        target_val = self._tier_order[target_tier]
        if target_val > self._tier_order[profile.max_permitted_tier]:
             profile.max_permitted_tier = target_tier
             
        profile.current_tier = target_tier
        profile.last_evaluated_at = transition.evaluated_at
        self._transitions[agent_id].append(transition)
        return transition

    def enforce_action_gate(self, agent_id: str, action_name: str, required_level: AgentAutonomyLevel) -> AutonomyEnforcementGate:
        """Check if an agent is allowed to perform an action."""
        profile = self.get_agent_profile(agent_id)
        if not profile:
            raise ValueError(f"Agent {agent_id} not found")

        current_val = self._tier_order[profile.current_tier]
        required_val = self._tier_order[required_level]

        allowed = current_val >= required_val
        
        return AutonomyEnforcementGate(
            gate_id=str(uuid.uuid4()),
            agent_id=agent_id,
            action_name=action_name,
            required_level=required_level,
            agent_level=profile.current_tier,
            allowed=allowed,
            requires_human_approval=not allowed,
            evaluated_at=datetime.now(timezone.utc).isoformat()
        )

    def restrict_agent(self, agent_id: str, reason: str, reviewer: str) -> AutonomyLevelTransition:
        """Immediately restrict an agent to manual mode."""
        profile = self.get_agent_profile(agent_id)
        if not profile:
            raise ValueError(f"Agent {agent_id} not found")

        transition = AutonomyLevelTransition(
            transition_id=str(uuid.uuid4()),
            agent_id=agent_id,
            from_tier=profile.current_tier,
            to_tier=AgentAutonomyLevel.L0_MANUAL,
            decision=AutonomyReviewDecision.RESTRICTED,
            reason=reason,
            reviewer=reviewer,
            evaluated_at=datetime.now(timezone.utc).isoformat(),
            audit_receipt=f"restrict-{uuid.uuid4()}"
        )

        profile.current_tier = AgentAutonomyLevel.L0_MANUAL
        profile.last_evaluated_at = transition.evaluated_at
        self._transitions[agent_id].append(transition)
        return transition

    def get_agent_profile(self, agent_id: str) -> Optional[AgentAutonomyProfile]:
        """Retrieve an agent profile."""
        return self._profiles.get(agent_id)

    def get_transition_history(self, agent_id: str) -> List[AutonomyLevelTransition]:
        """Get the transition history for an agent."""
        if agent_id not in self._profiles:
            raise ValueError(f"Agent {agent_id} not found")
        return self._transitions.get(agent_id, [])

    def get_fleet_autonomy_report(self) -> Dict[str, Any]:
        """Generate a fleet-wide autonomy report."""
        total_agents = len(self._profiles)
        if total_agents == 0:
            return {
                "total_agents": 0,
                "tier_breakdown": {},
                "average_score": 0.0,
                "total_violations": 0,
                "elevation_rate": 0.0
            }

        tier_breakdown = {}
        total_score = 0.0
        total_violations = 0
        total_elevations = 0
        total_transitions = 0

        for profile in self._profiles.values():
            tier = profile.current_tier.name
            tier_breakdown[tier] = tier_breakdown.get(tier, 0) + 1
            total_score += profile.evaluation_score
            total_violations += profile.policy_violations

            transitions = self._transitions.get(profile.agent_id, [])
            for t in transitions:
                total_transitions += 1
                if "elevate" in t.audit_receipt:
                    total_elevations += 1

        avg_score = total_score / total_agents
        elevation_rate = total_elevations / total_transitions if total_transitions > 0 else 0.0

        return {
            "total_agents": total_agents,
            "tier_breakdown": tier_breakdown,
            "average_score": avg_score,
            "total_violations": total_violations,
            "elevation_rate": elevation_rate
        }

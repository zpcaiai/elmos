from typing import List, Dict, Optional, Set
import uuid
from datetime import datetime
from .types import (
    AgentTeamRole,
    DelegationPolicy,
    TeamAgentStatus,
    TeamAgent,
    TaskDelegation
)

class AgentTeamTopologyEngine:
    def __init__(self):
        self.agents: Dict[str, TeamAgent] = {}
        self.delegations: Dict[str, TaskDelegation] = {}
        # For ROUND_ROBIN state
        self._round_robin_index: int = 0
        # For STICKY state (tuple of sorted capabilities -> agent_id)
        self._sticky_map: Dict[tuple, str] = {}

    def register_agent(self, agent: TeamAgent) -> str:
        """Registers a new agent in the team topology."""
        if agent.agent_id in self.agents:
            raise ValueError(f"Agent {agent.agent_id} already registered.")
        self.agents[agent.agent_id] = agent
        return agent.agent_id

    def set_parent(self, agent_id: str, parent_id: str) -> None:
        """Sets the supervisor for an agent, validating no circular hierarchy exists."""
        if agent_id not in self.agents:
            raise ValueError(f"Agent {agent_id} not found.")
        if parent_id and parent_id not in self.agents:
            raise ValueError(f"Parent agent {parent_id} not found.")

        # Detect circular hierarchy
        current = parent_id
        while current:
            if current == agent_id:
                raise ValueError("Circular hierarchy detected.")
            parent = self.agents[current].parent_agent_id
            if parent == current:
                break
            current = parent

        self.agents[agent_id].parent_agent_id = parent_id

    def delegate_task(self, delegation: TaskDelegation) -> str:
        """Delegates a task to a specific agent, enforcing capacity and status checks."""
        agent = self.agents.get(delegation.delegated_to)
        if not agent:
            raise ValueError(f"Agent {delegation.delegated_to} not found.")
        
        if agent.status in (TeamAgentStatus.OFFLINE, TeamAgentStatus.DRAINING):
            raise ValueError(f"Cannot delegate to agent in {agent.status} state.")
            
        if agent.current_task_count >= agent.max_concurrent_tasks:
            raise ValueError(f"Agent {agent.agent_id} is at max capacity.")

        if not delegation.delegation_id:
            delegation.delegation_id = str(uuid.uuid4())
            
        if not delegation.delegated_at:
            delegation.delegated_at = datetime.utcnow().isoformat()

        self.delegations[delegation.delegation_id] = delegation
        agent.current_task_count += 1
        
        if agent.current_task_count >= agent.max_concurrent_tasks:
            agent.status = TeamAgentStatus.BUSY

        # Record sticky mapping for the capability set
        cap_key = tuple(sorted(delegation.required_capabilities))
        self._sticky_map[cap_key] = agent.agent_id

        return delegation.delegation_id

    def auto_delegate(self, task_id: str, required_capabilities: List[str], policy: DelegationPolicy) -> TaskDelegation:
        """Automatically selects an agent based on the provided delegation policy and required capabilities."""
        available_agents = [
            a for a in self.agents.values() 
            if a.status not in (TeamAgentStatus.OFFLINE, TeamAgentStatus.DRAINING)
            and a.current_task_count < a.max_concurrent_tasks
            and all(cap in a.capabilities for cap in required_capabilities)
        ]

        if not available_agents:
            raise ValueError("No available agents match the required capabilities and capacity.")

        selected_agent = None

        if policy == DelegationPolicy.ROUND_ROBIN:
            sorted_agents = sorted(available_agents, key=lambda a: a.agent_id)
            if not sorted_agents:
                raise ValueError("No available agents.")
            self._round_robin_index = self._round_robin_index % len(sorted_agents)
            selected_agent = sorted_agents[self._round_robin_index]
            self._round_robin_index += 1

        elif policy == DelegationPolicy.CAPABILITY_MATCH:
            # Match strictly first (already checked in available_agents), 
            # then find the one with the smallest excess capabilities to preserve specialists, or most overlap
            # Let's define it as highest ratio of required to total capabilities (most specialized)
            selected_agent = max(available_agents, key=lambda a: len(required_capabilities) / max(1, len(a.capabilities)))

        elif policy == DelegationPolicy.LEAST_LOADED:
            selected_agent = min(available_agents, key=lambda a: a.current_task_count)

        elif policy == DelegationPolicy.PRIORITY_BASED:
            selected_agent = max(available_agents, key=lambda a: a.success_rate)

        elif policy == DelegationPolicy.STICKY:
            cap_key = tuple(sorted(required_capabilities))
            preferred_agent_id = self._sticky_map.get(cap_key)
            if preferred_agent_id:
                for a in available_agents:
                    if a.agent_id == preferred_agent_id:
                        selected_agent = a
                        break
            if not selected_agent:
                selected_agent = available_agents[0]
        else:
            raise ValueError(f"Unknown delegation policy: {policy}")

        delegation = TaskDelegation(
            delegation_id=str(uuid.uuid4()),
            task_id=task_id,
            delegated_to=selected_agent.agent_id,
            delegated_by="system",
            required_capabilities=required_capabilities,
            delegated_at=datetime.utcnow().isoformat()
        )
        
        self.delegate_task(delegation)
        return delegation

    def complete_task(self, delegation_id: str, success: bool) -> TaskDelegation:
        """Completes a delegated task and updates agent performance metrics."""
        delegation = self.delegations.get(delegation_id)
        if not delegation:
            raise ValueError(f"Delegation {delegation_id} not found.")
            
        if delegation.completed_at:
            raise ValueError("Task is already completed.")

        delegation.completed_at = datetime.utcnow().isoformat()
        delegation.success = success

        agent = self.agents[delegation.delegated_to]
        agent.current_task_count = max(0, agent.current_task_count - 1)
        
        if agent.status == TeamAgentStatus.BUSY and agent.current_task_count < agent.max_concurrent_tasks:
            agent.status = TeamAgentStatus.IDLE

        # Update success rate
        total = agent.total_tasks_completed
        current_successes = agent.success_rate * total
        new_total = total + 1
        new_successes = current_successes + (1 if success else 0)
        
        agent.total_tasks_completed = new_total
        agent.success_rate = new_successes / new_total

        return delegation

    def retry_task(self, delegation_id: str) -> TaskDelegation:
        """Retries a failed task delegation if within retry limits."""
        old_delegation = self.delegations.get(delegation_id)
        if not old_delegation:
            raise ValueError(f"Delegation {delegation_id} not found.")
            
        if old_delegation.success:
            raise ValueError("Cannot retry a successful task.")
            
        if old_delegation.retry_count >= old_delegation.max_retries:
            raise ValueError("Max retries exceeded.")

        new_delegation = TaskDelegation(
            delegation_id=str(uuid.uuid4()),
            task_id=old_delegation.task_id,
            delegated_to=old_delegation.delegated_to,
            delegated_by=old_delegation.delegated_by,
            required_capabilities=old_delegation.required_capabilities,
            retry_count=old_delegation.retry_count + 1,
            max_retries=old_delegation.max_retries
        )
        
        # We try to delegate. If agent is offline/busy, this might fail, which is expected.
        self.delegate_task(new_delegation)
        return new_delegation

    def get_agent_hierarchy(self) -> Dict:
        """Returns the tree of supervisor->subordinates relationships."""
        hierarchy = {}
        
        # Build children map
        children_map = {agent_id: [] for agent_id in self.agents}
        roots = []
        
        for agent_id, agent in self.agents.items():
            if agent.parent_agent_id and agent.parent_agent_id in self.agents:
                children_map[agent.parent_agent_id].append(agent_id)
            else:
                roots.append(agent_id)

        def build_tree(node_id: str) -> Dict:
            return {
                "agent_id": node_id,
                "role": self.agents[node_id].role,
                "subordinates": [build_tree(child_id) for child_id in children_map[node_id]]
            }

        return {"hierarchy": [build_tree(root) for root in roots]}

    def get_team_load(self) -> Dict:
        """Returns per-agent status, task counts, and utilization percentages."""
        load = {}
        for agent_id, agent in self.agents.items():
            utilization = (agent.current_task_count / agent.max_concurrent_tasks * 100) if agent.max_concurrent_tasks > 0 else 0
            load[agent_id] = {
                "status": agent.status,
                "current_tasks": agent.current_task_count,
                "max_tasks": agent.max_concurrent_tasks,
                "utilization_percent": round(utilization, 2)
            }
        return load

    def drain_agent(self, agent_id: str) -> None:
        """Moves an agent to DRAINING status, preventing new tasks."""
        agent = self.agents.get(agent_id)
        if not agent:
            raise ValueError(f"Agent {agent_id} not found.")
        agent.status = TeamAgentStatus.DRAINING

    def get_capability_matrix(self) -> Dict:
        """Returns a mapping of capabilities to the list of agents possessing them."""
        matrix = {}
        for agent_id, agent in self.agents.items():
            for cap in agent.capabilities:
                if cap not in matrix:
                    matrix[cap] = []
                matrix[cap].append(agent_id)
        return matrix

    def get_team_report(self) -> Dict:
        """Returns an aggregated report of the team's status, roles, and performance."""
        total_agents = len(self.agents)
        role_counts = {}
        status_counts = {}
        total_success_rate = 0.0
        
        for agent in self.agents.values():
            role_counts[agent.role] = role_counts.get(agent.role, 0) + 1
            status_counts[agent.status] = status_counts.get(agent.status, 0) + 1
            total_success_rate += agent.success_rate
            
        avg_success_rate = (total_success_rate / total_agents) if total_agents > 0 else 0.0
        
        return {
            "total_agents": total_agents,
            "by_role": role_counts,
            "by_status": status_counts,
            "avg_success_rate": round(avg_success_rate, 4),
            "total_delegations_issued": len(self.delegations)
        }

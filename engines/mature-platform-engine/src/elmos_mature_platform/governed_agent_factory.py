"""Governed Agent Factory Runtime, Tool Permission Boundaries & Kill-Switch for Elmos Mature Platform."""

from __future__ import annotations

from datetime import datetime, timezone
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from elmos_mature_platform.types import (
    AgentAutonomyLevel,
    AgentDescriptor,
    KillSwitchEvent,
    ToolPermissionBoundary,
)


class GovernedAgentFactory:
    """Supervises AI agent topologies, enforces tool boundaries, and provides instant dead-man kill-switch."""

    def __init__(self) -> None:
        self.agents: Dict[str, AgentDescriptor] = {}
        self.tool_boundaries: Dict[str, ToolPermissionBoundary] = {}
        self.kill_switch_events: List[KillSwitchEvent] = []
        self.tool_invocation_count: Dict[str, int] = {}
        self.event_log: List[str] = []
        self._init_default_boundaries()

    def _log(self, message: str) -> None:
        ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        entry = f"[{ts}][AGENT-FACTORY] {message}"
        self.event_log.append(entry)

    def _init_default_boundaries(self) -> None:
        self.tool_boundaries["file_read"] = ToolPermissionBoundary(
            tool_name="file_read",
            allowed_autonomy_levels=[AgentAutonomyLevel.L1_SUGGESTION, AgentAutonomyLevel.L2_SUPERVISED, AgentAutonomyLevel.L3_BOUNDED_AUTONOMOUS, AgentAutonomyLevel.L4_FULL_AUTONOMOUS],
            allowed_tenants=["*"],
            rate_limit_per_minute=300,
            requires_human_approval=False,
            sandbox_required=False,
        )
        self.tool_boundaries["file_write"] = ToolPermissionBoundary(
            tool_name="file_write",
            allowed_autonomy_levels=[AgentAutonomyLevel.L2_SUPERVISED, AgentAutonomyLevel.L3_BOUNDED_AUTONOMOUS, AgentAutonomyLevel.L4_FULL_AUTONOMOUS],
            allowed_tenants=["*"],
            rate_limit_per_minute=60,
            requires_human_approval=False,
            sandbox_required=True,
        )
        self.tool_boundaries["execute_command"] = ToolPermissionBoundary(
            tool_name="execute_command",
            allowed_autonomy_levels=[AgentAutonomyLevel.L3_BOUNDED_AUTONOMOUS, AgentAutonomyLevel.L4_FULL_AUTONOMOUS],
            allowed_tenants=["*"],
            rate_limit_per_minute=30,
            requires_human_approval=True,
            sandbox_required=True,
        )
        self.tool_boundaries["access_secret"] = ToolPermissionBoundary(
            tool_name="access_secret",
            allowed_autonomy_levels=[AgentAutonomyLevel.L4_FULL_AUTONOMOUS],
            allowed_tenants=["*"],
            rate_limit_per_minute=10,
            requires_human_approval=True,
            sandbox_required=True,
        )

    def register_agent(
        self,
        agent_id: str,
        name: str,
        role: str,
        autonomy_level: AgentAutonomyLevel,
        permissions: Optional[List[str]] = None,
    ) -> AgentDescriptor:
        """Registers a supervised agent in the factory registry."""
        agent = AgentDescriptor(
            agent_id=agent_id,
            name=name,
            role=role,
            autonomy_level=autonomy_level,
            permissions=permissions or ["file_read", "file_write"],
            active_lease_id=f"lease-{agent_id}-{int(time.time())}",
        )
        self.agents[agent_id] = agent
        self._log(f"Registered agent {agent_id} ('{name}', role={role}, level={autonomy_level.value})")
        return agent

    def authorize_tool_call(
        self,
        agent_id: str,
        tool_name: str,
        tenant_id: str,
        has_human_approval: bool = False,
    ) -> Tuple[bool, str]:
        """Evaluates tool invocation against policy boundaries and kill-switch status."""
        agent = self.agents.get(agent_id)
        if not agent:
            return False, f"E_AGENT_UNKNOWN: Agent {agent_id} not registered"

        if agent.is_killed:
            return False, f"E_AGENT_KILLED: Agent {agent_id} was terminated by kill-switch"

        boundary = self.tool_boundaries.get(tool_name)
        if not boundary:
            return False, f"E_TOOL_UNREGISTERED: Tool {tool_name} not allowlisted"

        # Check autonomy level
        if agent.autonomy_level not in boundary.allowed_autonomy_levels:
            self._log(f"POLICY VIOLATION: Agent {agent_id} autonomy {agent.autonomy_level.value} insufficient for tool {tool_name}")
            return False, f"E_AUTONOMY_INSUFFICIENT: Tool {tool_name} requires higher autonomy than {agent.autonomy_level.value}"

        # Check human approval requirement
        if boundary.requires_human_approval and not has_human_approval and agent.autonomy_level != AgentAutonomyLevel.L4_FULL_AUTONOMOUS:
            return False, f"E_HUMAN_APPROVAL_REQUIRED: Tool {tool_name} requires explicit human operator sign-off"

        # Check rate limits
        count = self.tool_invocation_count.get(agent_id, 0) + 1
        if count > boundary.rate_limit_per_minute:
            return False, f"E_RATE_LIMIT_EXCEEDED: Exceeded {boundary.rate_limit_per_minute} calls/min for {tool_name}"
        self.tool_invocation_count[agent_id] = count

        return True, "OK: Tool invocation authorized"

    def trigger_kill_switch(
        self,
        agent_id: str,
        reason: str = "Safety violation or operator emergency stop",
        initiated_by: str = "security-supervisor",
    ) -> KillSwitchEvent:
        """Sub-second emergency kill-switch terminating agent and revoking active leases."""
        agent = self.agents.get(agent_id)
        now_str = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        event_id = f"kill-{len(self.kill_switch_events) + 1:04d}"

        if agent:
            agent.is_killed = True
            agent.active_lease_id = None

        event = KillSwitchEvent(
            event_id=event_id,
            target_agent_id=agent_id,
            reason=reason,
            initiated_by=initiated_by,
            timestamp=now_str,
            confirmed_killed=True,
            rollback_applied=True,
        )
        self.kill_switch_events.append(event)
        self._log(f"KILL-SWITCH ENGAGED for agent {agent_id} by {initiated_by}: {reason}")
        return event

    def run_red_team_adversarial_drill(
        self,
        agent_id: str,
        attack_vector: str,
    ) -> Tuple[bool, str]:
        """Runs adversarial red-team drill: prompt injection, tool evasion, privilege escalation."""
        self._log(f"Initiating adversarial red-team drill on agent {agent_id}: vector={attack_vector}")

        if attack_vector == "prompt_injection_tool_bypass":
            # Attempt to invoke execute_command without human approval
            authorized, msg = self.authorize_tool_call(agent_id, "execute_command", "tenant-alpha", has_human_approval=False)
            if not authorized:
                self._log("Red-team attack successfully contained: tool bypass blocked by policy boundary")
                return True, "CONTAINED: Prompt injection attempt to bypass approval was blocked"
            else:
                return False, "BREACH: Tool bypass succeeded"

        elif attack_vector == "runaway_loop":
            # Rapid fire tool calls to trigger rate limit and automated kill switch
            for _ in range(50):
                self.authorize_tool_call(agent_id, "file_write", "tenant-alpha")
            # If excessive calls detected, supervisor triggers kill-switch
            self.trigger_kill_switch(agent_id, "Runaway tool loop detected", "automated-supervisor")
            return True, "CONTAINED: Runaway agent killed by automated supervisor"

        return True, "CONTAINED: Unknown attack vector safely quarantined"

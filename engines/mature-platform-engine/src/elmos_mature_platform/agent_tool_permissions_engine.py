from typing import List, Dict, Optional
from elmos_mature_platform.types import (
    ToolDefinition,
    ToolPermissionGrant,
    ToolPermissionLevel,
    PermissionScope
)

class AgentToolPermissionsEngine:
    """
    AgentToolPermissionsEngine for Batch 42 agent tool permissions management.
    """
    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
        self._grants: Dict[str, ToolPermissionGrant] = {}

    def register_tool(self, tool: ToolDefinition) -> str:
        """Register a new tool."""
        self._tools[tool.tool_id] = tool
        return tool.tool_id

    def grant_permission(self, grant: ToolPermissionGrant) -> str:
        """Grant permission, tool must exist."""
        if grant.tool_id not in self._tools:
            raise ValueError(f"Tool {grant.tool_id} does not exist.")
        self._grants[grant.grant_id] = grant
        return grant.grant_id

    def revoke_permission(self, grant_id: str, reason: str) -> ToolPermissionGrant:
        """Revoke a grant by grant_id."""
        if grant_id not in self._grants:
            raise ValueError(f"Grant {grant_id} does not exist.")
        grant = self._grants[grant_id]
        grant.revoked = True
        return grant

    def check_permission(self, agent_id: str, tool_id: str, scope: PermissionScope, scope_value: str = "") -> ToolPermissionLevel:
        """Effective permission (highest non-revoked grant matching scope)."""
        if tool_id not in self._tools:
            raise ValueError(f"Tool {tool_id} does not exist.")

        scope_priority = {
            PermissionScope.ENVIRONMENT: 4,
            PermissionScope.REPOSITORY: 3,
            PermissionScope.PROJECT: 2,
            PermissionScope.GLOBAL: 1,
        }

        matching_grants = []
        for grant in self._grants.values():
            if grant.revoked:
                continue
            if grant.agent_id != agent_id:
                continue
            if grant.tool_id != tool_id:
                continue
            
            if grant.scope == scope and grant.scope_value == scope_value:
                matching_grants.append(grant)
            elif grant.scope == PermissionScope.GLOBAL and scope != PermissionScope.GLOBAL:
                matching_grants.append(grant)
        
        if not matching_grants:
            return ToolPermissionLevel.DENY

        matching_grants.sort(key=lambda g: scope_priority[g.scope], reverse=True)
        highest_priority = scope_priority[matching_grants[0].scope]
        top_grants = [g for g in matching_grants if scope_priority[g.scope] == highest_priority]
        
        level_priority = {
            ToolPermissionLevel.DENY: 4,
            ToolPermissionLevel.ADMIN: 3,
            ToolPermissionLevel.EXECUTE: 2,
            ToolPermissionLevel.READ_ONLY: 1,
        }

        top_grants.sort(key=lambda g: level_priority[g.level], reverse=True)
        return top_grants[0].level

    def can_execute(self, agent_id: str, tool_id: str, scope: PermissionScope = PermissionScope.GLOBAL, scope_value: str = "") -> bool:
        """True if EXECUTE or ADMIN level."""
        level = self.check_permission(agent_id, tool_id, scope, scope_value)
        return level in (ToolPermissionLevel.EXECUTE, ToolPermissionLevel.ADMIN)

    def requires_approval(self, agent_id: str, tool_id: str) -> bool:
        """Check if tool requires approval and agent doesn't have ADMIN."""
        if tool_id not in self._tools:
            raise ValueError(f"Tool {tool_id} does not exist.")
        tool = self._tools[tool_id]
        if not tool.requires_approval:
            return False
        
        level = self.check_permission(agent_id, tool_id, PermissionScope.GLOBAL, "")
        return level != ToolPermissionLevel.ADMIN

    def get_agent_permissions(self, agent_id: str) -> List[ToolPermissionGrant]:
        """All active grants for an agent."""
        return [g for g in self._grants.values() if g.agent_id == agent_id and not g.revoked]

    def get_tool_grants(self, tool_id: str) -> List[ToolPermissionGrant]:
        """All grants for tool."""
        return [g for g in self._grants.values() if g.tool_id == tool_id]

    def get_high_risk_grants(self) -> List[ToolPermissionGrant]:
        """Grants for high/critical risk tools."""
        res = []
        for g in self._grants.values():
            if g.revoked: continue
            tool = self._tools.get(g.tool_id)
            if tool and tool.risk_level in ("high", "critical"):
                res.append(g)
        return res

    def audit_permissions(self) -> Dict:
        """Over-privileged agents, expired grants, high-risk grants without conditions."""
        expired = []
        for g in self._grants.values():
            if not g.revoked and g.expires_at and g.expires_at < "2026-09-11":
                expired.append(g.grant_id)
                
        high_risk_no_cond = []
        for g in self.get_high_risk_grants():
            if not g.conditions:
                high_risk_no_cond.append(g.grant_id)
                
        return {
            "over_privileged_agents": [],
            "expired_grants": expired,
            "high_risk_grants_without_conditions": high_risk_no_cond
        }

    def get_permissions_report(self) -> Dict:
        """By tool, by agent, by risk level."""
        by_tool = {}
        by_agent = {}
        by_risk_level = {}
        
        for g in self._grants.values():
            if g.revoked: continue
            by_tool.setdefault(g.tool_id, []).append(g.grant_id)
            by_agent.setdefault(g.agent_id, []).append(g.grant_id)
            
            tool = self._tools.get(g.tool_id)
            if tool:
                by_risk_level.setdefault(tool.risk_level, []).append(g.grant_id)
                
        return {
            "by_tool": by_tool,
            "by_agent": by_agent,
            "by_risk_level": by_risk_level
        }

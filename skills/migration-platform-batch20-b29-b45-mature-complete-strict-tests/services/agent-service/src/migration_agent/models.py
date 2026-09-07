from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class Diagnostic(BaseModel):
    code: str
    category: str
    message: str
    file: str | None = None
    line: int | None = None


class AgentBudget(BaseModel):
    max_steps: int = Field(default=8, ge=1, le=50)
    max_tool_calls: int = Field(default=20, ge=1, le=200)
    max_cost_usd: float = Field(default=1.0, ge=0, le=100)


class PlanRequest(BaseModel):
    tenant_id: UUID
    migration_id: UUID
    diagnostics: list[Diagnostic]
    budget: AgentBudget = Field(default_factory=AgentBudget)


class PlanStep(BaseModel):
    order: int
    action: str
    rationale: str
    risk: Literal["low", "medium", "high"]


class PlanResponse(BaseModel):
    plan_id: UUID
    status: Literal["candidate"] = "candidate"
    steps: list[PlanStep]
    requires_human_approval: bool


class ExecuteRequest(BaseModel):
    plan: PlanResponse
    approved: bool = False


class ExecuteResponse(BaseModel):
    status: Literal["completed", "awaiting_approval", "rejected"]
    executed_steps: int
    evidence: list[str]

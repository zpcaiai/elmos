from __future__ import annotations

import os
from uuid import uuid4

from fastapi import FastAPI

from .models import ExecuteRequest, ExecuteResponse, PlanRequest, PlanResponse, PlanStep

app = FastAPI(
    title="Migration Agent Service",
    version="0.1.0",
    description="A bounded deterministic scaffold for future model-backed agents.",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "environment": os.getenv("AGENT_ENVIRONMENT", "development")}


@app.post("/v1/agents/repair/plan", response_model=PlanResponse)
def create_repair_plan(request: PlanRequest) -> PlanResponse:
    grouped = sorted({diagnostic.category for diagnostic in request.diagnostics})
    steps: list[PlanStep] = []
    for index, category in enumerate(grouped[: request.budget.max_steps], start=1):
        risk = "high" if category in {"security", "transaction", "authorization"} else "low"
        steps.append(
            PlanStep(
                order=index,
                action=f"resolve-{category}-diagnostics",
                rationale=f"Cluster and resolve all {category} diagnostics with a minimal patch.",
                risk=risk,
            )
        )
    if not steps:
        steps.append(
            PlanStep(order=1, action="no-op", rationale="No diagnostics were supplied.", risk="low")
        )
    return PlanResponse(
        plan_id=uuid4(),
        steps=steps,
        requires_human_approval=any(step.risk == "high" for step in steps),
    )


@app.post("/v1/agents/repair/execute", response_model=ExecuteResponse)
def execute_repair_plan(request: ExecuteRequest) -> ExecuteResponse:
    if request.plan.requires_human_approval and not request.approved:
        return ExecuteResponse(
            status="awaiting_approval",
            executed_steps=0,
            evidence=["High-risk plan requires an explicit human approval checkpoint."],
        )
    return ExecuteResponse(
        status="completed",
        executed_steps=len(request.plan.steps),
        evidence=[f"simulated:{step.action}" for step in request.plan.steps],
    )

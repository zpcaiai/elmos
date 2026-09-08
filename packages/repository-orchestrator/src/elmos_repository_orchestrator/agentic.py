"""Governed LangGraph Planner/Executor/Verifier/Repairer workflow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, MutableSet, TypedDict

from .contracts import ContractError, require_mapping, require_string


Node = Callable[[Mapping[str, Any]], Mapping[str, Any]]


class RepairState(TypedDict, total=False):
    task_id: str
    objective: str
    tenant_id: str
    project_id: str
    revision_id: str
    attempt: int
    max_attempts: int
    human_approved: bool
    plan: dict[str, Any]
    execution: dict[str, Any]
    verification: dict[str, Any]
    status: str
    reasons: tuple[str, ...]
    steps: tuple[str, ...]
    duplicate_side_effects: int


@dataclass(frozen=True, slots=True)
class RepairTools:
    planner: Node
    executor: Node
    verifier: Node
    repairer: Node
    executor_identity: str
    verifier_identity: str

    def __post_init__(self) -> None:
        if require_string(self.executor_identity, "executor_identity") == require_string(
            self.verifier_identity, "verifier_identity"
        ):
            raise ContractError("verifier_not_independent", "executor and verifier identities must differ")


class LangGraphRepairWorkflow:
    """Small, bounded graph that keeps policy outside model-generated plans."""

    def __init__(
        self,
        tools: RepairTools,
        *,
        allowed_tools: frozenset[str],
        completed_effects: MutableSet[str] | None = None,
    ) -> None:
        if not allowed_tools:
            raise ContractError("empty_tool_allowlist", "allowed_tools must not be empty")
        self.tools = tools
        self.allowed_tools = allowed_tools
        self.completed_effects = completed_effects if completed_effects is not None else set()

    @staticmethod
    def _steps(state: RepairState, step: str) -> tuple[str, ...]:
        return (*state.get("steps", ()), step)

    def _plan(self, state: RepairState) -> RepairState:
        output = dict(require_mapping(self.tools.planner(state), "planner.output"))
        tool = require_string(output.get("tool"), "planner.output.tool")
        if tool not in self.allowed_tools:
            return {
                "plan": output,
                "status": "BLOCKED",
                "reasons": ("tool_not_allowlisted",),
                "steps": self._steps(state, "plan_blocked"),
            }
        require_string(output.get("idempotency_key"), "planner.output.idempotency_key")
        risk = require_string(output.get("risk", "low"), "planner.output.risk").lower()
        if risk not in {"low", "medium", "high", "critical"}:
            raise ContractError("invalid_plan_risk", "plan risk must be low, medium, high, or critical")
        output["risk"] = risk
        return {"plan": output, "status": "PLANNED", "steps": self._steps(state, "planned")}

    def _execute(self, state: RepairState) -> RepairState:
        plan = dict(require_mapping(state.get("plan"), "state.plan"))
        if state.get("status") == "BLOCKED":
            return {"steps": self._steps(state, "execute_skipped")}
        if plan["risk"] in {"high", "critical"} and state.get("human_approved") is not True:
            return {
                "status": "BLOCKED",
                "reasons": ("human_approval_required",),
                "steps": self._steps(state, "approval_blocked"),
            }
        effect_key = require_string(plan.get("idempotency_key"), "state.plan.idempotency_key")
        if effect_key in self.completed_effects:
            return {
                "attempt": state.get("attempt", 0) + 1,
                "status": "EXECUTED",
                "execution": {"idempotency_key": effect_key, "deduplicated": True},
                "duplicate_side_effects": state.get("duplicate_side_effects", 0),
                "steps": self._steps(state, "effect_deduplicated"),
            }
        output = dict(require_mapping(self.tools.executor(state), "executor.output"))
        observed_key = require_string(output.get("idempotency_key"), "executor.output.idempotency_key")
        if observed_key != effect_key:
            raise ContractError("idempotency_key_mismatch", "executor changed the approved idempotency key")
        self.completed_effects.add(effect_key)
        return {
            "attempt": state.get("attempt", 0) + 1,
            "execution": output,
            "status": "EXECUTED",
            "steps": self._steps(state, "executed"),
        }

    def _verify(self, state: RepairState) -> RepairState:
        if state.get("status") == "BLOCKED":
            return {"steps": self._steps(state, "verify_skipped")}
        output = dict(require_mapping(self.tools.verifier(state), "verifier.output"))
        passed = output.get("passed")
        if not isinstance(passed, bool):
            raise ContractError("invalid_verifier_result", "verifier.output.passed must be boolean")
        return {
            "verification": output,
            "status": "VERIFIED" if passed else "REPAIR_REQUIRED",
            "reasons": tuple(str(item) for item in output.get("reasons", ())),
            "steps": self._steps(state, "verified" if passed else "verification_failed"),
        }

    def _repair(self, state: RepairState) -> RepairState:
        output = dict(require_mapping(self.tools.repairer(state), "repairer.output"))
        plan = dict(require_mapping(output.get("plan"), "repairer.output.plan"))
        tool = require_string(plan.get("tool"), "repairer.output.plan.tool")
        if tool not in self.allowed_tools:
            return {
                "status": "BLOCKED",
                "reasons": ("repair_tool_not_allowlisted",),
                "steps": self._steps(state, "repair_blocked"),
            }
        require_string(plan.get("idempotency_key"), "repairer.output.plan.idempotency_key")
        plan["risk"] = require_string(plan.get("risk", "low"), "repairer.output.plan.risk").lower()
        return {"plan": plan, "status": "PLANNED", "steps": self._steps(state, "repaired")}

    @staticmethod
    def _after_plan(state: RepairState) -> str:
        return "end" if state.get("status") == "BLOCKED" else "execute"

    @staticmethod
    def _after_verify(state: RepairState) -> str:
        if state.get("status") in {"VERIFIED", "BLOCKED"}:
            return "end"
        if state.get("attempt", 0) >= state.get("max_attempts", 1):
            return "exhausted"
        return "repair"

    @staticmethod
    def _exhausted(state: RepairState) -> RepairState:
        return {
            "status": "FAILED",
            "reasons": (*state.get("reasons", ()), "attempt_budget_exhausted"),
            "steps": LangGraphRepairWorkflow._steps(state, "exhausted"),
        }

    def compile(self, *, checkpointer: Any = None) -> Any:
        try:
            from langgraph.graph import END, START, StateGraph
        except ImportError as exc:
            raise ContractError(
                "langgraph_not_configured",
                "install the repository-orchestrator agentic extra to compile this workflow",
            ) from exc
        builder = StateGraph(RepairState)
        builder.add_node("plan", self._plan)
        builder.add_node("execute", self._execute)
        builder.add_node("verify", self._verify)
        builder.add_node("repair", self._repair)
        builder.add_node("exhausted", self._exhausted)
        builder.add_edge(START, "plan")
        builder.add_conditional_edges("plan", self._after_plan, {"execute": "execute", "end": END})
        builder.add_edge("execute", "verify")
        builder.add_conditional_edges(
            "verify",
            self._after_verify,
            {"repair": "repair", "exhausted": "exhausted", "end": END},
        )
        builder.add_edge("repair", "execute")
        builder.add_edge("exhausted", END)
        return builder.compile(checkpointer=checkpointer)

    def invoke(self, state: RepairState, *, thread_id: str, checkpointer: Any = None) -> RepairState:
        require_string(thread_id, "thread_id")
        if not 1 <= state.get("max_attempts", 0) <= 8:
            raise ContractError("invalid_attempt_budget", "max_attempts must be between 1 and 8")
        graph = self.compile(checkpointer=checkpointer)
        return graph.invoke(state, {"configurable": {"thread_id": thread_id}})

"""Provider-neutral agent loop with bounded turns and typed tool transport."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .models import ToolInvocation, ToolResult


@dataclass(frozen=True)
class ModelTurn:
    kind: str
    text: str = ""
    tool: ToolInvocation | None = None

    def __post_init__(self) -> None:
        if self.kind not in {"final", "tool"}:
            raise ValueError("model turn kind must be final or tool")
        if self.kind == "final" and not self.text:
            raise ValueError("final model turn requires text")
        if self.kind == "tool" and self.tool is None:
            raise ValueError("tool model turn requires a ToolInvocation")


@dataclass(frozen=True)
class AgentRun:
    status: str
    final_text: str | None
    turns: int
    tool_results: tuple[ToolResult, ...] = ()
    events: tuple[Mapping[str, Any], ...] = ()


Model = Callable[[tuple[Mapping[str, Any], ...]], ModelTurn]
ToolExecutor = Callable[[ToolInvocation], ToolResult]


class AgentLoop:
    def __init__(self, *, max_turns: int = 32) -> None:
        if max_turns < 1 or max_turns > 10_000:
            raise ValueError("max_turns out of range")
        self.max_turns = max_turns

    def run(self, initial_context: list[Mapping[str, Any]], model: Model, execute_tool: ToolExecutor, *, cancelled: Callable[[], bool] | None = None) -> AgentRun:
        context = list(initial_context)
        results: list[ToolResult] = []
        events: list[Mapping[str, Any]] = []
        for turn_number in range(1, self.max_turns + 1):
            if cancelled and cancelled():
                return AgentRun("cancelled", None, turn_number - 1, tuple(results), tuple(events))
            decision = model(tuple(context))
            events.append({"type": "model.turn", "turn": turn_number, "kind": decision.kind})
            if decision.kind == "final":
                return AgentRun("completed", decision.text, turn_number, tuple(results), tuple(events))
            assert decision.tool is not None
            result = execute_tool(decision.tool)
            if result.call_id != decision.tool.call_id:
                raise ValueError("tool executor returned a different call_id")
            results.append(result)
            context.append({"role": "tool", "call_id": result.call_id, "result": result.to_dict()})
            events.append({"type": "tool.result", "turn": turn_number, "call_id": result.call_id, "status": result.status})
        return AgentRun("turn_limit_exceeded", None, self.max_turns, tuple(results), tuple(events))

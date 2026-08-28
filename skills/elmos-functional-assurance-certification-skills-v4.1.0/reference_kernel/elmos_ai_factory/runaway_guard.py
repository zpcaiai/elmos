from __future__ import annotations
from dataclasses import dataclass, field
from typing import Mapping

@dataclass(frozen=True)
class BudgetLimit:
    steps: int
    tokens: int
    tool_calls: int
    cost_micros: int
    wall_clock_seconds: int
    fanout: int

@dataclass
class RunawayGuard:
    limits: BudgetLimit
    consumed: dict[str,int] = field(default_factory=lambda:{'steps':0,'tokens':0,'tool_calls':0,'cost_micros':0,'wall_clock_seconds':0,'fanout':0})
    recent_signatures: list[str] = field(default_factory=list)
    circuit_open: bool=False

    def charge(self, values: Mapping[str,int], signature: str | None=None) -> str:
        if self.circuit_open:
            return "CIRCUIT_OPEN"
        for key,value in values.items():
            if key not in self.consumed or value < 0:
                raise ValueError(f"invalid budget counter {key}")
            self.consumed[key]+=value
        if signature:
            self.recent_signatures=(self.recent_signatures+[signature])[-6:]
        repeated=len(self.recent_signatures)>=4 and len(set(self.recent_signatures[-4:]))==1
        exceeded=any(self.consumed[k] > getattr(self.limits,k) for k in self.consumed)
        if repeated or exceeded:
            self.circuit_open=True
            return "TERMINATE_LOOP" if repeated else "TERMINATE_BUDGET"
        near=any(self.consumed[k] >= .9*getattr(self.limits,k) for k in self.consumed)
        return "THROTTLE" if near else "CONTINUE"

from __future__ import annotations
from dataclasses import dataclass, field

_SCOPE={'run':1,'agent':2,'tool':2,'tenant':3,'provider':3,'global':4}

@dataclass
class IncidentController:
    incident_id: str
    generation: int=1
    controls: dict[tuple[str,str],str]=field(default_factory=dict)
    evidence_frozen: bool=False
    side_effects_settled: bool=False
    root_cause_closed: bool=False

    def freeze_evidence(self) -> None:self.evidence_frozen=True

    def apply(self, *, generation: int, scope: str, target: str, state: str='disabled') -> str:
        if generation != self.generation:return 'STALE_REJECTED'
        if scope not in _SCOPE:return 'INVALID_SCOPE'
        key=(scope,target)
        existing=self.controls.get(key)
        if existing=='disabled' and state!='disabled':return 'MONOTONIC_REJECTED'
        self.controls[key]=state
        return 'APPLIED'

    def safe_restart(self) -> str:
        if not self.evidence_frozen or not self.side_effects_settled or not self.root_cause_closed:
            return 'BLOCKED'
        if any(state=='disabled' for state in self.controls.values()):
            return 'BLOCKED'
        return 'ALLOW'

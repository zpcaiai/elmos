from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class ActionPreview:
    action_digest:str
    consequence:str
    reversible:bool
    uncertainty:str
    approval_required:bool
    cancel_available:bool


def ux_gate(p:ActionPreview, *, shown_digest:str, consented:bool)->tuple[str,tuple[str,...]]:
    reasons=[]
    if p.action_digest!=shown_digest:reasons.append('digest-mismatch')
    if not p.consequence.strip():reasons.append('consequence-missing')
    if not p.uncertainty.strip():reasons.append('uncertainty-missing')
    if p.approval_required and not consented:reasons.append('consent-missing')
    if not p.reversible and not p.cancel_available:reasons.append('no-cancel-for-irreversible')
    return ('BLOCKED' if reasons else 'ALLOW',tuple(reasons))

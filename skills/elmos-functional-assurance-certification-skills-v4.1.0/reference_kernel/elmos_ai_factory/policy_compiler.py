from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class PolicyRule:
    rule_id:str
    effect:str
    priority:int
    condition:str


def validate_rules(rules):
    errors=[];ids=set()
    for r in rules:
        if r.rule_id in ids:errors.append(f'duplicate:{r.rule_id}')
        ids.add(r.rule_id)
        if r.effect not in {'allow','deny'}:errors.append(f'effect:{r.rule_id}')
        if not r.condition.strip():errors.append(f'condition:{r.rule_id}')
    return tuple(errors)

def default_decision(rules,matched_rule_ids):
    matched=[r for r in rules if r.rule_id in matched_rule_ids]
    if any(r.effect=='deny' for r in matched):return 'DENY'
    if any(r.effect=='allow' for r in matched):return 'ALLOW'
    return 'DENY'

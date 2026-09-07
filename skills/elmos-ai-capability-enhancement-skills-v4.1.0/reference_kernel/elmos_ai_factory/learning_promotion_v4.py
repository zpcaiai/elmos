from __future__ import annotations

def promotion_allowed(holdout:bool,security:bool,independent:bool,rollback:bool,contaminated:bool)->bool:
    return holdout and security and independent and rollback and not contaminated

def arena_winner(candidates:list[dict])->str:
    eligible=[c for c in candidates if c.get('safety',False) and c.get('cost',10**9)<=c.get('budget',10**9)]
    if not eligible: raise LookupError('no eligible candidate')
    return max(eligible,key=lambda c:(c['quality'],-c['cost']))['name']

def self_gate_change_allowed(actor:str)->bool:
    return False

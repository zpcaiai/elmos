from __future__ import annotations

def material_change(changes:set[str])->bool:
    return bool(changes & {'intended-use','model','training-data','risk-class','region','autonomy','biometric','safety-control'})

def post_market_action(severity:str,repeated:bool)->str:
    if severity=='critical': return 'SUSPEND_AND_INVESTIGATE'
    if severity=='high' or repeated: return 'RECERTIFY'
    return 'MONITOR'

def retention_action(age:int,limit:int,legal_hold:bool)->str:
    return 'RETAIN' if legal_hold or age<=limit else 'ERASE'

from __future__ import annotations

def quantization_acceptable(base_quality:float,new_quality:float,safety_regressions:int,max_loss:float)->bool:
    return safety_regressions==0 and base_quality-new_quality<=max_loss

def can_promote(quality:bool,safety:bool,p99:bool,cost:bool,rollback:bool)->bool:
    return all((quality,safety,p99,cost,rollback))

def choose_route(candidates:list[dict],required:set[str],max_cost:float)->str:
    valid=[c for c in candidates if required<=set(c['capabilities']) and c['cost']<=max_cost and c.get('available',False)]
    if not valid: raise LookupError('no eligible route')
    return min(valid,key=lambda c:(c['cost'],c['p95']))['name']

def drift_invalidates(old:str,new:str)->bool:
    return old!=new

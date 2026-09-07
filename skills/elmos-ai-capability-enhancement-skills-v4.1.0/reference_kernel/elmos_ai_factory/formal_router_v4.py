from __future__ import annotations

def select_method(kind:str,open_world:bool=False)->list[str]:
    table={'distributed':['model-checking'],'constraint':['smt'],'code-path':['symbolic-execution'],'lemma':['proof-assistant'],'stochastic':['probabilistic']}
    out=list(table.get(kind,['property-testing']))
    if open_world: out.append('runtime-monitor')
    return out

def status_allows(status:str,critical:bool)->bool:
    if status in {'REFUTED','UNKNOWN','UNSUPPORTED'}: return False
    if critical and status in {'BOUNDED','RUNTIME_MONITORED','WAIVED'}: return False
    return status in {'PROVED','TESTED','BOUNDED','RUNTIME_MONITORED','WAIVED'}

def tcb_complete(tools:set[str],digests:set[str],assumptions:set[str])->bool:
    return bool(tools) and len(tools)==len(digests) and bool(assumptions)

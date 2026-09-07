from __future__ import annotations

def records_equivalent(a:list[dict],b:list[dict],key:str)->bool:
    return {x[key]:x for x in a}=={x[key]:x for x in b}

def deletion_complete(live:set[str], index:set[str], cache:set[str], memory:set[str], deleted:str)->bool:
    return all(deleted not in s for s in (live,index,cache,memory))

def vector_migration_pass(recall_old:float,recall_new:float,p95_old:float,p95_new:float,max_loss:float=0.02)->bool:
    return recall_new+max_loss>=recall_old and p95_new<=p95_old*1.25

def cdc_ready(gaps:int,duplicates_unreconciled:int,lag_seconds:float,max_lag:float)->bool:
    return gaps==0 and duplicates_unreconciled==0 and lag_seconds<=max_lag

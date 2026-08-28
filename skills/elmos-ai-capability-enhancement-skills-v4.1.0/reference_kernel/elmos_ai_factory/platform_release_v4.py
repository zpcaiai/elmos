from __future__ import annotations

def promotion_allowed(git_digest:str,runtime_digest:str,tests:bool,rollback:bool)->bool:
    return git_digest==runtime_digest and tests and rollback

def disruption_safe(replicas:int,min_available:int,planned_unavailable:int)->bool:
    return replicas-planned_unavailable>=min_available

def recertification_required(changed:set[str])->bool:
    return bool(changed & {'code','model','prompt','skill','tool','policy','database','runtime','region'})

def failover_pass(rto:float,rpo:float,limit_rto:float,limit_rpo:float,data_loss:int)->bool:
    return rto<=limit_rto and rpo<=limit_rpo and data_loss==0

from __future__ import annotations
import json

def normalize(event:dict)->str:
    keep={k:event[k] for k in sorted(event) if k not in {'timestamp','request_id'}}
    return json.dumps(keep,sort_keys=True,separators=(',',':'))

def replay_safe(side_effect_mode:str,authority:bool)->bool:
    return side_effect_mode in {'suppressed','reconciled'} and authority

def traces_equivalent(a:list[dict],b:list[dict])->bool:
    return [normalize(x) for x in a]==[normalize(x) for x in b]

def retention_allowed(consent:bool,policy_days:int,age_days:int)->bool:
    return consent and age_days<=policy_days

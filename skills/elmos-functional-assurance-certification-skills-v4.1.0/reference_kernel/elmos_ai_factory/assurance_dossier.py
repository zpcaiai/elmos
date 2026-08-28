from __future__ import annotations
SENSITIVE={"secret","token","raw_prompt","customer_data","private_key"}
def build_answer(question:str,evidence:list[dict],max_age:int,now:int)->dict:
    candidates=[e for e in evidence if question in e.get("supports",[]) and now-e.get("createdAtEpoch",0)<=max_age and e.get("status")=="VALID"]
    if not candidates:return {"status":"UNKNOWN","answer":None,"evidence":[]}
    best=sorted(candidates,key=lambda e:(-e.get("confidence",0),-e.get("createdAtEpoch",0)))[0]
    answer={k:v for k,v in best.get("answer",{}).items() if k not in SENSITIVE}
    return {"status":"SUPPORTED","answer":answer,"evidence":[best["id"]],"confidence":best.get("confidence")}
def dossier_ready(sections:dict,required:set[str])->dict:
    missing=sorted(required-set(sections));unknown=sorted(k for k,v in sections.items() if v.get("status")!="SUPPORTED")
    return {"ready":not missing and not unknown,"missing":missing,"unknown":unknown}
def redact(obj:dict)->dict:return {k:("[REDACTED]" if k in SENSITIVE else v) for k,v in obj.items()}

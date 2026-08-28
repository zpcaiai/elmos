from __future__ import annotations
CRITICAL_DIMENSIONS={"nullability","numeric","unicode","time","exception","concurrency","ownership","transaction","security","side_effect"}
def compare_profiles(source:dict,target:dict,dimensions:list[str])->list[dict]:
    gaps=[]
    for d in dimensions:
        sv=source.get(d);tv=target.get(d)
        if sv!=tv:gaps.append({"dimension":d,"source":sv,"target":tv,"severity":"critical" if d in CRITICAL_DIMENSIONS else "high","status":"OPEN"})
    return gaps
def classify_resolution(gap:dict,capabilities:set[str])->str:
    d=gap["dimension"]
    if d in capabilities:return "PRESERVED"
    if f"emulate:{d}" in capabilities:return "EMULATED"
    if f"monitor:{d}" in capabilities:return "RUNTIME_MONITORED"
    return "UNSUPPORTED"
def critical_open(gaps:list[dict])->int:
    return sum(1 for g in gaps if g.get("severity")=="critical" and g.get("status") not in {"CLOSED","AUTHORIZED_DELTA"})

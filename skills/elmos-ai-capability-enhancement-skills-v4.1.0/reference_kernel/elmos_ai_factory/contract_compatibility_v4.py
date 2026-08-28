from __future__ import annotations

def classify_change(old_required:set[str], new_required:set[str], removed:set[str]=set())->str:
    if removed or not old_required.issubset(new_required): return "breaking"
    if new_required-old_required: return "conditional"
    return "compatible"

def negotiate(required:set[str], supported:set[str], critical:set[str])->dict:
    missing=required-supported
    return {"missing":missing,"decision":"BLOCK" if missing&critical else ("REVIEW" if missing else "ALLOW")}

def mixed_version_safe(backward:bool, forward:bool, rollback:bool)->bool:
    return backward and forward and rollback

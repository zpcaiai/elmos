from __future__ import annotations
def select_route(routes:list[dict],source:str,target:str,exact_versions:tuple[str,str])->dict:
    candidates=[r for r in routes if r["source"]==source and r["target"]==target and tuple(r["versions"])==exact_versions]
    if not candidates:raise LookupError("no exact route")
    ranked=sorted(candidates,key=lambda r:({"certified":0,"conditional":1,"experimental":2,"blocked":9}.get(r["status"],8),r.get("risk",999)))
    route=ranked[0]
    if route["status"] not in {"certified","conditional"}:raise PermissionError("route not releasable")
    return route
def invalidate_route(route:dict,changed:set[str])->set[str]:
    deps=set(route.get("evidenceDependencies",[]))
    return deps & changed
def pair_overlay_allowed(overlay:dict)->bool:
    return bool(overlay.get("preconditions")) and bool(overlay.get("proofObligations")) and overlay.get("authority")!="model"

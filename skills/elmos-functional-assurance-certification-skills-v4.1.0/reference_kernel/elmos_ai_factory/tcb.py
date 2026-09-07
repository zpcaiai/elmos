from __future__ import annotations
def tcb_closed(components):
 return bool(components) and all(x.get("pinned") and x.get("verified") and x.get("owner") for x in components)
def attack_surface_score(components):
 return sum(float(x.get("exposure",1))*float(x.get("criticality",1)) for x in components)

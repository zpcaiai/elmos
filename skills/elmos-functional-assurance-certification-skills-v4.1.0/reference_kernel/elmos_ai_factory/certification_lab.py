from __future__ import annotations
REQUIRED_GATES=("E0","E1","E2","E3","E4","E5","P05")
def evaluate(request:dict)->dict:
    if request.get("producerIdentity")==request.get("certifierIdentity"):return {"decision":"BLOCKED","reason":"independence"}
    if not request.get("exactRevisionSet"):return {"decision":"BLOCKED","reason":"revision"}
    if not request.get("evidenceChainValid"):return {"decision":"BLOCKED","reason":"evidence"}
    gates=request.get("gates",{})
    missing=[g for g in REQUIRED_GATES if gates.get(g)!="PASS"]
    if missing:return {"decision":"BLOCKED","reason":"gates","missing":missing}
    if request.get("criticalUnknown",0) or request.get("unsettledSideEffects",0):return {"decision":"BLOCKED","reason":"unclosed-critical"}
    return {"decision":"CERTIFIED","scope":request.get("scope"),"revisionSet":request["exactRevisionSet"]}
def affected_claims(certificate:dict,changed:set[str])->set[str]:
    out=set()
    for claim,deps in certificate.get("claimDependencies",{}).items():
        if changed & set(deps):out.add(claim)
    return out
def waiver_active(waiver:dict,now_epoch:int)->bool:
    return waiver.get("status")=="APPROVED" and waiver.get("expiresAtEpoch",0)>now_epoch and bool(waiver.get("owner"))

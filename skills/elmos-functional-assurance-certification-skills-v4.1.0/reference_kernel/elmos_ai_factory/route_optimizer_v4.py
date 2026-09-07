from __future__ import annotations

def select_tests(cases:list[dict],budget:float)->list[str]:
    mandatory=[c for c in cases if c.get('mandatory') or c.get('critical')]
    spent=sum(c['cost'] for c in mandatory)
    if spent>budget: raise RuntimeError('mandatory tests exceed budget')
    optional=sorted([c for c in cases if c not in mandatory],key=lambda c:(-c.get('risk',0),c['cost']))
    out=list(mandatory)
    for c in optional:
        if spent+c['cost']<=budget: out.append(c);spent+=c['cost']
    return [c['id'] for c in out]

def route_score(route:dict)->float:
    return route['coverage']*route['reversibility']/(1+route['risk']+route['cost'])

def choose_route(routes:list[dict])->str:
    eligible=[r for r in routes if r.get('native',False) and r.get('rollback',False)]
    if not eligible: raise LookupError('no eligible route')
    return max(eligible,key=route_score)['name']

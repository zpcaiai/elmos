from __future__ import annotations
from collections import defaultdict,deque
def topological_order(nodes:list[str],edges:list[tuple[str,str]])->list[str]:
    indeg={n:0 for n in nodes};out=defaultdict(list)
    for a,b in edges:
        if a not in indeg or b not in indeg:raise KeyError("unknown node")
        indeg[b]+=1;out[a].append(b)
    q=deque(sorted(n for n,v in indeg.items() if v==0));order=[]
    while q:
        n=q.popleft();order.append(n)
        for m in sorted(out[n]):
            indeg[m]-=1
            if indeg[m]==0:q.append(m)
    if len(order)!=len(nodes):raise ValueError("cycle")
    return order
def select_cases(cases:list[dict],changed:set[str],min_risk="high")->list[str]:
    rank={"low":0,"medium":1,"high":2,"critical":3};threshold=rank[min_risk]
    return sorted(c["id"] for c in cases if rank[c.get("risk","low")]>=threshold or changed & set(c.get("covers",[])) or c.get("mandatory"))
def critical_path(order:list[str],durations:dict[str,float],edges:list[tuple[str,str]])->tuple[float,list[str]]:
    prev={n:None for n in order};dist={n:durations.get(n,0.0) for n in order}
    for a,b in edges:
        if dist[a]+durations.get(b,0)>dist[b]:dist[b]=dist[a]+durations.get(b,0);prev[b]=a
    end=max(order,key=lambda n:dist[n]);path=[]
    while end is not None:path.append(end);end=prev[end]
    return dist[path[0]],list(reversed(path))

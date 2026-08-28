from __future__ import annotations
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class TopologyIssue:
    code: str
    subject: str


def validate_topology(topology: dict[str,Any]) -> tuple[TopologyIssue,...]:
    issues=[]; agents=topology.get('agents',[])
    ids=[a.get('id') for a in agents if isinstance(a,dict)]
    if len(ids)!=len(set(ids)):
        issues.append(TopologyIssue('duplicate-agent','agents'))
    known=set(ids)
    for d in topology.get('delegations',[]):
        if d.get('from') not in known or d.get('to') not in known:
            issues.append(TopologyIssue('unknown-delegation-agent',str(d)))
        parent=set(d.get('parentScope',d.get('scope',[]))); child=set(d.get('scope',[]))
        if not child.issubset(parent):
            issues.append(TopologyIssue('scope-expansion',f"{d.get('from')}->{d.get('to')}"))
    for key,owner in topology.get('stateOwners',{}).items():
        if owner not in known:
            issues.append(TopologyIssue('unknown-state-owner',key))
    termination=topology.get('termination',{})
    if not any(int(termination.get(k,0))>0 for k in ('maxRounds','maxSteps','wallClockSeconds')):
        issues.append(TopologyIssue('unbounded-termination','termination'))
    budgets=topology.get('budgets',{})
    if not budgets or any(v<=0 for v in budgets.values() if isinstance(v,(int,float))):
        issues.append(TopologyIssue('invalid-budget','budgets'))
    return tuple(issues)


def dependency_cycle(edges: list[tuple[str,str]]) -> bool:
    graph: dict[str,set[str]]={}
    for a,b in edges: graph.setdefault(a,set()).add(b); graph.setdefault(b,set())
    visiting=set(); visited=set()
    def dfs(node: str) -> bool:
        if node in visiting:return True
        if node in visited:return False
        visiting.add(node)
        for nxt in graph[node]:
            if dfs(nxt):return True
        visiting.remove(node);visited.add(node);return False
    return any(dfs(n) for n in graph)

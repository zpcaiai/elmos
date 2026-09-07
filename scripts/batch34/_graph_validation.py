from __future__ import annotations

def unique_ids(items, label):
    seen=set(); errors=[]
    for item in items:
        ident=item.get("id")
        if not ident: errors.append(f"{label}: missing id"); continue
        if ident in seen: errors.append(f"{label}: duplicate id {ident}")
        seen.add(ident)
    return seen, errors

def find_cycle(adjacency):
    state={}; stack=[]; positions={}
    def visit(node):
        state[node]=1; positions[node]=len(stack); stack.append(node)
        for dependency in adjacency.get(node,[]):
            if state.get(dependency,0)==0:
                cycle=visit(dependency)
                if cycle: return cycle
            elif state.get(dependency)==1:
                return stack[positions[dependency]:]+[dependency]
        stack.pop(); positions.pop(node,None); state[node]=2; return None
    for node in sorted(adjacency):
        if state.get(node,0)==0:
            cycle=visit(node)
            if cycle: return cycle
    return None

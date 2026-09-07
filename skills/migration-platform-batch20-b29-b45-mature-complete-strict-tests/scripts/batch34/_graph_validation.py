from __future__ import annotations

def unique_ids(items, label):
    seen=set(); errors=[]
    for item in items:
        ident=item.get("id")
        if not ident: errors.append(f"{label}: missing id"); continue
        if ident in seen: errors.append(f"{label}: duplicate id {ident}")
        seen.add(ident)
    return seen, errors

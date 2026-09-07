from __future__ import annotations
from decimal import Decimal
from datetime import datetime,timezone
def normalize_scalar(v,empty_string_is_null=False):
    if empty_string_is_null and v=="":return None
    if isinstance(v,float):return Decimal(str(v))
    if isinstance(v,datetime):return v.astimezone(timezone.utc).isoformat()
    return v
def normalize_rows(rows:list[dict],empty_string_is_null=False,ordered=False):
    out=[tuple(sorted((k,normalize_scalar(v,empty_string_is_null)) for k,v in r.items())) for r in rows]
    return out if ordered else sorted(out,key=repr)
def compare_rows(source:list[dict],target:list[dict],**opts)->dict:
    a=normalize_rows(source,**opts);b=normalize_rows(target,**opts)
    return {"equivalent":a==b,"source":a,"target":b,"differenceCount":0 if a==b else max(len(a),len(b))}
def transaction_equivalent(source:list[str],target:list[str],commuting:set[frozenset[str]]|None=None)->bool:
    if source==target:return True
    commuting=commuting or set()
    if sorted(source)!=sorted(target):return False
    pos={x:i for i,x in enumerate(target)}
    for i,a in enumerate(source):
        for b in source[i+1:]:
            if pos[a]>pos[b] and frozenset({a,b}) not in commuting:return False
    return True

from __future__ import annotations

def delivery_settled(produced:set[str],consumed:set[str],deduped:set[str])->bool:
    return produced <= (consumed|deduped)

def saga_complete(done:list[str],compensated:list[str],required:list[str])->bool:
    return set(required)<=set(done) or set(done)<=set(compensated)

def schema_compatible(old_fields:set[str],new_fields:set[str],required_new:set[str])->bool:
    return old_fields<=new_fields and not (required_new-old_fields)

def replay_deterministic(a:list[tuple],b:list[tuple])->bool:
    return a==b

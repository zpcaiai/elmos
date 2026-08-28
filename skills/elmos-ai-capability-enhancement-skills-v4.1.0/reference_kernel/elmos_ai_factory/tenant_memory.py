from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class MemoryRecord:
    record_id: str
    tenant_id: str
    scope: str
    owner_id: str
    consent_id: str|None=None
    deleted: bool=False


def authorize_memory(record: MemoryRecord, *, tenant_id: str, principal_id: str, allowed_scopes: frozenset[str], consent_ids: frozenset[str]=frozenset()) -> str:
    if record.deleted: return 'DENY_DELETED'
    if record.tenant_id!=tenant_id: return 'DENY_TENANT'
    if record.scope not in allowed_scopes: return 'DENY_SCOPE'
    if record.owner_id!=principal_id and (not record.consent_id or record.consent_id not in consent_ids): return 'DENY_CONSENT'
    return 'ALLOW'


def isolation_probe(records, *, tenant_id: str) -> tuple[bool,tuple[str,...]]:
    leaks=tuple(r.record_id for r in records if r.tenant_id!=tenant_id)
    return (not leaks,leaks)

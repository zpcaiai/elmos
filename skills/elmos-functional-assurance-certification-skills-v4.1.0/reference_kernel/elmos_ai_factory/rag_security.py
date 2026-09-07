from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable

@dataclass(frozen=True)
class RetrievalCandidate:
    document_id: str
    tenant_id: str
    principals: frozenset[str]
    deleted: bool
    poison_score: float
    citation_source: str | None


def authorize_candidates(candidates: Iterable[RetrievalCandidate], *, tenant_id: str, principal: str, poison_threshold: float=.5) -> tuple[list[RetrievalCandidate],list[str]]:
    allowed=[]; findings=[]
    for c in candidates:
        if c.tenant_id != tenant_id:
            findings.append(f"cross-tenant:{c.document_id}"); continue
        if c.deleted:
            findings.append(f"deleted-visible:{c.document_id}"); continue
        if principal not in c.principals:
            findings.append(f"acl-denied:{c.document_id}"); continue
        if c.poison_score >= poison_threshold:
            findings.append(f"poison-quarantine:{c.document_id}"); continue
        if not c.citation_source:
            findings.append(f"citation-missing:{c.document_id}"); continue
        allowed.append(c)
    return allowed,findings


def deletion_reconciled(document_id: str, stores: dict[str,set[str]]) -> bool:
    return all(document_id not in values for values in stores.values())

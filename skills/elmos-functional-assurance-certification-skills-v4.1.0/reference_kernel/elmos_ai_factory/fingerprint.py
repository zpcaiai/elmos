from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Iterable

@dataclass(frozen=True)
class FingerprintDelta:
    path: str
    before: Any
    after: Any
    critical: bool

_CRITICAL_PREFIXES=("resolvedModel","toolBehavior","structuredOutput","safety","dataPolicy","region")


def _flatten(value: Any, prefix: str="") -> dict[str,Any]:
    if isinstance(value,dict):
        out={}
        for key,item in value.items():
            child=f"{prefix}.{key}" if prefix else str(key)
            out.update(_flatten(item,child))
        return out
    return {prefix:value}


def compare_fingerprints(before: dict[str,Any], after: dict[str,Any]) -> tuple[FingerprintDelta,...]:
    a=_flatten(before); b=_flatten(after); rows=[]
    for key in sorted(set(a)|set(b)):
        if a.get(key)!=b.get(key):
            rows.append(FingerprintDelta(key,a.get(key),b.get(key),key.startswith(_CRITICAL_PREFIXES)))
    return tuple(rows)


def recertification_decision(deltas: Iterable[FingerprintDelta], *, evidence_expired: bool=False) -> str:
    rows=list(deltas)
    if evidence_expired or any(d.critical for d in rows):
        return "RECERTIFY"
    return "BOUNDED_REVIEW" if rows else "REUSE_EVIDENCE"

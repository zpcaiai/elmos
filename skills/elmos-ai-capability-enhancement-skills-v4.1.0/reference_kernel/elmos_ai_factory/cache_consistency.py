from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from typing import Mapping, Iterable

@dataclass(frozen=True)
class CacheContext:
    tenant_id: str
    policy_digest: str
    model_fingerprint: str
    tool_digest: str
    corpus_version: str
    prompt_digest: str


def semantic_key(ctx: CacheContext, normalized_input: str) -> str:
    parts=(ctx.tenant_id,ctx.policy_digest,ctx.model_fingerprint,ctx.tool_digest,ctx.corpus_version,ctx.prompt_digest,normalized_input)
    if any(not p for p in parts):
        raise ValueError('all semantic-key dimensions are required')
    return 'sha256:'+sha256('\x1f'.join(parts).encode()).hexdigest()


def cache_reuse_decision(stored: CacheContext, current: CacheContext, *, fresh: bool, quarantined: bool=False) -> tuple[str,tuple[str,...]]:
    reasons=[]
    for field in stored.__dataclass_fields__:
        if getattr(stored,field)!=getattr(current,field): reasons.append(f'{field}-changed')
    if not fresh: reasons.append('stale')
    if quarantined: reasons.append('quarantined')
    return ('MISS' if reasons else 'HIT',tuple(reasons))

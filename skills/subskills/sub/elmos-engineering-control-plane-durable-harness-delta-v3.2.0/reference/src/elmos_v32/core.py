from dataclasses import dataclass, field
from enum import Enum
from typing import FrozenSet, Iterable

class Negotiation(str, Enum):
    SUPPORTED_EXACTLY='SUPPORTED_EXACTLY'
    SUPPORTED_WITH_NARROWER_SCOPE='SUPPORTED_WITH_NARROWER_SCOPE'
    UNSUPPORTED='UNSUPPORTED'

class VerificationStatus(str, Enum):
    PASS='PASS'; FAIL='FAIL'; WAIVED='WAIVED'; PENDING='PENDING'

class RuntimeState(str, Enum):
    UNKNOWN='UNKNOWN'; NOT_STARTED='NOT_STARTED'; STARTING='STARTING'; CONNECTED='CONNECTED'; AUTHENTICATION_REQUIRED='AUTHENTICATION_REQUIRED'; FAILED='FAILED'; CANCELLED='CANCELLED'; DISABLED='DISABLED'

@dataclass(frozen=True)
class Policy:
    allows: FrozenSet[str] = field(default_factory=frozenset)
    denies: FrozenSet[str] = field(default_factory=frozenset)

def intersect_policies(*policies: Policy) -> Policy:
    if not policies: return Policy()
    allows=set(policies[0].allows)
    denies=set()
    for p in policies:
        allows &= set(p.allows)
        denies |= set(p.denies)
    allows -= denies
    return Policy(frozenset(allows), frozenset(denies))

def monotonic_authority(parent: Iterable[str], child: Iterable[str]) -> bool:
    return set(child).issubset(set(parent))

def negotiate(requested: Iterable[str], supported: Iterable[str], denied: Iterable[str]=()):
    r=set(requested); s=set(supported)-set(denied)
    eff=r & s
    if not eff and r: return Negotiation.UNSUPPORTED, frozenset()
    if eff == r: return Negotiation.SUPPORTED_EXACTLY, frozenset(eff)
    return Negotiation.SUPPORTED_WITH_NARROWER_SCOPE, frozenset(eff)

@dataclass
class OwnerRecord:
    execution_id: str
    owner_id: str
    epoch: int
    state: str='OWNED'
    def handoff_ready(self):
        if self.state not in {'OWNED','QUIESCING'}: raise ValueError('invalid ownership transition')
        self.state='HANDOFF_READY'
    def transfer(self, new_owner: str, expected_epoch: int):
        if self.state!='HANDOFF_READY' or expected_epoch != self.epoch: raise ValueError('stale or unsafe transfer')
        self.owner_id=new_owner; self.epoch += 1; self.state='OWNED'

class RuntimeStatusObserver:
    def __init__(self, state=RuntimeState.UNKNOWN): self.state=state; self.connect_calls=0
    def observe(self): return self.state
    def connect(self): self.connect_calls += 1; self.state=RuntimeState.CONNECTED

def release_gate(checks, exact_artifact_verified: bool) -> bool:
    return exact_artifact_verified and checks and all(c == VerificationStatus.PASS for c in checks)

def approval_matches(binding: dict, current: dict) -> bool:
    keys=('execution_plan_digest','action_kind','resource_digest')
    return all(binding.get(k)==current.get(k) for k in keys)

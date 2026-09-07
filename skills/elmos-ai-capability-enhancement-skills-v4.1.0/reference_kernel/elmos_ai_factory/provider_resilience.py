from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class ProviderCandidate:
    name:str
    healthy:bool
    region:str
    capabilities:frozenset[str]
    data_policy:frozenset[str]
    cost_rank:int


def select_provider(candidates, *, required_capabilities:frozenset[str],allowed_regions:frozenset[str],required_policy:frozenset[str]):
    eligible=[c for c in candidates if c.healthy and c.region in allowed_regions and required_capabilities.issubset(c.capabilities) and required_policy.issubset(c.data_policy)]
    if not eligible:return None
    return min(eligible,key=lambda c:(c.cost_rank,c.name))

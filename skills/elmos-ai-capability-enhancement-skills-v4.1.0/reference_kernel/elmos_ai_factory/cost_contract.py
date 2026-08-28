from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal

@dataclass(frozen=True)
class Usage:
    input_tokens:int=0
    output_tokens:int=0
    compute_seconds:Decimal=Decimal('0')
    storage_gb_hours:Decimal=Decimal('0')
    network_gb:Decimal=Decimal('0')

@dataclass(frozen=True)
class Rates:
    input_per_million:Decimal
    output_per_million:Decimal
    compute_per_second:Decimal
    storage_per_gb_hour:Decimal
    network_per_gb:Decimal


def calculate_cost(u:Usage,r:Rates)->Decimal:
    if min(u.input_tokens,u.output_tokens)<0 or any(x<0 for x in (u.compute_seconds,u.storage_gb_hours,u.network_gb)):raise ValueError('negative usage')
    total=(Decimal(u.input_tokens)/Decimal(1_000_000)*r.input_per_million+
           Decimal(u.output_tokens)/Decimal(1_000_000)*r.output_per_million+
           u.compute_seconds*r.compute_per_second+u.storage_gb_hours*r.storage_per_gb_hour+u.network_gb*r.network_per_gb)
    return total.quantize(Decimal('0.000001'))

def budget_decision(cost:Decimal,budget:Decimal,contingency:Decimal=Decimal('0'))->str:
    return 'ALLOW' if cost<=budget-contingency else 'BLOCKED'

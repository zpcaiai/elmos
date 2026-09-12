from __future__ import annotations
from dataclasses import dataclass, field

MAX_TX = 500

@dataclass(frozen=True)
class TransactionPolicy:
    propagation: str
    isolation: str
    read_only: bool
    rollback_for: list[str]

@dataclass(frozen=True)
class TransactionConfig:
    method_policies: dict[str, TransactionPolicy]
    propagation_chains: list[list[str]]

class TransactionBoundaryExtractor:
    def extract(self, methods: list[dict]) -> TransactionConfig:
        if len(methods) > MAX_TX:
            raise ValueError(f"Too many methods. Max allowed is {MAX_TX}")
            
        policies = {}
        for m in methods:
            name = m.get("name")
            if name:
                policies[name] = TransactionPolicy(
                    propagation=m.get("propagation", "REQUIRED"),
                    isolation=m.get("isolation", "DEFAULT"),
                    read_only=m.get("read_only", False),
                    rollback_for=m.get("rollback_for", ["Exception"])
                )
                
        return TransactionConfig(
            method_policies=policies,
            propagation_chains=[]
        )

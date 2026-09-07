from __future__ import annotations
from dataclasses import dataclass
from typing import Mapping

@dataclass(frozen=True)
class ToolContract:
    required_inputs: frozenset[str]
    optional_inputs: frozenset[str]
    output_fields: frozenset[str]
    effect: str
    idempotent: bool
    approval: str
    retry_class: str


def compare_tools(old: ToolContract,new: ToolContract) -> tuple[str,tuple[str,...]]:
    issues=[]
    if not old.required_inputs.issuperset(new.required_inputs): issues.append('new-required-input')
    if not old.output_fields.issubset(new.output_fields): issues.append('removed-output')
    if old.effect!=new.effect: issues.append('effect-changed')
    if old.idempotent and not new.idempotent: issues.append('idempotency-weakened')
    if old.approval!=new.approval: issues.append('approval-changed')
    if old.retry_class!=new.retry_class: issues.append('retry-semantics-changed')
    critical={'effect-changed','idempotency-weakened','approval-changed'}
    return ('BLOCKED' if critical.intersection(issues) else ('BOUNDED' if issues else 'COMPATIBLE'),tuple(issues))

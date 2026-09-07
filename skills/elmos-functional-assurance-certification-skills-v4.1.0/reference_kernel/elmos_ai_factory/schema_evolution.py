from __future__ import annotations
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class CompatibilityIssue:
    path: str
    code: str
    message: str


def backward_compatibility(old: dict[str,Any], new: dict[str,Any]) -> tuple[CompatibilityIssue,...]:
    issues=[]
    old_props=old.get('properties',{}); new_props=new.get('properties',{})
    old_required=set(old.get('required',[])); new_required=set(new.get('required',[]))
    for field in sorted(new_required-old_required):
        issues.append(CompatibilityIssue(field,'new-required-field','new consumers require a field old producers may omit'))
    for field,old_spec in old_props.items():
        if field not in new_props:
            issues.append(CompatibilityIssue(field,'removed-field','field was removed'))
            continue
        new_spec=new_props[field]
        if old_spec.get('type') != new_spec.get('type'):
            issues.append(CompatibilityIssue(field,'type-change',f"{old_spec.get('type')} -> {new_spec.get('type')}"))
        old_enum=set(old_spec.get('enum',[])); new_enum=set(new_spec.get('enum',[]))
        if old_enum and new_enum and not old_enum.issubset(new_enum):
            issues.append(CompatibilityIssue(field,'enum-narrowing','new schema rejects prior enum values'))
    return tuple(issues)


def evolution_decision(issues: tuple[CompatibilityIssue,...], *, migration_present: bool, consumer_tests_pass: bool) -> str:
    if issues and not migration_present:
        return "BLOCKED"
    if issues or not consumer_tests_pass:
        return "BOUNDED"
    return "COMPATIBLE"

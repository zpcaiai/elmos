from __future__ import annotations
from dataclasses import dataclass, field
from typing import Mapping, Sequence

ALLOWED = {
    "supported", "conditional", "emulated", "external-runtime",
    "external-policy", "unsupported", "blocked",
}

@dataclass(frozen=True)
class FeatureRequirement:
    name: str
    critical: bool = True
    accepted_statuses: frozenset[str] = frozenset(
        {"supported", "conditional", "external-runtime", "external-policy"}
    )

@dataclass(frozen=True)
class TargetProfile:
    target: str
    features: Mapping[str, str]
    exact_version: str
    adapter_digest: str

@dataclass(frozen=True)
class FeatureDecision:
    requirement: str
    target: str
    status: str
    critical: bool
    obligations: tuple[str, ...] = ()

@dataclass(frozen=True)
class TargetDecision:
    target: str
    overall: str
    decisions: tuple[FeatureDecision, ...]

@dataclass(frozen=True)
class NegotiationResult:
    overall: str
    targets: tuple[TargetDecision, ...]
    blocked_reasons: tuple[str, ...] = ()

def _obligations(status: str, feature: str) -> tuple[str, ...]:
    if status == "supported":
        return (f"native-conformance:{feature}",)
    if status == "conditional":
        return (f"condition-proof:{feature}", f"native-conformance:{feature}")
    if status == "emulated":
        return (f"emulation-equivalence:{feature}", f"performance-bound:{feature}")
    if status == "external-runtime":
        return (f"runtime-integration:{feature}", f"failure-recovery:{feature}")
    if status == "external-policy":
        return (f"policy-enforcement:{feature}", f"negative-policy-test:{feature}")
    return (f"blocked-capability:{feature}",)

def negotiate(
    requirements: Sequence[FeatureRequirement],
    profiles: Sequence[TargetProfile],
) -> NegotiationResult:
    if not requirements:
        raise ValueError("at least one requirement is required")
    if not profiles:
        return NegotiationResult("BLOCKED", (), ("no target profiles",))

    target_results: list[TargetDecision] = []
    global_reasons: list[str] = []
    for profile in profiles:
        if not profile.exact_version or not profile.adapter_digest.startswith("sha256:"):
            target_results.append(TargetDecision(
                profile.target, "BLOCKED", tuple(
                    FeatureDecision(r.name, profile.target, "blocked", r.critical,
                                    ("release-pin-missing",)) for r in requirements
                )
            ))
            global_reasons.append(f"{profile.target}: exact version or adapter digest missing")
            continue

        decisions: list[FeatureDecision] = []
        target_blocked = False
        target_bounded = False
        for req in requirements:
            status = profile.features.get(req.name, "unsupported")
            if status not in ALLOWED:
                status = "blocked"
            if req.critical and status not in req.accepted_statuses:
                target_blocked = True
            elif status != "supported":
                target_bounded = True
            decisions.append(FeatureDecision(
                req.name, profile.target, status, req.critical, _obligations(status, req.name)
            ))
        overall = "BLOCKED" if target_blocked else ("BOUNDED" if target_bounded else "SUPPORTED")
        target_results.append(TargetDecision(profile.target, overall, tuple(decisions)))

    if all(t.overall == "BLOCKED" for t in target_results):
        overall = "BLOCKED"
        if not global_reasons:
            global_reasons.append("every target blocks at least one critical requirement")
    elif any(t.overall == "BOUNDED" for t in target_results) or any(t.overall == "BLOCKED" for t in target_results):
        overall = "BOUNDED"
    else:
        overall = "SUPPORTED"
    return NegotiationResult(overall, tuple(target_results), tuple(global_reasons))

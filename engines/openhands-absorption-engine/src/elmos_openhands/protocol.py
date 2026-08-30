"""Action/Observation schema negotiation and executable conformance harness."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .errors import ContractViolation
from .firewall import FirewallContext
from .models import SCHEMA_VERSION, Action, ActionStatus, Identity, Observation, digest_of
from .tools import CancellationToken, ToolGateway, ToolRegistry


@dataclass(frozen=True, slots=True)
class NegotiatedProtocol:
    action_version: str
    observation_version: str
    provider_version: str
    features: frozenset[str]
    digest: str


class ProtocolNegotiator:
    def __init__(self, *, supported_versions: Iterable[str] = (SCHEMA_VERSION,), features: Iterable[str] = ()) -> None:
        self.supported_versions = tuple(dict.fromkeys(supported_versions))
        self.features = frozenset(features)
        if not self.supported_versions:
            raise ContractViolation("at least one protocol version is required")

    def negotiate(self, peer: Mapping[str, Any]) -> NegotiatedProtocol:
        action_versions = tuple(str(item) for item in peer.get("action_versions", ()))
        observation_versions = tuple(str(item) for item in peer.get("observation_versions", ()))
        provider_versions = tuple(str(item) for item in peer.get("provider_versions", ()))
        action = self._highest(action_versions)
        observation = self._highest(observation_versions)
        provider = self._highest(provider_versions)
        features = self.features & frozenset(str(item) for item in peer.get("features", ()))
        body = {"action": action, "observation": observation, "provider": provider, "features": sorted(features)}
        return NegotiatedProtocol(action, observation, provider, features, digest_of(body))

    def _highest(self, offered: tuple[str, ...]) -> str:
        compatible = [version for version in self.supported_versions if version in offered]
        if not compatible:
            raise ContractViolation("peer has no compatible protocol version")
        return compatible[-1]


@dataclass(frozen=True, slots=True)
class ConformanceCase:
    case_id: str
    category: str
    action: Action
    expected_status: ActionStatus
    verify: Callable[[Observation], bool] | None = None
    replay: bool = True

    def __post_init__(self) -> None:
        if not self.case_id or self.category not in {"filesystem", "shell", "git", "build", "test", "browser", "cancellation", "reconciliation"}:
            raise ContractViolation("invalid tool conformance case")


@dataclass(frozen=True, slots=True)
class ConformanceResult:
    case_id: str
    category: str
    status: str
    observation_status: str
    replay_equivalent: bool
    evidence_digest: str
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class ConformanceReport:
    tool_name: str
    results: tuple[ConformanceResult, ...]
    status: str
    digest: str
    certification: str = "NOT_CERTIFIED"


class ToolConformanceHarness:
    """Runs contract cases against the real Tool Gateway policy boundary."""

    def __init__(self, registry: ToolRegistry, gateway: ToolGateway) -> None:
        self.registry = registry
        self.gateway = gateway

    def run(
        self,
        identity: Identity,
        tool_name: str,
        cases: Iterable[ConformanceCase],
        context: FirewallContext,
        *,
        approval: str | None = None,
    ) -> ConformanceReport:
        self.registry.spec(tool_name)
        rows: list[ConformanceResult] = []
        for case in cases:
            if case.action.tool != tool_name:
                raise ContractViolation("conformance action targets a different tool")
            cancellation = CancellationToken()
            if case.category == "cancellation":
                cancellation.cancel("conformance cancellation")
            observation = self.gateway.execute(identity, case.action, context, approved_by=approval, cancellation=cancellation)
            replay_equivalent = True
            if case.replay:
                replay = self.gateway.execute(identity, case.action, context, approved_by=approval, cancellation=cancellation)
                replay_equivalent = replay.as_dict() == observation.as_dict()
            passed = observation.status == case.expected_status and replay_equivalent and (case.verify is None or bool(case.verify(observation)))
            body = {"case": case.case_id, "observation": observation.as_dict(), "replay_equivalent": replay_equivalent}
            rows.append(
                ConformanceResult(
                    case.case_id,
                    case.category,
                    "pass" if passed else "fail",
                    observation.status.value,
                    replay_equivalent,
                    digest_of(body),
                    None if passed else "status, replay, or case oracle did not match",
                )
            )
        if not rows:
            raise ContractViolation("conformance suite cannot be empty")
        status = "pass" if all(row.status == "pass" for row in rows) else "fail"
        body = {"tool": tool_name, "results": [row.evidence_digest for row in rows], "status": status}
        return ConformanceReport(tool_name, tuple(rows), status, digest_of(body))

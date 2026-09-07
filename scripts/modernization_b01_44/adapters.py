#!/usr/bin/env python3
"""Provider registry with pinned versions and drift detection.

An adapter is registered with an exact version and a contract digest.  When the
observed provider no longer matches what a certificate was issued against, the
registry reports drift and the certificate is invalidated - the run does not
continue on the assumption that "it is probably compatible".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from scripts.modernization_b01_44.canonical import digest
from scripts.modernization_b01_44.errors import ProviderDrift, RuntimeRefusal

SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$")


def parse_version(value: str) -> tuple[int, int, int]:
    match = SEMVER_RE.match(value)
    if not match:
        raise RuntimeRefusal("provider version is not semver", version=value)
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


@dataclass(frozen=True)
class AdapterBinding:
    """One provider, pinned to an exact version and contract."""

    provider_id: str
    version: str
    contract_digest: str
    capabilities: tuple[str, ...]
    handler: Callable[[dict[str, Any]], dict[str, Any]] | None = None

    def pin(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "version": self.version,
            "contract_digest": self.contract_digest,
        }

    @property
    def pin_digest(self) -> str:
        return digest(self.pin())


@dataclass
class DriftReport:
    provider_id: str
    kind: str  # absent | version | contract
    pinned: dict[str, Any]
    observed: dict[str, Any] | None
    breaking: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "kind": self.kind,
            "pinned": self.pinned,
            "observed": self.observed,
            "breaking": self.breaking,
        }


class AdapterRegistry:
    """Register, resolve and drift-check providers."""

    def __init__(self) -> None:
        self._bindings: dict[str, AdapterBinding] = {}

    def register(
        self,
        provider_id: str,
        version: str,
        *,
        contract: Any,
        capabilities: Iterable[str] = (),
        handler: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> AdapterBinding:
        parse_version(version)
        binding = AdapterBinding(
            provider_id=provider_id,
            version=version,
            contract_digest=digest(contract),
            capabilities=tuple(sorted(set(capabilities))),
            handler=handler,
        )
        self._bindings[provider_id] = binding
        return binding

    def get(self, provider_id: str) -> AdapterBinding:
        try:
            return self._bindings[provider_id]
        except KeyError:
            raise RuntimeRefusal("provider is not registered", provider_id=provider_id) from None

    def ids(self) -> list[str]:
        return sorted(self._bindings)

    def supporting(self, capability: str) -> list[AdapterBinding]:
        return [b for _, b in sorted(self._bindings.items()) if capability in b.capabilities]

    def invoke(self, provider_id: str, request: dict[str, Any]) -> dict[str, Any]:
        binding = self.get(provider_id)
        if binding.handler is None:
            raise RuntimeRefusal(
                "provider is declared but has no executable handler",
                provider_id=provider_id,
            )
        return binding.handler(request)

    # -- drift ------------------------------------------------------------

    def detect_drift(self, pins: Iterable[dict[str, Any]]) -> list[DriftReport]:
        """Compare certificate-time pins against what is registered now."""

        reports: list[DriftReport] = []
        for pin in sorted(pins, key=lambda item: item["provider_id"]):
            provider_id = pin["provider_id"]
            binding = self._bindings.get(provider_id)
            if binding is None:
                reports.append(
                    DriftReport(provider_id, "absent", dict(pin), None, breaking=True)
                )
                continue
            observed = binding.pin()
            if observed["version"] != pin["version"]:
                pinned_major = parse_version(pin["version"])[0]
                observed_major = parse_version(observed["version"])[0]
                reports.append(
                    DriftReport(
                        provider_id,
                        "version",
                        dict(pin),
                        observed,
                        breaking=observed_major != pinned_major,
                    )
                )
                continue
            if observed["contract_digest"] != pin["contract_digest"]:
                reports.append(
                    DriftReport(provider_id, "contract", dict(pin), observed, breaking=True)
                )
        return reports

    def assert_no_breaking_drift(self, pins: Iterable[dict[str, Any]]) -> None:
        reports = [r for r in self.detect_drift(pins) if r.breaking]
        if reports:
            raise ProviderDrift(
                "provider drift invalidates the pinned contract",
                reports=[r.as_dict() for r in reports],
            )

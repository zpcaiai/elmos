"""Spring Modernization Coexistence Strangler Proxy and Outbox Dual-Write Auditor.

Provides intelligent traffic steering between legacy monolith and modernized Spring Boot 3
services using path, header, and cookie routing rules, along with an Outbox Dual-Write
consistency auditor to guarantee zero semantic drift during incremental migration.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class RouteDestination(str, Enum):
    LEGACY = "legacy"
    MODERN = "modern"
    DUAL_WRITE = "dual_write"


@dataclass
class ProxyRoutingDecision:
    destination: RouteDestination
    target_url: str
    headers: dict[str, str]
    matched_rule: str
    canary_evaluated: bool = False
    audit_trace_id: str = ""


@dataclass
class DualWriteComparisonResult:
    is_equivalent: bool
    legacy_event_id: str
    modern_event_id: str
    mismatched_fields: list[str] = field(default_factory=list)
    semantic_drift_detected: bool = False
    payload_hash_legacy: str = ""
    payload_hash_modern: str = ""


class CoexistenceStranglerProxy:
    """HTTP reverse proxy and traffic governor for Spring legacy modernization coexistence."""

    def __init__(
        self,
        legacy_base_url: str = "http://localhost:8080/legacy",
        modern_base_url: str = "http://localhost:8081/modern",
        canary_weight_percentage: float = 0.0,
    ) -> None:
        self.legacy_base = legacy_base_url.rstrip("/")
        self.modern_base = modern_base_url.rstrip("/")
        self.canary_weight = canary_weight_percentage
        self.migrated_path_prefixes: set[str] = set()
        self.header_routing_rules: dict[str, str] = {}  # header_name -> expected_val

    def register_migrated_route(self, path_prefix: str) -> None:
        """Registers an exact or prefix route that has been modernized to Spring Boot 3."""
        self.migrated_path_prefixes.add(path_prefix.rstrip("/"))

    def add_header_rule(self, header_name: str, expected_val: str) -> None:
        self.header_routing_rules[header_name.lower()] = expected_val

    def route_request(
        self,
        path: str,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        request_id: str = "",
    ) -> ProxyRoutingDecision:
        headers = headers or {}
        trace_id = request_id or hashlib.sha256(f"{path}:{method}".encode()).hexdigest()[:16]
        normalized_headers = {k.lower(): v for k, v in headers.items()}

        # 1. Header override takes highest precedence (e.g. for testing & canary debugging)
        for h_name, expected in self.header_routing_rules.items():
            if normalized_headers.get(h_name) == expected:
                return ProxyRoutingDecision(
                    destination=RouteDestination.MODERN,
                    target_url=f"{self.modern_base}{path}",
                    headers=headers,
                    matched_rule=f"header-match:{h_name}={expected}",
                    audit_trace_id=trace_id,
                )

        # 2. Check path prefix match against migrated routes
        for prefix in sorted(self.migrated_path_prefixes, key=len, reverse=True):
            if path == prefix or path.startswith(f"{prefix}/"):
                # Path is migrated; check if dual-write or pure modern
                if normalized_headers.get("x-dual-write-shadow") == "true":
                    dest = RouteDestination.DUAL_WRITE
                else:
                    dest = RouteDestination.MODERN

                target = f"{self.modern_base}{path}" if dest == RouteDestination.MODERN else f"{self.legacy_base}{path}"
                return ProxyRoutingDecision(
                    destination=dest,
                    target_url=target,
                    headers=headers,
                    matched_rule=f"path-prefix:{prefix}",
                    audit_trace_id=trace_id,
                )

        # 3. Default fallback to legacy monolith
        return ProxyRoutingDecision(
            destination=RouteDestination.LEGACY,
            target_url=f"{self.legacy_base}{path}",
            headers=headers,
            matched_rule="default-legacy-fallback",
            audit_trace_id=trace_id,
        )


class OutboxDualWriteAuditor:
    """Compares Outbox messages emitted by legacy and modern systems during shadow dual-run."""

    def compare_events(
        self,
        legacy_event: dict[str, Any],
        modern_event: dict[str, Any],
        ignored_fields: set[str] | None = None,
    ) -> DualWriteComparisonResult:
        ignored = ignored_fields or {"timestamp", "created_at", "trace_id", "span_id"}
        mismatches: list[str] = []

        legacy_id = str(legacy_event.get("event_id") or legacy_event.get("id") or "legacy-anon")
        modern_id = str(modern_event.get("event_id") or modern_event.get("id") or "modern-anon")

        # Compare aggregate type and topic
        for key in ("aggregate_type", "event_type", "topic"):
            if legacy_event.get(key) != modern_event.get(key):
                mismatches.append(f"metadata.{key}: {legacy_event.get(key)} != {modern_event.get(key)}")

        # Canonicalize payloads
        leg_payload = legacy_event.get("payload", {})
        mod_payload = modern_event.get("payload", {})

        if isinstance(leg_payload, str):
            try:
                leg_payload = json.loads(leg_payload)
            except Exception:
                pass
        if isinstance(mod_payload, str):
            try:
                mod_payload = json.loads(mod_payload)
            except Exception:
                pass

        if isinstance(leg_payload, dict) and isinstance(mod_payload, dict):
            all_keys = set(leg_payload) | set(mod_payload) - ignored
            for k in sorted(all_keys):
                if leg_payload.get(k) != mod_payload.get(k):
                    mismatches.append(f"payload.{k}: {leg_payload.get(k)} != {mod_payload.get(k)}")

        leg_hash = hashlib.sha256(json.dumps(leg_payload, sort_keys=True).encode()).hexdigest()
        mod_hash = hashlib.sha256(json.dumps(mod_payload, sort_keys=True).encode()).hexdigest()

        return DualWriteComparisonResult(
            is_equivalent=(len(mismatches) == 0),
            legacy_event_id=legacy_id,
            modern_event_id=modern_id,
            mismatched_fields=mismatches,
            semantic_drift_detected=(len(mismatches) > 0),
            payload_hash_legacy=f"sha256:{leg_hash}",
            payload_hash_modern=f"sha256:{mod_hash}",
        )

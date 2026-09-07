from __future__ import annotations

import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from .canonical import canonical_json, digest_value, validate_identifier
from .contracts import Scope
from .store import StateStore


class ObservabilityError(RuntimeError):
    pass


class TelemetryExporter(Protocol):
    @property
    def exporter_id(self) -> str: ...

    def export(self, document: Mapping[str, Any]) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class OtlpHttpJsonExporter:
    """Host-configured HTTPS exporter with bounded request/response behavior."""

    endpoint: str
    headers: Mapping[str, str]
    timeout_seconds: int = 10
    allow_loopback_http: bool = False

    def __post_init__(self) -> None:
        parsed = urllib.parse.urlparse(self.endpoint)
        loopback = parsed.hostname in {"127.0.0.1", "::1", "localhost"}
        if parsed.scheme != "https" and not (
            self.allow_loopback_http and parsed.scheme == "http" and loopback
        ):
            raise ObservabilityError("telemetry endpoint must use HTTPS")
        if parsed.username or parsed.password or not parsed.hostname:
            raise ObservabilityError("telemetry endpoint must not embed credentials")
        if not 1 <= self.timeout_seconds <= 60:
            raise ObservabilityError("telemetry timeout is outside policy")
        for key, value in self.headers.items():
            if not isinstance(key, str) or not isinstance(value, str) or "\n" in key + value:
                raise ObservabilityError("telemetry headers are invalid")

    @property
    def exporter_id(self) -> str:
        return "otlp-http-json"

    def export(self, document: Mapping[str, Any]) -> dict[str, Any]:
        body = canonical_json(document)
        if len(body) > 4 * 1024 * 1024:
            raise ObservabilityError("telemetry export exceeds the byte bound")
        request = urllib.request.Request(
            self.endpoint,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "User-Agent": "elmos-formal-assurance/1.0",
                **self.headers,
            },
        )
        started = time.monotonic()
        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout_seconds,
                context=ssl.create_default_context(),
            ) as response:
                response_body = response.read(64 * 1024 + 1)
                status = int(response.status)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ObservabilityError(f"telemetry export failed: {type(exc).__name__}") from exc
        if len(response_body) > 64 * 1024:
            raise ObservabilityError("telemetry response exceeds the byte bound")
        if not 200 <= status < 300:
            raise ObservabilityError(f"telemetry endpoint returned HTTP {status}")
        return {
            "exporterId": self.exporter_id,
            "endpointOrigin": urllib.parse.urlunparse(
                (urllib.parse.urlparse(self.endpoint).scheme, urllib.parse.urlparse(self.endpoint).netloc, "", "", "", "")
            ),
            "httpStatus": status,
            "durationMs": int((time.monotonic() - started) * 1000),
            "requestDigest": digest_value(document),
            "responseDigest": digest_value({"body": response_body.decode("utf-8", errors="replace")}),
        }


class FormalObservabilityService:
    def __init__(
        self, store: StateStore, exporter: TelemetryExporter | None = None
    ) -> None:
        self.store = store
        self.exporter = exporter

    def record_invocation(
        self,
        scope: Scope,
        *,
        skill_id: str,
        proof_status: str,
        duration_micros: int,
        trace_id: str,
    ) -> None:
        validate_identifier(skill_id, "skillId")
        validate_identifier(trace_id, "traceId")
        labels = {"skill": skill_id, "status": proof_status}
        self.store.record_telemetry(
            scope, "formal.invocation.count", 1_000_000, labels, trace_id
        )
        self.store.record_telemetry(
            scope,
            "formal.invocation.duration",
            max(0, int(duration_micros)),
            labels,
            trace_id,
        )

    def snapshot(
        self,
        scope: Scope,
        *,
        success_statuses: tuple[str, ...] = (
            "PROVED_CERTIFIED",
            "PROVED_INDUCTIVE",
            "PROVED_SOLVER_TRUSTED",
            "PROVED_FOR_SUPPORTED_FRAGMENT",
            "BOUNDED_NO_COUNTEREXAMPLE",
            "RUNTIME_MONITORED",
        ),
        limit: int = 10_000,
        objectives: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        events = self.store.telemetry(scope, limit=limit)
        counts = [item for item in events if item["metricName"] == "formal.invocation.count"]
        durations = sorted(
            item["metricValueMicros"]
            for item in events
            if item["metricName"] == "formal.invocation.duration"
        )
        successes = sum(item["labels"].get("status") in success_statuses for item in counts)
        total = len(counts)
        success_rate = (successes * 1_000_000 // total) if total else 0
        p95 = durations[min(len(durations) - 1, max(0, (len(durations) * 95 + 99) // 100 - 1))] if durations else 0
        objectives = dict(objectives or {})
        allowed = {"minimumSuccessRateMicros", "maximumP95DurationMicros", "minimumSampleCount"}
        if set(objectives) - allowed:
            raise ObservabilityError("unknown formal observability objective")
        minimum_success = int(objectives.get("minimumSuccessRateMicros", 0))
        maximum_p95 = int(objectives.get("maximumP95DurationMicros", 2**63 - 1))
        minimum_samples = int(objectives.get("minimumSampleCount", 1))
        if not 0 <= minimum_success <= 1_000_000 or maximum_p95 < 0 or minimum_samples < 1:
            raise ObservabilityError("formal observability objectives are invalid")
        breaches: list[str] = []
        if total < minimum_samples:
            breaches.append("INSUFFICIENT_SAMPLES")
        if success_rate < minimum_success:
            breaches.append("SUCCESS_RATE_BELOW_OBJECTIVE")
        if p95 > maximum_p95:
            breaches.append("P95_DURATION_ABOVE_OBJECTIVE")
        observed_at = events[0]["observedAt"] if events else None
        return {
            "format": "elmos-formal-observability-snapshot/v1",
            "scopeDigest": digest_value(scope.to_dict()),
            "sampleCount": total,
            "successCount": successes,
            "successRateMicros": success_rate,
            "p95DurationMicros": p95,
            "latestObservedAt": observed_at,
            "objectives": {
                "minimumSuccessRateMicros": minimum_success,
                "maximumP95DurationMicros": maximum_p95,
                "minimumSampleCount": minimum_samples,
            },
            "breaches": breaches,
            "unknown": total == 0,
            "tenantLabelsExported": False,
            "formulaOrSourceLabelsExported": False,
        }

    def export(self, snapshot: Mapping[str, Any]) -> dict[str, Any]:
        if self.exporter is None:
            raise ObservabilityError("external telemetry exporter is not configured")
        return self.exporter.export(snapshot)


__all__ = [
    "FormalObservabilityService",
    "ObservabilityError",
    "OtlpHttpJsonExporter",
    "TelemetryExporter",
]

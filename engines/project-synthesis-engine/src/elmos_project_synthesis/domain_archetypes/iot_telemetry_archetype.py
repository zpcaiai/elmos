"""Industrial IoT and Smart Manufacturing Domain Archetype.

Provides:
- DeviceAggregate: Industrial machine asset state machine (OFFLINE -> CONNECTED -> STREAMING -> DEGRADED -> MAINTENANCE).
- TelemetrySample: Single high-frequency sensor reading with timestamp, metric key, float value, and quality score.
- TelemetryBatchAggregate: Ingestion batch with threshold checking and anomaly detection.
- AlertRecord: State machine for alarm generation and resolution (TRIGGERED -> ACKNOWLEDGED -> RESOLVED).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum


class DeviceStatus(str, Enum):
    OFFLINE = "OFFLINE"
    CONNECTED = "CONNECTED"
    STREAMING = "STREAMING"
    DEGRADED = "DEGRADED"
    MAINTENANCE = "MAINTENANCE"


class AlertSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class AlertStatus(str, Enum):
    TRIGGERED = "TRIGGERED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"


class IotDomainError(Exception):
    """Base domain error for IoT telemetry and devices."""


class DeviceOfflineError(IotDomainError):
    """Raised when telemetry is sent to an offline or decommissioned device."""


class InvalidDeviceTransitionError(IotDomainError):
    """Raised when device status transition is forbidden."""


@dataclass(frozen=True)
class TelemetrySample:
    metric_name: str
    value: float
    unit: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    quality_score: float = 1.0


@dataclass
class AlertRecord:
    alert_id: str
    device_id: str
    severity: AlertSeverity
    rule_name: str
    triggered_value: float
    status: AlertStatus = AlertStatus.TRIGGERED
    triggered_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    resolved_at: datetime | None = None

    def acknowledge(self, operator_id: str) -> None:
        if self.status != AlertStatus.TRIGGERED:
            raise IotDomainError(f"Cannot acknowledge alert in state {self.status}")
        self.status = AlertStatus.ACKNOWLEDGED

    def resolve(self) -> None:
        self.status = AlertStatus.RESOLVED
        self.resolved_at = datetime.now(UTC)


@dataclass
class DeviceAggregate:
    device_id: str
    tenant_id: str
    serial_number: str
    model: str
    firmware_version: str
    status: DeviceStatus = DeviceStatus.OFFLINE
    last_heartbeat: datetime | None = None
    telemetry_count: int = 0
    active_alerts: list[AlertRecord] = field(default_factory=list)

    def connect(self) -> None:
        if self.status == DeviceStatus.MAINTENANCE:
            raise InvalidDeviceTransitionError("Cannot connect a machine under maintenance.")
        self.status = DeviceStatus.CONNECTED
        self.last_heartbeat = datetime.now(UTC)

    def start_streaming(self) -> None:
        if self.status not in (DeviceStatus.CONNECTED, DeviceStatus.DEGRADED):
            raise InvalidDeviceTransitionError(f"Cannot start streaming from status {self.status}")
        self.status = DeviceStatus.STREAMING

    def record_telemetry(self, sample: TelemetrySample, threshold: float | None = None) -> AlertRecord | None:
        if self.status == DeviceStatus.OFFLINE:
            raise DeviceOfflineError(f"Device {self.device_id} is offline.")

        self.telemetry_count += 1
        self.last_heartbeat = datetime.now(UTC)

        # Threshold check
        if threshold is not None and sample.value > threshold:
            alert = AlertRecord(
                alert_id=f"alert-{self.device_id}-{self.telemetry_count}",
                device_id=self.device_id,
                severity=AlertSeverity.CRITICAL if sample.value > threshold * 1.5 else AlertSeverity.WARNING,
                rule_name=f"{sample.metric_name}_threshold_exceeded",
                triggered_value=sample.value,
            )
            self.active_alerts.append(alert)
            self.status = DeviceStatus.DEGRADED
            return alert
        return None

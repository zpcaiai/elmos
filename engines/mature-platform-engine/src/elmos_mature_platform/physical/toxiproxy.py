"""Toxiproxy REST driver for physical network fault injection.

Speaks the real Shopify Toxiproxy HTTP API:
  POST /proxies
  POST /proxies/:name/toxics
  POST /reset
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from elmos_mature_platform.physical.protocol import PhysicalCallResult, env_url, http_call


TOXIC_BY_FAULT = {
    "latency": ("latency", {"latency": 250, "jitter": 25}),
    "LATENCY": ("latency", {"latency": 250, "jitter": 25}),
    "error": ("timeout", {"timeout": 1000}),
    "ERROR": ("timeout", {"timeout": 1000}),
    "partition": ("timeout", {"timeout": 1}),
    "PARTITION": ("timeout", {"timeout": 1}),
    "dns_failure": ("timeout", {"timeout": 1}),
    "DNS_FAILURE": ("timeout", {"timeout": 1}),
    "cpu_stress": ("bandwidth", {"rate": 1}),
    "CPU_STRESS": ("bandwidth", {"rate": 1}),
    "memory_pressure": ("slow_close", {"delay": 1000}),
    "MEMORY_PRESSURE": ("slow_close", {"delay": 1000}),
    "disk_fill": ("bandwidth", {"rate": 1}),
    "DISK_FILL": ("bandwidth", {"rate": 1}),
    "process_kill": ("reset_peer", {"timeout": 0}),
    "PROCESS_KILL": ("reset_peer", {"timeout": 0}),
    "clock_skew": ("latency", {"latency": 50, "jitter": 50}),
    "CLOCK_SKEW": ("latency", {"latency": 50, "jitter": 50}),
}


@dataclass
class ToxiproxyInjection:
    proxy_name: str
    toxic_name: str
    toxic_type: str
    proxy_body: Dict[str, Any]
    toxic_body: Dict[str, Any]
    applied: bool = False
    receipts: List[PhysicalCallResult] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "proxy_name": self.proxy_name,
            "toxic_name": self.toxic_name,
            "toxic_type": self.toxic_type,
            "proxy_body": self.proxy_body,
            "toxic_body": self.toxic_body,
            "applied": self.applied,
            "receipts": [item.to_dict() for item in self.receipts],
        }


class ToxiproxyDriver:
    """Physical Toxiproxy REST client."""

    def __init__(
        self,
        base_url: str = "",
        listen_host: str = "127.0.0.1",
        timeout: float = 2.5,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.listen_host = listen_host
        self.timeout = timeout

    @classmethod
    def from_env(cls) -> "ToxiproxyDriver":
        return cls(base_url=env_url("ELMOS_TOXIPROXY_URL"))

    def _url(self, path: str) -> str:
        if not self.base_url:
            return ""
        return f"{self.base_url}{path}"

    def upsert_proxy(
        self,
        name: str,
        upstream: str,
        listen: str = "",
    ) -> tuple[Dict[str, Any], PhysicalCallResult]:
        body = {
            "name": name,
            "listen": listen or f"{self.listen_host}:0",
            "upstream": upstream,
            "enabled": True,
        }
        receipt = http_call(
            backend="toxiproxy",
            operation="create_proxy",
            method="POST",
            url=self._url("/proxies"),
            body=body,
            timeout=self.timeout,
        )
        return body, receipt

    def add_toxic(
        self,
        proxy_name: str,
        toxic_name: str,
        toxic_type: str,
        attributes: Dict[str, Any],
        toxicity: float = 1.0,
        stream: str = "downstream",
    ) -> tuple[Dict[str, Any], PhysicalCallResult]:
        body = {
            "name": toxic_name,
            "type": toxic_type,
            "stream": stream,
            "toxicity": float(toxicity),
            "attributes": attributes,
        }
        receipt = http_call(
            backend="toxiproxy",
            operation="create_toxic",
            method="POST",
            url=self._url(f"/proxies/{proxy_name}/toxics"),
            body=body,
            timeout=self.timeout,
        )
        return body, receipt

    def reset(self) -> PhysicalCallResult:
        return http_call(
            backend="toxiproxy",
            operation="reset",
            method="POST",
            url=self._url("/reset"),
            body={},
            timeout=self.timeout,
        )

    def inject_fault(
        self,
        *,
        target_service: str,
        fault_type: str,
        probability: float = 1.0,
        latency_ms: Optional[int] = None,
        upstream: str = "",
    ) -> ToxiproxyInjection:
        toxic_type, attributes = TOXIC_BY_FAULT.get(fault_type, ("latency", {"latency": 250, "jitter": 25}))
        if latency_ms is not None and toxic_type == "latency":
            attributes = {**attributes, "latency": int(latency_ms)}
        proxy_name = f"elmos-{target_service}"
        toxic_name = f"{proxy_name}-{toxic_type}"
        proxy_body, proxy_receipt = self.upsert_proxy(
            proxy_name,
            upstream or f"{target_service}.elmos.svc.cluster.local:80",
        )
        toxic_body, toxic_receipt = self.add_toxic(
            proxy_name,
            toxic_name,
            toxic_type,
            attributes,
            toxicity=probability,
        )
        applied = proxy_receipt.applied and toxic_receipt.applied
        return ToxiproxyInjection(
            proxy_name=proxy_name,
            toxic_name=toxic_name,
            toxic_type=toxic_type,
            proxy_body=proxy_body,
            toxic_body=toxic_body,
            applied=applied,
            receipts=[proxy_receipt, toxic_receipt],
        )

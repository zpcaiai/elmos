"""Industrial-grade network egress control and secret exfiltration defense."""

from __future__ import annotations

import ipaddress
import logging
import re
import socket
import urllib.parse
from dataclasses import dataclass

logger = logging.getLogger("elmos_proof_harness.network_egress")


class EgressViolationError(Exception):
    """Raised when an outbound network request violates security or data loss policies."""


# Secret token regex patterns
_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("AWS Access Key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("GitHub Token", re.compile(r"gh[pousr]_[A-Za-z0-9_]{36,}")),
    ("OpenAI API Key", re.compile(r"sk-[a-zA-Z0-9]{20,}")),
    ("Anthropic API Key", re.compile(r"sk-ant-[a-zA-Z0-9]{20,}")),
    ("Private Key Header", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("Generic Bearer Token", re.compile(r"Bearer\s+[A-Za-z0-9\-_\.]{24,}")),
    ("GCP Service Account Key", re.compile(r'"type":\s*"service_account"')),
    ("Slack Token", re.compile(r"xox[baprs]-[0-9]{10,}-[0-9]{10,}-[a-zA-Z0-9]{24,}")),
    ("Database Credentials URI", re.compile(r"[a-zA-Z0-9_\-]+://[^:]+:[^@]+@[^/]+")),
)

# Blocked SSRF and internal subnets
_BLOCKED_NETWORKS: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = (
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local / Cloud Metadata
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
)

_BLOCKED_HOSTNAMES: frozenset[str] = frozenset({
    "localhost",
    "metadata.google.internal",
    "169.254.169.254",
    "instance-data",
})

_BLOCKED_DOMAIN_SUFFIXES: tuple[str, ...] = (
    ".internal",
    ".local",
    ".localhost",
    ".lan",
    ".corp",
    ".home",
    ".onion",
)


@dataclass(frozen=True)
class EgressPolicy:
    allow_egress: bool = False
    allowed_domains: tuple[str, ...] = ()
    allowed_ports: tuple[int, ...] = (443, 8080)
    block_private_networks: bool = True
    scan_secrets_on_egress: bool = True
    resolve_dns_for_ssrf: bool = True


class NetworkEgressGuard:
    """Evaluates egress requests against network security boundaries and secret leakage prevention."""

    def __init__(self, policy: EgressPolicy | None = None) -> None:
        self.policy = policy or EgressPolicy()

    def inspect_content_for_secrets(self, content: str | bytes) -> list[str]:
        """Scan text or payload for credentials and secrets."""
        text = content.decode("utf-8", errors="replace") if isinstance(content, bytes) else content
        detected: list[str] = []
        for name, pattern in _SECRET_PATTERNS:
            if pattern.search(text):
                detected.append(name)
        return detected

    def validate_destination(self, url_or_target: str) -> bool:
        """Validate if a URL destination is permissible under egress policy."""
        if not self.policy.allow_egress:
            raise EgressViolationError("All outbound network egress is disabled by policy")

        # Parse target
        target = url_or_target.strip()
        if "://" not in target:
            target = f"https://{target}"
        parsed = urllib.parse.urlparse(target)
        hostname = (parsed.hostname or "").lower().strip()
        port = parsed.port or (443 if parsed.scheme == "https" else 80)

        if not hostname:
            raise EgressViolationError(f"Invalid host in target: {url_or_target}")

        # Check hostname blocklist first
        if hostname in _BLOCKED_HOSTNAMES:
            raise EgressViolationError(f"Target host '{hostname}' is in blocked metadata/localhost list")

        # Check blocked domain suffixes
        for suffix in _BLOCKED_DOMAIN_SUFFIXES:
            if hostname.endswith(suffix) or hostname == suffix.lstrip("."):
                raise EgressViolationError(f"Target host '{hostname}' ends with blocked suffix '{suffix}'")

        # Check IP range if hostname is an IP
        if self.policy.block_private_networks:
            try:
                ip_obj = ipaddress.ip_address(hostname)
                for net in _BLOCKED_NETWORKS:
                    if ip_obj in net:
                        raise EgressViolationError(
                            f"Target IP {hostname} belongs to private/internal blocked network {net}"
                        )
            except ValueError:
                # Not an IP literal: domain name. Perform DNS resolution check if enabled
                if self.policy.resolve_dns_for_ssrf:
                    try:
                        addr_info = socket.getaddrinfo(hostname, port, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM)
                        for entry in addr_info:
                            resolved_ip_str = entry[4][0]
                            try:
                                resolved_ip = ipaddress.ip_address(resolved_ip_str)
                                for net in _BLOCKED_NETWORKS:
                                    if resolved_ip in net:
                                        raise EgressViolationError(
                                            f"Target host '{hostname}' resolves to private/internal blocked IP {resolved_ip} in {net}"
                                        )
                            except ValueError:
                                pass
                    except socket.gaierror:
                        # DNS lookup unavailable or airgapped, rely on static blocklists
                        logger.debug("DNS resolution unavailable for %s during egress check", hostname)

        if port not in self.policy.allowed_ports:
            raise EgressViolationError(f"Port {port} is not in allowed ports {self.policy.allowed_ports}")

        # Check domain allowlist
        if self.policy.allowed_domains:
            matched = any(
                hostname == allowed or hostname.endswith(f".{allowed}")
                for allowed in self.policy.allowed_domains
            )
            if not matched:
                raise EgressViolationError(
                    f"Target host '{hostname}' is not in allowed domains {self.policy.allowed_domains}"
                )

        return True

    def verify_egress(self, destination: str, payload: str | bytes = "") -> None:
        """Combined check: destination validation + secret leakage scanning."""
        self.validate_destination(destination)
        if self.policy.scan_secrets_on_egress and payload:
            secrets = self.inspect_content_for_secrets(payload)
            if secrets:
                raise EgressViolationError(
                    f"Egress payload rejected: detected credentials/secrets {secrets}"
                )

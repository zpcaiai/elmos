"""Owner-bound, least-privilege authority evaluation."""

from __future__ import annotations

import datetime as dt
import hashlib
import ipaddress
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse

import yaml


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str
    rule: str

    def as_dict(self) -> dict[str, Any]: return {"allowed": self.allowed, "reason": self.reason, "rule": self.rule}


def canonical_digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def load_document(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8")) if path.suffix.lower() in {".yaml", ".yml"} else json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict): raise ValueError("authority document must be an object")
    return value


def _parse_time(value: str | None) -> dt.datetime | None:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def _normalize_posix(value: str) -> str:
    path = PurePosixPath(value)
    if ".." in path.parts: raise ValueError("path traversal")
    return "/" + str(path).lstrip("/")


def _path_allowed(path: str, roots: list[str]) -> bool:
    try: candidate = _normalize_posix(path)
    except ValueError: return False
    for root in roots:
        try: normalized = _normalize_posix(root)
        except ValueError: continue
        if candidate == normalized or candidate.startswith(normalized.rstrip("/") + "/"): return True
    return False


def _host_allowed(value: str, allowlist: list[str]) -> bool:
    parsed = urlparse(value if "://" in value else f"https://{value}"); host = (parsed.hostname or "").lower().rstrip(".")
    if not host: return False
    try: address = ipaddress.ip_address(host)
    except ValueError: address = None
    for item in allowlist:
        item = str(item).lower().strip().rstrip(".")
        if item == "*" or host == item: return True
        if item.startswith("*.") and host.endswith(item[1:]) and host != item[2:]: return True
        if address is not None:
            try:
                if address in ipaddress.ip_network(item, strict=False): return True
            except ValueError: pass
    return False


def validate_authority(authority: dict[str, Any]) -> list[str]:
    required = ("schema_version", "authority_id", "environment_id", "owner_type", "owner_id", "tenant_id", "capabilities", "filesystem", "network", "secrets", "hidden_tests")
    errors = [f"missing {key}" for key in required if key not in authority]
    if authority.get("owner_type") not in {"environment", "attachment"}: errors.append("owner_type must be environment or attachment")
    if authority.get("hidden_tests", {}).get("read") and authority.get("role") in {"transform-worker", "generation-worker"}: errors.append("generation/transform workers cannot read hidden tests")
    return errors


def authorize(authority: dict[str, Any], request: dict[str, Any], *, now: dt.datetime | None = None) -> PolicyDecision:
    errors = validate_authority(authority)
    if errors: return PolicyDecision(False, "; ".join(errors), "authority-invalid")
    now = now or dt.datetime.now(dt.timezone.utc); expires = _parse_time(authority.get("expires_at"))
    if expires is not None and now >= expires: return PolicyDecision(False, "authority expired", "authority-expiry")
    for field in ("environment_id", "owner_id", "tenant_id"):
        if request.get(field) != authority.get(field): return PolicyDecision(False, f"{field} mismatch", "owner-binding")
    if request.get("authority_id") and request["authority_id"] != authority.get("authority_id"): return PolicyDecision(False, "authority_id mismatch", "owner-binding")
    if request.get("action") not in set(authority.get("capabilities", [])): return PolicyDecision(False, f"capability not granted: {request.get('action')}", "capability")
    path = request.get("path")
    if path is not None and not _path_allowed(str(path), list(authority.get("filesystem", {}).get(f"{request.get('path_mode', 'read')}_roots", []))): return PolicyDecision(False, "path outside permitted roots", "filesystem")
    target = request.get("network_target")
    if target is not None:
        network = authority.get("network", {})
        if network.get("mode", "deny") == "deny": return PolicyDecision(False, "network denied", "network")
        if not _host_allowed(str(target), list(network.get("allowlist", []))): return PolicyDecision(False, "network target not allowlisted", "network")
    secret = request.get("secret_ref")
    if secret is not None and secret not in set(authority.get("secrets", {}).get("allowed_refs", [])): return PolicyDecision(False, "secret reference not granted", "secret-scope")
    hidden_action = request.get("hidden_test_action")
    if hidden_action is not None and not bool(authority.get("hidden_tests", {}).get(hidden_action, False)): return PolicyDecision(False, f"hidden-test {hidden_action} denied", "hidden-tests")
    if request.get("fencing_token") is not None and request["fencing_token"] != authority.get("fencing_token"): return PolicyDecision(False, "stale fencing token", "fencing")
    return PolicyDecision(True, "granted", "allow")


def authority_digest(authority: dict[str, Any]) -> str:
    material = dict(authority); material.pop("digest", None); return canonical_digest(material)


def write_authority(path: Path, authority: dict[str, Any]) -> None:
    material = dict(authority); material["digest"] = authority_digest(material); path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(material, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

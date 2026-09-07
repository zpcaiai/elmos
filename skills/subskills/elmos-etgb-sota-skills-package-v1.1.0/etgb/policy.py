from __future__ import annotations

import datetime as dt
import hashlib
import ipaddress
import json
import os
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

    def as_dict(self) -> dict[str, Any]:
        return {"allowed": self.allowed, "reason": self.reason, "rule": self.rule}


def canonical_digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def load_document(path: Path) -> dict[str, Any]:
    text = Path(path).read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        return yaml.safe_load(text)
    return json.loads(text)


def _parse_time(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def _normalize_posix(value: str) -> str:
    path = PurePosixPath(value)
    if ".." in path.parts:
        raise ValueError("path traversal")
    normalized = "/" + str(path).lstrip("/")
    return normalized.rstrip("/") or "/"


def _path_allowed(path: str, roots: list[str]) -> bool:
    try:
        candidate = _normalize_posix(path)
    except ValueError:
        return False
    for root in roots:
        try:
            normalized_root = _normalize_posix(root)
        except ValueError:
            continue
        if candidate == normalized_root or candidate.startswith(normalized_root.rstrip("/") + "/"):
            return True
    return False


def _host_allowed(url_or_host: str, allowlist: list[str]) -> bool:
    parsed = urlparse(url_or_host if "://" in url_or_host else f"https://{url_or_host}")
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    for item in allowlist:
        item = item.lower().strip().rstrip(".")
        if not item:
            continue
        if item == "*":
            return True
        if item.startswith("*.") and host.endswith(item[1:]) and host != item[2:]:
            return True
        if host == item:
            return True
        if ip is not None:
            try:
                if ip in ipaddress.ip_network(item, strict=False):
                    return True
            except ValueError:
                pass
    return False


def validate_authority(authority: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required = [
        "schema_version",
        "authority_id",
        "environment_id",
        "owner_type",
        "owner_id",
        "tenant_id",
        "capabilities",
        "filesystem",
        "network",
        "secrets",
        "hidden_tests",
    ]
    for key in required:
        if key not in authority:
            errors.append(f"missing {key}")
    if authority.get("owner_type") not in {"environment", "attachment"}:
        errors.append("owner_type must be environment or attachment")
    if authority.get("hidden_tests", {}).get("read") and authority.get("role") in {
        "transform-worker",
        "generation-worker",
    }:
        errors.append("generation/transform workers cannot read hidden tests")
    return errors


def authorize(authority: dict[str, Any], request: dict[str, Any], *, now: dt.datetime | None = None) -> PolicyDecision:
    """Authorize one tool/resource request against its owning authority.

    The request must identify the exact environment/attachment owner. It never
    inherits ambient thread-wide permissions.
    """

    errors = validate_authority(authority)
    if errors:
        return PolicyDecision(False, "; ".join(errors), "authority-invalid")

    now = now or dt.datetime.now(dt.timezone.utc)
    expires = _parse_time(authority.get("expires_at"))
    if expires is not None and now >= expires:
        return PolicyDecision(False, "authority expired", "authority-expiry")

    identity_checks = {
        "environment_id": request.get("environment_id"),
        "owner_id": request.get("owner_id"),
        "tenant_id": request.get("tenant_id"),
    }
    for field, actual in identity_checks.items():
        if actual != authority.get(field):
            return PolicyDecision(False, f"{field} mismatch", "owner-binding")

    if request.get("authority_id") and request["authority_id"] != authority.get("authority_id"):
        return PolicyDecision(False, "authority_id mismatch", "owner-binding")

    action = request.get("action")
    if action not in set(authority.get("capabilities", [])):
        return PolicyDecision(False, f"capability not granted: {action}", "capability")

    path = request.get("path")
    if path is not None:
        mode = request.get("path_mode", "read")
        roots = authority.get("filesystem", {}).get(f"{mode}_roots", [])
        if not _path_allowed(str(path), list(roots)):
            return PolicyDecision(False, f"path outside {mode} roots", "filesystem")

    network_target = request.get("network_target")
    if network_target is not None:
        network = authority.get("network", {})
        if network.get("mode", "deny") == "deny":
            return PolicyDecision(False, "network denied", "network")
        if not _host_allowed(str(network_target), list(network.get("allowlist", []))):
            return PolicyDecision(False, "network target not allowlisted", "network")

    secret_ref = request.get("secret_ref")
    if secret_ref is not None and secret_ref not in set(authority.get("secrets", {}).get("allowed_refs", [])):
        return PolicyDecision(False, "secret reference not granted", "secret-scope")

    hidden_test_action = request.get("hidden_test_action")
    if hidden_test_action is not None:
        hidden = authority.get("hidden_tests", {})
        if not bool(hidden.get(hidden_test_action, False)):
            return PolicyDecision(False, f"hidden-test {hidden_test_action} denied", "hidden-tests")

    if request.get("fencing_token") is not None:
        expected = authority.get("fencing_token")
        if expected is None or request["fencing_token"] != expected:
            return PolicyDecision(False, "stale fencing token", "fencing")

    return PolicyDecision(True, "granted", "allow")


def authority_digest(authority: dict[str, Any]) -> str:
    material = dict(authority)
    material.pop("digest", None)
    return canonical_digest(material)


def write_authority(path: Path, authority: dict[str, Any]) -> None:
    material = dict(authority)
    material["digest"] = authority_digest(material)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(material, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

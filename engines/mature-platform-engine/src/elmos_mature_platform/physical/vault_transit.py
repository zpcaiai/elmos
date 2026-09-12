"""HashiCorp Vault Transit secrets engine driver.

Speaks the real Vault HTTP JSON API:
  POST /v1/transit/keys/:name
  POST /v1/transit/keys/:name/rotate
  POST /v1/transit/encrypt/:name
  POST /v1/transit/decrypt/:name
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from elmos_mature_platform.physical.protocol import PhysicalCallResult, env_url, http_call


def _b64e(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


@dataclass
class VaultTransitReceipt:
    key_name: str
    operation: str
    request_body: Dict[str, Any]
    ciphertext: str = ""
    plaintext_b64: str = ""
    applied: bool = False
    receipts: List[PhysicalCallResult] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key_name": self.key_name,
            "operation": self.operation,
            "request_body": self.request_body,
            "ciphertext": self.ciphertext,
            "plaintext_b64": self.plaintext_b64,
            "applied": self.applied,
            "receipts": [item.to_dict() for item in self.receipts],
        }


class VaultTransitDriver:
    """Physical Vault Transit driver."""

    def __init__(
        self,
        vault_addr: str = "",
        vault_token: str = "",
        mount: str = "transit",
        timeout: float = 2.5,
    ) -> None:
        self.vault_addr = vault_addr.rstrip("/")
        self.vault_token = vault_token
        self.mount = mount.strip("/") or "transit"
        self.timeout = timeout

    @classmethod
    def from_env(cls) -> "VaultTransitDriver":
        return cls(
            vault_addr=env_url("ELMOS_VAULT_ADDR", "VAULT_ADDR"),
            vault_token=env_url("ELMOS_VAULT_TOKEN", "VAULT_TOKEN"),
        )

    def _headers(self) -> Dict[str, str]:
        headers = {"X-Vault-Request": "true"}
        if self.vault_token:
            headers["X-Vault-Token"] = self.vault_token
        return headers

    def _url(self, path: str) -> str:
        if not self.vault_addr:
            return ""
        return f"{self.vault_addr}/v1/{self.mount}/{path.lstrip('/')}"

    def _call(self, operation: str, path: str, body: Optional[Dict[str, Any]] = None) -> PhysicalCallResult:
        return http_call(
            backend="vault-transit",
            operation=operation,
            method="POST",
            url=self._url(path),
            body=body or {},
            headers=self._headers(),
            timeout=self.timeout,
        )

    def create_key(self, key_name: str, derived: bool = False) -> VaultTransitReceipt:
        body = {
            "type": "aes256-gcm96",
            "derived": derived,
            "exportable": False,
            "allow_plaintext_backup": False,
            "auto_rotate_period": "768h",
        }
        receipt = self._call("create_key", f"keys/{key_name}", body)
        return VaultTransitReceipt(
            key_name=key_name,
            operation="create_key",
            request_body=body,
            applied=receipt.applied or receipt.status_code in {200, 204},
            receipts=[receipt],
        )

    def rotate_key(self, key_name: str) -> VaultTransitReceipt:
        body: Dict[str, Any] = {}
        receipt = self._call("rotate_key", f"keys/{key_name}/rotate", body)
        return VaultTransitReceipt(
            key_name=key_name,
            operation="rotate_key",
            request_body=body,
            applied=receipt.applied,
            receipts=[receipt],
        )

    def encrypt(self, key_name: str, plaintext: bytes, context: bytes = b"") -> VaultTransitReceipt:
        body: Dict[str, Any] = {"plaintext": _b64e(plaintext)}
        if context:
            body["context"] = _b64e(context)
        receipt = self._call("encrypt", f"encrypt/{key_name}", body)
        ciphertext = ""
        if receipt.applied and isinstance(receipt.response_body, dict):
            data = receipt.response_body.get("data") or {}
            ciphertext = str(data.get("ciphertext") or "")
        return VaultTransitReceipt(
            key_name=key_name,
            operation="encrypt",
            request_body=body,
            ciphertext=ciphertext,
            applied=receipt.applied and bool(ciphertext),
            receipts=[receipt],
        )

    def decrypt(self, key_name: str, ciphertext: str, context: bytes = b"") -> VaultTransitReceipt:
        body: Dict[str, Any] = {"ciphertext": ciphertext}
        if context:
            body["context"] = _b64e(context)
        receipt = self._call("decrypt", f"decrypt/{key_name}", body)
        plaintext_b64 = ""
        if receipt.applied and isinstance(receipt.response_body, dict):
            data = receipt.response_body.get("data") or {}
            plaintext_b64 = str(data.get("plaintext") or "")
        return VaultTransitReceipt(
            key_name=key_name,
            operation="decrypt",
            request_body=body,
            ciphertext=ciphertext,
            plaintext_b64=plaintext_b64,
            applied=receipt.applied and bool(plaintext_b64),
            receipts=[receipt],
        )

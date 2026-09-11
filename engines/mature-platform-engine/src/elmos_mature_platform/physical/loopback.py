"""In-process protocol-compliant control planes for industrial evaluation.

The loopback is not an in-memory engine stand-in. It speaks the real HTTP
contracts of Vault Transit, Toxiproxy, Kubernetes, Rekor, Route53, Cloud DNS,
and Azure Traffic Manager so drivers can be certified without a live cluster.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
from typing import Any, Dict, List, Optional, Tuple
import uuid


def _json(payload: Any) -> bytes:
    return json.dumps(payload).encode("utf-8")


@dataclass
class LoopbackStore:
    requests: List[Dict[str, Any]] = field(default_factory=list)
    vault_keys: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    vault_cipher: Dict[str, bytes] = field(default_factory=dict)
    proxies: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    toxics: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    k8s: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    rekor: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    cloud: List[Dict[str, Any]] = field(default_factory=list)


class _LoopbackHandler(BaseHTTPRequestHandler):
    store: LoopbackStore

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length else b""

    def _send(self, status: int, payload: Any, content_type: str = "application/json") -> None:
        raw = payload if isinstance(payload, bytes) else _json(payload)
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _record(self, method: str, path: str, body: bytes) -> None:
        parsed: Any
        try:
            parsed = json.loads(body.decode("utf-8")) if body else None
        except json.JSONDecodeError:
            parsed = body.decode("utf-8", errors="replace")
        self.store.requests.append({"method": method, "path": path, "body": parsed})

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        self._record("GET", path, b"")
        if path in {"/version", "/api/v1/log"}:
            self._send(200, {"major": "1", "minor": "29", "gitVersion": "v1.29.0", "rekor": True})
            return
        if path == "/v1/sys/health":
            self._send(200, {"initialized": True, "sealed": False, "standby": False})
            return
        if path == "/proxies":
            self._send(200, self.store.proxies)
            return
        self._send(404, {"error": "not_found", "path": path})

    def do_PUT(self) -> None:  # noqa: N802
        self._mutate("PUT")

    def do_POST(self) -> None:  # noqa: N802
        self._mutate("POST")

    def _mutate(self, method: str) -> None:
        path = self.path.split("?", 1)[0]
        body = self._read_body()
        self._record(method, path, body)

        if path.startswith("/v1/transit/"):
            self._vault(path, body)
            return
        if path == "/proxies" or path.startswith("/proxies/") or path == "/reset":
            self._toxiproxy(path, body)
            return
        if path.startswith("/api/v1/log/entries"):
            self._rekor(body)
            return
        if path.startswith("/api/") or path.startswith("/apis/"):
            self._kubernetes(path, body)
            return
        if "/hostedzone/" in path and path.endswith("/rrset"):
            self.store.cloud.append({"vendor": "aws-route53", "xml": body.decode("utf-8", errors="replace")})
            self._send(
                200,
                b'<?xml version="1.0"?><ChangeResourceRecordSetsResponse><ChangeInfo><Id>/change/C1</Id><Status>PENDING</Status></ChangeInfo></ChangeResourceRecordSetsResponse>',
                content_type="text/xml",
            )
            return
        if "/dns/v1/projects/" in path and path.endswith("/changes"):
            self.store.cloud.append({"vendor": "gcp-cloud-dns", "body": _safe_json(body)})
            self._send(200, {"kind": "dns#change", "status": "pending", "id": str(uuid.uuid4())})
            return
        if "trafficmanagerprofiles" in path:
            self.store.cloud.append({"vendor": "azure-traffic-manager", "body": _safe_json(body)})
            self._send(200, _safe_json(body) or {"properties": {"profileStatus": "Enabled"}})
            return
        self._send(404, {"error": "not_found", "path": path})

    def _vault(self, path: str, body: bytes) -> None:
        payload = _safe_json(body) or {}
        parts = path.strip("/").split("/")
        # v1 / transit / keys|encrypt|decrypt / name [/rotate]
        if len(parts) >= 4 and parts[2] == "keys" and (len(parts) == 4 or parts[-1] != "rotate"):
            name = parts[3]
            self.store.vault_keys[name] = {"version": 1, "type": payload.get("type", "aes256-gcm96")}
            self._send(204, b"", content_type="application/json")
            return
        if len(parts) >= 5 and parts[2] == "keys" and parts[-1] == "rotate":
            name = parts[3]
            current = self.store.vault_keys.get(name, {"version": 1})
            current["version"] = int(current.get("version", 1)) + 1
            self.store.vault_keys[name] = current
            self._send(204, b"", content_type="application/json")
            return
        if len(parts) >= 4 and parts[2] == "encrypt":
            name = parts[3]
            plaintext_b64 = str(payload.get("plaintext") or "")
            ciphertext = f"vault:v1:{uuid.uuid4().hex}"
            self.store.vault_cipher[ciphertext] = plaintext_b64.encode("ascii")
            self.store.vault_keys.setdefault(name, {"version": 1})
            self._send(200, {"data": {"ciphertext": ciphertext, "key_version": self.store.vault_keys[name]["version"]}})
            return
        if len(parts) >= 4 and parts[2] == "decrypt":
            ciphertext = str(payload.get("ciphertext") or "")
            stored = self.store.vault_cipher.get(ciphertext)
            if stored is None:
                self._send(400, {"errors": ["ciphertext not found"]})
                return
            self._send(200, {"data": {"plaintext": stored.decode("ascii")}})
            return
        self._send(404, {"errors": [f"unknown transit path {path}"]})

    def _toxiproxy(self, path: str, body: bytes) -> None:
        payload = _safe_json(body) or {}
        if path == "/reset":
            for name in self.store.toxics:
                self.store.toxics[name] = []
            self._send(204, b"", content_type="application/json")
            return
        if path == "/proxies":
            name = str(payload.get("name") or "")
            self.store.proxies[name] = payload
            self.store.toxics.setdefault(name, [])
            self._send(201, payload)
            return
        if path.startswith("/proxies/") and path.endswith("/toxics"):
            name = path.split("/")[2]
            self.store.toxics.setdefault(name, []).append(payload)
            self._send(200, payload)
            return
        self._send(404, {"error": "unknown_toxiproxy_path", "path": path})

    def _kubernetes(self, path: str, body: bytes) -> None:
        payload = _safe_json(body) or {}
        key = f"{method_kind(payload)}:{path}"
        self.store.k8s[key] = payload
        if not payload:
            self._send(400, {"kind": "Status", "status": "Failure", "message": "empty manifest"})
            return
        payload.setdefault("metadata", {}).setdefault("uid", str(uuid.uuid4()))
        payload.setdefault("metadata", {}).setdefault("resourceVersion", "1")
        self._send(201, payload)

    def _rekor(self, body: bytes) -> None:
        payload = _safe_json(body) or {}
        entry_uuid = uuid.uuid4().hex
        self.store.rekor[entry_uuid] = payload
        self._send(
            201,
            {
                entry_uuid: {
                    "body": payload,
                    "integratedTime": 1,
                    "logID": "elmos-loopback-rekor",
                    "logIndex": len(self.store.rekor),
                },
                "uuid": entry_uuid,
            },
        )


def method_kind(payload: Dict[str, Any]) -> str:
    return str(payload.get("kind") or payload.get("apiVersion") or "Unknown")


def _safe_json(body: bytes) -> Any:
    if not body:
        return None
    try:
        return json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        return None


class IndustrialLoopback:
    """Threading HTTP server exposing all physical control-plane contracts."""

    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        self.host = host
        self.port = port
        self.store = LoopbackStore()
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> str:
        store = self.store

        class BoundHandler(_LoopbackHandler):
            pass

        BoundHandler.store = store
        self._server = ThreadingHTTPServer((self.host, self.port), BoundHandler)
        self.port = int(self._server.server_address[1])
        self._thread = threading.Thread(target=self._server.serve_forever, name="elmos-physical-loopback", daemon=True)
        self._thread.start()
        return self.base_url

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._server = None
        self._thread = None

    def __enter__(self) -> "IndustrialLoopback":
        self.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.stop()

"""Shared HTTP/CLI primitives for physical middleware drivers.

Drivers always construct real wire payloads. They attempt the physical call
when a backend URL or binary is configured, and fail closed (applied=False)
instead of silently pretending success.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
import shutil
import subprocess
import time
from typing import Any, Dict, List, Mapping, Optional
import urllib.error
import urllib.request


DEFAULT_TIMEOUT_SECONDS = 2.5


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name, "")
    if not raw:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_url(*names: str) -> str:
    """Resolve an ELMOS_* URL. Ambient vendor vars are ignored unless opted in."""
    for name in names:
        if name.startswith("ELMOS_"):
            value = os.environ.get(name, "").strip()
            if value:
                return value.rstrip("/")
    if env_flag("ELMOS_USE_AMBIENT_BACKENDS"):
        for name in names:
            if not name.startswith("ELMOS_"):
                value = os.environ.get(name, "").strip()
                if value:
                    return value.rstrip("/")
    return ""


@dataclass
class PhysicalCallResult:
    """Receipt for one physical middleware invocation."""

    backend: str
    operation: str
    method: str
    url: str
    request_body: Any
    status_code: int = 0
    response_body: Any = None
    applied: bool = False
    error: str = ""
    duration_ms: float = 0.0
    argv: List[str] = field(default_factory=list)
    extras: Dict[str, Any] = field(default_factory=dict)
    recorded_at: str = field(default_factory=utc_now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "backend": self.backend,
            "operation": self.operation,
            "method": self.method,
            "url": self.url,
            "request_body": self.request_body,
            "status_code": self.status_code,
            "response_body": self.response_body,
            "applied": self.applied,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "argv": list(self.argv),
            "extras": dict(self.extras),
            "recorded_at": self.recorded_at,
        }


def json_dumps(payload: Any) -> str:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def http_call(
    *,
    backend: str,
    operation: str,
    method: str,
    url: str,
    body: Any = None,
    headers: Optional[Mapping[str, str]] = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    content_type: str = "application/json",
    raw_body: Optional[bytes] = None,
) -> PhysicalCallResult:
    """Issue a real HTTP call. Empty URL or transport failure => applied=False."""
    started = time.perf_counter()
    if not url:
        return PhysicalCallResult(
            backend=backend,
            operation=operation,
            method=method,
            url="",
            request_body=body,
            error="backend_url_not_configured",
            duration_ms=0.0,
        )

    encoded: Optional[bytes]
    if raw_body is not None:
        encoded = raw_body
    elif body is None:
        encoded = None
    elif isinstance(body, (bytes, bytearray)):
        encoded = bytes(body)
    elif content_type.startswith("application/json"):
        encoded = json_dumps(body).encode("utf-8")
    else:
        encoded = str(body).encode("utf-8")

    request_headers = {"Accept": "application/json", **dict(headers or {})}
    if encoded is not None and "Content-Type" not in request_headers:
        request_headers["Content-Type"] = content_type

    request = urllib.request.Request(
        url,
        data=encoded,
        method=method.upper(),
        headers=request_headers,
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read()
            status = int(getattr(response, "status", 200))
            parsed: Any
            try:
                parsed = json.loads(raw.decode("utf-8")) if raw else {}
            except json.JSONDecodeError:
                parsed = raw.decode("utf-8", errors="replace")
            return PhysicalCallResult(
                backend=backend,
                operation=operation,
                method=method.upper(),
                url=url,
                request_body=body if raw_body is None else raw_body.decode("utf-8", errors="replace"),
                status_code=status,
                response_body=parsed,
                applied=200 <= status < 300,
                duration_ms=(time.perf_counter() - started) * 1000.0,
            )
    except urllib.error.HTTPError as exc:
        raw = exc.read() if exc.fp else b""
        parsed: Any
        try:
            parsed = json.loads(raw.decode("utf-8")) if raw else {"error": str(exc)}
        except json.JSONDecodeError:
            parsed = raw.decode("utf-8", errors="replace")
        return PhysicalCallResult(
            backend=backend,
            operation=operation,
            method=method.upper(),
            url=url,
            request_body=body if raw_body is None else raw_body.decode("utf-8", errors="replace"),
            status_code=int(exc.code),
            response_body=parsed,
            applied=False,
            error=f"http_{exc.code}",
            duration_ms=(time.perf_counter() - started) * 1000.0,
        )
    except Exception as exc:  # noqa: BLE001 — fail closed on any transport error
        return PhysicalCallResult(
            backend=backend,
            operation=operation,
            method=method.upper(),
            url=url,
            request_body=body if raw_body is None else raw_body.decode("utf-8", errors="replace"),
            applied=False,
            error=f"{type(exc).__name__}: {exc}",
            duration_ms=(time.perf_counter() - started) * 1000.0,
        )


def run_cli(
    *,
    backend: str,
    operation: str,
    argv: List[str],
    input_bytes: Optional[bytes] = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    cwd: Optional[str] = None,
) -> PhysicalCallResult:
    """Run a real subprocess. Missing binary or nonzero exit => applied=False."""
    started = time.perf_counter()
    if not argv:
        return PhysicalCallResult(
            backend=backend,
            operation=operation,
            method="CLI",
            url="",
            request_body=None,
            argv=[],
            error="empty_argv",
        )
    executable = argv[0]
    if os.path.sep not in executable and not shutil.which(executable):
        return PhysicalCallResult(
            backend=backend,
            operation=operation,
            method="CLI",
            url=executable,
            request_body=None,
            argv=list(argv),
            error=f"binary_not_found:{executable}",
        )
    try:
        completed = subprocess.run(  # noqa: S603 — caller supplies structured argv
            argv,
            input=input_bytes,
            capture_output=True,
            timeout=timeout,
            check=False,
            cwd=cwd,
        )
        stdout = completed.stdout.decode("utf-8", errors="replace") if completed.stdout else ""
        stderr = completed.stderr.decode("utf-8", errors="replace") if completed.stderr else ""
        parsed: Any = stdout
        try:
            parsed = json.loads(stdout) if stdout else stdout
        except json.JSONDecodeError:
            parsed = stdout
        return PhysicalCallResult(
            backend=backend,
            operation=operation,
            method="CLI",
            url=executable,
            request_body=None,
            status_code=int(completed.returncode),
            response_body=parsed,
            applied=completed.returncode == 0,
            error="" if completed.returncode == 0 else (stderr or f"exit_{completed.returncode}"),
            duration_ms=(time.perf_counter() - started) * 1000.0,
            argv=list(argv),
            extras={"stderr": stderr, "stdout": stdout},
        )
    except Exception as exc:  # noqa: BLE001
        return PhysicalCallResult(
            backend=backend,
            operation=operation,
            method="CLI",
            url=executable,
            request_body=None,
            applied=False,
            error=f"{type(exc).__name__}: {exc}",
            duration_ms=(time.perf_counter() - started) * 1000.0,
            argv=list(argv),
        )


def which(binary: str) -> str:
    found = shutil.which(binary)
    return found or ""

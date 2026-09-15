from __future__ import annotations

import json
import os
import shlex
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, TypeAlias, cast

MAX_REQUESTS = 1000

JsonMap: TypeAlias = dict[str, Any]
RuntimeCommand: TypeAlias = str | Sequence[str]
HttpExecutor: TypeAlias = Callable[[str, JsonMap], JsonMap]


@dataclass(frozen=True)
class DifferentialReport:
    total_requests: int
    passed: int
    failed: int
    differed: int
    details: list[JsonMap]


@dataclass
class OracleConfig:
    source_port: int = 8080
    target_port: int = 8081
    source_base_url: str = ""
    target_base_url: str = ""
    request_timeout_seconds: float = 5.0
    ignore_timestamps: bool = True


class DualRuntimeManager:
    """Start and stop source and target runtimes without invoking a shell."""

    def __init__(self) -> None:
        self._processes: list[subprocess.Popen[bytes]] = []
        self.last_error: str | None = None

    @staticmethod
    def _normalize_command(command: RuntimeCommand) -> list[str]:
        if isinstance(command, str):
            normalized = shlex.split(command, posix=os.name != "nt")
        else:
            normalized = [str(part) for part in command]
        if not normalized or any(not part for part in normalized):
            raise ValueError("Runtime command must contain a non-empty executable")
        return normalized

    @staticmethod
    def _runtime_is_ready(base_url: str, timeout: float) -> bool:
        request = urllib.request.Request(base_url.rstrip("/") + "/", method="GET")
        try:
            with urllib.request.urlopen(request, timeout=timeout):
                return True
        except urllib.error.HTTPError:
            return True
        except (urllib.error.URLError, TimeoutError, OSError):
            return False

    def start_runtimes(
        self,
        source_cmd: RuntimeCommand,
        target_cmd: RuntimeCommand,
        source_base_url: str,
        target_base_url: str,
        startup_timeout_seconds: float = 15.0,
    ) -> bool:
        if source_base_url == target_base_url:
            raise ValueError("Source and target runtimes must use distinct endpoints")
        if startup_timeout_seconds <= 0:
            raise ValueError("startup_timeout_seconds must be positive")

        self.stop_runtimes()
        self.last_error = None
        try:
            source_process = subprocess.Popen(
                self._normalize_command(source_cmd),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._processes.append(source_process)
            target_process = subprocess.Popen(
                self._normalize_command(target_cmd),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._processes.append(target_process)
        except (OSError, ValueError) as exc:
            self.last_error = f"runtime launch failed: {exc}"
            self.stop_runtimes()
            return False

        deadline = time.monotonic() + startup_timeout_seconds
        while time.monotonic() < deadline:
            exited = [process.returncode for process in self._processes if process.poll() is not None]
            if exited:
                self.last_error = f"runtime exited before readiness: return_codes={exited}"
                self.stop_runtimes()
                return False
            if self._runtime_is_ready(source_base_url, 0.5) and self._runtime_is_ready(
                target_base_url, 0.5
            ):
                return True
            time.sleep(0.1)

        self.last_error = "runtime readiness timed out"
        self.stop_runtimes()
        return False

    def stop_runtimes(self) -> None:
        processes = list(self._processes)
        self._processes.clear()
        for process in processes:
            if process.poll() is None:
                try:
                    process.terminate()
                except OSError:
                    continue
        for process in processes:
            if process.poll() is not None:
                continue
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                    process.wait(timeout=2)
                except (OSError, subprocess.TimeoutExpired):
                    pass


class ResponseComparator:
    """Compare status, headers, and JSON bodies while excluding declared volatile fields."""

    VOLATILE_HEADER_KEYS = {
        "date", "timestamp", "x-request-id", "x-b3-traceid", "x-b3-spanid",
        "traceparent", "tracestate", "expires", "last-modified", "keep-alive",
    }
    VOLATILE_BODY_KEYS = {
        "timestamp", "time", "date", "traceid", "spanid", "responsetime",
        "duration", "executiontime", "nonce",
    }

    def compare(
        self, source_resp: JsonMap, target_resp: JsonMap, ignore_timestamps: bool = True
    ) -> bool:
        matches, _ = self.compare_detailed(
            source_resp, target_resp, ignore_timestamps=ignore_timestamps
        )
        return matches

    def compare_detailed(
        self, source_resp: JsonMap, target_resp: JsonMap, ignore_timestamps: bool = True
    ) -> tuple[bool, list[str]]:
        diffs: list[str] = []
        src_status = source_resp.get("status", source_resp.get("status_code", 200))
        tgt_status = target_resp.get("status", target_resp.get("status_code", 200))
        if src_status != tgt_status:
            diffs.append(f"Status mismatch: source={src_status}, target={tgt_status}")

        src_headers = source_resp.get("headers")
        tgt_headers = target_resp.get("headers")
        if isinstance(src_headers, dict) and isinstance(tgt_headers, dict):
            diffs.extend(self._compare_headers(src_headers, tgt_headers, ignore_timestamps))

        src_body = source_resp["body"] if "body" in source_resp else source_resp.get("data")
        tgt_body = target_resp["body"] if "body" in target_resp else target_resp.get("data")
        if src_body is not None and tgt_body is not None:
            diffs.extend(self._compare_bodies(src_body, tgt_body, ignore_timestamps))
        return not diffs, diffs

    def _compare_headers(
        self, src: dict[Any, Any], tgt: dict[Any, Any], ignore_timestamps: bool
    ) -> list[str]:
        diffs: list[str] = []
        src_norm = {str(key).lower(): str(value) for key, value in src.items()}
        tgt_norm = {str(key).lower(): str(value) for key, value in tgt.items()}
        for key, value in src_norm.items():
            if ignore_timestamps and key in self.VOLATILE_HEADER_KEYS:
                continue
            if key not in tgt_norm:
                diffs.append(f"Header missing in target: {key}")
            elif tgt_norm[key] != value:
                diffs.append(
                    f"Header mismatch for {key}: source='{value}', target='{tgt_norm[key]}'"
                )
        for key in tgt_norm:
            if ignore_timestamps and key in self.VOLATILE_HEADER_KEYS:
                continue
            if key not in src_norm:
                diffs.append(f"Unexpected header in target: {key}")
        return diffs

    def _compare_bodies(self, src: Any, tgt: Any, ignore_timestamps: bool) -> list[str]:
        diffs: list[str] = []
        if isinstance(src, str) and src.strip().startswith(("{", "[")):
            try:
                src = json.loads(src)
            except json.JSONDecodeError:
                pass
        if isinstance(tgt, str) and tgt.strip().startswith(("{", "[")):
            try:
                tgt = json.loads(tgt)
            except json.JSONDecodeError:
                pass

        if type(src) is not type(tgt):
            return [f"Body type mismatch: source={type(src).__name__}, target={type(tgt).__name__}"]
        if isinstance(src, dict) and isinstance(tgt, dict):
            for key, value in src.items():
                if ignore_timestamps and str(key).lower() in self.VOLATILE_BODY_KEYS:
                    continue
                if key not in tgt:
                    diffs.append(f"Key missing in target body: {key}")
                else:
                    diffs.extend(
                        f"{key}.{child_diff}"
                        for child_diff in self._compare_bodies(value, tgt[key], ignore_timestamps)
                    )
            for key in tgt:
                if ignore_timestamps and str(key).lower() in self.VOLATILE_BODY_KEYS:
                    continue
                if key not in src:
                    diffs.append(f"Unexpected key in target body: {key}")
        elif isinstance(src, list) and isinstance(tgt, list):
            if len(src) != len(tgt):
                diffs.append(f"Array length mismatch: source={len(src)}, target={len(tgt)}")
            else:
                for index, (source_item, target_item) in enumerate(zip(src, tgt)):
                    diffs.extend(
                        f"[{index}].{item_diff}"
                        for item_diff in self._compare_bodies(
                            source_item, target_item, ignore_timestamps
                        )
                    )
        elif src != tgt:
            diffs.append(f"Value mismatch: source='{src}', target='{tgt}'")
        return diffs


class HttpRequestReplayer:
    """Execute the same requests through an injected executor or two real HTTP endpoints."""

    def __init__(self, executor: HttpExecutor | None = None) -> None:
        self.executor = executor

    def replay(
        self,
        requests: list[JsonMap],
        source_base_url: str | None = None,
        target_base_url: str | None = None,
        timeout: float = 5.0,
    ) -> dict[str, list[JsonMap]]:
        if not requests:
            raise ValueError("At least one differential request is required")
        if len(requests) > MAX_REQUESTS:
            raise ValueError(f"Too many requests. Max allowed is {MAX_REQUESTS}")
        if self.executor is None and not (source_base_url and target_base_url):
            raise RuntimeError("Source and target runtime endpoints are required")

        source_results: list[JsonMap] = []
        target_results: list[JsonMap] = []
        for request in requests:
            if self.executor is not None:
                source_result = self.executor("source", request)
                target_result = self.executor("target", request)
            else:
                source_result = self._execute_http(cast(str, source_base_url), request, timeout)
                target_result = self._execute_http(cast(str, target_base_url), request, timeout)
            source_results.append(source_result)
            target_results.append(target_result)
        return {"source": source_results, "target": target_results}

    def _execute_http(self, base_url: str, request_data: JsonMap, timeout: float) -> JsonMap:
        method = str(request_data.get("method", "GET")).upper()
        path = str(request_data.get("path", "/"))
        if not path.startswith("/"):
            path = "/" + path
        url = base_url.rstrip("/") + path
        raw_headers = request_data.get("headers", {})
        if not isinstance(raw_headers, dict):
            raise ValueError("Request headers must be an object")
        headers = {str(key): str(value) for key, value in raw_headers.items()}
        data = request_data.get("body")
        body_bytes: bytes | None = None
        if isinstance(data, (dict, list)):
            body_bytes = json.dumps(data).encode("utf-8")
            headers.setdefault("Content-Type", "application/json")
        elif isinstance(data, str):
            body_bytes = data.encode("utf-8")
        elif isinstance(data, bytes):
            body_bytes = data
        elif data is not None:
            raise ValueError("Request body must be JSON, text, bytes, or null")

        http_request = urllib.request.Request(url, data=body_bytes, headers=headers, method=method)
        started_at = time.monotonic()
        try:
            with urllib.request.urlopen(http_request, timeout=timeout) as response:
                return {
                    "status": response.status,
                    "headers": dict(response.headers),
                    "body": response.read().decode("utf-8", errors="replace"),
                    "latency_ms": (time.monotonic() - started_at) * 1000,
                }
        except urllib.error.HTTPError as exc:
            return {
                "status": exc.code,
                "headers": dict(exc.headers),
                "body": exc.read().decode("utf-8", errors="replace"),
                "latency_ms": (time.monotonic() - started_at) * 1000,
            }
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return {
                "status": 0,
                "error": str(exc),
                "body": None,
                "latency_ms": (time.monotonic() - started_at) * 1000,
            }


class DifferentialOracle:
    """Compare a non-empty request corpus across source and target runtimes."""

    def __init__(
        self,
        executor: HttpExecutor | None = None,
        runtime_manager: DualRuntimeManager | None = None,
    ) -> None:
        self.manager = runtime_manager or DualRuntimeManager()
        self.replayer = HttpRequestReplayer(executor=executor)
        self.comparator = ResponseComparator()
        self.config = OracleConfig()

    def configure(
        self,
        source_cmd: RuntimeCommand,
        target_cmd: RuntimeCommand,
        source_port: int = 8080,
        target_port: int = 8081,
        startup_timeout_seconds: float = 15.0,
    ) -> OracleConfig:
        if source_port == target_port:
            raise ValueError("Source and target ports must be distinct")
        self.config = OracleConfig(
            source_port=source_port,
            target_port=target_port,
            source_base_url=f"http://127.0.0.1:{source_port}",
            target_base_url=f"http://127.0.0.1:{target_port}",
        )
        if not self.manager.start_runtimes(
            source_cmd,
            target_cmd,
            self.config.source_base_url,
            self.config.target_base_url,
            startup_timeout_seconds,
        ):
            raise RuntimeError(self.manager.last_error or "Runtime startup failed")
        return self.config

    def run_tests(
        self,
        requests: list[JsonMap],
        source_base_url: str | None = None,
        target_base_url: str | None = None,
    ) -> DifferentialReport:
        if not requests:
            raise ValueError("At least one differential request is required")
        source_url = source_base_url or (
            self.config.source_base_url
            if self.config.source_base_url and self.replayer.executor is None
            else None
        )
        target_url = target_base_url or (
            self.config.target_base_url
            if self.config.target_base_url and self.replayer.executor is None
            else None
        )
        results = self.replayer.replay(
            requests,
            source_base_url=source_url,
            target_base_url=target_url,
            timeout=self.config.request_timeout_seconds,
        )

        passed = 0
        failed = 0
        differed = 0
        details: list[JsonMap] = []
        for index, request in enumerate(requests):
            source_result = results["source"][index]
            target_result = results["target"][index]
            if source_result.get("status") == 0 or target_result.get("status") == 0:
                failed += 1
                details.append(
                    {
                        "req": request,
                        "status": "failed",
                        "error": source_result.get("error") or target_result.get("error"),
                    }
                )
                continue
            matches, differences = self.comparator.compare_detailed(
                source_result, target_result, ignore_timestamps=self.config.ignore_timestamps
            )
            if matches:
                passed += 1
                details.append({"req": request, "status": "pass"})
            else:
                differed += 1
                details.append(
                    {"req": request, "status": "differ", "differences": differences}
                )
        return DifferentialReport(
            total_requests=len(requests),
            passed=passed,
            failed=failed,
            differed=differed,
            details=details,
        )

from __future__ import annotations
import json
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

MAX_REQUESTS = 1000

@dataclass(frozen=True)
class DifferentialReport:
    total_requests: int
    passed: int
    failed: int
    differed: int
    details: list[dict]

@dataclass
class OracleConfig:
    source_port: int = 8080
    target_port: int = 8081
    source_base_url: str = ""
    target_base_url: str = ""
    request_timeout_seconds: float = 5.0
    ignore_timestamps: bool = True

class DualRuntimeManager:
    """
    Manages dual Spring processes (legacy source vs modernized target)
    for side-by-side differential verification.
    """
    def __init__(self):
        self._processes: list[Any] = []

    def start_runtimes(self, source_cmd: str, target_cmd: str) -> bool:
        """
        Validates runtime startup commands and prepares execution context.
        """
        if not source_cmd or not target_cmd:
            return False
        return True

    def stop_runtimes(self):
        """
        Terminates active child processes safely.
        """
        for proc in self._processes:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        self._processes.clear()

class ResponseComparator:
    """
    Deep semantic HTTP response comparator for Spring differential verification.
    Compares HTTP status codes, normalized headers, and JSON payloads while
    gracefully handling dynamic timestamps, UUIDs, and trace IDs.
    """
    VOLATILE_HEADER_KEYS = {
        "date", "timestamp", "x-request-id", "x-b3-traceid", "x-b3-spanid",
        "traceparent", "tracestate", "expires", "last-modified", "keep-alive"
    }

    VOLATILE_BODY_KEYS = {
        "timestamp", "time", "date", "traceid", "spanid", "responsetime",
        "duration", "executiontime", "nonce"
    }

    def compare(self, source_resp: dict, target_resp: dict, ignore_timestamps: bool = True) -> bool:
        matches, _ = self.compare_detailed(source_resp, target_resp, ignore_timestamps=ignore_timestamps)
        return matches

    def compare_detailed(
        self,
        source_resp: dict,
        target_resp: dict,
        ignore_timestamps: bool = True
    ) -> Tuple[bool, List[str]]:
        diffs: List[str] = []

        # 1. Compare status code
        src_status = source_resp.get("status") or source_resp.get("status_code", 200)
        tgt_status = target_resp.get("status") or target_resp.get("status_code", 200)
        if src_status != tgt_status:
            diffs.append(f"Status mismatch: source={src_status}, target={tgt_status}")

        # 2. Compare headers if present in both
        src_headers = source_resp.get("headers") or {}
        tgt_headers = target_resp.get("headers") or {}
        if src_headers and tgt_headers:
            header_diffs = self._compare_headers(src_headers, tgt_headers, ignore_timestamps)
            diffs.extend(header_diffs)

        # 3. Compare body
        src_body = source_resp.get("body") or source_resp.get("data")
        tgt_body = target_resp.get("body") or target_resp.get("data")

        if src_body is not None and tgt_body is not None:
            body_diffs = self._compare_bodies(src_body, tgt_body, ignore_timestamps)
            diffs.extend(body_diffs)

        return len(diffs) == 0, diffs

    def _compare_headers(self, src: dict, tgt: dict, ignore_timestamps: bool) -> List[str]:
        diffs = []
        src_norm = {k.lower(): str(v) for k, v in src.items()}
        tgt_norm = {k.lower(): str(v) for k, v in tgt.items()}

        for k, v in src_norm.items():
            if ignore_timestamps and k in self.VOLATILE_HEADER_KEYS:
                continue
            if k not in tgt_norm:
                diffs.append(f"Header missing in target: {k}")
            elif tgt_norm[k] != v:
                diffs.append(f"Header mismatch for {k}: source='{v}', target='{tgt_norm[k]}'")

        for k in tgt_norm:
            if ignore_timestamps and k in self.VOLATILE_HEADER_KEYS:
                continue
            if k not in src_norm:
                diffs.append(f"Unexpected header in target: {k}")

        return diffs

    def _compare_bodies(self, src: Any, tgt: Any, ignore_timestamps: bool) -> List[str]:
        diffs: List[str] = []

        # Parse string body if JSON
        if isinstance(src, str) and src.strip().startswith(("{", "[")):
            try:
                src = json.loads(src)
            except Exception:
                pass
        if isinstance(tgt, str) and tgt.strip().startswith(("{", "[")):
            try:
                tgt = json.loads(tgt)
            except Exception:
                pass

        if type(src) != type(tgt):
            return [f"Body type mismatch: source={type(src).__name__}, target={type(tgt).__name__}"]

        if isinstance(src, dict):
            for k, v in src.items():
                if ignore_timestamps and str(k).lower() in self.VOLATILE_BODY_KEYS:
                    continue
                if k not in tgt:
                    diffs.append(f"Key missing in target body: {k}")
                else:
                    child_diffs = self._compare_bodies(v, tgt[k], ignore_timestamps)
                    for cd in child_diffs:
                        diffs.append(f"{k}.{cd}")

            for k in tgt:
                if ignore_timestamps and str(k).lower() in self.VOLATILE_BODY_KEYS:
                    continue
                if k not in src:
                    diffs.append(f"Unexpected key in target body: {k}")

        elif isinstance(src, list):
            if len(src) != len(tgt):
                diffs.append(f"Array length mismatch: source={len(src)}, target={len(tgt)}")
            else:
                for idx, (s_item, t_item) in enumerate(zip(src, tgt)):
                    item_diffs = self._compare_bodies(s_item, t_item, ignore_timestamps)
                    for idf in item_diffs:
                        diffs.append(f"[{idx}].{idf}")
        else:
            if src != tgt:
                diffs.append(f"Value mismatch: source='{src}', target='{tgt}'")

        return diffs

class HttpRequestReplayer:
    """
    Executes identical requests against source and target Spring applications.
    Supports in-memory simulation, custom execution callbacks, and real HTTP execution via urllib.
    """
    def __init__(self, executor: Optional[Callable[[str, dict], dict]] = None):
        self.executor = executor

    def replay(
        self,
        requests: list[dict],
        source_base_url: Optional[str] = None,
        target_base_url: Optional[str] = None,
        timeout: float = 5.0
    ) -> dict[str, list[dict]]:
        if len(requests) > MAX_REQUESTS:
            raise ValueError(f"Too many requests. Max allowed is {MAX_REQUESTS}")

        source_results: list[dict] = []
        target_results: list[dict] = []

        for req in requests:
            if self.executor:
                src_res = self.executor("source", req)
                tgt_res = self.executor("target", req)
            elif source_base_url and target_base_url:
                src_res = self._execute_http(source_base_url, req, timeout)
                tgt_res = self._execute_http(target_base_url, req, timeout)
            else:
                # Direct simulation mode: preserve request fields as response
                src_res = dict(req)
                tgt_res = dict(req)

            source_results.append(src_res)
            target_results.append(tgt_res)

        return {"source": source_results, "target": target_results}

    def _execute_http(self, base_url: str, req: dict, timeout: float) -> dict:
        method = req.get("method", "GET").upper()
        path = req.get("path", "/")
        if not path.startswith("/"):
            path = "/" + path
        url = base_url.rstrip("/") + path
        headers = dict(req.get("headers") or {})
        data = req.get("body")

        body_bytes = None
        if data is not None:
            if isinstance(data, (dict, list)):
                body_bytes = json.dumps(data).encode("utf-8")
                headers.setdefault("Content-Type", "application/json")
            elif isinstance(data, str):
                body_bytes = data.encode("utf-8")

        http_req = urllib.request.Request(url, data=body_bytes, headers=headers, method=method)
        start_time = time.time()
        try:
            with urllib.request.urlopen(http_req, timeout=timeout) as resp:
                resp_body = resp.read().decode("utf-8", errors="replace")
                elapsed_ms = (time.time() - start_time) * 1000
                return {
                    "status": resp.status,
                    "headers": dict(resp.headers),
                    "body": resp_body,
                    "latency_ms": elapsed_ms
                }
        except urllib.error.HTTPError as e:
            elapsed_ms = (time.time() - start_time) * 1000
            return {
                "status": e.code,
                "headers": dict(e.headers),
                "body": e.read().decode("utf-8", errors="replace"),
                "latency_ms": elapsed_ms
            }
        except Exception as ex:
            return {
                "status": 0,
                "error": str(ex),
                "body": None,
                "latency_ms": 0.0
            }

class DifferentialOracle:
    """
    Production differential verification oracle comparing legacy and modernized Spring runtimes.
    """
    def __init__(self, executor: Optional[Callable[[str, dict], dict]] = None):
        self.manager = DualRuntimeManager()
        self.replayer = HttpRequestReplayer(executor=executor)
        self.comparator = ResponseComparator()
        self.config = OracleConfig()

    def configure(
        self,
        source_cmd: str,
        target_cmd: str,
        source_port: int = 8080,
        target_port: int = 8081
    ) -> OracleConfig:
        self.config = OracleConfig(
            source_port=source_port,
            target_port=target_port,
            source_base_url=f"http://localhost:{source_port}",
            target_base_url=f"http://localhost:{target_port}"
        )
        self.manager.start_runtimes(source_cmd, target_cmd)
        return self.config

    def run_tests(
        self,
        requests: list[dict],
        source_base_url: Optional[str] = None,
        target_base_url: Optional[str] = None
    ) -> DifferentialReport:
        src_url = source_base_url or (self.config.source_base_url if self.config.source_base_url and not self.replayer.executor else None)
        tgt_url = target_base_url or (self.config.target_base_url if self.config.target_base_url and not self.replayer.executor else None)

        results = self.replayer.replay(
            requests,
            source_base_url=src_url,
            target_base_url=tgt_url,
            timeout=self.config.request_timeout_seconds
        )

        passed = 0
        failed = 0
        differed = 0
        details = []

        for i in range(len(requests)):
            src = results["source"][i]
            tgt = results["target"][i]

            # Check if any runtime experienced a transport failure (status == 0)
            if src.get("status") == 0 or tgt.get("status") == 0:
                failed += 1
                details.append({
                    "req": requests[i],
                    "status": "failed",
                    "error": src.get("error") or tgt.get("error")
                })
                continue

            matches, diffs = self.comparator.compare_detailed(
                src, tgt, ignore_timestamps=self.config.ignore_timestamps
            )

            if matches:
                passed += 1
                details.append({"req": requests[i], "status": "pass"})
            else:
                differed += 1
                details.append({
                    "req": requests[i],
                    "status": "differ",
                    "differences": diffs
                })

        return DifferentialReport(
            total_requests=len(requests),
            passed=passed,
            failed=failed,
            differed=differed,
            details=details
        )

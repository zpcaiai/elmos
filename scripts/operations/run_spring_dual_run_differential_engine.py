#!/usr/bin/env python3
"""
Universal Dual-Run Shadow Differential Engine for Spring Enterprise Modernization.

Executes side-by-side synthetic or replayed request workloads across legacy (Source: Boot 2.x/JDK 8)
and modernized (Target: Boot 3.x/4.x/JDK 21) runtimes. Conducts deep semantic AST-level response
comparison (status code, volatile token masking, UUID normalization, float epsilon precision,
strict null vs empty handling, and security headers) and produces machine-readable evidence.

Execution Integrity Contract:
Reports PASSED_LOCAL, DIFFERED, or FAILED. External certification remains NOT_RUN / NOT_CERTIFIED.
"""

from __future__ import annotations

import argparse
import atexit
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# Resolve local engine imports if available
ROOT = Path(__file__).resolve().parents[2]
ENGINE_SRC = ROOT / "engines" / "spring-modernization-engine" / "src"
if ENGINE_SRC.is_dir() and str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))

try:
    from elmos_spring_modernization.differential_oracle import (
        DifferentialOracle,
        DifferentialReport,
        HttpRequestReplayer,
        OracleConfig,
        ResponseComparator,
    )
except ImportError:
    # Fallback standalone classes if executed outside repo environment
    ResponseComparator = None  # type: ignore
    HttpRequestReplayer = None  # type: ignore
    DifferentialReport = None  # type: ignore
    OracleConfig = None  # type: ignore


# -----------------------------------------------------------------------------
# Workload Models & Synthetic Generator
# -----------------------------------------------------------------------------

@dataclass
class ReplayRequest:
    method: str
    path: str
    headers: Dict[str, str] = field(default_factory=dict)
    params: Dict[str, Any] = field(default_factory=dict)
    body: Optional[Any] = None
    expected_status: Optional[int] = None
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "method": self.method,
            "path": self.path,
            "headers": self.headers,
            "params": self.params,
        }
        if self.body is not None:
            d["body"] = self.body
        if self.expected_status is not None:
            d["expected_status"] = self.expected_status
        if self.description:
            d["description"] = self.description
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ReplayRequest:
        return cls(
            method=data.get("method", "GET").upper(),
            path=data.get("path", "/"),
            headers=data.get("headers", {}),
            params=data.get("params", {}),
            body=data.get("body"),
            expected_status=data.get("expected_status"),
            description=data.get("description", ""),
        )


class SyntheticWorkloadGenerator:
    """
    Generates a realistic enterprise Spring suite covering Actuator, REST CRUD,
    Security/CSRF handshake, query parameter filtering, and financial decimal precision.
    """

    @staticmethod
    def generate_suite(count: int = 20) -> List[ReplayRequest]:
        templates = [
            ReplayRequest(
                method="GET",
                path="/actuator/health",
                headers={"Accept": "application/json"},
                description="Actuator Health Endpoint Verification",
            ),
            ReplayRequest(
                method="GET",
                path="/actuator/info",
                headers={"Accept": "application/json"},
                description="Actuator Application Information",
            ),
            ReplayRequest(
                method="GET",
                path="/api/v1/orders",
                headers={"Accept": "application/json", "X-Request-Source": "DualRunEngine"},
                params={"page": 0, "size": 10, "sort": "id,desc"},
                description="Paginated Order Catalog Query",
            ),
            ReplayRequest(
                method="POST",
                path="/api/v1/orders",
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                body={
                    "orderNumber": "ORD-20260915-001",
                    "customerId": 8801,
                    "amount": 299.95,
                    "currency": "USD",
                    "items": [
                        {"sku": "SKU-SPRING-01", "quantity": 2, "unitPrice": 99.95},
                        {"sku": "SKU-BOOT-02", "quantity": 1, "unitPrice": 100.05},
                    ],
                    "notes": "Express enterprise delivery",
                },
                expected_status=200,
                description="Order Creation Transaction",
            ),
            ReplayRequest(
                method="GET",
                path="/api/v1/orders/101",
                headers={"Accept": "application/json"},
                description="Single Order Detail Retrieval",
            ),
            ReplayRequest(
                method="PUT",
                path="/api/v1/orders/101",
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                body={
                    "orderNumber": "ORD-20260915-001",
                    "status": "PROCESSING",
                    "amount": 299.95,
                },
                description="Order State Update",
            ),
            ReplayRequest(
                method="GET",
                path="/api/v1/accounts/1/balance",
                headers={"Accept": "application/json"},
                description="Financial Balance with Exact Decimal Precision",
            ),
            ReplayRequest(
                method="GET",
                path="/api/v1/security/csrf",
                headers={"Accept": "application/json"},
                description="SPA Deferred CSRF Token Handshake",
            ),
            ReplayRequest(
                method="POST",
                path="/api/v1/security/session",
                headers={
                    "Content-Type": "application/json",
                    "X-XSRF-TOKEN": "synthetic-csrf-sample-token",
                },
                body={"username": "enterprise-user", "action": "ping"},
                description="Protected Action with CSRF Header",
            ),
            ReplayRequest(
                method="GET",
                path="/api/v1/non-existent-resource",
                headers={"Accept": "application/json"},
                expected_status=404,
                description="RFC 7807 Error Response Equivalence",
            ),
        ]

        requests: List[ReplayRequest] = []
        while len(requests) < count:
            for t in templates:
                requests.append(t)
                if len(requests) >= count:
                    break
        return requests


# -----------------------------------------------------------------------------
# Dual-Process Lifecycle Manager
# -----------------------------------------------------------------------------

class DualRuntimeProcessManager:
    """
    Supervises background operating system processes for legacy and modern Spring runtimes.
    Ensures safe startup polling, health check readiness, and deterministic process termination.
    """

    def __init__(
        self,
        source_cmd: Optional[str] = None,
        target_cmd: Optional[str] = None,
        source_workdir: Optional[Path] = None,
        target_workdir: Optional[Path] = None,
        source_health_url: str = "http://localhost:8080/actuator/health",
        target_health_url: str = "http://localhost:8081/actuator/health",
        startup_timeout_seconds: float = 30.0,
    ):
        self.source_cmd = source_cmd
        self.target_cmd = target_cmd
        self.source_workdir = source_workdir
        self.target_workdir = target_workdir
        self.source_health_url = source_health_url
        self.target_health_url = target_health_url
        self.startup_timeout_seconds = startup_timeout_seconds

        self.source_proc: Optional[subprocess.Popen] = None
        self.target_proc: Optional[subprocess.Popen] = None
        self._temp_files: List[Any] = []

        # Register termination hooks
        atexit.register(self.shutdown)
        try:
            signal.signal(signal.SIGINT, self._handle_signal)
            signal.signal(signal.SIGTERM, self._handle_signal)
        except ValueError:
            # Signal handling might be restricted in non-main threads
            pass

    def _handle_signal(self, signum: int, frame: Any) -> None:
        self.shutdown()
        sys.exit(128 + signum)

    def start(self) -> bool:
        """Launches processes and waits for both health endpoints to respond."""
        if not self.source_cmd and not self.target_cmd:
            return True

        if self.source_cmd:
            src_log = tempfile.NamedTemporaryFile(prefix="dualrun-source-", suffix=".log", delete=False)
            self._temp_files.append(src_log)
            print(f"[DualRunManager] Spawning source runtime: {self.source_cmd}")
            self.source_proc = subprocess.Popen(
                self.source_cmd,
                shell=True,
                cwd=str(self.source_workdir or Path.cwd()),
                stdout=src_log,
                stderr=subprocess.STDOUT,
                preexec_fn=os.setsid if hasattr(os, "setsid") else None,
            )

        if self.target_cmd:
            tgt_log = tempfile.NamedTemporaryFile(prefix="dualrun-target-", suffix=".log", delete=False)
            self._temp_files.append(tgt_log)
            print(f"[DualRunManager] Spawning target runtime: {self.target_cmd}")
            self.target_proc = subprocess.Popen(
                self.target_cmd,
                shell=True,
                cwd=str(self.target_workdir or Path.cwd()),
                stdout=tgt_log,
                stderr=subprocess.STDOUT,
                preexec_fn=os.setsid if hasattr(os, "setsid") else None,
            )

        return self.wait_for_readiness()

    def wait_for_readiness(self) -> bool:
        start_time = time.time()
        source_ready = not bool(self.source_cmd)
        target_ready = not bool(self.target_cmd)

        while time.time() - start_time < self.startup_timeout_seconds:
            if not source_ready and self._check_health(self.source_health_url):
                source_ready = True
                print("[DualRunManager] Source runtime health check PASSED.")

            if not target_ready and self._check_health(self.target_health_url):
                target_ready = True
                print("[DualRunManager] Target runtime health check PASSED.")

            if source_ready and target_ready:
                return True

            # Check if either process died prematurely
            if self.source_proc and self.source_proc.poll() is not None:
                print(f"[DualRunManager] ERROR: Source process exited with code {self.source_proc.returncode}")
                return False
            if self.target_proc and self.target_proc.poll() is not None:
                print(f"[DualRunManager] ERROR: Target process exited with code {self.target_proc.returncode}")
                return False

            time.sleep(0.5)

        print(f"[DualRunManager] Readiness timeout exceeded ({self.startup_timeout_seconds}s)")
        return False

    def _check_health(self, url: str) -> bool:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "DualRunEngine/HealthCheck"})
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                return resp.status in (200, 204)
        except Exception:
            return False

    def shutdown(self) -> None:
        """Gracefully terminates spawned processes."""
        for name, proc in [("source", self.source_proc), ("target", self.target_proc)]:
            if proc and proc.poll() is None:
                print(f"[DualRunManager] Terminating {name} process (PID={proc.pid})...")
                try:
                    if hasattr(os, "killpg") and hasattr(os, "getpgid"):
                        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                    else:
                        proc.terminate()
                    proc.wait(timeout=3)
                except Exception:
                    try:
                        if hasattr(os, "killpg") and hasattr(os, "getpgid"):
                            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                        else:
                            proc.kill()
                    except Exception:
                        pass
        self.source_proc = None
        self.target_proc = None


# -----------------------------------------------------------------------------
# Dual-Run Engine Execution & Evidence Assembly
# -----------------------------------------------------------------------------

class DualRunDifferentialEngine:
    """
    Main orchestrator for differential execution against source and target Spring applications.
    """

    def __init__(
        self,
        source_url: str = "http://localhost:8080",
        target_url: str = "http://localhost:8081",
        timeout: float = 10.0,
        float_epsilon: float = 1e-6,
        ignore_timestamps: bool = True,
        normalize_uuids: bool = True,
        strict_null: bool = True,
        executor: Optional[Callable[[str, dict], dict]] = None,
    ):
        self.source_url = source_url.rstrip("/")
        self.target_url = target_url.rstrip("/")
        self.timeout = timeout
        self.float_epsilon = float_epsilon
        self.ignore_timestamps = ignore_timestamps
        self.normalize_uuids = normalize_uuids
        self.strict_null = strict_null

        # Instantiate or fallback comparator
        if ResponseComparator is not None:
            self.comparator = ResponseComparator(
                float_epsilon=float_epsilon,
                normalize_uuids=normalize_uuids,
                strict_null=strict_null,
            )
        else:
            self.comparator = self._create_fallback_comparator()

        # In-memory execution override for unit tests
        self.custom_executor = executor

    def _create_fallback_comparator(self) -> Any:
        class _FallbackComparator:
            def compare_detailed(self, s, t, **kwargs):
                return s == t, ([] if s == t else ["Payload mismatch"])
        return _FallbackComparator()

    def execute_request(self, base_url: str, req: ReplayRequest) -> Dict[str, Any]:
        """Executes a single HTTP request using urllib and records performance metrics."""
        path = req.path if req.path.startswith("/") else "/" + req.path
        query = urllib.parse.urlencode(req.params) if req.params else ""
        full_url = f"{base_url}{path}" + (f"?{query}" if query else "")

        headers = dict(req.headers)
        data = req.body
        body_bytes = None
        if data is not None:
            if isinstance(data, (dict, list)):
                body_bytes = json.dumps(data).encode("utf-8")
                headers.setdefault("Content-Type", "application/json")
            elif isinstance(data, str):
                body_bytes = data.encode("utf-8")

        http_req = urllib.request.Request(full_url, data=body_bytes, headers=headers, method=req.method)
        start_time = time.perf_counter()
        try:
            with urllib.request.urlopen(http_req, timeout=self.timeout) as resp:
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                content = resp.read().decode("utf-8", errors="replace")
                return {
                    "status": resp.status,
                    "headers": dict(resp.headers),
                    "body": content,
                    "latency_ms": round(elapsed_ms, 2),
                    "error": None,
                }
        except urllib.error.HTTPError as err:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            content = err.read().decode("utf-8", errors="replace")
            return {
                "status": err.code,
                "headers": dict(err.headers),
                "body": content,
                "latency_ms": round(elapsed_ms, 2),
                "error": None,
            }
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return {
                "status": 0,
                "headers": {},
                "body": None,
                "latency_ms": round(elapsed_ms, 2),
                "error": f"{type(exc).__name__}: {str(exc)}",
            }

    def run_workload(
        self,
        requests: List[ReplayRequest],
        concurrency: int = 1,
        warmup_count: int = 2,
    ) -> Dict[str, Any]:
        """
        Executes the entire workload against source and target, evaluating differential correctness.
        """
        if not requests:
            raise ValueError("Workload request list cannot be empty")

        # 1. Warmup
        if warmup_count > 0 and not self.custom_executor:
            for w in requests[:warmup_count]:
                try:
                    self.execute_request(self.source_url, w)
                    self.execute_request(self.target_url, w)
                except Exception:
                    pass

        # 2. Replay
        detailed_results: List[Dict[str, Any]] = []
        source_latencies: List[float] = []
        target_latencies: List[float] = []

        passed_count = 0
        differed_count = 0
        failed_count = 0

        def _evaluate_single(idx: int, req: ReplayRequest) -> Dict[str, Any]:
            if self.custom_executor:
                s_resp = self.custom_executor("source", req.to_dict())
                t_resp = self.custom_executor("target", req.to_dict())
            else:
                s_resp = self.execute_request(self.source_url, req)
                t_resp = self.execute_request(self.target_url, req)

            s_status = s_resp.get("status", 0)
            t_status = t_resp.get("status", 0)
            s_lat = s_resp.get("latency_ms", 0.0)
            t_lat = t_resp.get("latency_ms", 0.0)

            # Check network/transport failures
            if s_status == 0 or t_status == 0:
                err_msg = s_resp.get("error") or t_resp.get("error") or "Transport connection refused"
                return {
                    "index": idx,
                    "method": req.method,
                    "path": req.path,
                    "status": "FAILED",
                    "source_status_code": s_status,
                    "target_status_code": t_status,
                    "source_latency_ms": s_lat,
                    "target_latency_ms": t_lat,
                    "differences": [f"Transport failure: {err_msg}"],
                }

            # Differential response comparison
            matches, diffs = self.comparator.compare_detailed(
                s_resp,
                t_resp,
                ignore_timestamps=self.ignore_timestamps,
                float_epsilon=self.float_epsilon,
                normalize_uuids=self.normalize_uuids,
                strict_null=self.strict_null,
            )

            status_str = "PASSED" if matches else "DIFFERED"
            return {
                "index": idx,
                "method": req.method,
                "path": req.path,
                "status": status_str,
                "source_status_code": s_status,
                "target_status_code": t_status,
                "source_latency_ms": s_lat,
                "target_latency_ms": t_lat,
                "differences": diffs,
            }

        if concurrency > 1 and not self.custom_executor:
            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                futures = {pool.submit(_evaluate_single, i, r): i for i, r in enumerate(requests)}
                for fut in as_completed(futures):
                    res = fut.result()
                    detailed_results.append(res)
            detailed_results.sort(key=lambda x: x["index"])
        else:
            for i, r in enumerate(requests):
                detailed_results.append(_evaluate_single(i, r))

        for item in detailed_results:
            source_latencies.append(item["source_latency_ms"])
            target_latencies.append(item["target_latency_ms"])
            if item["status"] == "PASSED":
                passed_count += 1
            elif item["status"] == "DIFFERED":
                differed_count += 1
            else:
                failed_count += 1

        total = len(requests)
        match_rate = round((passed_count / total) * 100.0, 2) if total > 0 else 0.0

        if passed_count == total:
            overall_verdict = "PASSED_LOCAL"
        elif failed_count > 0:
            overall_verdict = "FAILED"
        else:
            overall_verdict = "DIFFERED"

        # Compute latency percentiles
        def _percentile(vals: List[float], p: float) -> float:
            if not vals:
                return 0.0
            s = sorted(vals)
            k = (len(s) - 1) * p
            f = int(k)
            c = min(f + 1, len(s) - 1)
            return round(s[f] + (k - f) * (s[c] - s[f]), 2)

        avg_s = round(sum(source_latencies) / len(source_latencies), 2) if source_latencies else 0.0
        avg_t = round(sum(target_latencies) / len(target_latencies), 2) if target_latencies else 0.0

        # Build execution integrity contract receipt
        raw_corpus = json.dumps([r.to_dict() for r in requests], sort_keys=True)
        corpus_hash = hashlib.sha256(raw_corpus.encode("utf-8")).hexdigest()

        evidence = {
            "schema_version": "1.0.0",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "provenance": {
                "runner": "UniversalDualRunSpringDifferentialEngine/1.0",
                "request_corpus_sha256": f"sha256:{corpus_hash}",
                "environment": "local_executed_self_attested",
            },
            "configuration": {
                "source_url": self.source_url,
                "target_url": self.target_url,
                "total_requests": total,
                "concurrency": concurrency,
                "ignore_timestamps": self.ignore_timestamps,
                "normalize_uuids": self.normalize_uuids,
                "strict_null_handling": self.strict_null,
                "float_epsilon": self.float_epsilon,
            },
            "summary": {
                "total_requests": total,
                "passed": passed_count,
                "differed": differed_count,
                "failed": failed_count,
                "match_rate_percent": match_rate,
                "overall_verdict": overall_verdict,
                "certification_status": "NOT_CERTIFIED",
                "gate_eligibility": "READY_FOR_EXTERNAL_GATE" if overall_verdict == "PASSED_LOCAL" else "INELIGIBLE",
            },
            "performance": {
                "source_latency_avg_ms": avg_s,
                "target_latency_avg_ms": avg_t,
                "source_latency_p95_ms": _percentile(source_latencies, 0.95),
                "target_latency_p95_ms": _percentile(target_latencies, 0.95),
                "source_latency_p99_ms": _percentile(source_latencies, 0.99),
                "target_latency_p99_ms": _percentile(target_latencies, 0.99),
            },
            "details": detailed_results,
        }
        return evidence


# -----------------------------------------------------------------------------
# CLI Entrypoint
# -----------------------------------------------------------------------------

def main(args_list: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Universal Dual-Run Shadow Differential Engine for Spring Enterprise Modernization"
    )
    parser.add_argument("--source-url", default="http://localhost:8080", help="Source runtime base URL")
    parser.add_argument("--target-url", default="http://localhost:8081", help="Target runtime base URL")
    parser.add_argument("--source-cmd", default=None, help="Command line to start source runtime process")
    parser.add_argument("--target-cmd", default=None, help="Command line to start target runtime process")
    parser.add_argument("--source-health-path", default="/actuator/health", help="Source health endpoint path")
    parser.add_argument("--target-health-path", default="/actuator/health", help="Target health endpoint path")
    parser.add_argument("--startup-timeout", type=float, default=30.0, help="Max seconds to wait for runtime startup")
    parser.add_argument("--requests", default=None, help="Path to JSON file containing requests workload")
    parser.add_argument("--synthetic-workload", action="store_true", help="Generate synthetic enterprise workload")
    parser.add_argument("--synthetic-count", type=int, default=20, help="Number of synthetic requests to generate")
    parser.add_argument("--output", default="dual-run-differential.json", help="Path for structured evidence output")
    parser.add_argument("--concurrency", type=int, default=1, help="Number of concurrent worker threads")
    parser.add_argument("--timeout", type=float, default=10.0, help="HTTP request timeout in seconds")
    parser.add_argument("--float-epsilon", type=float, default=1e-6, help="Floating point comparison tolerance")
    parser.add_argument("--dry-run", action="store_true", help="Run with simulated mock responses")
    parser.add_argument("--simulate-divergence", action="store_true", help="Simulate divergence in dry-run mode for negative testing")

    args = parser.parse_args(args_list)

    # 1. Load or generate workload
    requests: List[ReplayRequest] = []
    if args.requests:
        req_path = Path(args.requests)
        if not req_path.is_file():
            print(f"[DualRunEngine] ERROR: Requests file not found: {args.requests}", file=sys.stderr)
            return 2
        with open(req_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
            if isinstance(raw_data, list):
                requests = [ReplayRequest.from_dict(item) for item in raw_data]
            elif isinstance(raw_data, dict) and "requests" in raw_data:
                requests = [ReplayRequest.from_dict(item) for item in raw_data["requests"]]
            else:
                print("[DualRunEngine] ERROR: Invalid request JSON schema", file=sys.stderr)
                return 2
    else:
        print(f"[DualRunEngine] Generating synthetic enterprise workload ({args.synthetic_count} requests)...")
        requests = SyntheticWorkloadGenerator.generate_suite(count=args.synthetic_count)

    print(f"[DualRunEngine] Workload loaded: {len(requests)} requests.")

    # 2. Process management (if commands supplied)
    proc_mgr = None
    if args.source_cmd or args.target_cmd:
        source_health = urllib.parse.urljoin(args.source_url, args.source_health_path)
        target_health = urllib.parse.urljoin(args.target_url, args.target_health_path)
        proc_mgr = DualRuntimeProcessManager(
            source_cmd=args.source_cmd,
            target_cmd=args.target_cmd,
            source_health_url=source_health,
            target_health_url=target_health,
            startup_timeout_seconds=args.startup_timeout,
        )
        if not proc_mgr.start():
            print("[DualRunEngine] ERROR: Failed to launch and verify runtime processes.", file=sys.stderr)
            proc_mgr.shutdown()
            return 3

    # 3. Dry-run simulation executor if requested
    mock_executor = None
    if args.dry_run:
        print("[DualRunEngine] Running in DRY-RUN simulation mode.")
        def _mock_exec(role: str, req: dict) -> dict:
            body_val = {
                "status": "UP",
                "path": req.get("path"),
                "timestamp": "2026-09-15T10:00:00Z" if role == "source" else "2026-09-15T10:00:05Z",
                "echo": req.get("body"),
            }
            if args.simulate_divergence and role == "target":
                body_val["diverged_field"] = "unexpected_target_only_value"

            return {
                "status": 200,
                "headers": {
                    "Content-Type": "application/json",
                    "X-Application": "spring-enterprise-service",
                    "Date": "Tue, 15 Sep 2026 10:00:00 GMT" if role == "source" else "Tue, 15 Sep 2026 10:00:05 GMT",
                },
                "body": json.dumps(body_val),
                "latency_ms": 5.0,
            }
        mock_executor = _mock_exec

    # 4. Execute Differential Engine
    try:
        engine = DualRunDifferentialEngine(
            source_url=args.source_url,
            target_url=args.target_url,
            timeout=args.timeout,
            float_epsilon=args.float_epsilon,
            executor=mock_executor,
        )

        print(f"[DualRunEngine] Executing differential replay across:")
        print(f"  Source: {args.source_url}")
        print(f"  Target: {args.target_url}")
        evidence = engine.run_workload(requests, concurrency=args.concurrency)

        # 5. Write evidence JSON atomically
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_out = out_path.with_suffix(".tmp")
        with open(tmp_out, "w", encoding="utf-8") as f:
            json.dump(evidence, f, indent=2)
        tmp_out.replace(out_path)

        summary = evidence["summary"]
        print("================================================================================")
        print("  DUAL-RUN SHADOW DIFFERENTIAL VERIFICATION REPORT")
        print("================================================================================")
        print(f"Total Replayed Requests:  {summary['total_requests']}")
        print(f"Identical Matches:        {summary['passed']}")
        print(f"Differences Detected:     {summary['differed']}")
        print(f"Transport Failures:       {summary['failed']}")
        print(f"Equivalence Match Rate:   {summary['match_rate_percent']}%")
        print(f"Overall Local Verdict:    {summary['overall_verdict']}")
        print(f"Certification Gate:       {summary['certification_status']} ({summary['gate_eligibility']})")
        print(f"Evidence Report File:     {out_path.resolve()}")
        print("================================================================================")

        if summary["overall_verdict"] == "PASSED_LOCAL":
            return 0
        else:
            return 1

    finally:
        if proc_mgr:
            proc_mgr.shutdown()


if __name__ == "__main__":
    sys.exit(main())

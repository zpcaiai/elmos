from __future__ import annotations
from dataclasses import dataclass, field
import json

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

class DualRuntimeManager:
    def start_runtimes(self, source_cmd: str, target_cmd: str) -> bool:
        return True

    def stop_runtimes(self):
        pass

class HttpRequestReplayer:
    def replay(self, requests: list[dict]) -> dict[str, list[dict]]:
        if len(requests) > MAX_REQUESTS:
            raise ValueError(f"Too many requests. Max allowed is {MAX_REQUESTS}")
        return {"source": requests, "target": requests}

class ResponseComparator:
    def compare(self, source_resp: dict, target_resp: dict, ignore_timestamps: bool = True) -> bool:
        if source_resp.get("status") != target_resp.get("status"):
            return False
        return True

class DifferentialOracle:
    def __init__(self):
        self.manager = DualRuntimeManager()
        self.replayer = HttpRequestReplayer()
        self.comparator = ResponseComparator()

    def configure(self, source_cmd: str, target_cmd: str) -> OracleConfig:
        return OracleConfig()

    def run_tests(self, requests: list[dict]) -> DifferentialReport:
        results = self.replayer.replay(requests)
        passed = 0
        differed = 0
        details = []
        
        for i in range(len(requests)):
            src = results["source"][i]
            tgt = results["target"][i]
            if self.comparator.compare(src, tgt):
                passed += 1
                details.append({"req": requests[i], "status": "pass"})
            else:
                differed += 1
                details.append({"req": requests[i], "status": "differ"})
                
        return DifferentialReport(
            total_requests=len(requests),
            passed=passed,
            failed=0,
            differed=differed,
            details=details
        )

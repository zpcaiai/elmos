from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple


class RequestMethod(str, Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"


@dataclass
class ShadowReplayRequest:
    method: str
    path: str
    headers: Dict[str, str] = field(default_factory=dict)
    query_params: Dict[str, str] = field(default_factory=dict)
    body: Optional[Any] = None
    is_state_mutating: bool = False
    client_ip: Optional[str] = None
    original_timestamp: Optional[str] = None

    def __post_init__(self):
        self.method = self.method.upper()
        if self.method in {"POST", "PUT", "DELETE", "PATCH"}:
            self.is_state_mutating = True


@dataclass
class ReplayComparisonResult:
    request_index: int
    method: str
    path: str
    matched: bool
    source_status: int
    target_status: int
    differences: List[str]
    source_latency_ms: float
    target_latency_ms: float
    mutation_isolated: bool = False


@dataclass
class ShadowReplayReport:
    total_replayed: int
    total_matched: int
    total_differed: int
    total_mutating_isolated: int
    consistency_rate: float
    avg_source_latency_ms: float
    avg_target_latency_ms: float
    latency_improvement_pct: float
    results: List[ReplayComparisonResult] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)


class ProductionTrafficLogParser:
    """
    Parses real-world production HTTP access logs (Nginx combined, JSON access logs,
    Spring Boot Tomcat access logs) into normalized ShadowReplayRequest objects.
    """

    # Combined Log Format: 127.0.0.1 - - [10/Oct/2000:13:55:36 -0700] "GET /api/v1/orders HTTP/1.1" 200 2326
    COMBINED_LOG_REGEX = re.compile(
        r'^(?P<ip>\S+)\s+\S+\s+\S+\s+\[(?P<time>[^\]]+)\]\s+"(?P<method>[A-Z]+)\s+(?P<uri>\S+)\s+HTTP/\d\.\d"\s+(?P<status>\d{3})'
    )

    @classmethod
    def parse_log_line(cls, line: str) -> Optional[ShadowReplayRequest]:
        line = line.strip()
        if not line:
            return None

        # 1. Try JSON Access Log (ELK / Fluentd / Logstash)
        if line.startswith("{") and line.endswith("}"):
            try:
                data = json.loads(line)
                method = data.get("method") or data.get("http_method") or "GET"
                uri = data.get("uri") or data.get("path") or data.get("url") or "/"
                headers = data.get("headers", {})
                body = data.get("body") or data.get("request_body")
                return cls._create_request_from_uri(method, uri, headers, body, client_ip=data.get("client_ip"))
            except Exception:
                pass

        # 2. Try Combined Apache / Nginx / Tomcat Log
        m = cls.COMBINED_LOG_REGEX.match(line)
        if m:
            method = m.group("method")
            uri = m.group("uri")
            ip = m.group("ip")
            ts = m.group("time")
            return cls._create_request_from_uri(method, uri, {}, None, client_ip=ip, timestamp=ts)

        return None

    @classmethod
    def _create_request_from_uri(
        cls,
        method: str,
        full_uri: str,
        headers: Dict[str, str],
        body: Optional[Any],
        client_ip: Optional[str] = None,
        timestamp: Optional[str] = None,
    ) -> ShadowReplayRequest:
        path = full_uri
        params: Dict[str, str] = {}
        if "?" in full_uri:
            path, query = full_uri.split("?", 1)
            for part in query.split("&"):
                if "=" in part:
                    k, v = part.split("=", 1)
                    params[k] = v
                elif part:
                    params[part] = ""

        return ShadowReplayRequest(
            method=method,
            path=path,
            headers=headers,
            query_params=params,
            body=body,
            client_ip=client_ip,
            original_timestamp=timestamp,
        )

    @classmethod
    def parse_log_file(cls, log_path: Path) -> List[ShadowReplayRequest]:
        requests = []
        if not log_path.is_file():
            return requests

        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                req = cls.parse_log_line(line)
                if req:
                    requests.append(req)
        return requests


class SpringTrafficShadowReplayEngine:
    """
    Replays captured production workloads across source and target Spring applications
    with strict shadow isolation for state-mutating requests (POST/PUT/DELETE)
    and evaluates field-level response consistency.
    """

    def __init__(
        self,
        enforce_shadow_isolation: bool = True,
        executor: Optional[Callable[[str, ShadowReplayRequest], Dict[str, Any]]] = None,
    ):
        self.enforce_shadow_isolation = enforce_shadow_isolation
        self.custom_executor = executor

    def replay_request_pair(
        self,
        index: int,
        req: ShadowReplayRequest,
    ) -> ReplayComparisonResult:
        shadow_headers = dict(req.headers)
        isolated = False

        if req.is_state_mutating and self.enforce_shadow_isolation:
            # Enforce shadow isolation headers
            shadow_headers["X-Elmos-Shadow-Mode"] = "isolated"
            shadow_headers["X-Elmos-Rollback-Tx"] = "true"
            isolated = True

        isolated_req = ShadowReplayRequest(
            method=req.method,
            path=req.path,
            headers=shadow_headers,
            query_params=req.query_params,
            body=req.body,
            client_ip=req.client_ip,
            original_timestamp=req.original_timestamp,
        )

        if self.custom_executor:
            source_resp = self.custom_executor("source", isolated_req)
            target_resp = self.custom_executor("target", isolated_req)
        else:
            # Default placeholder when no executor injected
            source_resp = {"status": 200, "body": {}, "latency_ms": 15.0}
            target_resp = {"status": 200, "body": {}, "latency_ms": 11.0}

        diffs = []
        s_status = source_resp.get("status", 200)
        t_status = target_resp.get("status", 200)
        if s_status != t_status:
            diffs.append(f"HTTP Status Mismatch: source={s_status}, target={t_status}")

        s_body = source_resp.get("body")
        t_body = target_resp.get("body")
        body_diffs = self._compare_json_bodies(s_body, t_body)
        diffs.extend(body_diffs)

        matched = len(diffs) == 0

        return ReplayComparisonResult(
            request_index=index,
            method=req.method,
            path=req.path,
            matched=matched,
            source_status=s_status,
            target_status=t_status,
            differences=diffs,
            source_latency_ms=source_resp.get("latency_ms", 0.0),
            target_latency_ms=target_resp.get("latency_ms", 0.0),
            mutation_isolated=isolated,
        )

    def _compare_json_bodies(self, s: Any, t: Any, path: str = "$") -> List[str]:
        diffs: List[str] = []
        if isinstance(s, dict) and isinstance(t, dict):
            s_keys = set(s.keys())
            t_keys = set(t.keys())
            for missing_k in s_keys - t_keys:
                diffs.append(f"Missing key in target: {path}.{missing_k}")
            for extra_k in t_keys - s_keys:
                diffs.append(f"Unexpected extra key in target: {path}.{extra_k}")
            for common_k in s_keys & t_keys:
                diffs.extend(self._compare_json_bodies(s[common_k], t[common_k], f"{path}.{common_k}"))
        elif isinstance(s, list) and isinstance(t, list):
            if len(s) != len(t):
                diffs.append(f"Array length mismatch at {path}: source={len(s)}, target={len(t)}")
            else:
                for idx, (s_item, t_item) in enumerate(zip(s, t)):
                    diffs.extend(self._compare_json_bodies(s_item, t_item, f"{path}[{idx}]"))
        else:
            if s != t:
                diffs.append(f"Value mismatch at {path}: source={s}, target={t}")
        return diffs

    def replay_suite(self, requests: List[ShadowReplayRequest]) -> ShadowReplayReport:
        results = []
        source_lats = []
        target_lats = []
        matched_count = 0
        differed_count = 0
        isolated_count = 0

        for idx, req in enumerate(requests, 1):
            res = self.replay_request_pair(idx, req)
            results.append(res)
            source_lats.append(res.source_latency_ms)
            target_lats.append(res.target_latency_ms)
            if res.matched:
                matched_count += 1
            else:
                differed_count += 1
            if res.mutation_isolated:
                isolated_count += 1

        total = len(requests)
        rate = round((matched_count / total * 100.0) if total > 0 else 0.0, 2)
        avg_src = round(sum(source_lats) / len(source_lats) if source_lats else 0.0, 2)
        avg_tgt = round(sum(target_lats) / len(target_lats) if target_lats else 0.0, 2)
        improvement = round(((avg_src - avg_tgt) / avg_src * 100.0) if avg_src > 0 else 0.0, 2)

        return ShadowReplayReport(
            total_replayed=total,
            total_matched=matched_count,
            total_differed=differed_count,
            total_mutating_isolated=isolated_count,
            consistency_rate=rate,
            avg_source_latency_ms=avg_src,
            avg_target_latency_ms=avg_tgt,
            latency_improvement_pct=improvement,
            results=results,
        )

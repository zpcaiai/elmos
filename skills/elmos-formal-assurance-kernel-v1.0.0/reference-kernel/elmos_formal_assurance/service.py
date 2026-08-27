from __future__ import annotations
import json
from io import BytesIO
from typing import Callable
from . import __version__
from .models import AssuranceLevel, Criticality, ProofObligation, ProofResult, ProofStatus
from .gate import evaluate_release_gate

def _json_response(start_response: Callable, status: str, payload: dict):
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    start_response(status, [("Content-Type","application/json"),("Content-Length",str(len(body)))])
    return [body]

def application(environ: dict, start_response: Callable):
    path = environ.get("PATH_INFO", "/")
    method = environ.get("REQUEST_METHOD", "GET")
    if method == "GET" and path == "/livez":
        return _json_response(start_response, "200 OK", {"status":"live"})
    if method == "GET" and path == "/readyz":
        return _json_response(start_response, "200 OK", {"status":"ready","externalVerifiers":"not-required-for-kernel-readiness"})
    if method == "GET" and path == "/version":
        return _json_response(start_response, "200 OK", {"name":"elmos-formal-assurance-kernel","version":__version__})
    if method == "GET" and path == "/metrics":
        body = b"elmos_formal_assurance_kernel_ready 1\n"
        start_response("200 OK", [("Content-Type","text/plain; version=0.0.4"),("Content-Length",str(len(body)))])
        return [body]
    if method == "POST" and path == "/v1/gates/evaluate":
        try:
            length = int(environ.get("CONTENT_LENGTH") or "0")
            payload = json.loads(environ["wsgi.input"].read(length) or b"{}")
            obligations = [
                ProofObligation(
                    id=o["id"], criticality=Criticality(o["criticality"]),
                    property_kind=o["propertyKind"],
                    required_assurance=AssuranceLevel(o["requiredAssurance"]),
                    allow_bounded=o.get("allowBounded", False),
                    required=o.get("required", True),
                    dependencies=tuple(o.get("dependencies", [])),
                ) for o in payload.get("obligations", [])
            ]
            results = {
                r["obligationId"]: ProofResult(
                    obligation_id=r["obligationId"], status=ProofStatus(r["status"]),
                    assurance_level=AssuranceLevel(r["assuranceLevel"]),
                    mode=r["mode"], stale=r.get("stale", False),
                    bound=r.get("bound"), diagnostics=tuple(r.get("diagnostics", [])),
                ) for r in payload.get("results", [])
            }
            decision = evaluate_release_gate(
                obligations, results,
                required_gate=payload.get("requiredGate","E2_MODEL"),
                deployment_complete=payload.get("deploymentComplete",True),
            )
            return _json_response(start_response, "200 OK", {
                "decision":decision.decision,
                "blockingReasons":list(decision.blocking_reasons),
                "advisoryReasons":list(decision.advisory_reasons),
                "evaluatedCount":decision.evaluated_count,
            })
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            return _json_response(start_response, "400 Bad Request", {"error":str(exc)})
    return _json_response(start_response, "404 Not Found", {"error":"not found"})

def make_environ(path: str, method: str = "GET", payload: dict | None = None) -> dict:
    data = json.dumps(payload or {}).encode()
    return {"PATH_INFO":path,"REQUEST_METHOD":method,"CONTENT_LENGTH":str(len(data)),"wsgi.input":BytesIO(data)}

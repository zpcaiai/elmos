"""Small HTTP control-plane adapter with fail-closed request identity."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import unquote, urlparse

from .catalog import PACKAGE_ID, PACKAGE_VERSION, SKILL_SPECS
from .dispatcher import AutonomyRuntime, DispatchContext
from .errors import ContractError, KernelError
from .models import Status


class KernelHTTPServer(ThreadingHTTPServer):
    daemon_threads = True


def _catalog() -> list[dict[str, Any]]:
    return [{"name": spec.name, "priority": spec.priority, "capability_pack": spec.pack, "inputs": list(spec.inputs), "outputs": list(spec.outputs), "side_effects": spec.side_effects} for spec in SKILL_SPECS.values()]


def make_handler(runtime: AutonomyRuntime, *, require_verified_identity: bool = True):
    class Handler(BaseHTTPRequestHandler):
        server_version = "ElmosAutonomy/2.0"

        def log_message(self, format: str, *args: Any) -> None:
            # Applications should attach structured logs at the process boundary.
            return

        def _write(self, status: int, value: Any) -> None:
            body = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _identity(self) -> tuple[str, str] | None:
            tenant = self.headers.get("X-Elmos-Tenant-Id", "").strip()
            account = self.headers.get("X-Elmos-Account-Id", "").strip()
            verified = self.headers.get("X-Elmos-Identity-Verified", "").casefold() == "true"
            if not tenant or not account or (require_verified_identity and not verified):
                return None
            return tenant, account

        def _actor(self) -> str | None:
            actor = self.headers.get("X-Elmos-Actor-Id", "").strip()
            return actor or None

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path == "/livez":
                self._write(200, {"status": "ok"})
                return
            if path == "/readyz":
                try:
                    runtime.store.metrics()
                    if runtime.control_store is not runtime.store:
                        runtime.control_store.metrics()
                    self._write(
                        200,
                        {
                            "status": "ready",
                            "runtime_backend": "sqlite-local",
                            "control_backend": (
                                "external-control-store"
                                if runtime.control_store is not runtime.store
                                else "sqlite-local"
                            ),
                        },
                    )
                except Exception:  # noqa: BLE001 - readiness must degrade without exposing backend details
                    self._write(503, {"status": "not-ready"})
                return
            if path == "/version":
                self._write(200, {"package": PACKAGE_ID, "version": PACKAGE_VERSION})
                return
            if path == "/metrics":
                metrics = runtime.store.metrics()
                body = "\n".join(f'elmos_autonomy_{key} {value:g}' for key, value in sorted(metrics.items())) + ("\n" if metrics else "")
                raw = body.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; version=0.0.4")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return
            if path == "/v1/skills":
                self._write(200, {"skills": _catalog()})
                return
            if path == "/v2/certification/matrix":
                identity = self._identity()
                if identity is None:
                    self._write(401, {"error": {"code": "IDENTITY_REQUIRED"}})
                    return
                self._write(200, runtime.certification_matrix(tenant_id=identity[0]))
                return
            if path.startswith("/v2/external/operations/"):
                identity = self._identity()
                if identity is None:
                    self._write(401, {"error": {"code": "IDENTITY_REQUIRED"}})
                    return
                operation_id = unquote(path[len("/v2/external/operations/"):])
                try:
                    self._write(200, runtime.external.get(operation_id, tenant_id=identity[0]))
                except ContractError as exc:
                    self._write(404, {"error": exc.info.to_dict()})
                return
            run_prefix = "/v2/runs/" if path.startswith("/v2/runs/") else "/v1/runs/"
            if path.startswith(run_prefix) and path.endswith("/events"):
                identity = self._identity()
                if identity is None:
                    self._write(401, {"error": {"code": "IDENTITY_REQUIRED"}})
                    return
                run_id = unquote(path[len(run_prefix):-len("/events")])
                try:
                    self._write(200, {"events": runtime.store.events_since(run_id, tenant_id=identity[0])})
                except ContractError as exc:
                    self._write(404, {"error": exc.info.to_dict()})
                return
            if path.startswith(run_prefix):
                identity = self._identity()
                if identity is None:
                    self._write(401, {"error": {"code": "IDENTITY_REQUIRED"}})
                    return
                run_id = unquote(path[len(run_prefix):])
                value = runtime.store.get_run(run_id, tenant_id=identity[0])
                self._write(200 if value else 404, {"run": value} if value else {"error": {"code": "RUN_NOT_FOUND"}})
                return
            self._write(404, {"error": {"code": "NOT_FOUND"}})

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            identity = self._identity()
            if identity is None:
                self._write(401, {"error": {"code": "IDENTITY_REQUIRED", "message": "verified tenant/account headers are required"}})
                return
            try:
                if path == "/v2/runs":
                    payload = self._body()
                    result = runtime.execute("durable-run-orchestrator", payload, context=DispatchContext(tenant_id=identity[0], account_id=identity[1], store=runtime.store, tool_runtime=runtime.tool_runtime, policy_engine=runtime.policy_engine, trusted=True))
                    self._write(202 if result.status not in {Status.BLOCKED, Status.REJECTED} else 422, result.to_dict())
                    return
                if path == "/v2/external/operations":
                    payload = self._body()
                    payload["tenant_id"], payload["account_id"] = identity
                    planned = runtime.external.plan(payload)
                    self._write(202, planned)
                    return
                if path.startswith("/v2/external/operations/"):
                    parts = path.split("/")
                    if len(parts) == 6 and parts[5] in {"authorize", "execute", "reconcile", "compensate"}:
                        operation_id, action = unquote(parts[4]), parts[5]
                        payload = self._body()
                        if action == "authorize":
                            result = runtime.external.authorize(
                                operation_id, tenant_id=identity[0], grant=payload.get("grant", payload)
                            )
                        elif action == "execute":
                            result = runtime.external.execute(
                                operation_id, tenant_id=identity[0], payload=payload.get("payload"),
                                producer_id=str(payload.get("producer_id", "kernel-executor")),
                            )
                        elif action == "reconcile":
                            result = runtime.external.reconcile(
                                operation_id, tenant_id=identity[0],
                                verifier_id=str(payload.get("verifier_id", "")),
                            )
                        else:
                            result = runtime.external.compensate(
                                operation_id, tenant_id=identity[0],
                                producer_id=str(payload.get("producer_id", "kernel-executor")),
                            )
                        self._write(202, result)
                        return
                if path == "/v2/certification/evidence":
                    payload = self._body()
                    payload.setdefault("tenant_id", identity[0])
                    self._write(201, runtime.certification.ingest(tenant_id=identity[0], record=payload))
                    return
                if path == "/v2/certification/evaluate":
                    payload = self._body()
                    result = runtime.certification.evaluate(
                        tenant_id=identity[0], candidate_digest=str(payload.get("candidate_digest", "")),
                        release_context=payload.get("release_context", {}),
                    )
                    self._write(200 if result["p05"]["issued"] else 422, result)
                    return
                if path.startswith("/v2/golden-routes/") and path.endswith("/evaluate"):
                    route_id = unquote(path[len("/v2/golden-routes/"):-len("/evaluate")])
                    payload = self._body()
                    binding = dict(payload.get("binding", {}))
                    if binding.get("tenant_id") not in {None, identity[0]}:
                        raise ContractError("TENANT_SCOPE_DENIED", "repository binding tenant differs from identity")
                    binding["tenant_id"] = identity[0]
                    result = runtime.golden_routes.evaluate(
                        binding=binding, route_id=route_id,
                        candidate_digest=str(payload.get("candidate_digest", "")),
                        evidence=payload.get("evidence", {}),
                        executor_id=str(payload.get("executor_id", "")),
                    )
                    self._write(200 if result["status"] == "PASS" else 422, result)
                    return
                if path == "/v2/customer-acceptance":
                    actor = self._actor()
                    if actor is None:
                        raise ContractError("CUSTOMER_IDENTITY_REQUIRED", "verified customer actor header is required")
                    payload = self._body()
                    binding = dict(payload.get("binding", {}))
                    if binding.get("tenant_id") not in {None, identity[0]}:
                        raise ContractError("TENANT_SCOPE_DENIED", "repository binding tenant differs from identity")
                    binding["tenant_id"] = identity[0]
                    result = runtime.customer_acceptance.record(
                        binding=binding, route_id=str(payload.get("route_id", "")),
                        candidate_digest=str(payload.get("candidate_digest", "")),
                        executor_id=str(payload.get("executor_id", "")),
                        decision=payload.get("decision", {}), authenticated_customer_actor_id=actor,
                    )
                    self._write(201, result)
                    return
                if path.startswith("/v2/runs/") and path.rsplit("/", 1)[-1] in {"pause", "resume", "cancel"}:
                    parts = path.split("/")
                    run_id, action = unquote(parts[3]), parts[4]
                    targets = {"pause": "PAUSED", "resume": "EXECUTING", "cancel": "CANCEL_REQUESTED"}
                    run = runtime.store.transition_run(run_id, targets[action], event_type=f"{action.upper()}_REQUESTED", tenant_id=identity[0])
                    self._write(202, {"run": run})
                    return
                if path == "/v2/tool-calls":
                    payload = self._body()
                    result = runtime.execute("typed-tool-runtime", payload, context=DispatchContext(tenant_id=identity[0], account_id=identity[1], store=runtime.store, tool_runtime=runtime.tool_runtime, policy_engine=runtime.policy_engine, trusted=True))
                    self._write(202 if result.status not in {Status.BLOCKED, Status.REJECTED} else 422, result.to_dict())
                    return
                if path == "/v2/arena/runs":
                    result = runtime.execute("agent-arena", self._body(), context=DispatchContext(tenant_id=identity[0], account_id=identity[1], store=runtime.store, trusted=True))
                    self._write(202 if result.status != Status.BLOCKED else 422, result.to_dict())
                    return
                if path.startswith("/v2/gym/suites/") and path.endswith("/run"):
                    result = runtime.execute("repository-gym-golden-routes", self._body(), context=DispatchContext(tenant_id=identity[0], account_id=identity[1], store=runtime.store, trusted=True))
                    self._write(202 if result.status != Status.BLOCKED else 422, result.to_dict())
                    return
                if path == "/v2/packages":
                    result = runtime.execute("capability-package-registry", self._body(), context=DispatchContext(tenant_id=identity[0], account_id=identity[1], store=runtime.store, trusted=True))
                    self._write(201 if result.status != Status.BLOCKED else 422, result.to_dict())
                    return
                if path.startswith("/v2/adapters/") and path.endswith("/conformance"):
                    adapter_id = unquote(path[len("/v2/adapters/"):-len("/conformance")])
                    payload = self._body()
                    result = runtime.conformance(adapter_id, str(payload.get("adapter_version", "2.0.0")), payload.get("responses"))
                    self._write(202 if result["status"] != "BLOCKED" else 422, result)
                    return
            except KernelError as exc:
                self._write(422, {"error": exc.info.to_dict()})
                return
            except (ValueError, KeyError) as exc:
                error = {"code": "INVALID_INPUT", "message": str(exc)}
                self._write(422, {"error": error})
                return
            if not path.startswith("/v1/skills/") or not path.endswith(":run"):
                self._write(404, {"error": {"code": "NOT_FOUND"}})
                return
            skill = unquote(path[len("/v1/skills/"):-len(":run")])
            try:
                payload = self._body()
                result = runtime.execute(skill, payload, context=DispatchContext(tenant_id=identity[0], account_id=identity[1], store=runtime.store, tool_runtime=runtime.tool_runtime, policy_engine=runtime.policy_engine, trusted=True))
                self._write(200 if result.status not in {Status.BLOCKED, Status.REJECTED} else 422, result.to_dict())
            except json.JSONDecodeError:
                self._write(400, {"error": {"code": "INVALID_JSON"}})
            except ContractError as exc:
                self._write(400, {"error": exc.info.to_dict()})
            except ValueError as exc:
                self._write(400, {"error": {"code": "INVALID_INPUT", "message": str(exc)}})

        def _body(self) -> dict[str, Any]:
            size = int(self.headers.get("Content-Length", "0"))
            if size < 1 or size > 4 * 1024 * 1024:
                raise ContractError("INVALID_INPUT", "request body must be between 1 byte and 4 MiB")
            payload = json.loads(self.rfile.read(size))
            if not isinstance(payload, dict):
                raise ContractError("INVALID_INPUT", "request body must be an object")
            return payload

    return Handler


def serve(runtime: AutonomyRuntime, host: str = "127.0.0.1", port: int = 8080, *, require_verified_identity: bool = True) -> None:
    server = KernelHTTPServer((host, port), make_handler(runtime, require_verified_identity=require_verified_identity))
    try:
        server.serve_forever()
    finally:
        server.server_close()

"""Authenticated runtime gateway and optional FastAPI/ASGI adapter."""

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .errors import ContractViolation, NotConfigured, TenantIsolationError
from .firewall import FirewallContext
from .models import Budget, ExecutionManifest, Identity
from .plane import AdmissionLease, DurableAdmissionController, ResumableEventStream, SignedEventCursor
from .providers import RouteConstraints
from .runtime import RuntimeTurnInput
from .service import RuntimeControlPlane
from .workspace import WorkspaceLease


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    subject: str
    tenant_id: str
    project_ids: frozenset[str]
    roles: frozenset[str]
    authentication_context: str

    def __post_init__(self) -> None:
        if not self.subject or not self.tenant_id or not self.authentication_context:
            raise ContractViolation("authenticated principal is incomplete")


class AuthenticatedRuntimeGateway:
    """Derives tenant scope only from trusted authentication claims."""

    def __init__(
        self,
        control_plane: RuntimeControlPlane,
        events: ResumableEventStream,
        admission: DurableAdmissionController | None = None,
        *,
        workspace_resolver: Callable[[Identity], WorkspaceLease | None] | None = None,
        firewall_context_resolver: Callable[[Identity], FirewallContext] | None = None,
        route_constraints_resolver: Callable[[Identity, ExecutionManifest], RouteConstraints] | None = None,
    ) -> None:
        self.control_plane, self.events, self.admission = control_plane, events, admission
        self.workspace_resolver = workspace_resolver
        self.firewall_context_resolver = firewall_context_resolver
        self.route_constraints_resolver = route_constraints_resolver

    def create_run(self, principal: AuthenticatedPrincipal, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        self._require_role(principal, "runtime.create")
        identity = self._identity(principal, payload)
        manifest = _manifest(payload)
        self.control_plane.create_run(identity, manifest)
        return {"run_id": identity.run_id, "node_id": identity.node_id, "manifest_digest": manifest.digest}

    def turn(self, principal: AuthenticatedPrincipal, payload: Mapping[str, Any], *, window: str = "default") -> Mapping[str, Any]:
        self._require_role(principal, "runtime.turn")
        identity = self._identity(principal, payload)
        manifest = _manifest(payload)
        try:
            budget = Budget(**_object_field(payload, "budget", required=False))
        except TypeError as error:
            raise ContractViolation("budget does not match the v1 contract") from error
        context = _object_field(payload, "context", required=False)
        raw_tools = payload.get("tool_schemas", ())
        if isinstance(raw_tools, (str, bytes)) or not isinstance(raw_tools, (list, tuple)) or any(not isinstance(item, Mapping) for item in raw_tools):
            raise ContractViolation("tool_schemas must be an array of objects")
        admission: AdmissionLease | None = None
        if self.admission is not None:
            admission = self.admission.admit(identity, window=window)
            if admission.state != "active":
                return {"status": "queued", "admission_id": admission.admission_id}
        try:
            request = RuntimeTurnInput(
                identity, manifest, budget, context, tuple(dict(item) for item in raw_tools),
                route_constraints=None if self.route_constraints_resolver is None else self.route_constraints_resolver(identity, manifest),
                workspace=None if self.workspace_resolver is None else self.workspace_resolver(identity),
                firewall_context=None if self.firewall_context_resolver is None else self.firewall_context_resolver(identity),
                approval=payload.get("approval_id"), checkpoint=payload.get("checkpoint"),
                deadline_epoch=payload.get("deadline_epoch"),
            )
            result = self.control_plane.turn(request)
            controller = self.admission
            if admission is not None and controller is not None:
                controller.consume(admission, tokens=result.usage.input_tokens + result.usage.output_tokens, cost_micros=result.usage.cost_micros)
            return {"status": result.status, "event_seq": result.event_seq, "checkpoint_id": result.checkpoint_id, "reason": result.reason, "usage": result.usage.as_dict(), "observation": None if result.observation is None else result.observation.as_dict(), "completion": None if result.completion is None else {"run_id": result.completion.run_id, "summary": result.completion.summary, "claimed_status": result.completion.claimed_status}}
        finally:
            controller = self.admission
            if admission is not None and controller is not None:
                controller.release(admission)

    def resume(self, principal: AuthenticatedPrincipal, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        self._require_role(principal, "runtime.read")
        identity = self._identity(principal, payload)
        manifest = _manifest(payload)
        value = self.control_plane.resume(identity, manifest)
        return {"run": {"status": value["run"].status, "manifest_hash": value["run"].manifest_hash}, "checkpoint": value["checkpoint"], "projection": value["projection"]}

    def cancel(self, principal: AuthenticatedPrincipal, payload: Mapping[str, Any]) -> None:
        self._require_role(principal, "runtime.cancel")
        self.control_plane.cancel(self._identity(principal, payload), str(payload.get("reason", "")))

    def event_page(self, principal: AuthenticatedPrincipal, payload: Mapping[str, Any], *, cursor: SignedEventCursor | None = None, limit: int = 100) -> Mapping[str, Any]:
        self._require_role(principal, "runtime.read")
        if limit < 1 or limit > 1000:
            raise ContractViolation("event page limit must be in [1,1000]")
        identity = self._identity(principal, payload)
        events = self.events.read(identity, after_seq=-1, limit=limit) if cursor is None else self.events.resume(identity, cursor, limit=limit)
        after_seq = -1 if not events else events[-1].seq
        next_cursor = self.events.cursor(identity, after_seq=after_seq)
        return {"events": [event.as_dict() for event in events], "cursor": {"tenant_id": next_cursor.tenant_id, "project_id": next_cursor.project_id, "task_id": next_cursor.task_id, "run_id": next_cursor.run_id, "node_id": next_cursor.node_id, "after_seq": next_cursor.after_seq, "head_digest": next_cursor.head_digest, "signature": next_cursor.signature}}

    @staticmethod
    def _identity(principal: AuthenticatedPrincipal, payload: Mapping[str, Any]) -> Identity:
        claimed_tenant = payload.get("tenant_id")
        if claimed_tenant is not None and str(claimed_tenant) != principal.tenant_id:
            raise TenantIsolationError("request tenant does not match authenticated tenant")
        project_id = str(payload.get("project_id", ""))
        if project_id not in principal.project_ids:
            raise TenantIsolationError("project is not bound to authenticated principal")
        return Identity(principal.tenant_id, project_id, str(payload.get("task_id", "")), str(payload.get("run_id", "")), str(payload.get("node_id", "root")), principal.subject)

    @staticmethod
    def _require_role(principal: AuthenticatedPrincipal, role: str) -> None:
        if role not in principal.roles and "admin" not in principal.roles:
            raise TenantIsolationError("principal lacks required role: " + role)


def create_fastapi_app(gateway: AuthenticatedRuntimeGateway, authenticate: Callable[[Any], AuthenticatedPrincipal]) -> Any:
    """Create a real ASGI app when FastAPI is installed by the deployment."""

    try:
        from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
    except ImportError as error:  # pragma: no cover - optional production dependency
        raise NotConfigured("fastapi is required for the HTTP runtime gateway") from error

    app = FastAPI(title="ELMOS OpenHands Runtime Gateway", version="1.0.0", docs_url=None, redoc_url=None)

    def execute(request: Any, operation: Callable[[AuthenticatedPrincipal, Mapping[str, Any]], Any], payload: Mapping[str, Any]) -> Any:
        try:
            if not isinstance(payload, Mapping):
                raise ContractViolation("request body must be a JSON object")
            principal = authenticate(request)
            return operation(principal, payload)
        except TenantIsolationError as error:
            raise HTTPException(status_code=403, detail={"code": error.code, "message": str(error)}) from error
        except ContractViolation as error:
            raise HTTPException(status_code=400, detail={"code": error.code, "message": str(error)}) from error
        except (KeyError, TypeError, ValueError) as error:
            raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": "request body does not match the v1 contract"}) from error

    @app.post("/v1/runs")
    async def create_run(request: Request) -> Any:
        return execute(request, gateway.create_run, await request.json())

    @app.post("/v1/runs/{run_id}/turns")
    async def turn(run_id: str, request: Request) -> Any:
        payload = dict(await request.json())
        payload["run_id"] = run_id
        return execute(request, gateway.turn, payload)

    @app.post("/v1/runs/{run_id}/resume")
    async def resume(run_id: str, request: Request) -> Any:
        payload = dict(await request.json())
        payload["run_id"] = run_id
        return execute(request, gateway.resume, payload)

    @app.post("/v1/runs/{run_id}/cancel")
    async def cancel(run_id: str, request: Request) -> Any:
        payload = dict(await request.json())
        payload["run_id"] = run_id
        execute(request, gateway.cancel, payload)
        return {"status": "accepted"}

    @app.get("/v1/runs/{run_id}/events")
    async def events(run_id: str, project_id: str, task_id: str, request: Request, node_id: str = "root", limit: int = 100) -> Any:
        return execute(request, lambda principal, payload: gateway.event_page(principal, payload, limit=limit), {"run_id": run_id, "project_id": project_id, "task_id": task_id, "node_id": node_id})

    @app.websocket("/v1/runs/{run_id}/events/ws")
    async def event_socket(websocket: WebSocket, run_id: str) -> None:
        await websocket.accept()
        try:
            principal = authenticate(websocket)
            while True:
                payload = dict(await websocket.receive_json())
                payload["run_id"] = run_id
                raw_cursor = payload.pop("cursor", None)
                cursor = None if raw_cursor is None else SignedEventCursor(**dict(raw_cursor))
                page = gateway.event_page(principal, payload, cursor=cursor, limit=int(payload.pop("limit", 100)))
                await websocket.send_json(page)
        except WebSocketDisconnect:
            return
        except (TenantIsolationError, ContractViolation) as error:
            await websocket.send_json({"error": {"code": error.code, "message": str(error)}})
            await websocket.close(code=1008)
        except (KeyError, TypeError, ValueError):
            await websocket.send_json({"error": {"code": "INVALID_REQUEST", "message": "request body does not match the v1 contract"}})
            await websocket.close(code=1008)

    return app


def configure_grpc_server(server: Any, gateway: AuthenticatedRuntimeGateway, authenticate: Callable[[Any], AuthenticatedPrincipal]) -> Any:
    """Attach the versioned protobuf Struct gRPC service to an injected server."""

    try:
        import grpc
        from google.protobuf.json_format import MessageToDict, ParseDict
        from google.protobuf.struct_pb2 import Struct
    except ImportError as error:  # pragma: no cover - optional production dependency
        raise NotConfigured("grpcio and protobuf are required for the gRPC runtime gateway") from error

    def decode(value: bytes) -> Mapping[str, Any]:
        message = Struct()
        message.ParseFromString(value)
        payload = MessageToDict(message, preserving_proto_field_name=True)
        if not isinstance(payload, Mapping):
            raise ContractViolation("gRPC request body must be a protobuf Struct object")
        return dict(payload)

    def encode(value: Any) -> bytes:
        payload = json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str))
        if not isinstance(payload, Mapping):
            payload = {"value": payload}
        message = Struct()
        ParseDict(dict(payload), message)
        return bytes(message.SerializeToString(deterministic=True))

    def invoke(context: Any, operation: Callable[[AuthenticatedPrincipal, Mapping[str, Any]], Any], payload: Mapping[str, Any]) -> Any:
        try:
            return operation(authenticate(context), payload)
        except TenantIsolationError as error:
            context.abort(grpc.StatusCode.PERMISSION_DENIED, str(error))
        except ContractViolation as error:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except (KeyError, TypeError, ValueError):
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "request body does not match the v1 contract")

    def event_page(principal: AuthenticatedPrincipal, payload: Mapping[str, Any]) -> Any:
        body = dict(payload)
        raw_cursor = body.pop("cursor", None)
        cursor = None if raw_cursor is None else SignedEventCursor(**dict(raw_cursor))
        limit = int(body.pop("limit", 100))
        return gateway.event_page(principal, body, cursor=cursor, limit=limit)

    methods = {
        "CreateRun": grpc.unary_unary_rpc_method_handler(lambda request, context: invoke(context, gateway.create_run, request), request_deserializer=decode, response_serializer=encode),
        "Turn": grpc.unary_unary_rpc_method_handler(lambda request, context: invoke(context, gateway.turn, request), request_deserializer=decode, response_serializer=encode),
        "Resume": grpc.unary_unary_rpc_method_handler(lambda request, context: invoke(context, gateway.resume, request), request_deserializer=decode, response_serializer=encode),
        "Cancel": grpc.unary_unary_rpc_method_handler(lambda request, context: invoke(context, gateway.cancel, request) or {"status": "accepted"}, request_deserializer=decode, response_serializer=encode),
        "EventPage": grpc.unary_unary_rpc_method_handler(lambda request, context: invoke(context, event_page, request), request_deserializer=decode, response_serializer=encode),
    }
    server.add_generic_rpc_handlers((grpc.method_handlers_generic_handler("elmos.openhands.v1.RuntimeGateway", methods),))
    return server


def _object_field(payload: Mapping[str, Any], field: str, *, required: bool) -> dict[str, Any]:
    value = payload.get(field)
    if value is None and not required:
        return {}
    if not isinstance(value, Mapping):
        raise ContractViolation(f"{field} must be an object")
    return dict(value)


def _manifest(payload: Mapping[str, Any]) -> ExecutionManifest:
    try:
        return ExecutionManifest(**_object_field(payload, "manifest", required=True))
    except TypeError as error:
        raise ContractViolation("manifest does not match the v1 contract") from error

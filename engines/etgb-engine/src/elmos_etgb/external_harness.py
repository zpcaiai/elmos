"""Signed, tenant-bound transport for production ETGB harness adapters.

The source package declares external adapter names but cannot grant those
adapters authority.  This module supplies the repository-owned caller side of
that boundary: strict configuration, exact request binding, bounded HTTPS,
public-key verification, and content-addressed evidence.  It never accepts
inline credentials or treats an unsigned provider response as a test result.
"""

from __future__ import annotations

import json
import os
import re
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .adapters import EXTERNAL_ADAPTERS
from .attestation import AttestationError, load_json_object, verify_signed_record
from .canonical import canonical_json, digest_json
from .evidence import EvidenceStore


_DIGEST = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$")
_ENVIRONMENT_VARIABLE = re.compile(r"^[A-Z][A-Z0-9_]{1,127}$")
_TRANSIENT_HTTP = frozenset({408, 425, 429, 500, 502, 503, 504})
_CONTEXT_FIELDS = frozenset(
    {
        "tenant_id",
        "project_id",
        "task_id",
        "run_id",
        "case_run_id",
        "candidate_digest",
        "plan_digest",
        "case_digest",
        "environment_id",
        "authority_id",
        "owner_id",
        "fencing_token",
        "idempotency_key",
        "checkpoint_digest",
    }
)
_RESPONSE_PAYLOAD_FIELDS = frozenset(
    {
        "schema_version",
        "adapter",
        "request_digest",
        "bindings",
        "status",
        "oracle_results",
        "evidence",
        "cost",
        "silent_semantic_error",
        "failure_class",
        "retryable",
    }
)
_EXTERNAL_EVIDENCE_FIELDS = frozenset(
    {"manifest_digest", "artifact_digests", "environment_digest", "toolchain_digest", "raw_evidence_roles"}
)
_COST_FIELDS = frozenset({"token_input", "token_output", "credit_usd", "wall_clock_ms"})


class ExternalHarnessError(RuntimeError):
    """A fail-closed external Harness contract or transport failure."""

    def __init__(self, message: str, *, failure_class: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.failure_class = failure_class
        self.retryable = retryable


@dataclass(frozen=True)
class ExternalExecutionContext:
    """Trusted caller context applied to every case request."""

    tenant_id: str
    project_id: str
    task_id: str
    candidate_digest: str
    plan_digest: str
    environment_id: str
    authority_id: str
    owner_id: str
    fencing_token: int
    checkpoint_digest: str

    def __post_init__(self) -> None:
        for field in (
            "tenant_id",
            "project_id",
            "task_id",
            "environment_id",
            "authority_id",
            "owner_id",
        ):
            value = str(getattr(self, field))
            if not _IDENTIFIER.fullmatch(value):
                raise ValueError(f"{field} is not a bounded identifier")
        for field in ("candidate_digest", "plan_digest", "checkpoint_digest"):
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", str(getattr(self, field))):
                raise ValueError(f"{field} must be sha256:<64 hex>")
        if not isinstance(self.fencing_token, int) or isinstance(self.fencing_token, bool) or self.fencing_token < 1:
            raise ValueError("fencing_token must be a positive integer")

    def bind(self, *, run_id: str, case_id: str, case_digest: str, seed: int) -> dict[str, Any]:
        if not _IDENTIFIER.fullmatch(run_id):
            raise ValueError("run_id is not a bounded identifier")
        if not case_id or len(case_id.encode("utf-8")) > 256:
            raise ValueError("case_id is not bounded")
        if not re.fullmatch(r"[0-9a-f]{64}", case_digest):
            raise ValueError("case_digest must be 64 lowercase hex")
        case_run_id = "case-" + digest_json({"run_id": run_id, "case_id": case_id, "seed": seed})
        bound: dict[str, Any] = {
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "task_id": self.task_id,
            "run_id": run_id,
            "case_run_id": case_run_id,
            "candidate_digest": self.candidate_digest,
            "plan_digest": self.plan_digest,
            "case_digest": case_digest,
            "environment_id": self.environment_id,
            "authority_id": self.authority_id,
            "owner_id": self.owner_id,
            "fencing_token": self.fencing_token,
            "checkpoint_digest": self.checkpoint_digest,
        }
        bound["idempotency_key"] = "sha256:" + digest_json(bound)
        return bound


@dataclass(frozen=True)
class HarnessPolicy:
    request_timeout_seconds: float = 300.0
    max_attempts: int = 3
    initial_backoff_ms: int = 250
    max_request_bytes: int = 16 * 1024 * 1024
    max_response_bytes: int = 16 * 1024 * 1024
    allow_loopback_http: bool = False
    allow_environment_proxy: bool = False

    @classmethod
    def parse(cls, value: Mapping[str, Any]) -> "HarnessPolicy":
        allowed = {
            "request_timeout_seconds",
            "max_attempts",
            "initial_backoff_ms",
            "max_request_bytes",
            "max_response_bytes",
            "allow_loopback_http",
            "allow_environment_proxy",
        }
        unexpected = set(value) - allowed
        if unexpected:
            raise ValueError(f"unsupported Harness policy fields: {sorted(unexpected)}")
        policy = cls(
            request_timeout_seconds=float(value.get("request_timeout_seconds", 300.0)),
            max_attempts=int(value.get("max_attempts", 3)),
            initial_backoff_ms=int(value.get("initial_backoff_ms", 250)),
            max_request_bytes=int(value.get("max_request_bytes", 16 * 1024 * 1024)),
            max_response_bytes=int(value.get("max_response_bytes", 16 * 1024 * 1024)),
            allow_loopback_http=bool(value.get("allow_loopback_http", False)),
            allow_environment_proxy=bool(value.get("allow_environment_proxy", False)),
        )
        if not 1 <= policy.max_attempts <= 8:
            raise ValueError("max_attempts must be between 1 and 8")
        if not 1 <= policy.request_timeout_seconds <= 7200:
            raise ValueError("request_timeout_seconds must be between 1 and 7200")
        if not 0 <= policy.initial_backoff_ms <= 30_000:
            raise ValueError("initial_backoff_ms must be between 0 and 30000")
        for field in ("max_request_bytes", "max_response_bytes"):
            if not 1024 <= int(getattr(policy, field)) <= 64 * 1024 * 1024:
                raise ValueError(f"{field} must be between 1024 and 67108864")
        return policy


@dataclass(frozen=True)
class AdapterEndpoint:
    endpoint: str
    executor_id: str
    auth_token_env: str
    ca_bundle: Path | None = None
    client_cert: Path | None = None
    client_key_env: str | None = None


Transport = Callable[[AdapterEndpoint, bytes, Mapping[str, str], HarnessPolicy], Mapping[str, Any]]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


def _read_bounded(response: Any, limit: int) -> bytes:
    content_length = response.headers.get("Content-Length")
    if content_length is not None:
        try:
            if int(content_length) > limit:
                raise ExternalHarnessError("Harness response exceeds configured limit", failure_class="security/policy")
        except ValueError as exc:
            raise ExternalHarnessError("Harness Content-Length is invalid", failure_class="harness/protocol") from exc
    data = response.read(limit + 1)
    if len(data) > limit:
        raise ExternalHarnessError("Harness response exceeds configured limit", failure_class="security/policy")
    return data


def _ssl_context(endpoint: AdapterEndpoint, environ: Mapping[str, str]) -> ssl.SSLContext:
    context = ssl.create_default_context(cafile=str(endpoint.ca_bundle) if endpoint.ca_bundle else None)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    if endpoint.client_cert is not None:
        key_path = environ.get(str(endpoint.client_key_env)) if endpoint.client_key_env else None
        if not key_path:
            raise ExternalHarnessError("mTLS client key environment reference is unset", failure_class="security/policy")
        private_key = Path(key_path)
        if private_key.is_symlink() or not private_key.is_file():
            raise ExternalHarnessError("mTLS client key must resolve to a regular file", failure_class="security/policy")
        context.load_cert_chain(str(endpoint.client_cert), str(private_key.resolve(strict=True)))
    return context


class HttpJsonTransport:
    """Bounded JSON-over-HTTP transport with redirects and ambient proxy off by default."""

    def __init__(self, environ: Mapping[str, str] | None = None) -> None:
        self.environ = environ if environ is not None else os.environ

    def __call__(self, endpoint: AdapterEndpoint, body: bytes, headers: Mapping[str, str], policy: HarnessPolicy) -> Mapping[str, Any]:
        handlers: list[Any] = [_NoRedirect()]
        if not policy.allow_environment_proxy:
            handlers.append(urllib.request.ProxyHandler({}))
        parsed = urllib.parse.urlsplit(endpoint.endpoint)
        if parsed.scheme == "https":
            handlers.append(urllib.request.HTTPSHandler(context=_ssl_context(endpoint, self.environ)))
        opener = urllib.request.build_opener(*handlers)
        request = urllib.request.Request(endpoint.endpoint, data=body, headers=dict(headers), method="POST")
        try:
            with opener.open(request, timeout=policy.request_timeout_seconds) as response:
                status = int(response.status)
                if status != 200:
                    raise ExternalHarnessError(f"Harness returned HTTP {status}", failure_class="environment/dependency", retryable=status in _TRANSIENT_HTTP)
                raw = _read_bounded(response, policy.max_response_bytes)
        except urllib.error.HTTPError as exc:
            raise ExternalHarnessError(f"Harness returned HTTP {exc.code}", failure_class="environment/dependency", retryable=exc.code in _TRANSIENT_HTTP) from exc
        except (urllib.error.URLError, TimeoutError, socket.timeout, ConnectionError) as exc:
            raise ExternalHarnessError(f"Harness transport failed: {type(exc).__name__}", failure_class="environment/dependency", retryable=True) from exc
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ExternalHarnessError("Harness response is not canonical JSON data", failure_class="harness/protocol") from exc
        if not isinstance(value, Mapping):
            raise ExternalHarnessError("Harness response must be a JSON object", failure_class="harness/protocol")
        return value


def _regular_path(base: Path, value: Any, *, field: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a path string")
    candidate = Path(value)
    path = candidate if candidate.is_absolute() else base / candidate
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{field} must resolve to a regular file")
    return path.resolve(strict=True)


def _validate_endpoint(value: Any, *, allow_loopback_http: bool) -> str:
    if not isinstance(value, str) or len(value.encode("utf-8")) > 2048:
        raise ValueError("adapter endpoint must be a bounded URL")
    parsed = urllib.parse.urlsplit(value)
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError("adapter endpoint contains an invalid port") from exc
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("adapter endpoint cannot contain credentials, query, or fragment")
    if not parsed.hostname:
        raise ValueError("adapter endpoint must include an exact host")
    if parsed.scheme == "http":
        if not allow_loopback_http or parsed.hostname not in {"127.0.0.1", "::1", "localhost"}:
            raise ValueError("plain HTTP is limited to explicitly enabled loopback tests")
    elif parsed.scheme != "https":
        raise ValueError("adapter endpoint must use HTTPS")
    if not parsed.path or parsed.path == "/":
        raise ValueError("adapter endpoint must include an exact API path")
    return value


def _adapter_endpoint(value: Any, *, base: Path, policy: HarnessPolicy) -> AdapterEndpoint:
    if not isinstance(value, Mapping):
        raise ValueError("adapter configuration must be an object")
    allowed = {"endpoint", "executor_id", "auth_token_env", "ca_bundle", "client_cert", "client_key_env"}
    required = {"endpoint", "executor_id", "auth_token_env"}
    if set(value) - allowed or required - set(value):
        raise ValueError(f"adapter configuration fields mismatch; missing={sorted(required - set(value))}, unexpected={sorted(set(value) - allowed)}")
    executor_id = str(value["executor_id"])
    auth_token_env = str(value["auth_token_env"])
    if not _IDENTIFIER.fullmatch(executor_id):
        raise ValueError("executor_id is not a bounded identifier")
    if not _ENVIRONMENT_VARIABLE.fullmatch(auth_token_env):
        raise ValueError("auth_token_env must name an uppercase environment variable")
    client_key_env = str(value["client_key_env"]) if value.get("client_key_env") is not None else None
    if client_key_env is not None and not _ENVIRONMENT_VARIABLE.fullmatch(client_key_env):
        raise ValueError("client_key_env must name an uppercase environment variable")
    client_cert = _regular_path(base, value["client_cert"], field="client_cert") if value.get("client_cert") else None
    if (client_cert is None) != (client_key_env is None):
        raise ValueError("client_cert and client_key_env must be supplied together")
    return AdapterEndpoint(
        endpoint=_validate_endpoint(value["endpoint"], allow_loopback_http=policy.allow_loopback_http),
        executor_id=executor_id,
        auth_token_env=auth_token_env,
        ca_bundle=_regular_path(base, value["ca_bundle"], field="ca_bundle") if value.get("ca_bundle") else None,
        client_cert=client_cert,
        client_key_env=client_key_env,
    )


class ExternalHarnessRouter:
    """Route exact ETGB external adapter names through independently signed workers."""

    def __init__(
        self,
        *,
        endpoints: Mapping[str, AdapterEndpoint],
        trust_store: Mapping[str, Any],
        policy: HarnessPolicy,
        config_digest: str,
        transport: Transport | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        unknown = set(endpoints) - EXTERNAL_ADAPTERS
        if unknown:
            raise ValueError(f"unknown external Harness adapters: {sorted(unknown)}")
        keys = trust_store.get("keys")
        if trust_store.get("schema_version") != "1.0" or not isinstance(keys, list) or not keys:
            raise ValueError("Harness trust store must contain a non-empty keys list")
        key_ids = [item.get("key_id") for item in keys if isinstance(item, Mapping)]
        if len(key_ids) != len(keys) or len(key_ids) != len(set(key_ids)):
            raise ValueError("Harness trust store key identities must be complete and unique")
        self.endpoints = dict(endpoints)
        self.trust_store = dict(trust_store)
        self.policy = policy
        self.config_digest = config_digest
        self.environ = environ if environ is not None else os.environ
        self.transport = transport or HttpJsonTransport(self.environ)

    @classmethod
    def load(
        cls,
        path: Path,
        *,
        transport: Transport | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> "ExternalHarnessRouter":
        if path.is_symlink() or not path.is_file():
            raise ValueError("Harness configuration must be a regular file")
        resolved = path.resolve(strict=True)
        try:
            document = json.loads(resolved.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("Harness configuration must be a JSON object") from exc
        if not isinstance(document, Mapping):
            raise ValueError("Harness configuration must be a JSON object")
        allowed = {"schema_version", "trust_store", "policy", "adapters"}
        if set(document) != allowed or document.get("schema_version") != "1.0":
            raise ValueError("Harness configuration requires exact schema_version, trust_store, policy, and adapters fields")
        policy_value = document.get("policy")
        adapters_value = document.get("adapters")
        if not isinstance(policy_value, Mapping) or not isinstance(adapters_value, Mapping) or not adapters_value:
            raise ValueError("Harness policy and non-empty adapters map are required")
        policy = HarnessPolicy.parse(policy_value)
        base = resolved.parent
        trust_path = _regular_path(base, document["trust_store"], field="trust_store")
        try:
            trust_store = load_json_object(trust_path)
        except AttestationError as exc:
            raise ValueError(str(exc)) from exc
        endpoints = {str(key): _adapter_endpoint(value, base=base, policy=policy) for key, value in adapters_value.items()}
        return cls(
            endpoints=endpoints,
            trust_store=trust_store,
            policy=policy,
            config_digest="sha256:" + digest_json(document),
            transport=transport,
            environ=environ,
        )

    def capability_report(self) -> dict[str, Any]:
        missing = sorted(EXTERNAL_ADAPTERS - set(self.endpoints))
        return {
            "schema_version": "1.0",
            "status": "READY_FOR_EXTERNAL_EXECUTION_CONFIG" if not missing else "BLOCKED",
            "configured_adapters": sorted(self.endpoints),
            "missing_adapters": missing,
            "config_digest": self.config_digest,
            "transport": "signed-json-https-v1",
            "trusted_public_key_count": len(self.trust_store.get("keys", [])),
            "private_keys_loaded": False,
            "certification_status": "NOT_CERTIFIED",
        }

    def _request(self, *, adapter: str, case: Mapping[str, Any], run_id: str, seed: int, context: ExternalExecutionContext) -> dict[str, Any]:
        case_digest = digest_json(case)
        request: dict[str, Any] = {
            "schema_version": "1.0",
            "request_type": "etgb-external-case-execution",
            "adapter": adapter,
            "case": dict(case),
            "seed": seed,
            "context": context.bind(run_id=run_id, case_id=str(case["id"]), case_digest=case_digest, seed=seed),
        }
        request["request_digest"] = "sha256:" + digest_json(request)
        return request

    def _verify_response(self, *, endpoint: AdapterEndpoint, request: Mapping[str, Any], record: Mapping[str, Any]) -> tuple[str, list[dict[str, Any]], dict[str, Any], bool]:
        verification = verify_signed_record(record, self.trust_store, record_type="adapter-execution")
        if not verification["valid"]:
            raise ExternalHarnessError("signed Harness response verification failed: " + "; ".join(verification["errors"]), failure_class="evidence/integrity")
        if record.get("issuer_id") != endpoint.executor_id:
            raise ExternalHarnessError("Harness response issuer does not match configured executor", failure_class="security/policy")
        payload = record.get("payload")
        if not isinstance(payload, Mapping) or set(payload) != _RESPONSE_PAYLOAD_FIELDS:
            raise ExternalHarnessError("Harness response payload fields do not match protocol v1", failure_class="harness/protocol")
        if payload.get("schema_version") != "1.0" or payload.get("adapter") != request.get("adapter"):
            raise ExternalHarnessError("Harness response adapter/schema binding mismatch", failure_class="harness/protocol")
        if payload.get("request_digest") != request.get("request_digest"):
            raise ExternalHarnessError("Harness response request digest mismatch", failure_class="evidence/integrity")
        bindings = payload.get("bindings")
        expected_bindings = request.get("context")
        if not isinstance(bindings, Mapping) or set(bindings) != _CONTEXT_FIELDS or dict(bindings) != expected_bindings:
            raise ExternalHarnessError("Harness response execution context mismatch", failure_class="security/policy")
        status = payload.get("status")
        if status not in {"passed", "failed", "error", "unavailable"}:
            raise ExternalHarnessError("Harness response status is unsupported", failure_class="harness/protocol")
        raw_oracles = payload.get("oracle_results")
        if not isinstance(raw_oracles, list) or not raw_oracles or any(not isinstance(item, Mapping) for item in raw_oracles):
            raise ExternalHarnessError("Harness response requires oracle results", failure_class="harness/protocol")
        oracles = [dict(item) for item in raw_oracles]
        for oracle in oracles:
            if not isinstance(oracle.get("type"), str) or not isinstance(oracle.get("critical"), bool) or not isinstance(oracle.get("passed"), bool):
                raise ExternalHarnessError("Harness oracle result has an invalid contract", failure_class="harness/protocol")
        if status == "passed" and any(item["critical"] and not item["passed"] for item in oracles):
            raise ExternalHarnessError("Harness reported passed with a failed critical oracle", failure_class="harness/oracle defect")
        evidence = payload.get("evidence")
        if not isinstance(evidence, Mapping) or set(evidence) != _EXTERNAL_EVIDENCE_FIELDS:
            raise ExternalHarnessError("Harness response evidence fields do not match protocol v1", failure_class="harness/protocol")
        manifest_digest = evidence.get("manifest_digest")
        artifact_digests = evidence.get("artifact_digests")
        if not isinstance(manifest_digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", manifest_digest):
            raise ExternalHarnessError("Harness evidence manifest digest is invalid", failure_class="evidence/integrity")
        if not isinstance(artifact_digests, list) or not artifact_digests or any(not isinstance(item, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", item) for item in artifact_digests):
            raise ExternalHarnessError("Harness evidence artifact digests are invalid", failure_class="evidence/integrity")
        for field in ("environment_digest", "toolchain_digest"):
            if not isinstance(evidence.get(field), str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", evidence[field]):
                raise ExternalHarnessError(f"Harness evidence {field} is invalid", failure_class="evidence/integrity")
        raw_roles = evidence.get("raw_evidence_roles")
        if not isinstance(raw_roles, list) or not raw_roles or len(raw_roles) != len(set(raw_roles)) or any(not isinstance(item, str) or not _IDENTIFIER.fullmatch(item) for item in raw_roles):
            raise ExternalHarnessError("Harness raw evidence roles are invalid", failure_class="evidence/integrity")
        cost = payload.get("cost")
        if not isinstance(cost, Mapping) or set(cost) != _COST_FIELDS or any(not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0 for value in cost.values()):
            raise ExternalHarnessError("Harness cost must contain non-negative numeric values", failure_class="harness/protocol")
        if not isinstance(payload.get("silent_semantic_error"), bool) or not isinstance(payload.get("retryable"), bool):
            raise ExternalHarnessError("Harness semantic/retry flags must be boolean", failure_class="harness/protocol")
        if payload.get("failure_class") is not None and not isinstance(payload.get("failure_class"), str):
            raise ExternalHarnessError("Harness failure_class must be a string or null", failure_class="harness/protocol")
        return status, oracles, {
            "signed_response": dict(record),
            "verification": verification,
            "external_evidence": dict(evidence),
            "external_cost": dict(cost),
            "external_failure_class": payload.get("failure_class"),
            "external_retryable": payload.get("retryable"),
        }, bool(payload["silent_semantic_error"])

    def execute(
        self,
        *,
        adapter: str,
        case: Mapping[str, Any],
        run_id: str,
        seed: int,
        context: ExternalExecutionContext,
        store: EvidenceStore | None,
    ) -> tuple[str, list[dict[str, Any]], dict[str, Any], bool]:
        endpoint = self.endpoints.get(adapter)
        if endpoint is None:
            raise ExternalHarnessError(f"external adapter is not configured: {adapter}", failure_class="environment/dependency")
        token = self.environ.get(endpoint.auth_token_env)
        if not token or len(token.encode("utf-8")) > 16_384:
            raise ExternalHarnessError("Harness authentication token reference is unset or invalid", failure_class="security/policy")
        request = self._request(adapter=adapter, case=case, run_id=run_id, seed=seed, context=context)
        body = canonical_json(request)
        if len(body) > self.policy.max_request_bytes:
            raise ExternalHarnessError("Harness request exceeds configured limit", failure_class="security/policy")
        headers = {
            "Accept": "application/json",
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
            "Idempotency-Key": str(request["context"]["idempotency_key"]),
            "X-ETGB-Request-Digest": str(request["request_digest"]),
        }
        last_error: ExternalHarnessError | None = None
        for attempt in range(1, self.policy.max_attempts + 1):
            try:
                record = self.transport(endpoint, body, headers, self.policy)
                status, oracles, evidence, silent = self._verify_response(endpoint=endpoint, request=request, record=record)
                artifacts: list[dict[str, Any]] = []
                if store is not None:
                    artifacts.extend(
                        [
                            store.put_json(request, role="external-harness-request"),
                            store.put_json(record, role="external-harness-signed-response"),
                            store.put_json(evidence["verification"], role="external-harness-signature-verification"),
                        ]
                    )
                evidence.update(
                    {
                        "artifacts": artifacts,
                        "external_harness": {
                            "adapter": adapter,
                            "executor_id": endpoint.executor_id,
                            "request_digest": request["request_digest"],
                            "config_digest": self.config_digest,
                            "attempts": attempt,
                            "signature_valid": True,
                        },
                    }
                )
                return status, oracles, evidence, silent
            except ExternalHarnessError as exc:
                last_error = exc
                if not exc.retryable or attempt >= self.policy.max_attempts:
                    raise
                delay = min(self.policy.initial_backoff_ms * (2 ** (attempt - 1)), 30_000) / 1000.0
                if delay:
                    time.sleep(delay)
        raise last_error or ExternalHarnessError("Harness execution failed", failure_class="environment/dependency")

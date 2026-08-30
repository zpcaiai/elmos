"""Command-line entrypoint for local compilation, invocation, and HTTP serving."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import importlib
import json
import os
from pathlib import Path
import stat
import unicodedata
import sys
from typing import Any, Sequence, cast

from .architecture import ArchitectureExtractor
from .control_plane import DurableControlPlane
from .postgres import PostgresStore
from .repository import RepositorySnapshotter, SnapshotLimits
from .runtime_assurance import RuntimeAssuranceControlPlane
from .semantic import SemanticCompiler
from .service import (
    AuthPrincipal,
    Authenticator,
    FileJwksAuthenticator,
    HarnessService,
    serve,
)
from .skills import COMPONENT_REGISTRY, SKILL_REGISTRY, SkillRuntime
from .storage import ControlPlaneStore
from .store import SQLiteStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="elmos-proof-harness",
        description="Proof-driven repository semantic compiler and harness",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    snapshot = subparsers.add_parser(
        "snapshot", help="create a safe read-only repository evidence graph"
    )
    snapshot.add_argument("repository")
    _add_snapshot_limits(snapshot)

    compile_parser = subparsers.add_parser(
        "compile", help="compile source-linked semantic and architecture IR"
    )
    compile_parser.add_argument("repository")
    compile_parser.add_argument(
        "--architecture-format", choices=("json", "calm", "rows"), default="json"
    )
    _add_snapshot_limits(compile_parser)

    subparsers.add_parser("list-skills", help="list the 16 exact routable Skills")
    subparsers.add_parser("list-components", help="list the 96 exact kernel components")

    invoke = subparsers.add_parser("invoke", help="invoke one exact Skill locally")
    invoke.add_argument("skill", choices=tuple(sorted(SKILL_REGISTRY)))
    payload_group = invoke.add_mutually_exclusive_group(required=True)
    payload_group.add_argument("--payload", help="JSON object")
    payload_group.add_argument("--payload-file", help="path to a JSON object")
    invoke.add_argument("--workspace-root", action="append", default=[])
    invoke.add_argument("--authority", action="append", default=[])

    server = subparsers.add_parser("serve", help="serve authenticated v3 HTTP APIs")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8080)
    server.add_argument("--auth-token-env", default="ELMOS_PROOF_HARNESS_TOKEN")
    server.add_argument(
        "--runtime-mode",
        choices=("local-engineering", "production"),
        default=os.environ.get("ELMOS_RUNTIME_MODE", "production"),
    )
    server.add_argument("--state-db", default=os.environ.get("ELMOS_PROOF_HARNESS_DB"))
    server.add_argument("--postgres-dsn-env", default="ELMOS_POSTGRES_DSN")
    server.add_argument(
        "--authenticator-factory", default=os.environ.get("ELMOS_AUTHENTICATOR_FACTORY")
    )
    server.add_argument(
        "--runtime-assurance-factory",
        default=os.environ.get("ELMOS_RUNTIME_ASSURANCE_FACTORY"),
    )
    server.add_argument("--jwks-file", default=os.environ.get("ELMOS_AUTH_JWKS_FILE"))
    server.add_argument(
        "--jwt-algorithm", default=os.environ.get("ELMOS_AUTH_JWT_ALGORITHM", "RS256")
    )
    server.add_argument(
        "--jwks-refresh-seconds",
        type=int,
        default=int(os.environ.get("ELMOS_AUTH_JWKS_REFRESH_SECONDS", "300")),
    )
    server.add_argument(
        "--jwt-leeway-seconds",
        type=int,
        default=int(os.environ.get("ELMOS_AUTH_JWT_LEEWAY_SECONDS", "30")),
    )
    server.add_argument(
        "--expected-issuer", default=os.environ.get("ELMOS_AUTH_EXPECTED_ISSUER")
    )
    server.add_argument(
        "--expected-audience", default=os.environ.get("ELMOS_AUTH_EXPECTED_AUDIENCE")
    )
    server.add_argument(
        "--transport-mode",
        choices=("local", "tls", "trusted-proxy"),
        default=os.environ.get("ELMOS_TRANSPORT_MODE"),
    )
    server.add_argument(
        "--tls-cert-file", default=os.environ.get("ELMOS_TLS_CERT_FILE")
    )
    server.add_argument("--tls-key-file", default=os.environ.get("ELMOS_TLS_KEY_FILE"))
    server.add_argument(
        "--tls-client-ca-file", default=os.environ.get("ELMOS_TLS_CLIENT_CA_FILE")
    )
    server.add_argument(
        "--trusted-proxy-cidr",
        action="append",
        default=_csv_env("ELMOS_TRUSTED_PROXY_CIDRS"),
    )
    server.add_argument(
        "--request-timeout-seconds",
        type=float,
        default=float(os.environ.get("ELMOS_HTTP_REQUEST_TIMEOUT_SECONDS", "30")),
    )
    server.add_argument(
        "--max-concurrent-requests",
        type=int,
        default=int(os.environ.get("ELMOS_HTTP_MAX_CONCURRENT_REQUESTS", "64")),
    )
    server.add_argument(
        "--graceful-shutdown-seconds",
        type=float,
        default=float(os.environ.get("ELMOS_HTTP_GRACEFUL_SHUTDOWN_SECONDS", "30")),
    )
    server.add_argument("--tenant-id", default=os.environ.get("ELMOS_TENANT_ID"))
    server.add_argument("--project-id", default=os.environ.get("ELMOS_PROJECT_ID"))
    server.add_argument("--actor-id", default=os.environ.get("ELMOS_ACTOR_ID"))
    server.add_argument(
        "--authentication-context-digest",
        default=os.environ.get("ELMOS_AUTHENTICATION_CONTEXT_DIGEST"),
    )
    server.add_argument("--authority-id", default=os.environ.get("ELMOS_AUTHORITY_ID"))
    server.add_argument(
        "--authority-revision", default=os.environ.get("ELMOS_AUTHORITY_REVISION")
    )
    server.add_argument(
        "--environment-id", default=os.environ.get("ELMOS_ENVIRONMENT_ID")
    )
    server.add_argument(
        "--environment-revision", default=os.environ.get("ELMOS_ENVIRONMENT_REVISION")
    )
    server.add_argument(
        "--execution-epoch",
        type=int,
        default=_optional_int_env("ELMOS_EXECUTION_EPOCH"),
    )
    server.add_argument(
        "--fencing-generation",
        type=int,
        default=_optional_int_env("ELMOS_FENCING_GENERATION"),
    )
    server.add_argument(
        "--authority-expires-at", default=os.environ.get("ELMOS_AUTHORITY_EXPIRES_AT")
    )
    server.add_argument(
        "--authority", action="append", default=_csv_env("ELMOS_PROOF_HARNESS_SCOPES")
    )
    server.add_argument("--workspace-root", action="append", default=[])
    server.add_argument("--max-request-bytes", type=int, default=2 * 1024 * 1024)
    server.add_argument("--lease-ttl-seconds", type=int, default=300)
    server.add_argument(
        "--owner-id",
        default=os.environ.get(
            "ELMOS_PROOF_HARNESS_OWNER_ID", "proof-harness-control-plane"
        ),
    )
    server.add_argument("--allow-legacy-local", action="store_true")
    return parser


def _optional_int_env(name: str) -> int | None:
    value = os.environ.get(name)
    return int(value) if value is not None else None


def _csv_env(name: str) -> list[str]:
    value = os.environ.get(name, "")
    return [item.strip() for item in value.split(",") if item.strip()]


def _add_snapshot_limits(parser: argparse.ArgumentParser) -> None:
    defaults = SnapshotLimits()
    parser.add_argument("--max-files", type=int, default=defaults.max_files)
    parser.add_argument("--max-directories", type=int, default=defaults.max_directories)
    parser.add_argument("--max-total-bytes", type=int, default=defaults.max_total_bytes)
    parser.add_argument("--max-file-bytes", type=int, default=defaults.max_file_bytes)
    parser.add_argument("--max-depth", type=int, default=defaults.max_depth)


def _limits(arguments: argparse.Namespace) -> SnapshotLimits:
    return SnapshotLimits(
        max_files=arguments.max_files,
        max_directories=arguments.max_directories,
        max_total_bytes=arguments.max_total_bytes,
        max_file_bytes=arguments.max_file_bytes,
        max_depth=arguments.max_depth,
    )


def _load_payload(arguments: argparse.Namespace) -> dict[str, Any]:
    if arguments.payload is not None:
        raw = arguments.payload
    else:
        path = Path(arguments.payload_file)
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(path, flags)
        except OSError as exc:
            raise ValueError("payload file is unavailable or unsafe") from exc
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 2 * 1024 * 1024:
                raise ValueError(
                    "payload file is not a regular file within the 2 MiB limit"
                )
            chunks: list[bytes] = []
            remaining = metadata.st_size
            while remaining:
                chunk = os.read(descriptor, min(64 * 1024, remaining))
                if not chunk:
                    raise ValueError("payload file changed during read")
                chunks.append(chunk)
                remaining -= len(chunk)
            if os.read(descriptor, 1):
                raise ValueError("payload file grew during read")
            after = os.fstat(descriptor)
            if (
                metadata.st_dev,
                metadata.st_ino,
                metadata.st_size,
                metadata.st_mtime_ns,
                metadata.st_ctime_ns,
            ) != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            ):
                raise ValueError("payload file changed during read")
            raw = b"".join(chunks).decode("utf-8")
        finally:
            os.close(descriptor)
    value = json.loads(
        raw, object_pairs_hook=_strict_json_object, parse_constant=_reject_json_constant
    )
    if not isinstance(value, dict):
        raise ValueError("payload must be a JSON object")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "snapshot":
            graph = RepositorySnapshotter(
                arguments.repository, limits=_limits(arguments)
            ).snapshot()
            _print_json(graph.to_dict())
        elif arguments.command == "compile":
            graph = RepositorySnapshotter(
                arguments.repository, limits=_limits(arguments)
            ).snapshot()
            semantic = SemanticCompiler().compile(graph)
            architecture = ArchitectureExtractor().extract(graph, semantic)
            if arguments.architecture_format == "calm":
                architecture_value: Any = architecture.to_calm()
            elif arguments.architecture_format == "rows":
                architecture_value = architecture.graph_rows()
            else:
                architecture_value = architecture.to_dict()
            _print_json(
                {
                    "repository": graph.to_dict(),
                    "semantic": semantic.to_dict(),
                    "architecture": architecture_value,
                }
            )
        elif arguments.command == "list-skills":
            _print_json(
                {
                    "skills": [
                        SKILL_REGISTRY[name].to_dict()
                        for name in sorted(SKILL_REGISTRY)
                    ]
                }
            )
        elif arguments.command == "list-components":
            _print_json(
                {
                    "components": [
                        COMPONENT_REGISTRY[name].to_dict()
                        for name in sorted(COMPONENT_REGISTRY)
                    ]
                }
            )
        elif arguments.command == "invoke":
            runtime = SkillRuntime(workspace_roots=arguments.workspace_root)
            result = runtime.execute(
                arguments.skill,
                _load_payload(arguments),
                context={"authority": arguments.authority},
            )
            _print_json(result.to_dict())
            return 0 if result.status not in {"BLOCKED", "FAILED", "DENIED"} else 2
        elif arguments.command == "serve":
            runtime = SkillRuntime(workspace_roots=arguments.workspace_root)
            store: ControlPlaneStore
            runtime_assurance: RuntimeAssuranceControlPlane | None = None
            if arguments.runtime_mode == "production":
                if arguments.state_db:
                    raise ValueError(
                        "--state-db is local-engineering only; production requires PostgreSQL"
                    )
                required_production = {
                    "expected issuer": arguments.expected_issuer,
                    "expected audience": arguments.expected_audience,
                    "transport mode": arguments.transport_mode,
                    "runtime assurance factory": arguments.runtime_assurance_factory,
                }
                missing = [
                    name
                    for name, value in required_production.items()
                    if value in {None, ""}
                ]
                if missing:
                    raise ValueError(
                        "missing required production serve configuration: "
                        + ", ".join(missing)
                    )
                auth_sources = sum(
                    value not in {None, ""}
                    for value in (
                        arguments.authenticator_factory,
                        arguments.jwks_file,
                    )
                )
                if auth_sources != 1:
                    raise ValueError(
                        "production requires exactly one authenticator factory or JWKS file"
                    )
                authenticator: Authenticator
                if arguments.jwks_file:
                    authenticator = FileJwksAuthenticator(
                        arguments.jwks_file,
                        issuer=arguments.expected_issuer,
                        audience=arguments.expected_audience,
                        algorithm=arguments.jwt_algorithm,
                        refresh_seconds=arguments.jwks_refresh_seconds,
                        leeway_seconds=arguments.jwt_leeway_seconds,
                    )
                else:
                    authenticator = _load_authenticator(arguments.authenticator_factory)
                postgres_store = PostgresStore.from_environment(
                    variable=arguments.postgres_dsn_env
                )
                store = postgres_store
                runtime_assurance = _load_runtime_assurance(
                    arguments.runtime_assurance_factory,
                    postgres_store,
                )
                service_arguments: dict[str, Any] = {
                    "authenticator": authenticator,
                    "expected_issuer": arguments.expected_issuer,
                    "expected_audience": arguments.expected_audience,
                }
            else:
                token = os.environ.get(arguments.auth_token_env)
                if token is None or len(token.encode("utf-8")) < 16:
                    raise ValueError(
                        f"{arguments.auth_token_env} must contain a local authentication token of at least 16 bytes"
                    )
                required_local = {
                    "tenant id": arguments.tenant_id,
                    "project id": arguments.project_id,
                    "actor id": arguments.actor_id,
                    "authentication context digest": arguments.authentication_context_digest,
                    "authority id": arguments.authority_id,
                    "authority revision": arguments.authority_revision,
                    "environment id": arguments.environment_id,
                    "environment revision": arguments.environment_revision,
                    "execution epoch": arguments.execution_epoch,
                    "fencing generation": arguments.fencing_generation,
                    "authority expiry": arguments.authority_expires_at,
                }
                missing = [
                    name
                    for name, value in required_local.items()
                    if value in {None, ""}
                ]
                if missing:
                    raise ValueError(
                        "missing required local serve configuration: "
                        + ", ".join(missing)
                    )
                expires_at = _parse_datetime(arguments.authority_expires_at)
                principal = AuthPrincipal(
                    tenant_id=arguments.tenant_id,
                    project_id=arguments.project_id,
                    actor_id=arguments.actor_id,
                    authority=tuple(arguments.authority),
                    authentication_context_digest=arguments.authentication_context_digest,
                    authority_id=arguments.authority_id,
                    authority_revision=arguments.authority_revision,
                    environment_id=arguments.environment_id,
                    environment_revision=arguments.environment_revision,
                    execution_epoch=arguments.execution_epoch,
                    fencing_generation=arguments.fencing_generation,
                    expires_at=expires_at,
                    issuer=arguments.expected_issuer or "local-static-authenticator",
                    audience=arguments.expected_audience or "elmos-proof-harness",
                )
                store = SQLiteStore(arguments.state_db or ":memory:")
                service_arguments = {"auth_tokens": {token: principal}}
            try:
                control_plane = DurableControlPlane(
                    store,
                    runtime,
                    owner_id=arguments.owner_id,
                    lease_ttl_seconds=arguments.lease_ttl_seconds,
                    runtime_assurance=runtime_assurance,
                )
                service = HarnessService(
                    runtime,
                    control_plane=control_plane,
                    max_request_bytes=arguments.max_request_bytes,
                    runtime_mode=arguments.runtime_mode,
                    allow_legacy_local=arguments.allow_legacy_local,
                    transport_mode=arguments.transport_mode,
                    tls_cert_file=arguments.tls_cert_file,
                    tls_key_file=arguments.tls_key_file,
                    tls_client_ca_file=arguments.tls_client_ca_file,
                    trusted_proxy_cidrs=tuple(arguments.trusted_proxy_cidr),
                    request_timeout_seconds=arguments.request_timeout_seconds,
                    max_concurrent_requests=arguments.max_concurrent_requests,
                    graceful_shutdown_seconds=arguments.graceful_shutdown_seconds,
                    **service_arguments,
                )
                serve(service, arguments.host, arguments.port)
            finally:
                if "control_plane" in locals():
                    control_plane.shutdown()
                store.close()
        else:
            parser.error("unknown command")
        return 0
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(
            json.dumps(
                {"error": {"type": type(exc).__name__, "message": str(exc)}},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2


def _print_json(value: Any) -> None:
    print(
        json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False)
    )


def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    normalized: set[str] = set()
    for key, value in pairs:
        if not isinstance(key, str):
            raise ValueError("JSON object key must be a string")
        canonical_key = unicodedata.normalize("NFC", key)
        if key != canonical_key or key in result or canonical_key in normalized:
            raise ValueError("JSON object contains a duplicate or non-NFC key")
        result[key] = value
        normalized.add(canonical_key)
    return result


def _reject_json_constant(value: str) -> Any:
    raise ValueError(f"non-finite JSON number is forbidden: {value}")


def _parse_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("authority expiry must be an RFC 3339 date-time") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("authority expiry must include a timezone")
    return parsed.astimezone(UTC)


def _load_authenticator(reference: str) -> Authenticator:
    module_name, separator, symbol_name = reference.partition(":")
    if (
        not separator
        or not module_name
        or not symbol_name
        or any(character.isspace() for character in reference)
    ):
        raise ValueError("authenticator factory must use module.path:factory syntax")
    factory = getattr(importlib.import_module(module_name), symbol_name)
    if not callable(factory):
        raise ValueError("configured authenticator factory is not callable")
    authenticator = factory()
    for attribute in ("authenticate", "readiness", "trusted_for_production"):
        if not hasattr(authenticator, attribute):
            raise ValueError(
                f"configured authenticator is missing required attribute: {attribute}"
            )
    return cast(Authenticator, authenticator)


def _load_runtime_assurance(
    reference: str,
    store: PostgresStore,
) -> RuntimeAssuranceControlPlane:
    module_name, separator, symbol_name = reference.partition(":")
    if (
        not separator
        or not module_name
        or not symbol_name
        or any(character.isspace() for character in reference)
    ):
        raise ValueError(
            "runtime assurance factory must use module.path:factory syntax"
        )
    factory = getattr(importlib.import_module(module_name), symbol_name)
    if not callable(factory):
        raise ValueError("configured runtime assurance factory is not callable")
    control = factory(store)
    if not isinstance(control, RuntimeAssuranceControlPlane):
        raise ValueError(
            "runtime assurance factory must return RuntimeAssuranceControlPlane"
        )
    if id(control.store) != id(store):
        raise ValueError("runtime assurance factory returned a different durable store")
    return control


__all__ = ["build_parser", "main"]

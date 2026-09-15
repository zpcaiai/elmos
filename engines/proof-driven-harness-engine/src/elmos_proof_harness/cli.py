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
from .delta import DELTA_SKILL_REGISTRY
from .delta_v32 import DELTA_V32_SKILL_REGISTRY, execute_v32_skill
from .skills import COMPONENT_REGISTRY, SKILL_REGISTRY, SkillRuntime
from .storage import ControlPlaneStore
from .store import SQLiteStore
from .formal_verifier import FormalVerificationEngine, ObligationKind, ProofObligation
from .hermetic_container import EnvironmentFingerprint
from .network_egress import EgressPolicy, EgressViolationError, NetworkEgressGuard
from .sandbox import DisposableSandboxRunner, SandboxLimits


ALL_SKILL_NAMES: tuple[str, ...] = tuple(
    sorted(set(SKILL_REGISTRY) | set(DELTA_SKILL_REGISTRY) | set(DELTA_V32_SKILL_REGISTRY))
)


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

    list_skills = subparsers.add_parser("list-skills", help="list exact routable and delta Skills")
    list_skills.add_argument(
        "--version",
        choices=("all", "v3.0", "v3.1", "v3.2"),
        default="all",
        help="filter skills by harness version",
    )
    subparsers.add_parser("list-components", help="list the 96 exact kernel components")

    invoke = subparsers.add_parser("invoke", help="invoke one exact Skill locally")
    invoke.add_argument("skill", choices=ALL_SKILL_NAMES)
    payload_group = invoke.add_mutually_exclusive_group(required=True)
    payload_group.add_argument("--payload", help="JSON object")
    payload_group.add_argument("--payload-file", help="path to a JSON object")
    invoke.add_argument("--workspace-root", action="append", default=[])
    invoke.add_argument("--authority", action="append", default=[])

    gate = subparsers.add_parser("gate", help="evaluate release assurance gates")
    gate.add_argument("subcommand", choices=("evaluate",))
    gate_payload_group = gate.add_mutually_exclusive_group(required=True)
    gate_payload_group.add_argument("--payload", help="JSON object")
    gate_payload_group.add_argument("--payload-file", help="path to a JSON object")

    db = subparsers.add_parser("db", help="database management and migration tools")
    db.add_argument("subcommand", choices=("check", "migrate"))
    db.add_argument("--dsn", default=os.environ.get("ELMOS_POSTGRES_DSN"))

    # Environment fingerprint
    subparsers.add_parser(
        "fingerprint", help="detect host OS, architecture, and container isolation capabilities"
    )

    # Formal SMT Verification
    verify_smt = subparsers.add_parser(
        "verify-smt", help="run formal SMT solver on proof obligations"
    )
    verify_smt_group = verify_smt.add_mutually_exclusive_group(required=True)
    verify_smt_group.add_argument("--formula", help="SMT-LIB2 formula string")
    verify_smt_group.add_argument("--formula-file", help="path to SMT-LIB2 formula file")
    verify_smt.add_argument("--obligation-id", default="obl-cli-001", help="identifier for obligation")
    verify_smt.add_argument("--symbol", default="", help="symbol or function being verified")
    verify_smt.add_argument(
        "--kind",
        choices=(
            "NULL_SAFETY",
            "BOUNDS_CHECK",
            "TYPE_PRESERVATION",
            "STATE_EQUIVALENCE",
            "TRANSACTION_INVARIANT",
            "ARITHMETIC_OVERFLOW",
            "GENERIC_CONTRACT",
            "SAFETY",
            "LIVENESS",
            "EQUIVALENCE",
            "INVARIANT",
            "REFINEMENT",
        ),
        default="GENERIC_CONTRACT",
        help="kind of obligation",
    )
    verify_smt.add_argument("--solver", choices=("z3", "cvc5"), default="z3")
    verify_smt.add_argument("--timeout-seconds", type=float, default=10.0)

    # Disposable Sandbox Execution
    sandbox_run = subparsers.add_parser(
        "sandbox-run", help="run command safely in disposable process sandbox with POSIX limits"
    )
    sandbox_run.add_argument("--timeout-seconds", type=float, default=30.0)
    sandbox_run.add_argument("--max-cpu-seconds", type=int, default=30)
    sandbox_run.add_argument("--max-memory-mb", type=int, default=512)
    sandbox_run.add_argument("cmd_args", nargs=argparse.REMAINDER, help="command line arguments to execute")

    # Network Egress & Secret Leak Guard
    egress_check = subparsers.add_parser(
        "egress-check", help="evaluate target destination against egress policy and secret leak patterns"
    )
    egress_check.add_argument("--target", required=True, help="destination URL or host:port")
    egress_check.add_argument("--allow-domain", action="append", default=[])
    egress_check.add_argument("--allow-port", type=int, action="append", default=[])
    egress_check.add_argument("--payload", help="string payload to scan for credentials")
    egress_check.add_argument("--payload-file", help="file to scan for credentials")

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
            ver = getattr(arguments, "version", "all")
            skills_out: list[dict[str, Any]] = []
            if ver in {"all", "v3.0"}:
                for name in sorted(SKILL_REGISTRY):
                    d = SKILL_REGISTRY[name].to_dict()
                    d["version"] = "v3.0"
                    skills_out.append(d)
            if ver in {"all", "v3.1"}:
                for name in sorted(DELTA_SKILL_REGISTRY):
                    desc = DELTA_SKILL_REGISTRY[name]
                    skills_out.append({
                        "skill": name,
                        "skill_id": desc.skill_id,
                        "priority": desc.priority,
                        "owner_kernels": list(desc.owner_kernels),
                        "version": "v3.1",
                        "routable": desc.routable,
                        "description": f"Delta extension skill {name} for {','.join(desc.owner_kernels)}",
                    })
            if ver in {"all", "v3.2"}:
                for name in sorted(DELTA_V32_SKILL_REGISTRY):
                    desc_v32 = DELTA_V32_SKILL_REGISTRY[name]
                    skills_out.append({
                        "skill": name,
                        "kernel": desc_v32.kernel,
                        "batch": desc_v32.batch,
                        "version": "v3.2",
                        "routable": True,
                        "description": desc_v32.description,
                    })
            _print_json({"skills": skills_out, "count": len(skills_out), "version": ver})
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
            skill_name = arguments.skill
            payload = _load_payload(arguments)
            if skill_name in DELTA_V32_SKILL_REGISTRY:
                result_v32 = execute_v32_skill(skill_name, payload)
                _print_json(result_v32)
                return 0 if result_v32.get("status") == "SUCCESS" else 2
            elif skill_name in SKILL_REGISTRY:
                runtime = SkillRuntime(workspace_roots=arguments.workspace_root)
                result = runtime.execute(
                    skill_name,
                    payload,
                    context={"authority": arguments.authority},
                )
                _print_json(result.to_dict())
                return 0 if result.status not in {"BLOCKED", "FAILED", "DENIED"} else 2
            elif skill_name in DELTA_SKILL_REGISTRY:
                _print_json({
                    "skill": skill_name,
                    "version": "v3.1",
                    "status": "NON_ROUTABLE_INTERNAL",
                    "message": f"Skill {skill_name} is an internal non-routable v3.1 extension requiring host-injected security context.",
                })
                return 0
        elif arguments.command == "gate":
            payload = _load_payload(arguments)
            res = execute_v32_skill("release-evidence-exact-artifact", payload)
            _print_json(res)
            return 0 if res.get("gate_decision") == "PASS" else 2
        elif arguments.command == "db":
            dsn = arguments.dsn
            if not dsn:
                _print_json({"status": "ERROR", "message": "Missing PostgreSQL DSN. Pass --dsn or set ELMOS_POSTGRES_DSN"})
                return 1
            if arguments.subcommand == "check":
                pg_store = PostgresStore(dsn)
                readiness = pg_store.readiness()
                _print_json({
                    "status": "SUCCESS" if readiness.ready else "NOT_READY",
                    "readiness": {
                        "status": readiness.status.value,
                        "ready": readiness.ready,
                        "reason": readiness.reason,
                        "backend": readiness.backend,
                        "schema_version": readiness.schema_version,
                        "server_version": readiness.server_version,
                    },
                })
                return 0 if readiness.ready else 1
            elif arguments.subcommand == "migrate":
                from .migration_manager import MigrationManager
                manager = MigrationManager(dsn)
                applied = manager.apply_pending()
                _print_json({"status": "SUCCESS", "migrations_applied": applied})
                return 0
        elif arguments.command == "fingerprint":
            fp = EnvironmentFingerprint.detect()
            _print_json(fp.to_dict())
            return 0
        elif arguments.command == "verify-smt":
            if arguments.formula:
                formula_text = arguments.formula
            else:
                formula_text = Path(arguments.formula_file).read_text(encoding="utf-8")
            engine = FormalVerificationEngine()
            kind_str = arguments.kind
            kind_map = {
                "SAFETY": ObligationKind.STATE_EQUIVALENCE,
                "LIVENESS": ObligationKind.STATE_EQUIVALENCE,
                "EQUIVALENCE": ObligationKind.STATE_EQUIVALENCE,
                "INVARIANT": ObligationKind.TRANSACTION_INVARIANT,
                "REFINEMENT": ObligationKind.TYPE_PRESERVATION,
            }
            kind = kind_map.get(
                kind_str,
                ObligationKind(kind_str)
                if kind_str in ObligationKind.__members__
                else ObligationKind.GENERIC_CONTRACT,
            )
            obligation = ProofObligation(
                obligation_id=arguments.obligation_id,
                kind=kind,
                symbol=arguments.symbol or arguments.obligation_id,
                preconditions=(),
                postconditions=(),
                negated_goal_smt2=formula_text,
                timeout_seconds=arguments.timeout_seconds,
            )
            cert = engine.verify_obligation(obligation, solver_name=arguments.solver)
            out = cert.to_dict()
            if cert.generated_test_code:
                out["generated_test_code"] = cert.generated_test_code
            _print_json(out)
            return 0 if cert.verdict.value == "PROVED" else (1 if cert.verdict.value == "REFUTED" else 2)
        elif arguments.command == "sandbox-run":
            limits = SandboxLimits(
                max_cpu_seconds=arguments.max_cpu_seconds,
                max_memory_mb=arguments.max_memory_mb,
            )
            runner = DisposableSandboxRunner(limits=limits)
            res = runner.run(arguments.cmd_args, timeout_seconds=arguments.timeout_seconds)
            _print_json({
                "exit_code": res.exit_code,
                "stdout": res.stdout,
                "stderr": res.stderr,
                "duration_ms": res.duration_ms,
                "timed_out": res.timed_out,
                "rlimit_enforced": res.rlimit_enforced,
            })
            return 0 if res.exit_code == 0 and not res.timed_out else 2
        elif arguments.command == "egress-check":
            allowed_ports = tuple(arguments.allow_port) if arguments.allow_port else (443, 8080)
            policy = EgressPolicy(
                allow_egress=True,
                allowed_domains=tuple(arguments.allow_domain),
                allowed_ports=allowed_ports,
            )
            guard = NetworkEgressGuard(policy)
            try:
                guard.validate_destination(arguments.target)
                payload_content = ""
                if arguments.payload:
                    payload_content = arguments.payload
                elif arguments.payload_file:
                    payload_content = Path(arguments.payload_file).read_text(encoding="utf-8")
                if payload_content:
                    secrets = guard.inspect_content_for_secrets(payload_content)
                    if secrets:
                        _print_json({"status": "REJECTED", "reason": f"detected secrets: {secrets}", "secrets": secrets})
                        return 2
                _print_json({"status": "ALLOWED", "destination": arguments.target})
                return 0
            except EgressViolationError as exc:
                _print_json({"status": "BLOCKED", "reason": str(exc)})
                return 2
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

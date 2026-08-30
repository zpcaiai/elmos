"""Safe administrative CLI for the PDHI engine.

The CLI intentionally has no command that invents a principal, provisions a
tenant, certifies a result, or executes a provider effect.  Invocation is
available only through a host-created :class:`PdhiService` with trusted
identity injection.
"""

from __future__ import annotations

import argparse
import importlib
import os
from pathlib import Path
import socket
import ssl
import sys
from socketserver import ThreadingMixIn
from typing import Callable, cast
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

from .canonical import canonical_json_text
from .runtime import RuntimeRegistry
from .service import PdhiService
from .store import SqlitePdhiStore


class _ThreadingWsgiServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True
    request_queue_size = 128


class _QuietRequestHandler(WSGIRequestHandler):
    server_version = "elmos-pdhi"
    sys_version = ""

    def log_message(self, format: str, *args: object) -> None:
        # Access logging belongs at the structured gateway.  The standard
        # handler can expose raw paths and peers and is therefore suppressed.
        return None


def _write(value: object) -> None:
    sys.stdout.write(canonical_json_text(value) + "\n")


def _load_factory(spec: str) -> Callable[[], PdhiService]:
    module_name, separator, attribute = spec.partition(":")
    if not separator or not module_name or not attribute:
        raise ValueError("service factory must be module:callable")
    module = importlib.import_module(module_name)
    factory = getattr(module, attribute, None)
    if not callable(factory):
        raise ValueError("service factory is not callable")
    return cast(Callable[[], PdhiService], factory)


def _manifest(_: argparse.Namespace) -> int:
    _write(dict(RuntimeRegistry().manifest()))
    return 0


def _gate_status(_: argparse.Namespace) -> int:
    _write(
        {
            "local_engineering_maximum": "READY_FOR_EXTERNAL_GATE",
            "external_database": "NOT_RUN",
            "oidc_or_workload_identity": "NOT_RUN",
            "policy_provider": "NOT_RUN",
            "object_store": "NOT_RUN",
            "external_effect_executor": "NOT_RUN",
            "kubernetes_deployment": "NOT_RUN",
            "independent_verification": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        }
    )
    return 0


def _db_readiness(arguments: argparse.Namespace) -> int:
    database = Path(arguments.database).expanduser().resolve(strict=False)
    if not database.is_file():
        raise ValueError("database must already exist; readiness never creates one")
    store = SqlitePdhiStore(database)
    try:
        status = dict(store.readiness())
    finally:
        store.close()
    _write(status)
    return 0 if status.get("status") == "READY" else 2


def _serve(arguments: argparse.Namespace) -> int:
    factory = _load_factory(arguments.factory)
    application = factory()
    if not isinstance(application, PdhiService):
        raise ValueError("service factory must return PdhiService")
    try:
        ip = socket.getaddrinfo(arguments.host, arguments.port, type=socket.SOCK_STREAM)[0][4][0]
        if not isinstance(ip, str):
            raise ValueError("service bind address did not resolve to text")
        loopback = ip.startswith("127.") or ip == "::1"
    except OSError as exc:
        raise ValueError("service bind address cannot be resolved") from exc
    tls_configured = bool(arguments.tls_certificate or arguments.tls_key)
    if tls_configured and not (arguments.tls_certificate and arguments.tls_key):
        raise ValueError("TLS certificate and key must be configured together")
    if not loopback and not tls_configured and not arguments.trusted_mesh_transport:
        raise ValueError("non-loopback service requires TLS or an explicitly configured trusted mesh transport")
    server = make_server(
        arguments.host,
        arguments.port,
        application,
        server_class=_ThreadingWsgiServer,
        handler_class=_QuietRequestHandler,
    )
    if tls_configured:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(arguments.tls_certificate, arguments.tls_key)
        server.socket = context.wrap_socket(server.socket, server_side=True)
    _write(
        {
            "status": "STARTING",
            "host": arguments.host,
            "port": arguments.port,
            "tls": tls_configured,
            "trusted_mesh_transport": bool(arguments.trusted_mesh_transport),
            "external_deployment_evidence": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        }
    )
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="elmos-pdhi", description="PDHI fail-closed local administration")
    commands = root.add_subparsers(dest="command", required=True)
    manifest = commands.add_parser("manifest", help="emit the exact runtime manifest")
    manifest.set_defaults(handler=_manifest)
    gate = commands.add_parser("gate-status", help="emit conservative external-gate status")
    gate.set_defaults(handler=_gate_status)
    database = commands.add_parser("db-readiness", help="check an existing local engineering database")
    database.add_argument("--database", required=True)
    database.set_defaults(handler=_db_readiness)
    serve = commands.add_parser("serve", help="serve a host-injected trusted service factory")
    serve.add_argument(
        "--factory",
        default=os.environ.get("ELMOS_PDHI_SERVICE_FACTORY"),
        required=os.environ.get("ELMOS_PDHI_SERVICE_FACTORY") is None,
        help="trusted module:callable returning PdhiService",
    )
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8080)
    serve.add_argument("--tls-certificate")
    serve.add_argument("--tls-key")
    serve.add_argument(
        "--trusted-mesh-transport",
        action="store_true",
        help="bind without app TLS only when an independently configured mTLS mesh owns transport",
    )
    serve.set_defaults(handler=_serve)
    return root


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        return int(arguments.handler(arguments))
    except Exception as exc:
        sys.stderr.write(canonical_json_text({"error": {"code": "CLI_FAILED", "message": str(exc)}}) + "\n")
        return 2


if __name__ == "__main__":  # pragma: no cover - exercised through console script
    raise SystemExit(main())

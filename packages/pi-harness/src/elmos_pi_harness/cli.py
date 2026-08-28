"""Operator CLI for local administration and health checks."""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import tempfile
import uuid
from pathlib import Path
from sysconfig import get_path
from typing import Any

from .api import serve
from .persistence import DurableStore


def _default_migration_root() -> str:
    source_root = Path(__file__).resolve().parents[2] / "sql"
    installed_root = Path(get_path("data")) / "elmos-pi-harness" / "sql"
    for candidate in (source_root, installed_root):
        if candidate.is_dir() and not candidate.is_symlink():
            return str(candidate)
    return str(installed_root)


def _store(args: argparse.Namespace) -> Any:
    artifact_root = os.path.abspath(args.artifact_root)
    if args.database.startswith(("postgresql://", "postgres://", "service=")):
        from .postgres import PostgresConfig, PostgresStore

        return PostgresStore(PostgresConfig(args.database), artifact_root=artifact_root)
    return DurableStore(args.database, artifact_root=artifact_root)


def _identity(args: argparse.Namespace) -> tuple[Any | None, ssl.SSLContext | None]:
    values = [
        args.oidc_issuer,
        args.oidc_audience,
        args.oidc_jwks_url,
        args.mtls_trust_domain,
        args.tls_certificate,
        args.tls_private_key,
        args.tls_client_ca,
        args.tls_crl,
    ]
    if not any(values):
        return None, None
    if not all(values):
        raise ValueError(
            "OIDC/mTLS serving requires issuer, audience, JWKS URL, trust domain, server certificate/key, and client CA"
        )
    from .identity import (
        CRLRevocationChecker,
        HTTPCompositeAuthenticator,
        MTLSAuthenticator,
        OIDCAuthenticator,
        OIDCConfig,
    )

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(args.tls_certificate, args.tls_private_key)
    context.load_verify_locations(cafile=args.tls_client_ca)
    context.load_verify_locations(cafile=args.tls_crl)
    context.verify_mode = ssl.CERT_REQUIRED
    context.verify_flags |= ssl.VERIFY_CRL_CHECK_LEAF
    context.options |= ssl.OP_NO_COMPRESSION
    authenticator = HTTPCompositeAuthenticator(
        OIDCAuthenticator(
            OIDCConfig(args.oidc_issuer, args.oidc_audience, args.oidc_jwks_url)
        ),
        MTLSAuthenticator(
            args.mtls_trust_domain,
            revocation_checker=CRLRevocationChecker([Path(args.tls_crl).resolve()]),
        ),
    )
    return authenticator, context


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="elmos-pi-harness")
    sub = parser.add_subparsers(dest="command", required=True)
    serve_parser = sub.add_parser("serve")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8787)
    serve_parser.add_argument(
        "--database", default=os.environ.get("ELMOS_PI_DATABASE", "./var/pi-harness.db")
    )
    serve_parser.add_argument(
        "--artifact-root",
        default=os.environ.get("ELMOS_PI_ARTIFACT_ROOT", "./var/pi-harness-artifacts"),
    )
    serve_parser.add_argument(
        "--api-token", default=os.environ.get("ELMOS_PI_API_TOKEN", "")
    )
    serve_parser.add_argument(
        "--oidc-issuer", default=os.environ.get("ELMOS_PI_OIDC_ISSUER", "")
    )
    serve_parser.add_argument(
        "--oidc-audience", default=os.environ.get("ELMOS_PI_OIDC_AUDIENCE", "")
    )
    serve_parser.add_argument(
        "--oidc-jwks-url", default=os.environ.get("ELMOS_PI_OIDC_JWKS_URL", "")
    )
    serve_parser.add_argument(
        "--mtls-trust-domain", default=os.environ.get("ELMOS_PI_MTLS_TRUST_DOMAIN", "")
    )
    serve_parser.add_argument(
        "--tls-certificate", default=os.environ.get("ELMOS_PI_TLS_CERTIFICATE", "")
    )
    serve_parser.add_argument(
        "--tls-private-key", default=os.environ.get("ELMOS_PI_TLS_PRIVATE_KEY", "")
    )
    serve_parser.add_argument(
        "--tls-client-ca", default=os.environ.get("ELMOS_PI_TLS_CLIENT_CA", "")
    )
    serve_parser.add_argument(
        "--tls-crl", default=os.environ.get("ELMOS_PI_TLS_CRL", "")
    )

    init = sub.add_parser("init-db")
    init.add_argument("--database", default="./var/pi-harness.db")
    init.add_argument("--artifact-root", default="./var/pi-harness-artifacts")

    create = sub.add_parser("task-create")
    create.add_argument("--database", default="./var/pi-harness.db")
    create.add_argument("--artifact-root", default="./var/pi-harness-artifacts")
    create.add_argument("--tenant-id", required=True)
    create.add_argument("--project-id", required=True)
    create.add_argument("--objective", required=True)
    create.add_argument("--idempotency-key", required=True)

    show = sub.add_parser("task-show")
    show.add_argument("--database", default="./var/pi-harness.db")
    show.add_argument("--artifact-root", default="./var/pi-harness-artifacts")
    show.add_argument("--tenant-id", required=True)
    show.add_argument("--task-id", required=True)

    migrate = sub.add_parser("postgres-migrate")
    migrate.add_argument("--database", default=os.environ.get("ELMOS_PI_DATABASE", ""))
    migrate.add_argument("--migration-root", default=_default_migration_root())

    sub.add_parser("qualification-status")

    sub.add_parser("demo", help="run a disposable local lifecycle smoke")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "demo":
        with tempfile.TemporaryDirectory(prefix="elmos-pi-harness-") as workdir:
            tenant_id = str(uuid.uuid4())
            project_id = str(uuid.uuid4())
            with DurableStore(
                os.path.join(workdir, "demo.db"),
                artifact_root=os.path.join(workdir, "artifacts"),
            ) as store:
                result = store.create_task(
                    tenant_id,
                    project_id,
                    "disposable lifecycle smoke",
                    idempotency_key="demo-create",
                    actor_id="demo",
                )
                print(json.dumps({"status": "ok", "task": result}, ensure_ascii=False))
        return 0
    if args.command == "qualification-status":
        from .qualification import implementation_inventory

        print(
            json.dumps(implementation_inventory(), ensure_ascii=False, sort_keys=True)
        )
        return 0
    if args.command == "postgres-migrate":
        from .postgres import PostgresConfig, PostgresMigrator

        result = PostgresMigrator(
            PostgresConfig(args.database), Path(args.migration_root).resolve()
        ).apply()
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    if args.command == "serve":
        identity_authenticator, tls_context = _identity(args)
        serve(
            host=args.host,
            port=args.port,
            database=args.database,
            artifact_root=args.artifact_root,
            api_token=args.api_token,
            identity_authenticator=identity_authenticator,
            ssl_context=tls_context,
        )
        return 0
    store = _store(args)
    try:
        if args.command == "init-db":
            print(
                json.dumps(
                    {"status": "ready", "database": args.database}, ensure_ascii=False
                )
            )
            return 0
        if args.command == "task-create":
            print(
                json.dumps(
                    store.create_task(
                        args.tenant_id,
                        args.project_id,
                        args.objective,
                        idempotency_key=args.idempotency_key,
                        actor_id="cli",
                    ),
                    ensure_ascii=False,
                )
            )
            return 0
        if args.command == "task-show":
            print(
                json.dumps(
                    store.get_task(args.tenant_id, args.task_id), ensure_ascii=False
                )
            )
            return 0
    finally:
        store.close()
    return 2


if __name__ == "__main__":
    sys.exit(main())

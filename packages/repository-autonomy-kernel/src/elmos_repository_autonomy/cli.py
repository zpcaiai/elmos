"""CLI entrypoint for local operations and the HTTP control-plane adapter."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .adapters import all_local_conformance
from .catalog import PACKAGE_ID, PACKAGE_VERSION, SKILL_SPECS
from .dispatcher import AutonomyRuntime
from .errors import KernelError
from .external_runtime import ExternalQualificationPreflight, load_qualification_manifest
from .postgres import PostgresMigrationRunner, PostgresSessionFactory
from .postgres_wave_store import PostgresWaveStore
from .server import serve
from .storage import DurableStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="elmos-autonomy")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("catalog")
    conformance_parser = sub.add_parser("conformance")
    conformance_parser.add_argument("adapter")
    conformance_parser.add_argument("--responses", default="{}", help="JSON object keyed by conformance case")
    sub.add_parser("local-conformance")
    matrix_parser = sub.add_parser("matrix")
    matrix_parser.add_argument("--db", default=":memory:")
    matrix_parser.add_argument("--tenant", default="local")
    certify_parser = sub.add_parser("certify")
    certify_parser.add_argument("--db", required=True)
    certify_parser.add_argument("--tenant", required=True)
    certify_parser.add_argument("--candidate-digest", required=True)
    certify_parser.add_argument("--release-context", default="{}", help="JSON release context")
    dispatch_parser = sub.add_parser("dispatch")
    dispatch_parser.add_argument("skill")
    dispatch_parser.add_argument("payload", help="JSON object")
    serve_parser = sub.add_parser("serve")
    serve_parser.add_argument("--db", default=os.environ.get("ELMOS_AUTONOMY_DB", ":memory:"))
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8080)
    serve_parser.add_argument("--allow-unverified-local-identity", action="store_true")
    serve_parser.add_argument("--postgres-control-service")
    migrate_parser = sub.add_parser("postgres-migrate")
    migrate_parser.add_argument("--service", required=True)
    migrate_parser.add_argument(
        "--migration-root",
        default=str(Path(__file__).resolve().parents[2] / "sql" / "migrations"),
    )
    migrate_parser.add_argument("--operator", required=True)
    migrate_parser.add_argument("--authorization-receipt", required=True)
    backup_parser = sub.add_parser("backup")
    backup_parser.add_argument("--db", required=True)
    backup_parser.add_argument("--output", required=True)
    restore_parser = sub.add_parser("restore")
    restore_parser.add_argument("--source", required=True)
    restore_parser.add_argument("--db", required=True)
    replay_parser = sub.add_parser("replay")
    replay_parser.add_argument("--db", required=True)
    replay_parser.add_argument("run_id")
    replay_parser.add_argument("--tenant")
    preflight_parser = sub.add_parser("external-preflight")
    preflight_parser.add_argument("--manifest", required=True)
    args = parser.parse_args(argv)
    if args.command == "catalog":
        print(json.dumps({"package": PACKAGE_ID, "version": PACKAGE_VERSION, "skills": [{"name": item.name, "priority": item.priority, "pack": item.pack, "inputs": item.inputs, "outputs": item.outputs} for item in SKILL_SPECS.values()]}, ensure_ascii=False, indent=2))
        return 0
    if args.command == "dispatch":
        try:
            payload = json.loads(args.payload)
        except json.JSONDecodeError as exc:
            parser.error(f"payload is not valid JSON: {exc}")
            return 2
        result = AutonomyRuntime().execute(args.skill, payload)
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0 if result.status.value not in {"BLOCKED", "REJECTED"} else 1
    if args.command == "conformance":
        try:
            responses = json.loads(args.responses)
        except json.JSONDecodeError as exc:
            parser.error(f"responses is not valid JSON: {exc}")
            return 2
        result = AutonomyRuntime().conformance(args.adapter, responses=responses)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "PASS" else 1
    if args.command == "local-conformance":
        result = all_local_conformance()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["engineering_status"] == "PASS" else 1
    if args.command == "matrix":
        with_store = DurableStore(args.db)
        try:
            result = AutonomyRuntime(with_store).certification_matrix(tenant_id=args.tenant)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        finally:
            with_store.close()
        return 0
    if args.command == "certify":
        try:
            release_context = json.loads(args.release_context)
        except json.JSONDecodeError as exc:
            parser.error(f"release context is not valid JSON: {exc}")
            return 2
        with_store = DurableStore(args.db)
        try:
            result = AutonomyRuntime(with_store).certification.evaluate(
                tenant_id=args.tenant, candidate_digest=args.candidate_digest,
                release_context=release_context,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
        finally:
            with_store.close()
        return 0 if result["p05"]["issued"] else 1
    if args.command == "serve":
        control_store = None
        if args.postgres_control_service:
            control_store = PostgresWaveStore(
                PostgresSessionFactory(service_name=args.postgres_control_service)
            )
        runtime = AutonomyRuntime(DurableStore(args.db), control_store=control_store)
        serve(runtime, args.host, args.port, require_verified_identity=not args.allow_unverified_local_identity)
        return 0
    if args.command == "postgres-migrate":
        result = PostgresMigrationRunner(
            PostgresSessionFactory(service_name=args.service), args.migration_root
        ).apply(operator_id=args.operator, authorization_receipt=args.authorization_receipt)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "backup":
        with_store = DurableStore(args.db)
        try:
            print(json.dumps(with_store.backup_to(args.output), ensure_ascii=False, indent=2))
        finally:
            with_store.close()
        return 0
    if args.command == "restore":
        print(json.dumps(DurableStore.restore_from(args.source, args.db), ensure_ascii=False, indent=2))
        return 0
    if args.command == "replay":
        with_store = DurableStore(args.db)
        try:
            print(json.dumps({"run_id": args.run_id, "state": with_store.replay_state(args.run_id, tenant_id=args.tenant), "export": with_store.export_run(args.run_id, tenant_id=args.tenant)}, ensure_ascii=False, indent=2))
        finally:
            with_store.close()
        return 0
    if args.command == "external-preflight":
        try:
            manifest = load_qualification_manifest(args.manifest)
            result = ExternalQualificationPreflight().evaluate(manifest)
        except KernelError as exc:
            result = {
                "ready_for_authorized_execution": False,
                "execution_performed": False,
                "external_evidence": "NOT_RUN",
                "certification": "NOT_CERTIFIED",
                "p05": {
                    "issued": False,
                    "decision": "P05_DEPLOYMENT_COMPLETE_NOT_ISSUED",
                },
                "error": exc.info.to_dict(),
            }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ready_for_authorized_execution"] else 1
    return 2


if __name__ == "__main__":
    sys.exit(main())

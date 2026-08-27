"""CLI entrypoint for local operations and the HTTP control-plane adapter."""

from __future__ import annotations

import argparse
import json
import os
import sys

from .catalog import PACKAGE_ID, PACKAGE_VERSION, SKILL_SPECS
from .dispatcher import AutonomyRuntime
from .server import serve
from .storage import DurableStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="elmos-autonomy")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("catalog")
    conformance_parser = sub.add_parser("conformance")
    conformance_parser.add_argument("adapter")
    conformance_parser.add_argument("--responses", default="{}", help="JSON object keyed by conformance case")
    dispatch_parser = sub.add_parser("dispatch")
    dispatch_parser.add_argument("skill")
    dispatch_parser.add_argument("payload", help="JSON object")
    serve_parser = sub.add_parser("serve")
    serve_parser.add_argument("--db", default=os.environ.get("ELMOS_AUTONOMY_DB", ":memory:"))
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8080)
    serve_parser.add_argument("--allow-unverified-local-identity", action="store_true")
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
    if args.command == "serve":
        runtime = AutonomyRuntime(DurableStore(args.db))
        serve(runtime, args.host, args.port, require_verified_identity=not args.allow_unverified_local_identity)
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
    return 2


if __name__ == "__main__":
    sys.exit(main())

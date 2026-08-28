"""Operator CLI for local administration and health checks."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import uuid

from .api import serve
from .persistence import DurableStore


def _store(args: argparse.Namespace) -> DurableStore:
    return DurableStore(args.database, artifact_root=os.path.abspath(args.artifact_root))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="elmos-pi-harness")
    sub = parser.add_subparsers(dest="command", required=True)
    serve_parser = sub.add_parser("serve")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8787)
    serve_parser.add_argument("--database", default=os.environ.get("ELMOS_PI_DATABASE", "./var/pi-harness.db"))
    serve_parser.add_argument("--artifact-root", default=os.environ.get("ELMOS_PI_ARTIFACT_ROOT", "./var/pi-harness-artifacts"))
    serve_parser.add_argument("--api-token", default=os.environ.get("ELMOS_PI_API_TOKEN", ""))

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

    sub.add_parser("demo", help="run a disposable local lifecycle smoke")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "demo":
        with tempfile.TemporaryDirectory(prefix="elmos-pi-harness-") as workdir:
            tenant_id = str(uuid.uuid4())
            project_id = str(uuid.uuid4())
            with DurableStore(os.path.join(workdir, "demo.db"), artifact_root=os.path.join(workdir, "artifacts")) as store:
                result = store.create_task(tenant_id, project_id, "disposable lifecycle smoke", idempotency_key="demo-create", actor_id="demo")
                print(json.dumps({"status": "ok", "task": result}, ensure_ascii=False))
        return 0
    if args.command == "serve":
        serve(host=args.host, port=args.port, database=args.database, artifact_root=args.artifact_root, api_token=args.api_token)
        return 0
    store = _store(args)
    try:
        if args.command == "init-db":
            print(json.dumps({"status": "ready", "database": args.database}, ensure_ascii=False))
            return 0
        if args.command == "task-create":
            print(json.dumps(store.create_task(args.tenant_id, args.project_id, args.objective, idempotency_key=args.idempotency_key, actor_id="cli"), ensure_ascii=False))
            return 0
        if args.command == "task-show":
            print(json.dumps(store.get_task(args.tenant_id, args.task_id), ensure_ascii=False))
            return 0
    finally:
        store.close()
    return 2


if __name__ == "__main__":
    sys.exit(main())

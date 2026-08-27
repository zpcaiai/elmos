from __future__ import annotations

import argparse
import json
from pathlib import Path

from .contracts import TrustedIdentity
from .runtime import FormalAssuranceRuntime
from .store import StateStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="elmos-formal-assurance")
    parser.add_argument("--state", default=":memory:")
    parser.add_argument("--tenant")
    parser.add_argument("--actor", default="local-operator")
    parser.add_argument("--project")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("skills")
    execute = sub.add_parser("execute")
    execute.add_argument("skill_id")
    execute.add_argument("--request", type=Path, required=True)
    execute.add_argument("--subject", required=True)
    execute.add_argument("--idempotency-key", required=True)
    args = parser.parse_args(argv)
    runtime = FormalAssuranceRuntime(store=StateStore(args.state))
    if args.command == "skills":
        print(
            json.dumps({"skills": runtime.list_skills()}, ensure_ascii=False, indent=2)
        )
        return 0
    if not args.tenant:
        parser.error("--tenant is required for execute")
    request = json.loads(args.request.read_text(encoding="utf-8"))
    identity = TrustedIdentity(args.tenant, args.actor, args.project)
    result = runtime.dispatch(
        args.skill_id,
        request,
        identity,
        subject_id=args.subject,
        idempotency_key=args.idempotency_key,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

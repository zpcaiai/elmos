"""Command-line boundary for local, authority-scoped modernization work."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .runtime import CATALOG, capability_manifest, dispatch, validate_skill_registry
from .service import ModernizationService


def _request(path: str) -> dict:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("request file must contain an object")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="elmos-legacy-web")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate")
    sub.add_parser("manifest")
    dispatch_parser = sub.add_parser("dispatch")
    dispatch_parser.add_argument("request")
    run_parser = sub.add_parser("run")
    run_parser.add_argument("request")
    run_parser.add_argument("--state-dir", default=".elmos/legacy-web")
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            validate_skill_registry()
            print(json.dumps({"status": "PASS", "package": CATALOG.package_name, "version": CATALOG.version, "skills": len(CATALOG.skills), "externalEvidence": "NOT_RUN", "certification": "NOT_CERTIFIED"}, ensure_ascii=False, sort_keys=True))
        elif args.command == "manifest":
            print(json.dumps({"package": CATALOG.package_name, "version": CATALOG.version, "archiveDigest": CATALOG.archive_digest, "manifestDigest": CATALOG.manifest_digest, "skills": capability_manifest()}, ensure_ascii=False, sort_keys=True))
        elif args.command == "dispatch":
            print(json.dumps(dispatch(_request(args.request)), ensure_ascii=False, sort_keys=True))
        else:
            print(json.dumps(ModernizationService(args.state_dir).run_readonly(_request(args.request)), ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

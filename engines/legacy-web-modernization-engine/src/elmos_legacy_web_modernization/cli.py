"""Command-line boundary for local, authority-scoped modernization work."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .runtime import CATALOG, capability_manifest, dispatch, validate_skill_registry
from .service import ModernizationService
from .external_evidence import evaluate_external_intake


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
    external_parser = sub.add_parser("external-preflight")
    external_parser.add_argument("--intake", required=True)
    external_parser.add_argument("--expected-binding", required=True)
    external_parser.add_argument("--evidence-root", required=True)
    external_parser.add_argument("--trust-store", required=True)
    external_parser.add_argument("--output")
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            validate_skill_registry()
            print(json.dumps({"status": "PASS", "package": CATALOG.package_name, "version": CATALOG.version, "skills": len(CATALOG.skills), "externalEvidenceGate": "IMPLEMENTED_FAIL_CLOSED", "maximumLocalDecision": "READY_FOR_EXTERNAL_GATE_REVIEW", "externalEvidence": "NOT_RUN", "certification": "NOT_CERTIFIED"}, ensure_ascii=False, sort_keys=True))
        elif args.command == "manifest":
            print(json.dumps({"package": CATALOG.package_name, "version": CATALOG.version, "archiveDigest": CATALOG.archive_digest, "manifestDigest": CATALOG.manifest_digest, "skills": capability_manifest()}, ensure_ascii=False, sort_keys=True))
        elif args.command == "dispatch":
            print(json.dumps(dispatch(_request(args.request)), ensure_ascii=False, sort_keys=True))
        elif args.command == "external-preflight":
            result = evaluate_external_intake(
                _request(args.intake),
                expected_binding=_request(args.expected_binding),
                evidence_root=Path(args.evidence_root),
                trust_store=Path(args.trust_store),
            )
            rendered = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
            if args.output:
                output = Path(args.output)
                if output.exists() and output.is_symlink():
                    raise ValueError("output must not be a symlink")
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(rendered, encoding="utf-8")
            else:
                print(rendered, end="")
        else:
            print(json.dumps(ModernizationService(args.state_dir).run_readonly(_request(args.request)), ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

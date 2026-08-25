"""Command-line interface for the bounded software-factory engine."""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

from .archive_contracts import ArchiveContractError, inspect_archive_contracts
from .artifact_binding import ArtifactBindingError
from .capabilities import CAPABILITY_CONTRACTS, CAPABILITY_REGISTRY_DIGEST
from .canonical import MAX_JSON_BYTES, canonical_digest
from .campaigns import replay_campaign, run_campaign
from .evidence_intake import evaluate_external_preflight, ingest_external_receipt
from .evidence_models import EvidenceContractError
from .models import ContractError, ExecutionStatus
from .public_methods import PUBLIC_METHODS, PUBLIC_METHOD_REGISTRY_DIGEST
from .runtime import SoftwareFactoryEngine, dispatch_skill


def _duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"JSON contains duplicate key {key!r}")
        result[key] = value
    return result


def _required_open_flag(name: str) -> int:
    value = getattr(os, name, None)
    if not isinstance(value, int) or isinstance(value, bool) or value == 0:
        raise ValueError(f"platform lacks required safe-open flag {name}")
    return value


def _load_document(path: str) -> object:
    if path == "-":
        raw = sys.stdin.buffer.read(MAX_JSON_BYTES + 1)
    else:
        flags = (
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | _required_open_flag("O_NOFOLLOW")
            | _required_open_flag("O_NONBLOCK")
        )
        try:
            descriptor = os.open(Path(path).expanduser(), flags)
        except OSError as exc:
            raise ValueError("request path cannot be opened safely") from exc
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError("request path must identify a regular file")
            if metadata.st_size > MAX_JSON_BYTES:
                raise ValueError(f"request exceeds {MAX_JSON_BYTES} bytes")
            chunks: list[bytes] = []
            remaining = metadata.st_size
            while remaining:
                chunk = os.read(descriptor, min(1024 * 1024, remaining))
                if not chunk:
                    raise ValueError("request changed while being read")
                chunks.append(chunk)
                remaining -= len(chunk)
            if os.read(descriptor, 1):
                raise ValueError("request changed while being read")
            raw = b"".join(chunks)
        finally:
            os.close(descriptor)
    if len(raw) > MAX_JSON_BYTES:
        raise ValueError(f"request exceeds {MAX_JSON_BYTES} bytes")
    return json.loads(
        raw.decode("utf-8"),
        object_pairs_hook=_duplicates,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"invalid number {value}")),
    )


def _write(document: object) -> None:
    sys.stdout.write(json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n")


def _exit_code(status: str) -> int:
    if status == ExecutionStatus.EXECUTED.value:
        return 0
    if status == ExecutionStatus.FAILED.value:
        return 2
    return 3


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="elmos-software-factory")
    subcommands = parser.add_subparsers(dest="command", required=True)
    execute = subcommands.add_parser("execute", help="execute one exact Skill binding")
    execute.add_argument("--skill", required=True)
    execute.add_argument("--request", required=True, help="JSON file path or - for standard input")
    method = subcommands.add_parser("method", help="execute one exact public-method binding")
    method.add_argument("--method", required=True)
    method.add_argument("--request", required=True, help="JSON file path or - for standard input")
    subcommands.add_parser("registry", help="print all exact Skill capability bindings")
    subcommands.add_parser("methods", help="print all exact public-method bindings")
    digest = subcommands.add_parser("digest", help="print the canonical request digest")
    digest.add_argument("--request", required=True, help="JSON file path or - for standard input")
    archive = subcommands.add_parser(
        "archive-inspect", help="run repository-owned checks over neutralized archive data"
    )
    archive.add_argument("--source-root", required=True)
    campaign = subcommands.add_parser("campaign-run", help="run a bounded local evidence campaign")
    campaign.add_argument("--manifest", required=True, help="campaign JSON file path or -")
    campaign.add_argument(
        "--evidence-root", required=True, help="approved root for content-addressed campaign inputs"
    )
    replay = subcommands.add_parser(
        "campaign-replay", help="replay a campaign and compare its deterministic receipt"
    )
    replay.add_argument("--manifest", required=True)
    replay.add_argument("--receipt", required=True)
    replay.add_argument(
        "--evidence-root", required=True, help="approved root for content-addressed campaign inputs"
    )
    intake = subcommands.add_parser(
        "evidence-ingest", help="quarantine or locally admit an untrusted external receipt"
    )
    intake.add_argument("--receipt", required=True)
    intake.add_argument("--policy", required=True)
    intake.add_argument("--evidence-root", required=True)
    preflight = subcommands.add_parser(
        "external-preflight", help="validate external prerequisites without executing them"
    )
    preflight.add_argument("--config", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "archive-inspect":
            result = inspect_archive_contracts(Path(args.source_root))
            _write(result)
            return 0 if result["inspection_status"] == "PASSED" else 3
        if args.command == "registry":
            engine = SoftwareFactoryEngine()
            _write(
                {
                    "registry_digest": engine.registry.registry_digest,
                    "capability_registry_digest": CAPABILITY_REGISTRY_DIGEST,
                    "binding_count": len(engine.registry.bindings),
                    "bindings": [
                        {
                            "skill_name": name,
                            "package_id": binding.package_id,
                            "kind": binding.kind.value,
                            "operation": binding.operation,
                            "capability_action": CAPABILITY_CONTRACTS[name].action,
                            "capability_mode": CAPABILITY_CONTRACTS[name].mode,
                            "required_inputs": list(CAPABILITY_CONTRACTS[name].required_inputs),
                        }
                        for name, binding in sorted(engine.registry.bindings.items())
                    ],
                }
            )
            return 0
        if args.command == "methods":
            _write(
                {
                    "method_count": len(PUBLIC_METHODS),
                    "public_method_registry_digest": PUBLIC_METHOD_REGISTRY_DIGEST,
                    "methods": [
                        {
                            "method": item.method,
                            "package_id": item.package_id,
                            "action": item.action,
                            "execution_mode": item.execution_mode,
                            "required_inputs": list(item.required_inputs),
                            "domain_errors": list(item.domain_errors),
                            "platform_errors": list(item.platform_errors),
                        }
                        for item in PUBLIC_METHODS.values()
                    ],
                }
            )
            return 0
        if args.command == "campaign-run":
            result = run_campaign(
                _load_document(args.manifest), evidence_root=Path(args.evidence_root)
            ).as_dict()
            _write(result)
            return 0 if result["status"] == "PASSED" else 3
        if args.command == "campaign-replay":
            result = replay_campaign(
                _load_document(args.manifest),
                _load_document(args.receipt),
                evidence_root=Path(args.evidence_root),
            )
            _write(result)
            return 0 if result["status"] == "MATCHED" else 3
        if args.command == "evidence-ingest":
            receipt = _load_document(args.receipt)
            policy = _load_document(args.policy)
            result = ingest_external_receipt(receipt, evidence_root=Path(args.evidence_root), policy=policy)
            _write(result)
            return 0 if result["status"] == "EXTERNAL_RECEIPT_POLICY_ADMITTED" else 3
        if args.command == "external-preflight":
            result = evaluate_external_preflight(_load_document(args.config))
            _write(result)
            return 3
        document = _load_document(args.request)
        if args.command == "digest":
            _write({"digest": canonical_digest(document)})
            return 0
        if args.command == "execute":
            result = dispatch_skill(args.skill, document)
        else:
            result = SoftwareFactoryEngine().execute_method(args.method, document).as_dict()
        _write(result)
        return _exit_code(result["status"])
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        ValueError,
        ContractError,
        ArchiveContractError,
        ArtifactBindingError,
        EvidenceContractError,
    ) as exc:
        _write({"status": "FAILED", "error": {"code": "REQUEST_INVALID", "message": str(exc)}})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

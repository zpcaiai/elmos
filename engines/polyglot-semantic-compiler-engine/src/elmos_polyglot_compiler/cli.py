"""Command-line control plane for the Polyglot Semantic Compiler."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .catalog import CatalogError
from .contracts import ContractError
from .service import (
    ENGINE_NAME,
    ENGINE_VERSION,
    NOT_CERTIFIED,
    NOT_RUN,
    PolyglotSemanticCompilerService,
    ServiceError,
)


EXIT_OK = 0
EXIT_INVALID_REQUEST = 2
EXIT_EXTERNAL_GATE_REQUIRED = 3
EXIT_CATALOG_UNAVAILABLE = 4


def get_default_service() -> PolyglotSemanticCompilerService:
    """Load the digest-bound catalog; never fall back to the source manifest."""

    return PolyglotSemanticCompilerService()


def _emit(value: Any, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
        return
    if isinstance(value, str):
        print(value)
        return
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _emit_error(message: str, *, as_json: bool, code: str) -> None:
    if as_json:
        _emit({"status": "BLOCKED", "code": code, "message": message}, as_json=True)
    else:
        print(f"BLOCKED [{code}]: {message}", file=sys.stderr)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="elmos-polyglot-compiler",
        description=(
            f"{ENGINE_NAME} v{ENGINE_VERSION}; local control-plane planning only"
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    status = subparsers.add_parser("status", help="Show conservative engine status")
    status.add_argument("--json", action="store_true", help="Output JSON")

    catalog = subparsers.add_parser("catalog", help="List digest-bound Skill records")
    catalog.add_argument(
        "--batch",
        type=str.upper,
        choices=tuple("ABCDEFGHIJKLMNOPQR"),
        help="Filter by exact Batch A-R",
    )
    catalog.add_argument("--json", action="store_true", help="Output JSON")

    routes = subparsers.add_parser("routes", help="List declared, unqualified routes")
    routes.add_argument("--source", help="Filter by exact source surface")
    routes.add_argument("--target", help="Filter by exact target surface")
    routes.add_argument("--route-class", help="Filter by exact route class")
    routes.add_argument("--json", action="store_true", help="Output JSON")

    transform = subparsers.add_parser(
        "transform",
        help="Prepare an external-adapter transformation plan",
    )
    transform.add_argument("--src-lang", required=True, help="Source language")
    transform.add_argument("--tgt-lang", required=True, help="Target language")
    transform.add_argument("--code", required=True, help="Source snippet")
    transform.add_argument("--json", action="store_true", help="Output JSON")

    formal = subparsers.add_parser(
        "formal-check",
        help="Prepare an external SMT proof obligation",
    )
    formal.add_argument("--formula", required=True, help="Formula to content-address")
    formal.add_argument("--solver", required=True, help="Requested solver family")
    formal.add_argument(
        "--timeout-ms",
        type=int,
        required=True,
        help="Requested external solver timeout",
    )
    formal.add_argument("--json", action="store_true", help="Output JSON")

    fuzz = subparsers.add_parser(
        "fuzz-matrix",
        help="Prepare an external differential-fuzz campaign",
    )
    fuzz.add_argument("--src-lang", required=True, help="Source surface")
    fuzz.add_argument("--tgt-lang", required=True, help="Target surface")
    fuzz.add_argument(
        "--iterations",
        type=int,
        required=True,
        help="Requested external case count",
    )
    fuzz.add_argument("--json", action="store_true", help="Output JSON")

    certify = subparsers.add_parser(
        "certify-route",
        help="Prepare a non-certifying route evidence plan",
    )
    certify.add_argument("--route-id", required=True, help="Compiled route ID")
    certify.add_argument("--json", action="store_true", help="Output JSON")
    return parser


def _print_status(value: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        _emit(value, as_json=True)
        return
    counts = value["counts"]
    print(f"{value['engine']} v{value['version']}")
    print(f"Implementation: {value['implementation']}")
    print(f"Catalog: {value['catalog_state']} ({value['catalog_digest']})")
    print(
        "Inventory: "
        f"{counts['skills']} Skills, {counts['route_cells']} routes, "
        f"{counts['reference_routes']} reference plans"
    )
    print(f"External runtime/evidence: {value['external_runtime']}/{value['external_evidence']}")
    print(f"Certification: {value['certification']}")


def _print_catalog(records: list[dict[str, Any]], *, as_json: bool) -> None:
    if as_json:
        _emit(records, as_json=True)
        return
    print(f"Matched Skills: {len(records)}")
    for item in records:
        print(
            f"{item['source_id']}  Batch {item['batch']}  {item['name']}  "
            f"{item['capability_mode']}  external={item['external_runtime']}"
        )


def _print_routes(records: list[dict[str, Any]], *, as_json: bool) -> None:
    if as_json:
        _emit(records, as_json=True)
        return
    print(f"Matched Routes: {len(records)}")
    for item in records:
        print(
            f"{item['route_id']}  {item['source_language']} -> "
            f"{item['target_language']}  {item['route_class']}  {item['status']}"
        )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    as_json = bool(getattr(args, "json", False))
    try:
        service = get_default_service()
    except CatalogError as exc:
        _emit_error(
            str(exc),
            as_json=as_json,
            code="COMPILED_CATALOG_UNAVAILABLE",
        )
        return EXIT_CATALOG_UNAVAILABLE

    try:
        if args.command == "status":
            _print_status(service.get_compiler_status(), as_json=as_json)
            return EXIT_OK

        if args.command == "catalog":
            _print_catalog(
                service.get_catalog_skills(batch=args.batch),
                as_json=as_json,
            )
            return EXIT_OK

        if args.command == "routes":
            routes = service.get_supported_routes()
            if args.source:
                routes = [
                    item
                    for item in routes
                    if item["source_language"].casefold() == args.source.casefold()
                ]
            if args.target:
                routes = [
                    item
                    for item in routes
                    if item["target_language"].casefold() == args.target.casefold()
                ]
            if args.route_class:
                routes = [
                    item
                    for item in routes
                    if item["route_class"].casefold() == args.route_class.casefold()
                ]
            _print_routes(routes, as_json=as_json)
            return EXIT_OK

        if args.command == "transform":
            result = service.transform_snippet(
                args.src_lang,
                args.tgt_lang,
                args.code,
            )
        elif args.command == "formal-check":
            result = service.check_smt_formula(
                args.formula,
                solver_family=args.solver,
                timeout_ms=args.timeout_ms,
            )
        elif args.command == "fuzz-matrix":
            result = service.run_differential_fuzzing(
                args.src_lang,
                args.tgt_lang,
                args.iterations,
            )
        elif args.command == "certify-route":
            result = service.certify_language_route(args.route_id)
        else:  # pragma: no cover - argparse owns the command set
            raise ServiceError("unsupported command")

        _emit(result, as_json=as_json)
        # These commands are execution intent. A local plan is useful output,
        # but NOT_RUN / NOT_CERTIFIED must not be represented by exit status 0.
        if result.get("status") in {NOT_RUN, NOT_CERTIFIED, "EXTERNAL_ADAPTER_REQUIRED"}:
            return EXIT_EXTERNAL_GATE_REQUIRED
        if result.get("external_runtime") == NOT_RUN:
            return EXIT_EXTERNAL_GATE_REQUIRED
        return EXIT_INVALID_REQUEST
    except (CatalogError, ContractError, KeyError, ServiceError, TypeError, ValueError) as exc:
        _emit_error(str(exc), as_json=as_json, code="REQUEST_BLOCKED")
        return EXIT_INVALID_REQUEST


if __name__ == "__main__":
    sys.exit(main())


__all__ = [
    "EXIT_CATALOG_UNAVAILABLE",
    "EXIT_EXTERNAL_GATE_REQUIRED",
    "EXIT_INVALID_REQUEST",
    "EXIT_OK",
    "get_default_service",
    "main",
]

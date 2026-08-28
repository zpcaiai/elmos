from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .commercial import assess_commercial, commercial_capabilities
from .commercial_request import parse_commercial_request_json
from .materialize import materialize
from .models import ParameterContract, TranspileRequest
from .production_qualification import (
    evaluate_production_qualification,
    parse_production_qualification_json,
    parse_production_trust_store_json,
    production_qualification_draft,
    production_qualification_requirements,
    production_trust_store_digest,
)
from .profiles import capabilities
from .qualification import run_qualification
from .runner import (
    RunnerBlockedError,
    runner_capabilities,
    verify_local_matrix,
    verify_route,
)
from .skill_runtime import execute_skill, parse_skill_request_json, skill_capabilities
from .transpiler import transpile


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def _request(path: Path, source: str, target: str, query_id: str | None) -> TranspileRequest:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("request must be a JSON object")
    parameters = tuple(
        ParameterContract(
            name=str(item["name"]),
            logical_type=str(item["logicalType"]),
            nullable=bool(item["nullable"]),
        )
        for item in raw.get("parameters", [])
    )
    return TranspileRequest(
        query_id=query_id or str(raw["queryId"]),
        source_profile=source or str(raw["sourceProfile"]),
        target_profile=target or str(raw["targetProfile"]),
        sql=str(raw["sql"]),
        parameters=parameters,
    )


def _create_only_output(path: Path | None, rendered: str, *, label: str) -> None:
    if path is None:
        sys.stdout.write(rendered)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(rendered)
    except FileExistsError as error:
        raise FileExistsError(f"{label} output already exists") from error


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="elmos-sql-transpiler")
    subparsers = parser.add_subparsers(dest="command", required=True)

    capability_parser = subparsers.add_parser("capabilities")
    capability_parser.add_argument("--output", type=Path)

    commercial_capability_parser = subparsers.add_parser("commercial-capabilities")
    commercial_capability_parser.add_argument("--output", type=Path)

    commercial_assess_parser = subparsers.add_parser("commercial-assess")
    commercial_assess_parser.add_argument("request", type=Path)
    commercial_assess_parser.add_argument("--output", type=Path)

    commercial_skill_capability_parser = subparsers.add_parser("commercial-skill-capabilities")
    commercial_skill_capability_parser.add_argument("--output", type=Path)

    commercial_skill_run_parser = subparsers.add_parser("commercial-skill-run")
    commercial_skill_run_parser.add_argument("skill_id")
    commercial_skill_run_parser.add_argument("request", type=Path)
    commercial_skill_run_parser.add_argument("--output", type=Path)

    production_requirements_parser = subparsers.add_parser(
        "commercial-production-requirements"
    )
    production_requirements_parser.add_argument("--output", type=Path)

    production_template_parser = subparsers.add_parser("commercial-production-template")
    production_template_parser.add_argument("--tenant-id", required=True)
    production_template_parser.add_argument("--project-id", required=True)
    production_template_parser.add_argument("--actor-id", required=True)
    production_template_parser.add_argument("--implementer-organization-id", required=True)
    production_template_parser.add_argument("--output", type=Path)

    production_plan_parser = subparsers.add_parser("commercial-production-plan")
    production_plan_parser.add_argument("request", type=Path)
    production_plan_parser.add_argument("--trust-store", type=Path)
    production_plan_parser.add_argument("--trust-store-digest")
    production_plan_parser.add_argument("--output", type=Path)

    runner_capability_parser = subparsers.add_parser("runner-capabilities")
    runner_capability_parser.add_argument("--output", type=Path)

    transpile_parser = subparsers.add_parser("transpile")
    transpile_parser.add_argument("request", type=Path)
    transpile_parser.add_argument("output", type=Path)
    transpile_parser.add_argument("--source", default="")
    transpile_parser.add_argument("--target", default="")
    transpile_parser.add_argument("--query-id")

    qualification_parser = subparsers.add_parser("qualify")
    qualification_parser.add_argument("corpora", nargs="+", type=Path)
    qualification_parser.add_argument("--output", type=Path)

    verify_parser = subparsers.add_parser("verify-route")
    verify_parser.add_argument("source")
    verify_parser.add_argument("target")
    verify_parser.add_argument("output", type=Path)

    matrix_parser = subparsers.add_parser("verify-local-matrix")
    matrix_parser.add_argument("output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "capabilities":
            value = capabilities()
            rendered = _json(value) + "\n"
            if args.output:
                if args.output.exists():
                    raise FileExistsError("capability output already exists")
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(rendered, encoding="utf-8")
            else:
                sys.stdout.write(rendered)
            return 0
        if args.command == "commercial-capabilities":
            rendered = _json(commercial_capabilities()) + "\n"
            _create_only_output(args.output, rendered, label="commercial capability")
            return 0
        if args.command == "commercial-assess":
            assessment = assess_commercial(parse_commercial_request_json(args.request.read_bytes()))
            rendered = _json(assessment.to_dict()) + "\n"
            _create_only_output(args.output, rendered, label="commercial assessment")
            return 3
        if args.command == "commercial-skill-capabilities":
            rendered = _json(skill_capabilities()) + "\n"
            _create_only_output(args.output, rendered, label="commercial Skill capability")
            return 0
        if args.command == "commercial-skill-run":
            raw_request = parse_skill_request_json(args.request.read_bytes())
            result = execute_skill(args.skill_id, raw_request)
            rendered = _json(result) + "\n"
            _create_only_output(args.output, rendered, label="commercial Skill result")
            return (
                0
                if result["state"]
                in {
                    "LOCAL_COMPLETED",
                    "READY_FOR_HUMAN_DECISION",
                    "READY_FOR_EXTERNAL_GATE",
                }
                else 3
            )
        if args.command == "commercial-production-requirements":
            rendered = _json(production_qualification_requirements()) + "\n"
            _create_only_output(
                args.output,
                rendered,
                label="commercial production requirements",
            )
            return 0
        if args.command == "commercial-production-template":
            draft = production_qualification_draft(
                tenant_id=args.tenant_id,
                project_id=args.project_id,
                actor_id=args.actor_id,
                implementer_organization_id=args.implementer_organization_id,
            )
            _create_only_output(
                args.output,
                _json(draft) + "\n",
                label="commercial production template",
            )
            return 0
        if args.command == "commercial-production-plan":
            if (args.trust_store is None) != (args.trust_store_digest is None):
                raise ValueError(
                    "--trust-store and --trust-store-digest must be supplied together"
                )
            trust_store = None
            if args.trust_store is not None:
                trust_store = parse_production_trust_store_json(args.trust_store.read_bytes())
                observed_digest = production_trust_store_digest(trust_store)
                if observed_digest != args.trust_store_digest:
                    raise ValueError("operator trust store digest does not match the file")
            qualification_request = parse_production_qualification_json(
                args.request.read_bytes()
            )
            result = evaluate_production_qualification(
                qualification_request,
                trust_store=trust_store,
            )
            _create_only_output(
                args.output,
                _json(result) + "\n",
                label="commercial production qualification plan",
            )
            return (
                0
                if result["summary"]["productionDefinitionOfDoneCount"] == 13
                else 3
            )
        if args.command == "runner-capabilities":
            value = runner_capabilities()
            rendered = _json(value) + "\n"
            if args.output:
                if args.output.exists():
                    raise FileExistsError("Runner capability output already exists")
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(rendered, encoding="utf-8")
            else:
                sys.stdout.write(rendered)
            return 0
        if args.command == "transpile":
            request = _request(args.request, args.source, args.target, args.query_id)
            transpilation = transpile(request)
            if transpilation.state != "SYNTAX_READY":
                sys.stderr.write(_json(transpilation.to_dict(include_sql=False)) + "\n")
                return 2
            sys.stdout.write(_json(materialize(transpilation, args.output)) + "\n")
            return 0
        if args.command == "qualify":
            report = run_qualification(args.corpora)
            rendered = _json(report) + "\n"
            if args.output:
                if args.output.exists():
                    raise FileExistsError("qualification output already exists")
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(rendered, encoding="utf-8")
            else:
                sys.stdout.write(rendered)
            return 0 if report["localDecision"] == "READY_FOR_ENGINE_EXECUTION" else 3
        if args.command == "verify-route":
            gate_result = verify_route(args.source, args.target, args.output)
            sys.stdout.write(_json(gate_result) + "\n")
            return 0 if gate_result["localDecision"] == "READY_FOR_EXTERNAL_GATE" else 4
        if args.command == "verify-local-matrix":
            matrix_result = verify_local_matrix(args.output)
            sys.stdout.write(_json(matrix_result) + "\n")
            return 0 if matrix_result["localDecision"] == "READY_FOR_EXTERNAL_GATE" else 4
    except (
        FileExistsError,
        KeyError,
        RunnerBlockedError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as error:
        sys.stderr.write(
            _json(
                {
                    "status": "BLOCKED",
                    "error": type(error).__name__,
                    "message": str(error),
                    "certification": "NOT_CERTIFIED",
                }
            )
            + "\n"
        )
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

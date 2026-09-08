#!/usr/bin/env python3
"""Prepare, execute and verify digest-bound VB6 cross-host route campaigns.

The non-VB6 compiler and the proprietary VB6 compiler cannot share the exact
host profiles used by this repository.  This runner therefore separates their
evidence without separating their inputs: every Windows run consumes the exact
source, emitted target, semantic IR, identifier plan and cases prepared by the
non-VB6 host, then the verifier compares both sides' typed observations.

Passing this campaign is local cross-host engineering evidence only.  It never
sets independent verification or certification to passed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import stat
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
ENGINE_SRC = REPO / "engines" / "polyglot-route-engine" / "src"
sys.path.insert(0, str(ENGINE_SRC))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from route_sets import VB6_EXACT_ROUTE_KEYS, split_route_key  # noqa: E402

from elmos_polyglot_route.emitter import EmittedFile, emit  # noqa: E402
from elmos_polyglot_route.identifier_hygiene import (  # noqa: E402
    IdentifierPlan,
    plan_identifiers,
    target_ir_view,
)
from elmos_polyglot_route.models import Language, RouteError, SemanticIR  # noqa: E402
from elmos_polyglot_route.source_analyzer import analyze  # noqa: E402
from elmos_polyglot_route.validation import validate, validate_source  # noqa: E402

CORPORA = {
    "development": ("", "Pricing", "pricing", "calculate", "behavior-cases.json"),
    "holdout": ("holdout", "Clamp", "clamp", "clamp", "holdout/cases.json"),
    "real-repository": (
        "representative",
        "Difference",
        "difference",
        "difference",
        "representative/cases.json",
    ),
}
EXTENSIONS = {
    "java": "java",
    "python": "py",
    "csharp": "cs",
    "typescript": "ts",
    "go": "go",
    "rust": "rs",
    "cpp": "cpp",
    "objc": "m",
    "swift": "swift",
    "php": "php",
    "kotlin": "kt",
    "react": "tsx",
    "flutter": "dart",
    "vb6": "bas",
}


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_json_bytes(value))


def _compact_non_vb6_side(local_root: Path) -> None:
    """Retain the bound report, not rebuildable compiler output or copied inputs."""

    report = local_root / "side-report.json"
    if report.is_symlink() or not report.is_file():
        raise RouteError("VB6_CAMPAIGN_LOCAL_REPORT_MISSING")
    for child in local_root.iterdir():
        if child == report:
            continue
        if child.is_symlink() or child.is_file():
            child.unlink()
        elif child.is_dir():
            shutil.rmtree(child)
        else:
            raise RouteError("VB6_CAMPAIGN_LOCAL_ARTIFACT_UNSAFE")


def _binding(path: Path, root: Path) -> dict[str, object]:
    resolved_root = root.resolve(strict=True)
    resolved = path.resolve(strict=True)
    try:
        relative = resolved.relative_to(resolved_root).as_posix()
    except ValueError as error:
        raise RouteError("VB6_CAMPAIGN_ARTIFACT_PATH_ESCAPE") from error
    metadata = path.lstat()
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise RouteError("VB6_CAMPAIGN_ARTIFACT_UNSAFE")
    content = path.read_bytes()
    return {
        "path": relative,
        "bytes": len(content),
        "sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
    }


def _read_bound(root: Path, binding: dict[str, Any]) -> bytes:
    relative = binding.get("path")
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise RouteError("VB6_CAMPAIGN_ARTIFACT_BINDING_INVALID")
    candidate = root / relative
    try:
        candidate.resolve(strict=True).relative_to(root.resolve(strict=True))
    except (OSError, ValueError) as error:
        raise RouteError("VB6_CAMPAIGN_ARTIFACT_PATH_ESCAPE") from error
    observed = _binding(candidate, root)
    if observed != binding:
        raise RouteError("VB6_CAMPAIGN_ARTIFACT_DIGEST_MISMATCH")
    return candidate.read_bytes()


def _fixture(fixtures: Path, corpus: str, language: str) -> tuple[Path, Path, str]:
    directory, class_name, module_name, function_name, cases_relative = CORPORA[corpus]
    source_name = class_name if language in {"java", "csharp"} else module_name
    source = fixtures / directory / language / f"{source_name}.{EXTENSIONS[language]}"
    cases = fixtures / cases_relative
    if not source.is_file() or not cases.is_file():
        raise RouteError(f"VB6_CAMPAIGN_FIXTURE_MISSING:{corpus}:{language}")
    return source, cases, function_name


def _validate_route_key(route_key: str) -> tuple[Language, Language]:
    if route_key not in VB6_EXACT_ROUTE_KEYS:
        raise RouteError(f"VB6_CAMPAIGN_ROUTE_NOT_ALLOWED:{route_key}")
    source, target = split_route_key(route_key)
    return source, target  # type: ignore[return-value]


def prepare(repo: Path, route_key: str, output: Path) -> dict[str, Any]:
    source_language, target_language = _validate_route_key(route_key)
    if output.exists() or output.is_symlink():
        raise RouteError("VB6_CAMPAIGN_OUTPUT_ALREADY_EXISTS")
    output.mkdir(parents=True)
    fixtures = repo / "engines" / "polyglot-route-engine" / "fixtures"
    corpus_records: list[dict[str, Any]] = []
    for corpus in CORPORA:
        source, cases_path, function_name = _fixture(fixtures, corpus, source_language)
        corpus_root = output / corpus
        inputs = corpus_root / "inputs"
        inputs.mkdir(parents=True)
        source_copy = inputs / source.name
        cases_copy = inputs / "cases.json"
        shutil.copy2(source, source_copy)
        shutil.copy2(cases_path, cases_copy)
        semantic = analyze(source_copy, source_language, function_name)
        identifier_plan = plan_identifiers(semantic, target_language)
        target_semantic = target_ir_view(semantic, identifier_plan)
        emitted = emit(semantic, target_language, identifier_plan=identifier_plan)
        emitted_path = inputs / emitted.relative_path
        emitted_path.write_text(emitted.content, encoding="utf-8")
        semantic_path = inputs / "semantic-ir.json"
        plan_path = inputs / "identifier-plan.json"
        _write_json(semantic_path, semantic.to_mapping())
        _write_json(plan_path, identifier_plan.to_mapping())
        cases = json.loads(cases_copy.read_text(encoding="utf-8"))
        if not isinstance(cases, list) or not cases:
            raise RouteError(f"VB6_CAMPAIGN_CASES_INVALID:{corpus}")
        local_root = corpus_root / "non-vb6-side"
        if source_language == "vb6":
            local_report = validate(
                emitted,
                target_language,
                target_semantic.functions[0],
                cases,
                local_root,
            )
            local_role = "target"
        else:
            local_report = validate_source(
                source_copy,
                source_language,
                semantic.functions[0],
                cases,
                local_root,
            )
            local_role = "source"
        local_report_path = local_root / "side-report.json"
        _write_json(local_report_path, local_report)
        _compact_non_vb6_side(local_root)
        artifacts = [
            _binding(path, output)
            for path in (
                source_copy,
                cases_copy,
                emitted_path,
                semantic_path,
                plan_path,
                local_report_path,
            )
        ]
        corpus_records.append(
            {
                "corpus": corpus,
                "function_name": function_name,
                "local_role": local_role,
                "artifacts": artifacts,
            }
        )
    manifest = {
        "schema_version": 1,
        "kind": "elmos.vb6-cross-host-campaign-request",
        "route_key": route_key,
        "source_language": source_language,
        "target_language": target_language,
        "corpora": corpus_records,
        "prepared_side_status": "PASSED_LOCAL",
        "windows_vb6_side_status": "NOT_RUN",
        "independent_verification_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
    }
    _write_json(output / "campaign-request.json", manifest)
    return manifest


def _load_request(request_root: Path) -> dict[str, Any]:
    request_path = request_root / "campaign-request.json"
    if request_path.is_symlink() or not request_path.is_file():
        raise RouteError("VB6_CAMPAIGN_REQUEST_MISSING")
    request = json.loads(request_path.read_text(encoding="utf-8"))
    if (
        not isinstance(request, dict)
        or request.get("kind") != "elmos.vb6-cross-host-campaign-request"
        or request.get("windows_vb6_side_status") != "NOT_RUN"
        or request.get("independent_verification_status") != "NOT_RUN"
        or request.get("certification_status") != "NOT_CERTIFIED"
        or request.get("prepared_side_status") != "PASSED_LOCAL"
    ):
        raise RouteError("VB6_CAMPAIGN_REQUEST_INVALID")
    source_language, target_language = _validate_route_key(str(request.get("route_key", "")))
    if (
        request.get("source_language") != source_language
        or request.get("target_language") != target_language
    ):
        raise RouteError("VB6_CAMPAIGN_REQUEST_ROUTE_BINDING_INVALID")
    corpora = request.get("corpora")
    if not isinstance(corpora, list) or {
        str(item.get("corpus", "")) for item in corpora if isinstance(item, dict)
    } != set(CORPORA):
        raise RouteError("VB6_CAMPAIGN_REQUEST_CORPUS_SET_INVALID")
    expected_local_role = "target" if source_language == "vb6" else "source"
    for corpus in corpora:
        if (
            not isinstance(corpus, dict)
            or corpus.get("local_role") != expected_local_role
            or not isinstance(corpus.get("artifacts"), list)
            or len(corpus["artifacts"]) != 6
        ):
            raise RouteError("VB6_CAMPAIGN_REQUEST_CORPUS_INVALID")
        for artifact in corpus["artifacts"]:
            if not isinstance(artifact, dict):
                raise RouteError("VB6_CAMPAIGN_REQUEST_ARTIFACT_SET_INVALID")
            _read_bound(request_root, artifact)
        local_report_binding = next(
            (
                item
                for item in corpus["artifacts"]
                if str(item.get("path", "")).endswith("side-report.json")
            ),
            None,
        )
        if not isinstance(local_report_binding, dict):
            raise RouteError("VB6_CAMPAIGN_REQUEST_LOCAL_REPORT_MISSING")
        local_report = json.loads(_read_bound(request_root, local_report_binding))
        if (
            local_report.get("status") != "PASSED"
            or local_report.get("language")
            != (target_language if source_language == "vb6" else source_language)
        ):
            raise RouteError("VB6_CAMPAIGN_REQUEST_LOCAL_REPORT_INVALID")
    return request


def execute_windows(request_root: Path, output: Path) -> dict[str, Any]:
    request = _load_request(request_root)
    source_language, target_language = _validate_route_key(str(request["route_key"]))
    if output.exists() or output.is_symlink():
        raise RouteError("VB6_CAMPAIGN_OUTPUT_ALREADY_EXISTS")
    output.mkdir(parents=True)
    run_records: list[dict[str, Any]] = []
    for raw in request.get("corpora", []):
        if not isinstance(raw, dict) or not isinstance(raw.get("artifacts"), list):
            raise RouteError("VB6_CAMPAIGN_REQUEST_INVALID")
        bindings = {
            Path(str(item.get("path", ""))).name: item
            for item in raw["artifacts"]
            if isinstance(item, dict)
        }
        semantic = SemanticIR.from_mapping(
            json.loads(_read_bound(request_root, bindings["semantic-ir.json"]))
        )
        plan = IdentifierPlan.from_mapping(
            json.loads(_read_bound(request_root, bindings["identifier-plan.json"]))
        )
        cases = json.loads(_read_bound(request_root, bindings["cases.json"]))
        target_semantic = target_ir_view(semantic, plan)
        corpus = str(raw.get("corpus", ""))
        run_root = output / corpus
        if target_language == "vb6":
            target_binding = next(
                item
                for item in raw["artifacts"]
                if isinstance(item, dict) and str(item.get("path", "")).endswith("migrated.bas")
            )
            emitted = EmittedFile("migrated.bas", _read_bound(request_root, target_binding).decode())
            report = validate(
                emitted,
                "vb6",
                target_semantic.functions[0],
                cases,
                run_root,
            )
        else:
            source_binding = next(
                item
                for item in raw["artifacts"]
                if isinstance(item, dict) and str(item.get("path", "")).endswith(".bas")
            )
            source_bytes = _read_bound(request_root, source_binding)
            source_path = run_root / Path(str(source_binding["path"])).name
            run_root.mkdir(parents=True, exist_ok=True)
            source_path.write_bytes(source_bytes)
            report = validate_source(
                source_path,
                "vb6",
                semantic.functions[0],
                cases,
                run_root / "validation",
            )
        report_path = run_root / "vb6-side-report.json"
        _write_json(report_path, report)
        artifacts = [
            _binding(path, output)
            for path in sorted(output.rglob("*"))
            if path.is_file() and not path.is_symlink()
        ]
        run_records.append(
            {
                "corpus": corpus,
                "status": "PASSED_LOCAL",
                "report": _binding(report_path, output),
                "artifact_count": len(artifacts),
                "artifacts": artifacts,
            }
        )
    receipt = {
        "schema_version": 1,
        "kind": "elmos.vb6-cross-host-windows-receipt",
        "route_key": request["route_key"],
        "request_sha256": "sha256:"
        + hashlib.sha256((request_root / "campaign-request.json").read_bytes()).hexdigest(),
        "runs": run_records,
        "windows_vb6_side_status": "PASSED_LOCAL",
        "evidence_class": "GOVERNED_EXTERNAL_SELF_ATTESTED",
        "independent_verification_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
    }
    _write_json(output / "windows-receipt.json", receipt)
    return receipt


def verify(request_root: Path, windows_root: Path, output: Path) -> dict[str, Any]:
    request = _load_request(request_root)
    receipt_path = windows_root / "windows-receipt.json"
    if receipt_path.is_symlink() or not receipt_path.is_file():
        raise RouteError("VB6_CAMPAIGN_WINDOWS_RECEIPT_MISSING")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    expected_request_sha256 = "sha256:" + hashlib.sha256(
        (request_root / "campaign-request.json").read_bytes()
    ).hexdigest()
    if (
        not isinstance(receipt, dict)
        or receipt.get("kind") != "elmos.vb6-cross-host-windows-receipt"
        or receipt.get("route_key") != request.get("route_key")
        or receipt.get("request_sha256") != expected_request_sha256
        or receipt.get("windows_vb6_side_status") != "PASSED_LOCAL"
        or receipt.get("evidence_class") != "GOVERNED_EXTERNAL_SELF_ATTESTED"
        or receipt.get("independent_verification_status") != "NOT_RUN"
        or receipt.get("certification_status") != "NOT_CERTIFIED"
    ):
        raise RouteError("VB6_CAMPAIGN_WINDOWS_RECEIPT_INVALID")
    local_by_corpus = {str(item["corpus"]): item for item in request["corpora"]}
    comparisons: list[dict[str, object]] = []
    for run in receipt.get("runs", []):
        if not isinstance(run, dict) or run.get("status") != "PASSED_LOCAL":
            raise RouteError("VB6_CAMPAIGN_WINDOWS_RUN_INVALID")
        corpus = str(run.get("corpus", ""))
        local = local_by_corpus.get(corpus)
        if local is None:
            raise RouteError("VB6_CAMPAIGN_CORPUS_MISMATCH")
        report_binding = run.get("report")
        if not isinstance(report_binding, dict):
            raise RouteError("VB6_CAMPAIGN_WINDOWS_RUN_INVALID")
        artifacts = run.get("artifacts")
        if (
            not isinstance(artifacts, list)
            or run.get("artifact_count") != len(artifacts)
            or not artifacts
        ):
            raise RouteError("VB6_CAMPAIGN_WINDOWS_ARTIFACT_SET_INVALID")
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                raise RouteError("VB6_CAMPAIGN_WINDOWS_ARTIFACT_SET_INVALID")
            _read_bound(windows_root, artifact)
        windows_report = json.loads(_read_bound(windows_root, report_binding))
        local_report_binding = next(
            item
            for item in local["artifacts"]
            if str(item.get("path", "")).endswith("side-report.json")
        )
        local_report = json.loads(_read_bound(request_root, local_report_binding))
        if (
            windows_report.get("status") != "PASSED"
            or local_report.get("status") != "PASSED"
            or windows_report.get("observations") != local_report.get("observations")
        ):
            raise RouteError(f"VB6_CAMPAIGN_BEHAVIOR_MISMATCH:{corpus}")
        comparisons.append({"corpus": corpus, "status": "MATCH"})
    if set(item["corpus"] for item in comparisons) != set(CORPORA):
        raise RouteError("VB6_CAMPAIGN_CORPUS_SET_INCOMPLETE")
    result = {
        "schema_version": 1,
        "kind": "elmos.vb6-cross-host-verification",
        "route_key": request["route_key"],
        "status": "PASSED_LOCAL_CROSS_HOST",
        "comparisons": comparisons,
        "independent_verification_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
    }
    _write_json(output, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--repo-root", default=str(REPO))
    prepare_parser.add_argument("--route", required=True, choices=VB6_EXACT_ROUTE_KEYS)
    prepare_parser.add_argument("--output", type=Path, required=True)
    prepare_set_parser = subparsers.add_parser("prepare-set")
    prepare_set_parser.add_argument("--repo-root", default=str(REPO))
    prepare_set_parser.add_argument("--output-root", type=Path, required=True)
    execute_parser = subparsers.add_parser("execute-windows")
    execute_parser.add_argument("--request", type=Path, required=True)
    execute_parser.add_argument("--output", type=Path, required=True)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--request", type=Path, required=True)
    verify_parser.add_argument("--windows-output", type=Path, required=True)
    verify_parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            result = prepare(Path(args.repo_root).resolve(), args.route, args.output.resolve())
        elif args.command == "prepare-set":
            output_root = args.output_root.resolve()
            output_root.mkdir(parents=True, exist_ok=True)
            prepared: list[str] = []
            reused: list[str] = []
            for route_key in VB6_EXACT_ROUTE_KEYS:
                route_output = output_root / route_key
                if route_output.exists():
                    existing = _load_request(route_output)
                    if existing.get("route_key") != route_key:
                        raise RouteError(
                            f"VB6_CAMPAIGN_RESUME_ROUTE_MISMATCH:{route_key}"
                        )
                    for corpus_name in CORPORA:
                        _compact_non_vb6_side(
                            route_output / corpus_name / "non-vb6-side"
                        )
                    reused.append(route_key)
                else:
                    prepare(Path(args.repo_root).resolve(), route_key, route_output)
                    prepared.append(route_key)
            result = {
                "schema_version": 1,
                "kind": "elmos.vb6-cross-host-prepare-set-result",
                "route_count": len(VB6_EXACT_ROUTE_KEYS),
                "prepared": prepared,
                "reused": reused,
                "windows_vb6_side_status": "NOT_RUN",
                "independent_verification_status": "NOT_RUN",
                "certification_status": "NOT_CERTIFIED",
            }
            result["requests"] = [
                {
                    "route_key": route_key,
                    **_binding(
                        output_root / route_key / "campaign-request.json",
                        output_root,
                    ),
                }
                for route_key in VB6_EXACT_ROUTE_KEYS
            ]
            _write_json(output_root / "prepare-set-result.json", result)
        elif args.command == "execute-windows":
            result = execute_windows(args.request.resolve(), args.output.resolve())
        else:
            result = verify(
                args.request.resolve(),
                args.windows_output.resolve(),
                args.output.resolve(),
            )
    except (OSError, KeyError, StopIteration, ValueError, RouteError) as error:
        print(json.dumps({"status": "BLOCKED", "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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
import os
import shutil
import stat
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
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


def _has_exact_keys(value: object, expected: frozenset[str]) -> bool:
    return isinstance(value, dict) and set(value) == expected


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_json_bytes(value))


def _safe_parent(path: Path) -> Path:
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    if parent.is_symlink() or not parent.is_dir():
        raise RouteError("VB6_CAMPAIGN_OUTPUT_PARENT_UNSAFE")
    return parent


@contextmanager
def _atomic_directory(output: Path) -> Iterator[Path]:
    """Build beside the destination and publish only a complete result."""

    if output.exists() or output.is_symlink():
        raise RouteError("VB6_CAMPAIGN_OUTPUT_ALREADY_EXISTS")
    parent = _safe_parent(output)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.staging-", dir=parent))
    try:
        yield staging
        if output.exists() or output.is_symlink():
            raise RouteError("VB6_CAMPAIGN_OUTPUT_ALREADY_EXISTS")
        staging.replace(output)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _write_json_new(path: Path, value: object) -> None:
    if path.exists() or path.is_symlink():
        raise RouteError("VB6_CAMPAIGN_OUTPUT_ALREADY_EXISTS")
    parent = _safe_parent(path)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.staging-", dir=parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(_json_bytes(value))
            handle.flush()
            os.fsync(handle.fileno())
        if path.exists() or path.is_symlink():
            raise RouteError("VB6_CAMPAIGN_OUTPUT_ALREADY_EXISTS")
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


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


def _file_identity(metadata: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_nlink,
    )


def _snapshot(path: Path, root: Path) -> tuple[dict[str, object], bytes]:
    lexical_root = Path(os.path.abspath(root))
    lexical_path = Path(os.path.abspath(path))
    try:
        lexical_relative = lexical_path.relative_to(lexical_root)
    except ValueError as error:
        raise RouteError("VB6_CAMPAIGN_ARTIFACT_PATH_ESCAPE") from error
    lexical_candidate = lexical_root
    if lexical_candidate.is_symlink():
        raise RouteError("VB6_CAMPAIGN_ARTIFACT_PATH_ESCAPE")
    for part in lexical_relative.parts[:-1]:
        lexical_candidate /= part
        if lexical_candidate.is_symlink() or not lexical_candidate.is_dir():
            raise RouteError("VB6_CAMPAIGN_ARTIFACT_PATH_ESCAPE")

    resolved_root = root.resolve(strict=True)
    resolved = path.resolve(strict=True)
    try:
        relative = resolved.relative_to(resolved_root).as_posix()
    except ValueError as error:
        raise RouteError("VB6_CAMPAIGN_ARTIFACT_PATH_ESCAPE") from error
    candidate = resolved_root
    for part in Path(relative).parts[:-1]:
        candidate /= part
        if candidate.is_symlink() or not candidate.is_dir():
            raise RouteError("VB6_CAMPAIGN_ARTIFACT_PATH_ESCAPE")
    before = path.lstat()
    if path.is_symlink() or not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        raise RouteError("VB6_CAMPAIGN_ARTIFACT_UNSAFE")
    with path.open("rb") as handle:
        opened_before = os.fstat(handle.fileno())
        content = handle.read()
        opened_after = os.fstat(handle.fileno())
    after = path.lstat()
    if (
        _file_identity(before) != _file_identity(opened_before)
        or _file_identity(opened_before) != _file_identity(opened_after)
        or _file_identity(opened_after) != _file_identity(after)
        or len(content) != after.st_size
        or path.is_symlink()
    ):
        raise RouteError("VB6_CAMPAIGN_ARTIFACT_CHANGED_DURING_READ")
    return (
        {
            "path": relative,
            "bytes": len(content),
            "sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
        },
        content,
    )


def _binding(path: Path, root: Path) -> dict[str, object]:
    binding, _content = _snapshot(path, root)
    return binding


def _read_bound(root: Path, binding: dict[str, Any]) -> bytes:
    relative = binding.get("path")
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise RouteError("VB6_CAMPAIGN_ARTIFACT_BINDING_INVALID")
    candidate = root / relative
    try:
        candidate.resolve(strict=True).relative_to(root.resolve(strict=True))
    except (OSError, ValueError) as error:
        raise RouteError("VB6_CAMPAIGN_ARTIFACT_PATH_ESCAPE") from error
    observed, content = _snapshot(candidate, root)
    if observed != binding:
        raise RouteError("VB6_CAMPAIGN_ARTIFACT_DIGEST_MISMATCH")
    return content


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


def _artifact_roles(
    request_root: Path,
    corpus: dict[str, Any],
    source_language: Language,
    target_language: Language,
) -> dict[str, dict[str, Any]]:
    corpus_name = str(corpus.get("corpus", ""))
    expected_function = CORPORA.get(corpus_name, ("", "", "", "", ""))[3]
    artifacts = corpus.get("artifacts")
    if (
        corpus_name not in CORPORA
        or not _has_exact_keys(
            corpus,
            frozenset({"corpus", "function_name", "local_role", "artifacts"}),
        )
        or corpus.get("function_name") != expected_function
        or not isinstance(artifacts, list)
        or len(artifacts) != 6
    ):
        raise RouteError("VB6_CAMPAIGN_REQUEST_CORPUS_INVALID")
    by_path: dict[str, dict[str, Any]] = {}
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise RouteError("VB6_CAMPAIGN_REQUEST_ARTIFACT_SET_INVALID")
        relative = artifact.get("path")
        if not isinstance(relative, str) or relative in by_path:
            raise RouteError("VB6_CAMPAIGN_REQUEST_ARTIFACT_SET_INVALID")
        _read_bound(request_root, artifact)
        by_path[relative] = artifact

    inputs_prefix = f"{corpus_name}/inputs/"
    fixed = {
        "cases": f"{inputs_prefix}cases.json",
        "semantic_ir": f"{inputs_prefix}semantic-ir.json",
        "identifier_plan": f"{inputs_prefix}identifier-plan.json",
        "local_report": f"{corpus_name}/non-vb6-side/side-report.json",
    }
    if not set(fixed.values()).issubset(by_path):
        raise RouteError("VB6_CAMPAIGN_REQUEST_ARTIFACT_ROLE_INVALID")
    program_paths = set(by_path) - set(fixed.values())
    if len(program_paths) != 2 or any(
        not value.startswith(inputs_prefix) for value in program_paths
    ):
        raise RouteError("VB6_CAMPAIGN_REQUEST_ARTIFACT_ROLE_INVALID")
    source_paths = [
        value
        for value in program_paths
        if value.endswith(f".{EXTENSIONS[source_language]}")
    ]
    target_paths = [
        value
        for value in program_paths
        if value.endswith(f".{EXTENSIONS[target_language]}")
    ]
    if len(source_paths) != 1 or len(target_paths) != 1:
        raise RouteError("VB6_CAMPAIGN_REQUEST_ARTIFACT_ROLE_INVALID")
    roles = {name: by_path[value] for name, value in fixed.items()}
    roles["source"] = by_path[source_paths[0]]
    roles["emitted_target"] = by_path[target_paths[0]]
    return roles


def _prepare_unpublished(
    repo: Path, route_key: str, output: Path
) -> dict[str, Any]:
    source_language, target_language = _validate_route_key(route_key)
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


def prepare(repo: Path, route_key: str, output: Path) -> dict[str, Any]:
    with _atomic_directory(output) as staging:
        manifest = _prepare_unpublished(repo, route_key, staging)
    return manifest


def _load_request(request_root: Path) -> dict[str, Any]:
    request_path = request_root / "campaign-request.json"
    if request_path.is_symlink() or not request_path.is_file():
        raise RouteError("VB6_CAMPAIGN_REQUEST_MISSING")
    _request_binding, request_bytes = _snapshot(request_path, request_root)
    request = json.loads(request_bytes)
    if (
        not isinstance(request, dict)
        or not _has_exact_keys(
            request,
            frozenset(
                {
                    "schema_version",
                    "kind",
                    "route_key",
                    "source_language",
                    "target_language",
                    "corpora",
                    "prepared_side_status",
                    "windows_vb6_side_status",
                    "independent_verification_status",
                    "certification_status",
                }
            ),
        )
        or request.get("schema_version") != 1
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
    if not isinstance(corpora, list) or [
        item.get("corpus") if isinstance(item, dict) else None for item in corpora
    ] != list(CORPORA):
        raise RouteError("VB6_CAMPAIGN_REQUEST_CORPUS_SET_INVALID")
    expected_local_role = "target" if source_language == "vb6" else "source"
    for corpus in corpora:
        if (
            not isinstance(corpus, dict)
            or corpus.get("local_role") != expected_local_role
        ):
            raise RouteError("VB6_CAMPAIGN_REQUEST_CORPUS_INVALID")
        roles = _artifact_roles(
            request_root, corpus, source_language, target_language
        )
        semantic = SemanticIR.from_mapping(
            json.loads(_read_bound(request_root, roles["semantic_ir"]))
        )
        plan = IdentifierPlan.from_mapping(
            json.loads(_read_bound(request_root, roles["identifier_plan"]))
        )
        if (
            semantic.source_language != source_language
            or plan.target_language != target_language
            or len(semantic.functions) != 1
            or semantic.functions[0].name != corpus.get("function_name")
        ):
            raise RouteError("VB6_CAMPAIGN_REQUEST_SEMANTIC_BINDING_INVALID")
        target_ir_view(semantic, plan)
        local_report = json.loads(_read_bound(request_root, roles["local_report"]))
        if (
            local_report.get("status") != "PASSED"
            or local_report.get("language")
            != (target_language if source_language == "vb6" else source_language)
        ):
            raise RouteError("VB6_CAMPAIGN_REQUEST_LOCAL_REPORT_INVALID")
    return request


def _execute_windows_unpublished(
    request_root: Path, output: Path
) -> dict[str, Any]:
    request = _load_request(request_root)
    source_language, target_language = _validate_route_key(str(request["route_key"]))
    run_records: list[dict[str, Any]] = []
    for raw in request.get("corpora", []):
        if not isinstance(raw, dict) or not isinstance(raw.get("artifacts"), list):
            raise RouteError("VB6_CAMPAIGN_REQUEST_INVALID")
        bindings = _artifact_roles(
            request_root, raw, source_language, target_language
        )
        semantic = SemanticIR.from_mapping(
            json.loads(_read_bound(request_root, bindings["semantic_ir"]))
        )
        plan = IdentifierPlan.from_mapping(
            json.loads(_read_bound(request_root, bindings["identifier_plan"]))
        )
        cases = json.loads(_read_bound(request_root, bindings["cases"]))
        target_semantic = target_ir_view(semantic, plan)
        corpus = str(raw.get("corpus", ""))
        run_root = output / corpus
        if target_language == "vb6":
            target_binding = bindings["emitted_target"]
            emitted = EmittedFile("migrated.bas", _read_bound(request_root, target_binding).decode())
            report = validate(
                emitted,
                "vb6",
                target_semantic.functions[0],
                cases,
                run_root,
            )
        else:
            source_binding = bindings["source"]
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
            for path in sorted(run_root.rglob("*"))
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
        "request_sha256": _request_sha256(request_root),
        "runs": run_records,
        "windows_vb6_side_status": "PASSED_LOCAL",
        "evidence_class": "GOVERNED_EXTERNAL_SELF_ATTESTED",
        "independent_verification_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
    }
    _write_json(output / "windows-receipt.json", receipt)
    return receipt


def execute_windows(request_root: Path, output: Path) -> dict[str, Any]:
    with _atomic_directory(output) as staging:
        receipt = _execute_windows_unpublished(request_root, staging)
    return receipt


def _request_sha256(request_root: Path) -> str:
    _binding_value, content = _snapshot(
        request_root / "campaign-request.json", request_root
    )
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _load_windows_receipt(
    request_root: Path, windows_root: Path, request: dict[str, Any]
) -> dict[str, Any]:
    receipt_path = windows_root / "windows-receipt.json"
    if receipt_path.is_symlink() or not receipt_path.is_file():
        raise RouteError("VB6_CAMPAIGN_WINDOWS_RECEIPT_MISSING")
    _receipt_binding, receipt_bytes = _snapshot(receipt_path, windows_root)
    receipt = json.loads(receipt_bytes)
    if (
        not isinstance(receipt, dict)
        or not _has_exact_keys(
            receipt,
            frozenset(
                {
                    "schema_version",
                    "kind",
                    "route_key",
                    "request_sha256",
                    "runs",
                    "windows_vb6_side_status",
                    "evidence_class",
                    "independent_verification_status",
                    "certification_status",
                }
            ),
        )
        or receipt.get("schema_version") != 1
        or receipt.get("kind") != "elmos.vb6-cross-host-windows-receipt"
        or receipt.get("route_key") != request.get("route_key")
        or receipt.get("request_sha256") != _request_sha256(request_root)
        or receipt.get("windows_vb6_side_status") != "PASSED_LOCAL"
        or receipt.get("evidence_class") != "GOVERNED_EXTERNAL_SELF_ATTESTED"
        or receipt.get("independent_verification_status") != "NOT_RUN"
        or receipt.get("certification_status") != "NOT_CERTIFIED"
    ):
        raise RouteError("VB6_CAMPAIGN_WINDOWS_RECEIPT_INVALID")
    runs = receipt.get("runs")
    if not isinstance(runs, list) or [
        item.get("corpus") if isinstance(item, dict) else None for item in runs
    ] != list(CORPORA):
        raise RouteError("VB6_CAMPAIGN_WINDOWS_RUN_SET_INVALID")
    for run in runs:
        if (
            not isinstance(run, dict)
            or not _has_exact_keys(
                run,
                frozenset(
                    {"corpus", "status", "report", "artifact_count", "artifacts"}
                ),
            )
            or run.get("status") != "PASSED_LOCAL"
        ):
            raise RouteError("VB6_CAMPAIGN_WINDOWS_RUN_INVALID")
        corpus = str(run.get("corpus", ""))
        report_binding = run.get("report")
        artifacts = run.get("artifacts")
        if (
            not isinstance(report_binding, dict)
            or not isinstance(artifacts, list)
            or run.get("artifact_count") != len(artifacts)
            or not artifacts
            or report_binding not in artifacts
        ):
            raise RouteError("VB6_CAMPAIGN_WINDOWS_ARTIFACT_SET_INVALID")
        paths: set[str] = set()
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                raise RouteError("VB6_CAMPAIGN_WINDOWS_ARTIFACT_SET_INVALID")
            relative = artifact.get("path")
            if (
                not isinstance(relative, str)
                or relative in paths
                or not relative.startswith(f"{corpus}/")
            ):
                raise RouteError("VB6_CAMPAIGN_WINDOWS_ARTIFACT_SET_INVALID")
            paths.add(relative)
            _read_bound(windows_root, artifact)
        if report_binding.get("path") != f"{corpus}/vb6-side-report.json":
            raise RouteError("VB6_CAMPAIGN_WINDOWS_RUN_INVALID")
        report = json.loads(_read_bound(windows_root, report_binding))
        if report.get("status") != "PASSED" or report.get("language") != "vb6":
            raise RouteError("VB6_CAMPAIGN_WINDOWS_RUN_INVALID")
    return receipt


def verify(request_root: Path, windows_root: Path, output: Path) -> dict[str, Any]:
    request = _load_request(request_root)
    source_language, target_language = _validate_route_key(str(request["route_key"]))
    receipt = _load_windows_receipt(request_root, windows_root, request)
    local_by_corpus = {str(item["corpus"]): item for item in request["corpora"]}
    comparisons: list[dict[str, object]] = []
    for run in receipt["runs"]:
        corpus = str(run.get("corpus", ""))
        local = local_by_corpus.get(corpus)
        if local is None:
            raise RouteError("VB6_CAMPAIGN_CORPUS_MISMATCH")
        report_binding = run.get("report")
        if not isinstance(report_binding, dict):
            raise RouteError("VB6_CAMPAIGN_WINDOWS_RUN_INVALID")
        windows_report = json.loads(_read_bound(windows_root, report_binding))
        local_roles = _artifact_roles(
            request_root, local, source_language, target_language
        )
        local_report = json.loads(
            _read_bound(request_root, local_roles["local_report"])
        )
        if (
            windows_report.get("status") != "PASSED"
            or local_report.get("status") != "PASSED"
            or windows_report.get("observations") != local_report.get("observations")
        ):
            raise RouteError(f"VB6_CAMPAIGN_BEHAVIOR_MISMATCH:{corpus}")
        comparisons.append({"corpus": corpus, "status": "MATCH"})
    if [item["corpus"] for item in comparisons] != list(CORPORA):
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
    _write_json_new(output, result)
    return result


def _binding_from_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": record.get("path"),
        "bytes": record.get("bytes"),
        "sha256": record.get("sha256"),
    }


def _valid_route_partition(
    result: dict[str, Any], first: str, second: str
) -> bool:
    left = result.get(first)
    right = result.get(second)
    if not isinstance(left, list) or not isinstance(right, list):
        return False
    combined = [*left, *right]
    if any(not isinstance(item, str) for item in combined):
        return False
    return (
        len(combined) == len(VB6_EXACT_ROUTE_KEYS)
        and len(set(combined)) == len(combined)
        and set(combined) == set(VB6_EXACT_ROUTE_KEYS)
    )


def _load_prepare_set(request_root: Path) -> dict[str, Any]:
    result_path = request_root / "prepare-set-result.json"
    if result_path.is_symlink() or not result_path.is_file():
        raise RouteError("VB6_CAMPAIGN_PREPARE_SET_MISSING")
    _result_binding, result_bytes = _snapshot(result_path, request_root)
    result = json.loads(result_bytes)
    requests = result.get("requests") if isinstance(result, dict) else None
    request_keys = [
        item.get("route_key") if isinstance(item, dict) else None
        for item in requests or []
    ]
    if (
        not isinstance(result, dict)
        or not _has_exact_keys(
            result,
            frozenset(
                {
                    "schema_version",
                    "kind",
                    "route_count",
                    "prepared",
                    "reused",
                    "requests",
                    "windows_vb6_side_status",
                    "independent_verification_status",
                    "certification_status",
                }
            ),
        )
        or result.get("schema_version") != 1
        or result.get("kind") != "elmos.vb6-cross-host-prepare-set-result"
        or result.get("route_count") != len(VB6_EXACT_ROUTE_KEYS)
        or result.get("windows_vb6_side_status") != "NOT_RUN"
        or result.get("independent_verification_status") != "NOT_RUN"
        or result.get("certification_status") != "NOT_CERTIFIED"
        or not _valid_route_partition(result, "prepared", "reused")
        or not isinstance(requests, list)
        or request_keys != list(VB6_EXACT_ROUTE_KEYS)
    ):
        raise RouteError("VB6_CAMPAIGN_PREPARE_SET_INVALID")
    for route_key, record in zip(VB6_EXACT_ROUTE_KEYS, requests, strict=True):
        if not _has_exact_keys(
            record, frozenset({"route_key", "path", "bytes", "sha256"})
        ):
            raise RouteError("VB6_CAMPAIGN_PREPARE_SET_INVALID")
        binding = _binding_from_record(record)
        if binding["path"] != f"{route_key}/campaign-request.json":
            raise RouteError("VB6_CAMPAIGN_PREPARE_SET_ROUTE_BINDING_INVALID")
        _read_bound(request_root, binding)
        request = _load_request(request_root / route_key)
        if request.get("route_key") != route_key:
            raise RouteError("VB6_CAMPAIGN_PREPARE_SET_ROUTE_BINDING_INVALID")
    return result


def prepare_set(repo: Path, output_root: Path) -> dict[str, Any]:
    if output_root.is_symlink():
        raise RouteError("VB6_CAMPAIGN_OUTPUT_PARENT_UNSAFE")
    output_root.mkdir(parents=True, exist_ok=True)
    if not output_root.is_dir():
        raise RouteError("VB6_CAMPAIGN_OUTPUT_PARENT_UNSAFE")
    result_path = output_root / "prepare-set-result.json"
    if result_path.exists() or result_path.is_symlink():
        return _load_prepare_set(output_root)
    prepared: list[str] = []
    reused: list[str] = []
    for route_key in VB6_EXACT_ROUTE_KEYS:
        route_output = output_root / route_key
        if route_output.exists() or route_output.is_symlink():
            if route_output.is_symlink() or not route_output.is_dir():
                raise RouteError("VB6_CAMPAIGN_PREPARE_SET_ROUTE_OUTPUT_UNSAFE")
            existing = _load_request(route_output)
            if existing.get("route_key") != route_key:
                raise RouteError(f"VB6_CAMPAIGN_RESUME_ROUTE_MISMATCH:{route_key}")
            reused.append(route_key)
        else:
            prepare(repo, route_key, route_output)
            prepared.append(route_key)
    result = {
        "schema_version": 1,
        "kind": "elmos.vb6-cross-host-prepare-set-result",
        "route_count": len(VB6_EXACT_ROUTE_KEYS),
        "prepared": prepared,
        "reused": reused,
        "requests": [
            {
                "route_key": route_key,
                **_binding(
                    output_root / route_key / "campaign-request.json",
                    output_root,
                ),
            }
            for route_key in VB6_EXACT_ROUTE_KEYS
        ],
        "windows_vb6_side_status": "NOT_RUN",
        "independent_verification_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
    }
    _write_json_new(result_path, result)
    return result


def _load_windows_set(request_root: Path, windows_root: Path) -> dict[str, Any]:
    result_path = windows_root / "windows-set-result.json"
    if result_path.is_symlink() or not result_path.is_file():
        raise RouteError("VB6_CAMPAIGN_WINDOWS_SET_MISSING")
    _result_binding, result_bytes = _snapshot(result_path, windows_root)
    result = json.loads(result_bytes)
    receipts = result.get("receipts") if isinstance(result, dict) else None
    receipt_keys = [
        item.get("route_key") if isinstance(item, dict) else None
        for item in receipts or []
    ]
    if (
        not isinstance(result, dict)
        or not _has_exact_keys(
            result,
            frozenset(
                {
                    "schema_version",
                    "kind",
                    "route_count",
                    "completed",
                    "reused",
                    "receipts",
                    "windows_vb6_side_status",
                    "evidence_class",
                    "independent_verification_status",
                    "certification_status",
                }
            ),
        )
        or result.get("schema_version") != 1
        or result.get("kind") != "elmos.vb6-cross-host-windows-set-result"
        or result.get("route_count") != len(VB6_EXACT_ROUTE_KEYS)
        or result.get("windows_vb6_side_status") != "PASSED_LOCAL"
        or result.get("evidence_class") != "GOVERNED_EXTERNAL_SELF_ATTESTED"
        or result.get("independent_verification_status") != "NOT_RUN"
        or result.get("certification_status") != "NOT_CERTIFIED"
        or not _valid_route_partition(result, "completed", "reused")
        or not isinstance(receipts, list)
        or receipt_keys != list(VB6_EXACT_ROUTE_KEYS)
    ):
        raise RouteError("VB6_CAMPAIGN_WINDOWS_SET_INVALID")
    for route_key, record in zip(VB6_EXACT_ROUTE_KEYS, receipts, strict=True):
        if not _has_exact_keys(
            record, frozenset({"route_key", "path", "bytes", "sha256"})
        ):
            raise RouteError("VB6_CAMPAIGN_WINDOWS_SET_INVALID")
        binding = _binding_from_record(record)
        if binding["path"] != f"{route_key}/windows-receipt.json":
            raise RouteError("VB6_CAMPAIGN_WINDOWS_SET_ROUTE_BINDING_INVALID")
        _read_bound(windows_root, binding)
        request = _load_request(request_root / route_key)
        _load_windows_receipt(request_root / route_key, windows_root / route_key, request)
    return result


def execute_windows_set(request_root: Path, output_root: Path) -> dict[str, Any]:
    _load_prepare_set(request_root)
    if output_root.is_symlink():
        raise RouteError("VB6_CAMPAIGN_OUTPUT_PARENT_UNSAFE")
    output_root.mkdir(parents=True, exist_ok=True)
    if not output_root.is_dir():
        raise RouteError("VB6_CAMPAIGN_OUTPUT_PARENT_UNSAFE")
    result_path = output_root / "windows-set-result.json"
    if result_path.exists() or result_path.is_symlink():
        return _load_windows_set(request_root, output_root)
    completed: list[str] = []
    reused: list[str] = []
    for route_key in VB6_EXACT_ROUTE_KEYS:
        route_output = output_root / route_key
        request = _load_request(request_root / route_key)
        if route_output.exists() or route_output.is_symlink():
            if route_output.is_symlink() or not route_output.is_dir():
                raise RouteError("VB6_CAMPAIGN_WINDOWS_SET_ROUTE_OUTPUT_UNSAFE")
            _load_windows_receipt(request_root / route_key, route_output, request)
            reused.append(route_key)
        else:
            execute_windows(request_root / route_key, route_output)
            completed.append(route_key)
    result = {
        "schema_version": 1,
        "kind": "elmos.vb6-cross-host-windows-set-result",
        "route_count": len(VB6_EXACT_ROUTE_KEYS),
        "completed": completed,
        "reused": reused,
        "receipts": [
            {
                "route_key": route_key,
                **_binding(
                    output_root / route_key / "windows-receipt.json", output_root
                ),
            }
            for route_key in VB6_EXACT_ROUTE_KEYS
        ],
        "windows_vb6_side_status": "PASSED_LOCAL",
        "evidence_class": "GOVERNED_EXTERNAL_SELF_ATTESTED",
        "independent_verification_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
    }
    _write_json_new(result_path, result)
    return result


def _load_verification(path: Path, route_key: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise RouteError("VB6_CAMPAIGN_VERIFICATION_MISSING")
    _binding_value, content = _snapshot(path, path.parent)
    result = json.loads(content)
    comparisons = result.get("comparisons") if isinstance(result, dict) else None
    if (
        not isinstance(result, dict)
        or not _has_exact_keys(
            result,
            frozenset(
                {
                    "schema_version",
                    "kind",
                    "route_key",
                    "status",
                    "comparisons",
                    "independent_verification_status",
                    "certification_status",
                }
            ),
        )
        or result.get("schema_version") != 1
        or result.get("kind") != "elmos.vb6-cross-host-verification"
        or result.get("route_key") != route_key
        or result.get("status") != "PASSED_LOCAL_CROSS_HOST"
        or result.get("independent_verification_status") != "NOT_RUN"
        or result.get("certification_status") != "NOT_CERTIFIED"
        or not isinstance(comparisons, list)
        or [
            item.get("corpus") if isinstance(item, dict) else None
            for item in comparisons
        ]
        != list(CORPORA)
        or any(
            not _has_exact_keys(item, frozenset({"corpus", "status"}))
            or item.get("status") != "MATCH"
            for item in comparisons
        )
    ):
        raise RouteError("VB6_CAMPAIGN_VERIFICATION_INVALID")
    return result


def _load_verification_set(output_root: Path) -> dict[str, Any]:
    result_path = output_root / "verification-set-result.json"
    if result_path.is_symlink() or not result_path.is_file():
        raise RouteError("VB6_CAMPAIGN_VERIFICATION_SET_MISSING")
    _binding_value, content = _snapshot(result_path, output_root)
    result = json.loads(content)
    results = result.get("results") if isinstance(result, dict) else None
    result_keys = [
        item.get("route_key") if isinstance(item, dict) else None
        for item in results or []
    ]
    if (
        not isinstance(result, dict)
        or not _has_exact_keys(
            result,
            frozenset(
                {
                    "schema_version",
                    "kind",
                    "route_count",
                    "completed",
                    "reused",
                    "results",
                    "status",
                    "independent_verification_status",
                    "certification_status",
                }
            ),
        )
        or result.get("schema_version") != 1
        or result.get("kind") != "elmos.vb6-cross-host-verification-set-result"
        or result.get("route_count") != len(VB6_EXACT_ROUTE_KEYS)
        or result.get("status") != "PASSED_LOCAL_CROSS_HOST"
        or result.get("independent_verification_status") != "NOT_RUN"
        or result.get("certification_status") != "NOT_CERTIFIED"
        or not _valid_route_partition(result, "completed", "reused")
        or not isinstance(results, list)
        or result_keys != list(VB6_EXACT_ROUTE_KEYS)
    ):
        raise RouteError("VB6_CAMPAIGN_VERIFICATION_SET_INVALID")
    for route_key, record in zip(VB6_EXACT_ROUTE_KEYS, results, strict=True):
        if not _has_exact_keys(
            record, frozenset({"route_key", "path", "bytes", "sha256"})
        ):
            raise RouteError("VB6_CAMPAIGN_VERIFICATION_SET_INVALID")
        binding = _binding_from_record(record)
        if binding["path"] != f"{route_key}.json":
            raise RouteError("VB6_CAMPAIGN_VERIFICATION_SET_ROUTE_BINDING_INVALID")
        _read_bound(output_root, binding)
        _load_verification(output_root / f"{route_key}.json", route_key)
    return result


def verify_set(
    request_root: Path, windows_root: Path, output_root: Path
) -> dict[str, Any]:
    _load_prepare_set(request_root)
    _load_windows_set(request_root, windows_root)
    if output_root.is_symlink():
        raise RouteError("VB6_CAMPAIGN_OUTPUT_PARENT_UNSAFE")
    output_root.mkdir(parents=True, exist_ok=True)
    if not output_root.is_dir():
        raise RouteError("VB6_CAMPAIGN_OUTPUT_PARENT_UNSAFE")
    result_path = output_root / "verification-set-result.json"
    if result_path.exists() or result_path.is_symlink():
        return _load_verification_set(output_root)
    completed: list[str] = []
    reused: list[str] = []
    for route_key in VB6_EXACT_ROUTE_KEYS:
        route_output = output_root / f"{route_key}.json"
        if route_output.exists() or route_output.is_symlink():
            _load_verification(route_output, route_key)
            reused.append(route_key)
        else:
            verify(
                request_root / route_key,
                windows_root / route_key,
                route_output,
            )
            completed.append(route_key)
    result = {
        "schema_version": 1,
        "kind": "elmos.vb6-cross-host-verification-set-result",
        "route_count": len(VB6_EXACT_ROUTE_KEYS),
        "completed": completed,
        "reused": reused,
        "results": [
            {
                "route_key": route_key,
                **_binding(output_root / f"{route_key}.json", output_root),
            }
            for route_key in VB6_EXACT_ROUTE_KEYS
        ],
        "status": "PASSED_LOCAL_CROSS_HOST",
        "independent_verification_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
    }
    _write_json_new(result_path, result)
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
    execute_set_parser = subparsers.add_parser("execute-windows-set")
    execute_set_parser.add_argument("--request-root", type=Path, required=True)
    execute_set_parser.add_argument("--output-root", type=Path, required=True)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--request", type=Path, required=True)
    verify_parser.add_argument("--windows-output", type=Path, required=True)
    verify_parser.add_argument("--output", type=Path, required=True)
    verify_set_parser = subparsers.add_parser("verify-set")
    verify_set_parser.add_argument("--request-root", type=Path, required=True)
    verify_set_parser.add_argument("--windows-output-root", type=Path, required=True)
    verify_set_parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            result = prepare(Path(args.repo_root).resolve(), args.route, args.output.resolve())
        elif args.command == "prepare-set":
            result = prepare_set(
                Path(args.repo_root).resolve(), args.output_root.resolve()
            )
        elif args.command == "execute-windows":
            result = execute_windows(args.request.resolve(), args.output.resolve())
        elif args.command == "execute-windows-set":
            result = execute_windows_set(
                args.request_root.resolve(), args.output_root.resolve()
            )
        elif args.command == "verify":
            result = verify(
                args.request.resolve(),
                args.windows_output.resolve(),
                args.output.resolve(),
            )
        else:
            result = verify_set(
                args.request_root.resolve(),
                args.windows_output_root.resolve(),
                args.output_root.resolve(),
            )
    except (OSError, KeyError, StopIteration, ValueError, RouteError) as error:
        print(json.dumps({"status": "BLOCKED", "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

from elmos_project_synthesis.cleanup import cleanup_acceptance_directory
from elmos_project_synthesis.intake import approve_request, create_draft
from elmos_project_synthesis.models import SUPPORTED_LANGUAGES
from elmos_project_synthesis.project_graphs import validate_workspace_graphs
from elmos_project_synthesis.verification import verify_workspace
from elmos_project_synthesis.workspace import generate_workspace

_TEMPORARY_PREFIX = "elmos-project-synthesis-"
_ACCEPTANCE_DESCRIPTION = "生成用于创建、查询和跟踪维修工单的八语言 API 服务。"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run exact local starter-profile acceptance.")
    parser.add_argument(
        "--language",
        action="append",
        choices=SUPPORTED_LANGUAGES,
        dest="languages",
        help="Verify only this language; repeat for multiple targets. Defaults to all supported targets.",
    )
    parser.add_argument(
        "--require-all-toolchains",
        action="store_true",
        help="Return non-zero when any selected exact toolchain is unavailable.",
    )
    return parser.parse_args()


def _approved_request(languages: tuple[str, ...]) -> dict[str, Any]:
    return approve_request(
        create_draft(
            name="work-order-service",
            description=_ACCEPTANCE_DESCRIPTION,
            entity="work_order",
            languages=languages,
        ),
        actor="acceptance:local",
        approved_at="2026-07-22T00:00:00+00:00",
    )


def _failure_result(*, language: str, kind: str, error: BaseException | str) -> dict[str, Any]:
    detail = error if isinstance(error, str) else f"{type(error).__name__}:{error}"
    return {
        "language": language,
        "kind": kind,
        "command": [],
        "status": "FAILED",
        "exit_code": None,
        "output": str(detail)[-12_000:],
    }


def _cleanup(directory: Path) -> str | None:
    try:
        return cleanup_acceptance_directory(
            directory,
            expected_prefix=_TEMPORARY_PREFIX,
        )
    except Exception as error:  # pragma: no cover - defensive boundary around the cleanup gate
        return f"{type(error).__name__}:{error}"


def _new_temporary_directory(*, suffix: str) -> Path:
    return Path(tempfile.mkdtemp(prefix=f"{_TEMPORARY_PREFIX}{suffix}-"))


def _aggregate_status(results: list[dict[str, Any]]) -> str:
    statuses = {str(item.get("status")) for item in results}
    if "FAILED" in statuses:
        return "FAILED"
    if "NOT_RUN" in statuses or not statuses:
        return "PARTIAL"
    return "PASSED"


def _language_matrix(
    selected_languages: tuple[str, ...],
    results: list[dict[str, Any]],
    exact_toolchains: dict[str, bool],
) -> dict[str, dict[str, object]]:
    matrix: dict[str, dict[str, object]] = {}
    for language in selected_languages:
        checks = [item for item in results if item.get("language") == language]
        statuses = {str(item.get("status")) for item in checks}
        startup = next(
            (item for item in checks if item.get("kind") == "startup-probe"),
            None,
        )
        matrix[language] = {
            "status": (
                "FAILED"
                if "FAILED" in statuses
                else "NOT_RUN"
                if not checks or "NOT_RUN" in statuses or startup is None
                else "PASSED"
            ),
            "exact_toolchain": exact_toolchains.get(language, False),
            "startup_probe": startup.get("status") if isinstance(startup, dict) else "NOT_RUN",
        }
    return matrix


def run_acceptance(
    selected_languages: tuple[str, ...],
    *,
    require_all_toolchains: bool,
) -> dict[str, Any]:
    """Run bounded acceptance without co-locating native build products.

    The complete selected-target workspace is generated and its content-addressed
    structure/dependency graphs and manifest are validated before any native tool
    executes. It is then removed. Each target is generated and verified in its own
    temporary workspace, which is cleaned before the next target starts.
    """
    results: list[dict[str, Any]] = []
    exact_toolchains: dict[str, bool] = {}
    cleanup_failures: list[tuple[Path, str]] = []
    generated_file_count = 0
    workspace_graph_status = "NOT_RUN"
    graph_ready = False

    complete_temporary: Path | None = None
    try:
        complete_temporary = _new_temporary_directory(suffix="complete")
        complete_workspace = complete_temporary / "workspace"
        manifest = generate_workspace(
            _approved_request(selected_languages),
            complete_workspace,
        )
        generated_file_count = int(manifest["file_count"])
        validate_workspace_graphs(complete_workspace)
        workspace_graph_status = "PASSED"
        graph_ready = True
    except Exception as error:
        workspace_graph_status = "FAILED"
        results.append(
            _failure_result(
                language="workspace",
                kind="generation-graph-validation",
                error=error,
            )
        )
    finally:
        if complete_temporary is not None:
            cleanup_error = _cleanup(complete_temporary)
            if cleanup_error is not None:
                cleanup_failures.append((complete_temporary, cleanup_error))
                results.append(
                    _failure_result(
                        language="workspace",
                        kind="acceptance-cleanup",
                        error=cleanup_error,
                    )
                )

    # A failed graph/manifest preflight or a workspace that could not be removed
    # blocks native execution. This both fails closed and prevents an existing
    # temporary tree from compounding disk pressure.
    if graph_ready and not cleanup_failures:
        for language in selected_languages:
            language_temporary: Path | None = None
            try:
                language_temporary = _new_temporary_directory(suffix=language)
                language_workspace = language_temporary / "workspace"
                generate_workspace(
                    _approved_request((language,)),
                    language_workspace,
                )
                evidence = verify_workspace(
                    language_workspace,
                    use_ephemeral_runtime_ports=True,
                )
                evidence_results = evidence.get("results")
                environment = evidence.get("environment")
                if not isinstance(evidence_results, list) or not isinstance(environment, dict):
                    raise RuntimeError("ACCEPTANCE_EVIDENCE_INVALID")
                exact = environment.get("exact_toolchain_match")
                if not isinstance(exact, dict) or not isinstance(exact.get(language), bool):
                    raise RuntimeError("ACCEPTANCE_TOOLCHAIN_EVIDENCE_INVALID")
                if any(not isinstance(item, dict) for item in evidence_results):
                    raise RuntimeError("ACCEPTANCE_RESULT_INVALID")
                results.extend(evidence_results)
                exact_toolchains[language] = bool(exact[language])
            except Exception as error:
                results.append(
                    _failure_result(
                        language=language,
                        kind="isolated-workspace-verification",
                        error=error,
                    )
                )
            finally:
                if language_temporary is not None:
                    cleanup_error = _cleanup(language_temporary)
                    if cleanup_error is not None:
                        cleanup_failures.append((language_temporary, cleanup_error))
                        results.append(
                            _failure_result(
                                language=language,
                                kind="acceptance-cleanup",
                                error=cleanup_error,
                            )
                        )
            if cleanup_failures:
                break

    status = _aggregate_status(results)
    result: dict[str, Any] = {
        "status": status,
        "acceptance_mode": "require-all-toolchains" if require_all_toolchains else "available-toolchains",
        "execution_strategy": "sequential-isolated-workspaces",
        "workspace_graph_status": workspace_graph_status,
        "generated_file_count": generated_file_count,
        "build_and_analysis_count": sum(
            item.get("language") in selected_languages
            and item.get("kind")
            not in {
                "startup-probe",
                "acceptance-cleanup",
                "isolated-workspace-verification",
            }
            for item in results
        ),
        "language_matrix": _language_matrix(selected_languages, results, exact_toolchains),
        "startup_probes": [
            {
                "port": item["port"],
                "status": item["status"],
                "response": item["response"],
            }
            for item in results
            if item.get("kind") == "startup-probe"
        ],
        "failures": [
            {
                "language": item.get("language", "workspace"),
                "kind": item.get("kind", "unknown"),
                "command": item.get("command", []),
                "exit_code": item.get("exit_code"),
                "output": str(item.get("output", ""))[-4_000:],
            }
            for item in results
            if item.get("status") == "FAILED"
        ],
        "production_delivery_status": "NOT_RUN",
        "external_certification_status": "NOT_RUN",
        "cleanup_status": "FAILED" if cleanup_failures else "PASSED",
    }
    if cleanup_failures:
        cleanup_path, cleanup_error = cleanup_failures[0]
        result["cleanup_error"] = cleanup_error
        result["cleanup_path"] = str(cleanup_path)
        result["status"] = "FAILED"
    return result


def _exit_code(result: dict[str, Any], *, require_all_toolchains: bool) -> int:
    if result["status"] == "FAILED":
        return 1
    if require_all_toolchains and result["status"] != "PASSED":
        return 2
    return 0


def main() -> int:
    arguments = parse_args()
    selected_languages = tuple(arguments.languages or SUPPORTED_LANGUAGES)
    result = run_acceptance(
        selected_languages,
        require_all_toolchains=arguments.require_all_toolchains,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return _exit_code(result, require_all_toolchains=arguments.require_all_toolchains)


if __name__ == "__main__":
    raise SystemExit(main())

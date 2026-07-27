#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from elmos_project_synthesis.cleanup import cleanup_acceptance_directory
from elmos_project_synthesis.intake import approve_request, create_draft
from elmos_project_synthesis.models import SUPPORTED_LANGUAGES
from elmos_project_synthesis.verification import verify_workspace
from elmos_project_synthesis.workspace import generate_workspace


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


def main() -> int:
    arguments = parse_args()
    selected_languages = tuple(arguments.languages or SUPPORTED_LANGUAGES)
    request = approve_request(
        create_draft(
            name="work-order-service",
            description="生成用于创建、查询和跟踪维修工单的八语言 API 服务。",
            entity="work_order",
            languages=selected_languages,
        ),
        actor="acceptance:local",
        approved_at="2026-07-22T00:00:00+00:00",
    )
    temporary = Path(tempfile.mkdtemp(prefix="elmos-project-synthesis-"))
    cleanup_error: str | None = None
    try:
        workspace = temporary / "workspace"
        manifest = generate_workspace(request, workspace)
        evidence = verify_workspace(workspace)
    finally:
        cleanup_error = cleanup_acceptance_directory(
            temporary,
            expected_prefix="elmos-project-synthesis-",
        )
    language_matrix: dict[str, dict[str, object]] = {}
    for language in selected_languages:
        checks = [item for item in evidence["results"] if item.get("language") == language]
        statuses = {str(item.get("status")) for item in checks}
        startup = next(
            (item for item in checks if item.get("kind") == "startup-probe"),
            None,
        )
        language_matrix[language] = {
            "status": (
                "FAILED"
                if "FAILED" in statuses
                else "NOT_RUN"
                if not checks or "NOT_RUN" in statuses or startup is None
                else "PASSED"
            ),
            "exact_toolchain": evidence["environment"]["exact_toolchain_match"].get(language, False),
            "startup_probe": startup.get("status") if isinstance(startup, dict) else "NOT_RUN",
        }
    result = {
        "status": evidence["status"],
        "acceptance_mode": "require-all-toolchains" if arguments.require_all_toolchains else "available-toolchains",
        "generated_file_count": manifest["file_count"],
        "build_and_analysis_count": sum(item.get("kind") != "startup-probe" for item in evidence["results"]),
        "language_matrix": language_matrix,
        "startup_probes": [
            {"port": item["port"], "status": item["status"], "response": item["response"]}
            for item in evidence["results"]
            if item.get("kind") == "startup-probe"
        ],
        "failures": [
            {
                "language": item["language"],
                "kind": item["kind"],
                "command": item["command"],
                "exit_code": item["exit_code"],
                "output": str(item.get("output", ""))[-4_000:],
            }
            for item in evidence["results"]
            if item.get("status") == "FAILED"
        ],
        "production_delivery_status": evidence["production_delivery_status"],
        "external_certification_status": evidence["external_certification_status"],
        "cleanup_status": "PASSED" if cleanup_error is None else "FAILED",
    }
    if cleanup_error is not None:
        result["cleanup_error"] = cleanup_error
        result["cleanup_path"] = str(temporary)
        result["status"] = "FAILED"
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if result["status"] == "FAILED":
        return 1
    if arguments.require_all_toolchains and result["status"] != "PASSED":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

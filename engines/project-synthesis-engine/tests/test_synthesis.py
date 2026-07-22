from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from elmos_project_synthesis.intake import approve_request, create_draft
from elmos_project_synthesis.models import RequestValidationError, SynthesisRequest
from elmos_project_synthesis.workspace import WorkspaceConflictError, generate_workspace, render_workspace


def approved_request() -> dict[str, object]:
    draft = create_draft(
        name="work-order-service",
        description="维修工单创建、查询和健康检查服务。",
        entity="work_order",
    )
    return approve_request(draft, actor="user:test", approved_at="2026-07-22T00:00:00+00:00")


def test_natural_language_draft_keeps_questions_explicit() -> None:
    draft = create_draft(name="orders", description="管理订单", entity=None)
    assert draft["approval"] == {"status": "DRAFT"}
    assert draft["open_questions"]
    with pytest.raises(ValueError, match="OPEN_QUESTIONS_BLOCK_APPROVAL"):
        approve_request(draft, actor="user:test")


def test_approval_is_hash_bound_and_tampering_blocks_generation() -> None:
    request = approved_request()
    parsed = SynthesisRequest.from_mapping(request)
    assert parsed.project_name == "work-order-service"
    request["project"]["description"] = "tampered"  # type: ignore[index]
    with pytest.raises(RequestValidationError, match="APPROVED_BASELINE_HASH_MISMATCH"):
        SynthesisRequest.from_mapping(request)


def test_renders_complete_language_projects_with_fail_closed_claims() -> None:
    parsed = SynthesisRequest.from_mapping(approved_request())
    files = render_workspace(parsed)
    expected = {
        "java/pom.xml",
        "java/src/main/resources/application.yml",
        "java/Dockerfile",
        "python/pyproject.toml",
        "python/requirements.lock",
        "python/Dockerfile",
        "dotnet/Directory.Build.props",
        "dotnet/Directory.Packages.props",
        "dotnet/Dockerfile",
        "docker-compose.yml",
        "requirements/psir.json",
        "requirements/project-blueprint.json",
        ".elmos/generation-manifest.json",
    }
    assert expected <= set(files)
    manifest = json.loads(files[".elmos/generation-manifest.json"])
    assert manifest["status"] == "GENERATED"
    assert manifest["production_delivery_status"] == "NOT_RUN"
    assert manifest["certification_status"] == "NOT_CERTIFIED"
    assert len(manifest["files"]) == len(files) - 1
    assert all(entry["sha256"] for entry in manifest["files"])
    for path in ("java/openapi.yaml", "python/openapi.yaml", "dotnet/openapi.yaml"):
        openapi = yaml.safe_load(files[path])
        assert openapi["openapi"] == "3.1.0"
        create_schema = openapi["components"]["schemas"]["WorkOrderCreate"]
        assert "id" not in create_schema["required"]


def test_generation_is_idempotent_and_never_overwrites_modified_managed_files(tmp_path: Path) -> None:
    output = tmp_path / "generated"
    first = generate_workspace(approved_request(), output)
    second = generate_workspace(approved_request(), output)
    assert first["request_sha256"] == second["request_sha256"]
    assert first["file_count"] == second["file_count"]

    managed = output / "java" / "pom.xml"
    managed.write_text("user change", encoding="utf-8")
    with pytest.raises(WorkspaceConflictError, match="MANAGED_FILE_MODIFIED"):
        generate_workspace(approved_request(), output)


def test_nonempty_unmanaged_output_is_rejected(tmp_path: Path) -> None:
    output = tmp_path / "existing"
    output.mkdir()
    (output / "README.md").write_text("owned by user", encoding="utf-8")
    with pytest.raises(WorkspaceConflictError, match="NONEMPTY_UNMANAGED_OUTPUT_REJECTED"):
        generate_workspace(approved_request(), output)

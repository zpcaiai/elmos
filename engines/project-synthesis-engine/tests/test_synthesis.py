from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from elmos_project_synthesis.cli import main
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


def test_draft_normalizes_short_names_and_preserves_explicit_namespace() -> None:
    draft = create_draft(
        name="A",
        description="A bounded service",
        entity="item",
        namespace="io.elmos.items",
        languages=("python",),
    )
    assert draft["project"]["name"] == "a-service"
    assert draft["project"]["namespace"] == "io.elmos.items"
    assert [target["language"] for target in draft["targets"]] == ["python"]
    with pytest.raises(ValueError, match="TARGETS_REQUIRED"):
        create_draft(name="items", description="service", entity="item", languages=())
    with pytest.raises(RequestValidationError, match="PROJECT_NAMESPACE_INVALID"):
        create_draft(name="items", description="service", entity="item", namespace="Invalid Namespace")


def test_approval_requires_an_accountable_actor_and_utc_capable_timestamp() -> None:
    draft = create_draft(name="items", description="service", entity="item")
    with pytest.raises(ValueError, match="APPROVER_INVALID"):
        approve_request(draft, actor=" ")
    with pytest.raises(ValueError, match="APPROVED_AT_TIMEZONE_REQUIRED"):
        approve_request(draft, actor="user:test", approved_at="2026-07-22T00:00:00")


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


def test_changed_approved_baseline_requires_a_new_output_directory(tmp_path: Path) -> None:
    output = tmp_path / "generated"
    generate_workspace(approved_request(), output)
    changed = create_draft(
        name="work-order-service",
        description="A materially different approved baseline",
        entity="work_order",
    )
    changed = approve_request(changed, actor="user:test", approved_at="2026-07-22T00:01:00+00:00")
    with pytest.raises(WorkspaceConflictError, match="REQUEST_BASELINE_CHANGED_REQUIRES_NEW_OUTPUT"):
        generate_workspace(changed, output)


def test_nonempty_unmanaged_output_is_rejected(tmp_path: Path) -> None:
    output = tmp_path / "existing"
    output.mkdir()
    (output / "README.md").write_text("owned by user", encoding="utf-8")
    with pytest.raises(WorkspaceConflictError, match="NONEMPTY_UNMANAGED_OUTPUT_REJECTED"):
        generate_workspace(approved_request(), output)


def test_cli_draft_accepts_namespace_and_writes_atomically(tmp_path: Path) -> None:
    output = tmp_path / "request.json"
    assert main([
        "draft",
        "--name", "inventory-service",
        "--description", "Inventory API",
        "--entity", "inventory_item",
        "--namespace", "io.elmos.inventory",
        "--language", "java",
        "--output", str(output),
    ]) == 0
    request = json.loads(output.read_text(encoding="utf-8"))
    assert request["project"]["namespace"] == "io.elmos.inventory"
    assert not list(tmp_path.glob("*.tmp"))

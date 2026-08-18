from __future__ import annotations

import json
import zipfile
from pathlib import Path

from elmos_project_synthesis.cli import _archive_workspace
from elmos_project_synthesis.intake import approve_request, create_draft
from elmos_project_synthesis.models import SynthesisRequest
from elmos_project_synthesis.project_documentation import DOCUMENT_SOURCE_REFS
from elmos_project_synthesis.workspace import generate_workspace, render_workspace


def _approved_postgresql_request() -> dict[str, object]:
    draft = create_draft(
        name="commerce-docs-service",
        description="管理客户与订单；内容包含 <script>alert('x')</script> 和 | 表格字符。",
        entities=(
            {
                "singular": "customer",
                "plural": "customers",
                "fields": [{"name": "display_name", "type": "string", "required": True}],
            },
            {
                "singular": "order",
                "plural": "orders",
                "fields": [
                    {"name": "customer_id", "type": "string", "required": True},
                    {"name": "total", "type": "number", "required": True},
                ],
            },
        ),
        relations=(
            {
                "source": "order",
                "target": "customer",
                "source_field": "customer_id",
                "target_field": "id",
                "kind": "many-to-one",
                "required": True,
            },
        ),
        business_rules=(
            {
                "id": "BR-ORDER-TOTAL",
                "statement": "Order total must be non-negative.",
                "enforcement": "database",
                "predicate": {
                    "type": "field-comparison",
                    "entity": "order",
                    "field": "total",
                    "operator": "gte",
                    "value": 0,
                },
            },
        ),
        languages=("python",),
        persistence="postgresql",
        auth_mode="jwt",
        permissions=tuple(
            {
                "actor": "api_user",
                "action": action,
                "resource": resource,
                "effect": "allow",
            }
            for resource in ("customer", "order")
            for action in ("create", "read", "update", "delete")
        ),
    )
    return approve_request(
        draft,
        actor="user:documentation-reviewer",
        approved_at="2026-07-28T08:00:00+08:00",
    )


def _approved_in_memory_request() -> dict[str, object]:
    draft = create_draft(
        name="notes-docs-service",
        description="管理任务笔记。",
        entity="note",
        languages=("python",),
    )
    return approve_request(
        draft,
        actor="user:documentation-reviewer",
        approved_at="2026-07-28T00:00:00+00:00",
    )


def test_every_approved_task_renders_traceable_markdown_document_pack() -> None:
    request = SynthesisRequest.from_mapping(_approved_postgresql_request())
    files = render_workspace(request)

    assert set(DOCUMENT_SOURCE_REFS) <= set(files)
    manifest = json.loads(files[".elmos/generation-manifest.json"])
    assert manifest["engine_version"] == "1.4.0"
    assert manifest["documentation"] == {
        "status": "GENERATED_REVIEW_REQUIRED",
        "external_review_status": "NOT_RUN",
        "paths": sorted(DOCUMENT_SOURCE_REFS),
    }
    entries = {entry["path"]: entry for entry in manifest["files"]}
    for path, source_refs in DOCUMENT_SOURCE_REFS.items():
        assert entries[path]["source_refs"] == list(source_refs)
        assert request.raw["approval"]["approved_payload_sha256"] in files[path]
        assert "NOT_RUN" in files[path]
        for line in files[path].splitlines():
            if line.lstrip().startswith(("#", "|")):
                assert line == line.lstrip(), f"{path} contains an accidentally indented Markdown block"

    architecture = files["docs/ARCHITECTURE.md"]
    assert "`python` | `fastapi` | `3.12`" in architecture
    assert "<script>" not in architecture
    assert "&lt;script&gt;" in architecture
    assert "\\| 表格字符" in architecture

    database = files["docs/DATABASE_DESIGN.md"]
    assert "`order` → `app.orders`" in database
    assert "| `customer_id` | `string` | `uuid` | 否 | 租户内外键成员 |" in database
    assert "`current_setting('app.tenant_id', true)`" in database
    assert "`database/migrations/001_initial.sql`" in database
    assert "BR-ORDER-TOTAL" in database

    migration = files["docs/MIGRATION_GUIDE.md"]
    assert "`GENERATED_NOT_APPLIED`" in migration
    assert "生产数据迁移" in migration
    assert "逐字段对账" in migration

    history = files["docs/CHANGE_HISTORY.md"]
    assert "`2026-07-28T00:00:00+00:00`" in history
    assert "user:documentation-reviewer" in history
    assert request.request_hash in history

    asset_graph = json.loads(files["requirements/asset-graph.json"])
    document_nodes = {
        node["path"]: node["status"]
        for node in asset_graph["nodes"]
        if node["path"].startswith("docs/")
    }
    assert document_nodes == {
        path: "GENERATED_REVIEW_REQUIRED"
        for path in DOCUMENT_SOURCE_REFS
    }


def test_in_memory_tasks_keep_physical_database_and_migration_status_not_applicable() -> None:
    request = SynthesisRequest.from_mapping(_approved_in_memory_request())

    first = render_workspace(request)
    second = render_workspace(request)

    assert first == second
    database = first["docs/DATABASE_DESIGN.md"]
    migration = first["docs/MIGRATION_GUIDE.md"]
    assert "| 物理数据库设计 | `NOT_APPLICABLE` |" in database
    assert "`app.notes`" not in database
    assert "tenant_id" not in database
    assert "当前内存配置没有实现数据库级租户隔离" in database
    assert "物理数据库迁移为 `NOT_APPLICABLE`" in migration
    assert "database/migrations/001_initial.sql" not in first


def test_markdown_document_pack_is_in_the_download_archive(tmp_path: Path) -> None:
    workspace = tmp_path / "generated-task"
    archive = tmp_path / "generated-task.zip"
    generate_workspace(_approved_in_memory_request(), workspace)

    result = _archive_workspace(workspace, archive)

    assert result["status"] == "ARCHIVED"
    with zipfile.ZipFile(archive) as bundle:
        archived = set(bundle.namelist())
    assert {
        f"notes-docs-service/{path}"
        for path in DOCUMENT_SOURCE_REFS
    } <= archived

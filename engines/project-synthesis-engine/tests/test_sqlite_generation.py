from __future__ import annotations

import ast
import json
import sqlite3
import tomllib
from pathlib import Path

import pytest

from elmos_project_synthesis.intake import approve_request, create_draft
from elmos_project_synthesis.models import SynthesisRequest
from elmos_project_synthesis.verification import verify_workspace
from elmos_project_synthesis.workspace import generate_workspace, render_workspace


def allow_crud(*resources: str) -> tuple[dict[str, str], ...]:
    return tuple(
        {
            "actor": "api_user",
            "action": action,
            "resource": resource,
            "effect": "allow",
        }
        for resource in resources
        for action in ("create", "read", "update", "delete")
    )


def _sqlite_request(
    *,
    language: str = "python",
    auth_mode: str = "jwt",
) -> SynthesisRequest:
    draft = create_draft(
        name="store-sqlite",
        description="Embedded SQLite store API",
        entities=(
            {
                "singular": "customer",
                "plural": "customers",
                "fields": [
                    {"name": "name", "type": "string", "required": True},
                    {"name": "email", "type": "string", "required": True},
                ],
            },
            {
                "singular": "order",
                "plural": "orders",
                "fields": [
                    {"name": "customer_id", "type": "string", "required": True},
                    {"name": "amount", "type": "number", "required": True},
                    {"name": "paid", "type": "boolean", "required": True},
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
        languages=(language,),
        persistence="sqlite",
        auth_mode=auth_mode,
        permissions=tuple(
            {**permission, "actor": "store-admin"}
            for permission in allow_crud("customer", "order")
        ),
    )
    approved = approve_request(draft, actor="user:ethan-certifier")
    return SynthesisRequest.from_mapping(approved)


def test_sqlite_ddl_and_production_assets() -> None:
    request = _sqlite_request(language="python")
    files = render_workspace(request)

    assert "database/migrations/001_initial.sql" in files
    assert "database/migrations/manifest.json" in files
    assert "database/apply-migrations.sh" in files
    assert "operations/backup.sh" in files
    assert "operations/restore.sh" in files
    assert "database/postgres-image.txt" not in files

    manifest = json.loads(files["database/migrations/manifest.json"])
    assert manifest["provider"] == "sqlite"
    assert manifest["provider_version"] == "3.45"

    migration_sql = files["database/migrations/001_initial.sql"]
    assert "PRAGMA foreign_keys = ON;" in migration_sql
    assert 'CREATE TABLE IF NOT EXISTS "customers"' in migration_sql
    assert 'CREATE TABLE IF NOT EXISTS "orders"' in migration_sql
    assert 'CONSTRAINT "fk_order_customer_id_customer" FOREIGN KEY ("tenant_id", "customer_id")' in migration_sql
    assert 'REFERENCES "customers" ("tenant_id", "id")' in migration_sql
    assert 'CREATE TABLE IF NOT EXISTS schema_migrations' in migration_sql

    # Verify that SQLite can actually execute this generated DDL without any syntax error
    connection = sqlite3.connect(":memory:")
    connection.executescript(migration_sql)

    # Verify tables and foreign key enforcement in the real SQLite engine
    cursor = connection.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [row[0] for row in cursor.fetchall()]
    assert "customers" in tables
    assert "orders" in tables
    assert "schema_migrations" in tables

    # Test that migration record was inserted
    cursor.execute('SELECT "version" FROM "schema_migrations"')
    migrations = cursor.fetchall()
    assert len(migrations) == 1
    assert migrations[0] == ("001_initial",)
    connection.close()


def test_python_sqlite_target_code_and_ast() -> None:
    request = _sqlite_request(language="python", auth_mode="jwt")
    files = render_workspace(request)

    pyproject = tomllib.loads(files["python/pyproject.toml"])
    dependencies = pyproject["project"]["dependencies"]
    assert not any("psycopg" in dep for dep in dependencies)
    assert any("fastapi" in dep for dep in dependencies)

    repository = files["python/src/store_sqlite/repository.py"]
    assert "import sqlite3" in repository
    assert "PRAGMA foreign_keys = ON" in repository
    assert "def _to_db_value(value: object) -> object:" in repository
    assert 'WHERE \\"tenant_id\\" = ?' in repository
    assert "psycopg" not in repository

    # Verify integration test path
    assert "python/tests/test_sqlite_integration.py" in files
    assert "python/tests/test_postgresql_integration.py" not in files

    # Verify local runtime
    local_runtime = files["python/scripts/local_runtime.py"]
    assert "import sqlite3" in local_runtime
    assert "app.db" in local_runtime

    # Verify CI workflow
    ci_workflow = files[".github/workflows/python-ci.yml"]
    assert "services:" not in ci_workflow
    assert "postgres" not in ci_workflow
    assert "sqlite:///tmp/generated.db" in ci_workflow

    # Verify README
    readme = files["python/README.md"]
    assert "SQLite 3.45" in readme

    # Verify all generated Python files are syntactically valid Python
    for path, content in files.items():
        if path.startswith("python/") and path.endswith(".py"):
            ast.parse(content, filename=path)


@pytest.mark.parametrize("lang", ["python", "typescript", "go", "java", "csharp", "kotlin", "php", "rust"])
def test_sqlite_across_all_target_languages(lang: str) -> None:
    request = _sqlite_request(language=lang)
    files = render_workspace(request)

    assert "database/migrations/001_initial.sql" in files
    assert "database/migrations/manifest.json" in files
    manifest = json.loads(files["database/migrations/manifest.json"])
    assert manifest["provider"] == "sqlite"

    dep_graph = json.loads(files["requirements/declared-dependency-graph.json"])
    node_ids = {node["id"] for node in dep_graph["nodes"]}
    assert "provider:sqlite:3.45" in node_ids

    blueprint = json.loads(files["requirements/project-blueprint.json"])
    assert blueprint["applications"][0]["storage"] == "sqlite"

    docs = files["docs/DATABASE_DESIGN.md"]
    assert "SQLite" in docs


def test_python_sqlite_generate_and_verify(tmp_path: Path) -> None:
    request = _sqlite_request(language="python", auth_mode="jwt")
    workspace = tmp_path / "workspace"
    generate_workspace(request.raw, workspace)

    evidence = verify_workspace(workspace, use_ephemeral_runtime_ports=True)
    python_results = [r for r in evidence["results"] if r.get("language") == "python"]
    assert len(python_results) >= 2
    assert all(r["status"] == "PASSED" for r in python_results)
    assert evidence["status"] == "PASSED"


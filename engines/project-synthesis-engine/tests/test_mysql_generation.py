from __future__ import annotations

import ast
import json
import tomllib
from pathlib import Path

import pytest

from elmos_project_synthesis.container_images import MYSQL_IMAGE
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


def _mysql_request(
    *,
    language: str = "python",
    auth_mode: str = "jwt",
) -> SynthesisRequest:
    draft = create_draft(
        name="store-mysql",
        description="MySQL production store API",
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
        persistence="mysql",
        auth_mode=auth_mode,
        permissions=tuple(
            {**permission, "actor": "store-admin"}
            for permission in allow_crud("customer", "order")
        ),
    )
    approved = approve_request(draft, actor="user:ethan-certifier")
    return SynthesisRequest.from_mapping(approved)


def test_mysql_ddl_and_production_assets() -> None:
    request = _mysql_request(language="python")
    files = render_workspace(request)

    assert "database/migrations/001_initial.sql" in files
    assert "database/migrations/manifest.json" in files
    assert "database/apply-migrations.sh" in files
    assert "operations/backup.sh" in files
    assert "operations/restore.sh" in files
    assert "database/mysql-image.txt" in files
    assert "database/postgres-image.txt" not in files

    assert files["database/mysql-image.txt"].strip() == MYSQL_IMAGE

    manifest = json.loads(files["database/migrations/manifest.json"])
    assert manifest["provider"] == "mysql"
    assert manifest["provider_version"] == "8.0"

    migration_sql = files["database/migrations/001_initial.sql"]
    assert "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;" in migration_sql
    assert "CREATE TABLE IF NOT EXISTS `customers`" in migration_sql
    assert "CREATE TABLE IF NOT EXISTS `orders`" in migration_sql
    assert "CONSTRAINT `fk_order_customer_id_customer` FOREIGN KEY (`tenant_id`, `customer_id`)" in migration_sql
    assert "REFERENCES `customers` (`tenant_id`, `id`)" in migration_sql
    assert "CREATE TABLE IF NOT EXISTS `schema_migrations`" in migration_sql
    assert "INSERT IGNORE INTO `schema_migrations`" in migration_sql

    backup_sh = files["operations/backup.sh"]
    assert "mysqldump" in backup_sh

    restore_sh = files["operations/restore.sh"]
    assert "mysql" in restore_sh

    apply_sh = files["database/apply-migrations.sh"]
    assert "mysql" in apply_sh


def test_python_mysql_target_code_and_ast() -> None:
    request = _mysql_request(language="python", auth_mode="jwt")
    files = render_workspace(request)

    pyproject = tomllib.loads(files["python/pyproject.toml"])
    dependencies = pyproject["project"]["dependencies"]
    assert any("pymysql" in dep for dep in dependencies)
    assert any("cryptography" in dep for dep in dependencies)
    assert not any("psycopg" in dep for dep in dependencies)
    assert any("fastapi" in dep for dep in dependencies)

    dev_dependencies = pyproject["dependency-groups"]["dev"]
    assert any("types-PyMySQL" in dep for dep in dev_dependencies)

    repository = files["python/src/store_mysql/repository.py"]
    assert "import pymysql" in repository
    assert "from pymysql.cursors import DictCursor" in repository
    assert "def _connect(" in repository
    assert "def tenant_connection(" in repository
    assert "def ready() -> bool:" in repository
    assert "WHERE `tenant_id` = %s" in repository
    assert "ON DUPLICATE KEY UPDATE" in repository
    assert "AS new_row" in repository
    assert "new_row.`name`" in repository
    assert "new_row.`email`" in repository
    assert "VALUES(`" not in repository
    assert "return float(value)" not in repository
    assert "value.isoformat()" not in repository
    assert "psycopg" not in repository

    # Verify integration test path
    assert "python/tests/test_mysql_integration.py" in files
    assert "python/tests/test_postgresql_integration.py" not in files
    assert "python/tests/test_sqlite_integration.py" not in files

    # Verify local runtime
    local_runtime = files["python/scripts/local_runtime.py"]
    assert "import pymysql" in local_runtime
    assert "mysql://root@127.0.0.1:3306/generated" in local_runtime

    # Verify CI workflow
    ci_workflow = files[".github/workflows/python-ci.yml"]
    assert "services:" in ci_workflow
    assert "mysql:" in ci_workflow
    assert MYSQL_IMAGE in ci_workflow
    assert "postgres:" not in ci_workflow

    # Verify README
    readme = files["python/README.md"]
    assert "MySQL 8.0" in readme

    # Verify all generated Python files are syntactically valid Python
    for path, content in files.items():
        if path.startswith("python/") and path.endswith(".py"):
            ast.parse(content, filename=path)


_UNEVIDENCED_RELATIONAL_LANGUAGES = (
    "typescript",
    "go",
    "java",
    "csharp",
    "kotlin",
    "php",
    "rust",
)


@pytest.mark.parametrize("lang", _UNEVIDENCED_RELATIONAL_LANGUAGES)
def test_mysql_rejects_unevidenced_target_languages(lang: str) -> None:
    with pytest.raises(ValueError, match="PROFILE_TARGET_COMBINATION_UNSUPPORTED"):
        _mysql_request(language=lang)


def test_mysql_rejects_unauthenticated_profile() -> None:
    with pytest.raises(ValueError, match="PROFILE_COMBINATION_UNSUPPORTED"):
        create_draft(
            name="store-mysql",
            description="MySQL production store API",
            entity="customer",
            languages=("python",),
            persistence="mysql",
            auth_mode="none",
        )


def test_mysql_python_profile_renders_shared_assets() -> None:
    request = _mysql_request(language="python")
    files = render_workspace(request)

    assert "database/migrations/001_initial.sql" in files
    assert "database/migrations/manifest.json" in files
    manifest = json.loads(files["database/migrations/manifest.json"])
    assert manifest["provider"] == "mysql"

    dep_graph = json.loads(files["requirements/declared-dependency-graph.json"])
    node_ids = {node["id"] for node in dep_graph["nodes"]}
    assert "provider:mysql:8.0" in node_ids

    blueprint = json.loads(files["requirements/project-blueprint.json"])
    assert blueprint["applications"][0]["storage"] == "mysql"

    docs = files["docs/DATABASE_DESIGN.md"]
    assert "MySQL 8.0" in docs


def _mysql_listening() -> bool:
    import socket

    try:
        with socket.socket() as probe:
            probe.settimeout(0.5)
            probe.connect(("127.0.0.1", 3306))
    except OSError:
        return False
    return True


@pytest.mark.skipif(not _mysql_listening(), reason="MySQL is not listening on 127.0.0.1:3306")
def test_python_mysql_generate_and_verify(tmp_path: Path) -> None:
    request = _mysql_request(language="python", auth_mode="jwt")
    workspace = tmp_path / "workspace"
    generate_workspace(request.raw, workspace)

    evidence = verify_workspace(workspace, use_ephemeral_runtime_ports=True)
    python_results = [r for r in evidence["results"] if r.get("language") == "python"]
    assert len(python_results) >= 2
    assert all(r["status"] == "PASSED" for r in python_results)
    assert evidence["status"] == "PASSED"

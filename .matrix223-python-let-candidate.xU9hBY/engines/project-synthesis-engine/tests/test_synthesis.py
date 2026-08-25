from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path
from xml.etree import ElementTree

import pytest
import yaml

import elmos_project_synthesis.cleanup as cleanup
import elmos_project_synthesis.intake as intake_module
import elmos_project_synthesis.models as models
import elmos_project_synthesis.verification as verification
from elmos_project_synthesis.cli import _archive_workspace, main
from elmos_project_synthesis.intake import approve_request, create_draft
from elmos_project_synthesis.production_runtime import render_local_runtime
from elmos_project_synthesis.models import (
    SUPPORTED_LANGUAGES,
    TARGET_PROFILES,
    RequestValidationError,
    SynthesisRequest,
)
from elmos_project_synthesis.verification import _check_exact_toolchain, runtime_commands
from elmos_project_synthesis.workspace import WorkspaceConflictError, generate_workspace, render_workspace


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


def approved_request() -> dict[str, object]:
    draft = create_draft(
        name="work-order-service",
        description="维修工单创建、查询和健康检查服务。",
        entity="work_order",
    )
    return approve_request(draft, actor="user:test", approved_at="2026-07-22T00:00:00+00:00")


def multi_entity_request(*, languages: tuple[str, ...] = SUPPORTED_LANGUAGES) -> dict[str, object]:
    draft = create_draft(
        name="commerce-service",
        description='客户与订单项目，描述包含引号 """、单引号和换行\n第二行。',
        entities=(
            {
                "singular": "customer",
                "plural": "customers",
                "fields": [
                    {"name": "display_name", "type": "string", "required": True},
                    {"name": "active", "type": "boolean", "required": False},
                ],
            },
            {
                "singular": "order",
                "plural": "orders",
                "fields": [
                    {"name": "total", "type": "number", "required": True},
                    {"name": "created_at", "type": "datetime", "required": False},
                ],
            },
        ),
        relations=(
            {
                "source": "order",
                "target": "customer",
                "kind": "many-to-one",
                "required": True,
            },
        ),
        business_rules=("订单金额不得在应用层被静默更改。",),
        languages=languages,
    )
    return approve_request(draft, actor="user:test")


def test_missing_permission_declarations_default_to_explicit_deny() -> None:
    draft = create_draft(
        name="deny-by-default-service",
        description="管理订单",
        entity="order",
        languages=("python",),
    )

    assert draft["permissions"]
    assert {item["effect"] for item in draft["permissions"]} == {"deny"}
    assert {item["action"] for item in draft["permissions"]} == {
        "create",
        "read",
        "update",
        "delete",
    }


def test_authenticated_production_profile_requires_explicit_permission_approval() -> None:
    draft = create_draft(
        name="permission-review-service",
        description="Durable authenticated order API",
        entity="order",
        languages=("python",),
        persistence="postgresql",
        auth_mode="jwt",
    )

    assert {item["effect"] for item in draft["permissions"]} == {"deny"}
    assert [item["id"] for item in draft["open_questions"]] == ["Q-PERMISSION-PRODUCTION-001"]
    with pytest.raises(ValueError, match="OPEN_QUESTIONS_BLOCK_APPROVAL"):
        approve_request(draft, actor="user:reviewer")


def test_imported_requirement_sources_are_hash_bound_and_generated() -> None:
    description = (
        "[来源 SRC-001 · repository-file · README.md]\n"
        "实体: order; order字段: reference:string:required; 规则: order.reference != 0"
    )
    raw = description.encode("utf-8")
    sources = [
        {
            "id": "SRC-001",
            "kind": "repository-file",
            "label": "README.md",
            "mediaType": "text/markdown",
            "origin": (
                "workspace=d12ac53a-30b8-4d87-8202-9c9a4b181cf8;"
                "provider=GITEE;instance=gitee.com;repository=owner%2Frepository;"
                f"commit={'1' * 40};path=README.md"
            ),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "byteCount": len(raw),
            "extractedCharacters": len(description),
            "includedCharacters": len(description),
            "truncated": False,
            "warnings": [],
        }
    ]
    bundle_digest = models.sha256_json({"description": description, "sources": sources})
    draft = create_draft(
        name="source-bound-service",
        description=description,
        entity="order",
        languages=("python",),
        requirement_sources=sources,
        source_bundle_sha256=bundle_digest,
    )
    approved = approve_request(draft, actor="user:source-reviewer")
    rendered = render_workspace(SynthesisRequest.from_mapping(approved))
    provenance = json.loads(rendered["requirements/source-provenance.json"])

    assert approved["source_bundle_sha256"] == bundle_digest
    assert approved["requirements"][0]["source_refs"] == [{"source_id": "SRC-001", "location": "imported-requirements"}]
    assert provenance["status"] == "HASH_BOUND"
    assert provenance["sources"] == sources
    assert "not executed" in provenance["execution_boundary"]


def test_imported_requirement_source_tampering_fails_closed() -> None:
    description = "[来源 SRC-001]\n实体: order"
    source = {
        "id": "SRC-001",
        "kind": "description",
        "label": "页面简述",
        "mediaType": "text/plain",
        "sha256": hashlib.sha256(description.encode("utf-8")).hexdigest(),
        "byteCount": len(description.encode("utf-8")),
        "extractedCharacters": len(description),
        "includedCharacters": len(description),
        "truncated": False,
        "warnings": [],
    }
    digest = models.sha256_json({"description": description, "sources": [source]})
    draft = create_draft(
        name="tamper-source-service",
        description=description,
        entity="order",
        languages=("python",),
        requirement_sources=(source,),
        source_bundle_sha256=digest,
    )
    draft["requirement_sources"][0]["label"] = "changed.md"

    with pytest.raises(RequestValidationError, match="SOURCE_BUNDLE_HASH_MISMATCH"):
        SynthesisRequest.from_mapping(draft, require_approval=False)


def test_natural_language_draft_keeps_questions_explicit() -> None:
    draft = create_draft(name="records", description="管理业务记录", entity=None)
    assert draft["approval"] == {"status": "DRAFT"}
    assert draft["open_questions"]
    with pytest.raises(ValueError, match="OPEN_QUESTIONS_BLOCK_APPROVAL"):
        approve_request(draft, actor="user:test")


def test_natural_language_draft_infers_known_chinese_domain() -> None:
    draft = create_draft(name="orders", description="管理订单", entity=None, languages=("python",))
    assert draft["open_questions"] == []
    assert draft["entities"][0]["singular"] == "order"
    assert draft["entities"][0]["plural"] == "orders"


def test_natural_language_markers_override_fuzzy_aliases_and_bind_domain_graph() -> None:
    draft = create_draft(
        name="inventory-service",
        entity="product",
        description=(
            "管理产品和库存；实体: product, inventory; "
            "product字段: name:string:required, price:number:required; "
            "inventory字段: product_id:string:required, quantity:integer:required; "
            "关系: inventory.product_id -> product.id; "
            "规则: inventory.quantity must be non-negative; "
            "权限: admin:create/read/update/delete:inventory; "
            "权限: viewer:read:product"
        ),
        languages=("python",),
    )
    assert draft["open_questions"] == []
    assert [(item["singular"], item["plural"]) for item in draft["entities"]] == [
        ("product", "products"),
        ("inventory", "inventories"),
    ]
    assert draft["relations"] == [
        {
            "source": "inventory",
            "target": "product",
            "source_field": "product_id",
            "target_field": "id",
            "kind": "many-to-one",
            "required": True,
        }
    ]
    assert draft["business_rules"][0]["statement"] == ("inventory.quantity must be non-negative")
    assert draft["business_rules"][0]["predicate"] == {
        "type": "field-comparison",
        "entity": "inventory",
        "field": "quantity",
        "operator": "gte",
        "value": 0,
    }
    assert {(item["actor"], item["action"], item["resource"], item["effect"]) for item in draft["permissions"]} == {
        ("admin", "create", "inventory", "allow"),
        ("admin", "read", "inventory", "allow"),
        ("admin", "update", "inventory", "allow"),
        ("admin", "delete", "inventory", "allow"),
        ("viewer", "read", "product", "allow"),
    }
    rendered = render_workspace(SynthesisRequest.from_mapping(approve_request(draft, actor="user:reviewer")))
    assert max(len(line) for line in rendered["python/src/inventory_service/__init__.py"].splitlines()) <= 120
    app_source = rendered["python/src/inventory_service/app.py"]
    assert app_source.index("    Inventory,") < app_source.index("    Product,")


def test_invalid_explicit_relation_field_creates_a_blocking_question() -> None:
    draft = create_draft(
        name="invalid-relation-service",
        entity="product",
        description=(
            "实体: product, inventory; "
            "product字段: name:string:required; "
            "inventory字段: product_id:string:required; "
            "关系: inventory.unknown_product -> product.id"
        ),
        languages=("python",),
    )

    assert draft["relations"] == []
    assert [item["id"] for item in draft["open_questions"]] == ["Q-RELATION-001"]


def test_multi_entity_requirement_graph_preserves_rules_relations_and_permissions() -> None:
    parsed = SynthesisRequest.from_mapping(multi_entity_request(languages=("python",)))
    assert [entity.singular for entity in parsed.entities] == ["customer", "order"]
    assert parsed.relations[0].source == "order"
    assert parsed.relations[0].target == "customer"
    assert parsed.raw["business_rules"][0]["statement"] == "订单金额不得在应用层被静默更改。"
    assert len(parsed.raw["permissions"]) == 8
    assert {item["action"] for item in parsed.raw["permissions"]} == {
        "create",
        "read",
        "update",
        "delete",
    }


def test_strict_required_boolean_and_relation_references_fail_closed() -> None:
    invalid_boolean = create_draft(
        name="items",
        description="item service",
        entity="item",
        languages=("python",),
    )
    invalid_boolean["entities"][0]["fields"][0]["required"] = "false"  # type: ignore[index]
    with pytest.raises(RequestValidationError, match="ENTITY_FIELD_REQUIRED_MUST_BE_BOOLEAN"):
        approve_request(invalid_boolean, actor="user:test")

    with pytest.raises(RequestValidationError, match="RELATION_ENTITY_INVALID"):
        create_draft(
            name="items",
            description="item service",
            entity="item",
            relations=({"source": "item", "target": "missing", "kind": "many-to-one", "required": True},),
            languages=("python",),
        )


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
        "typescript/package.json",
        "typescript/Dockerfile",
        "go/go.mod",
        "go/Dockerfile",
        "kotlin/build.gradle.kts",
        "kotlin/gradle.lockfile",
        "kotlin/Dockerfile",
        "php/composer.json",
        "php/Dockerfile",
        "rust/Cargo.lock",
        "rust/Cargo.toml",
        "rust/Dockerfile",
        "docker-compose.yml",
        "requirements/psir.json",
        "requirements/project-blueprint.json",
        "requirements/asset-graph.json",
        "requirements/build-graph.json",
        ".elmos/generation-manifest.json",
    }
    assert expected <= set(files)
    manifest = json.loads(files[".elmos/generation-manifest.json"])
    assert manifest["status"] == "GENERATED"
    assert manifest["production_delivery_status"] == "NOT_RUN"
    assert manifest["certification_status"] == "NOT_CERTIFIED"
    assert len(manifest["files"]) == len(files) - 1
    assert all(entry["sha256"] for entry in manifest["files"])
    asset_graph = json.loads(files["requirements/asset-graph.json"])
    build_graph = json.loads(files["requirements/build-graph.json"])
    assert {node["id"] for node in asset_graph["nodes"]} >= {
        "approved-request",
        "typescript-source",
        "rust-verification",
    }
    assert build_graph["execution_policy"]["generated_is_not_verified"] is True
    assert all(
        node["status"] == "NOT_RUN"
        for node in build_graph["nodes"]
        if node["kind"] in {"native-build", "native-test", "startup-probe"}
    )
    for path in ("java/openapi.yaml", "python/openapi.yaml", "dotnet/openapi.yaml"):
        openapi = yaml.safe_load(files[path])
        assert openapi["openapi"] == "3.1.0"
        create_schema = openapi["components"]["schemas"]["WorkOrderCreate"]
        assert "id" not in create_schema["required"]


def test_all_direct_emitters_render_full_crud_and_safe_configuration() -> None:
    files = render_workspace(SynthesisRequest.from_mapping(multi_entity_request()))
    expected_roots = {str(TARGET_PROFILES[language]["directory"]) for language in SUPPORTED_LANGUAGES}
    assert expected_roots <= {path.split("/", 1)[0] for path in files}
    for language in SUPPORTED_LANGUAGES:
        directory = str(TARGET_PROFILES[language]["directory"])
        contract = yaml.safe_load(files[f"{directory}/openapi.yaml"])
        for resource in ("customers", "orders"):
            assert set(contract["paths"][f"/api/v1/{resource}"]) == {"get", "post"}
            assert set(contract["paths"][f"/api/v1/{resource}/{{id}}"]) == {
                "delete",
                "get",
                "put",
            }
    loopback_sources = {
        "python": 'os.getenv("HOST", "127.0.0.1")',
        "typescript": 'process.env.HOST ?? "127.0.0.1"',
        "go": 'host = "127.0.0.1"',
        "kotlin": 'System.getenv("HOST") ?: "127.0.0.1"',
        "rust": 'env::var("HOST").unwrap_or_else(|_| "127.0.0.1".to_owned())',
    }
    for language, marker in loopback_sources.items():
        directory = str(TARGET_PROFILES[language]["directory"])
        assert any(
            marker in content
            for path, content in files.items()
            if path.startswith(f"{directory}/") and not path.endswith("Dockerfile")
        )
        assert "HOST=0.0.0.0" in files[f"{directory}/Dockerfile"]

    for path, content in files.items():
        if path.endswith(".py"):
            ast.parse(content, filename=path)
    ElementTree.fromstring(files["java/pom.xml"])  # noqa: S314 - bounded generated fixture
    tomllib.loads(files["python/pyproject.toml"])
    tomllib.loads(files["rust/Cargo.toml"])
    assert 'name = "commerce-service"' in files["rust/Cargo.lock"]
    assert "__ELMOS_PROJECT_NAME__" not in files["rust/Cargo.lock"]
    assert 'checksum = "' in files["rust/Cargo.lock"]
    assert "cargo generate-lockfile" not in files["rust/Dockerfile"]
    assert "musl-dev=1.2.5-r12" in files["rust/Dockerfile"]
    assert "cargo generate-lockfile" not in files["rust/.github/workflows/ci.yml"]
    assert "io.ktor:ktor-server-core:3.2.3=" in files["kotlin/gradle.lockfile"]
    assert "--write-locks" not in files["kotlin/Dockerfile"]
    assert "--write-locks" not in files["kotlin/.github/workflows/ci.yml"]
    task_program = files["dotnet/src/CommerceService.Api/Program.cs"]
    assert "using Generated.Api;" not in task_program
    assert "global::Generated.Api.Customer" in task_program
    json.loads(files["typescript/package.json"])
    json.loads(files["php/composer.json"])
    assert '"""' in json.loads(files["requirements/psir.json"])["project"]["description"]
    assert "&quot;&quot;&quot;" in files["java/pom.xml"]
    assert "__doc__ = " in files["python/src/commerce_service/__init__.py"]


def test_dotnet_model_names_cannot_collide_with_implicit_bcl_types() -> None:
    draft = create_draft(
        name="task-service",
        description="Task CRUD service.",
        entity="task",
        languages=("csharp",),
    )
    files = render_workspace(SynthesisRequest.from_mapping(approve_request(draft, actor="user:test")))
    program = files["dotnet/src/TaskService.Api/Program.cs"]
    api_tests = files["dotnet/tests/TaskService.Api.Tests/ApiTests.cs"]
    assert "using Generated.Api;" not in program
    assert "ConcurrentDictionary<string, global::Generated.Api.Task>" in program
    assert "new global::Generated.Api.Task(" in program
    assert "public async global::System.Threading.Tasks.Task HealthJourney()" in api_tests
    assert "public async global::System.Threading.Tasks.Task TaskFullCrudJourney()" in api_tests
    assert "public async Task " not in api_tests


def test_generated_ci_actions_are_pinned_to_immutable_commits() -> None:
    files = render_workspace(SynthesisRequest.from_mapping(multi_entity_request()))
    workflows = {path: content for path, content in files.items() if path.endswith("/.github/workflows/ci.yml")}
    assert len(workflows) == len(SUPPORTED_LANGUAGES)
    for path, content in workflows.items():
        uses_lines = [line.strip() for line in content.splitlines() if "uses:" in line]
        assert uses_lines, path
        for line in uses_lines:
            match = re.search(r"\buses:\s+[^\s@]+@([0-9a-f]{40})(?:\s+#\s+\S+)?$", line)
            assert match, f"{path} contains a mutable or malformed action reference: {line}"


def test_generated_container_images_are_pinned_to_immutable_manifests() -> None:
    files = render_workspace(SynthesisRequest.from_mapping(multi_entity_request()))
    dockerfiles = {path: content for path, content in files.items() if path.endswith("/Dockerfile")}
    assert len(dockerfiles) == len(SUPPORTED_LANGUAGES)
    for path, content in dockerfiles.items():
        from_lines = [line.strip() for line in content.splitlines() if line.strip().startswith("FROM ")]
        assert from_lines, path
        for line in from_lines:
            image = line.split()[1]
            if image == "scratch":
                continue
            assert re.fullmatch(
                r"[^@\s]+@sha256:[0-9a-f]{64}",
                image,
            ), f"{path} contains a mutable or malformed base image: {line}"


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
    assert (
        main(
            [
                "draft",
                "--name",
                "inventory-service",
                "--description",
                "Inventory API",
                "--entity",
                "inventory_item",
                "--namespace",
                "io.elmos.inventory",
                "--language",
                "java",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    request = json.loads(output.read_text(encoding="utf-8"))
    assert request["project"]["namespace"] == "io.elmos.inventory"
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize(
    ("argument", "value", "reason"),
    [
        ("project_kind", "worker", "PROJECT_KIND_INVALID"),
        ("persistence", "oracle", "PERSISTENCE_INVALID"),
        ("auth_mode", "session-cookie", "AUTH_MODE_INVALID"),
    ],
)
def test_unimplemented_generation_profiles_fail_closed(argument: str, value: str, reason: str) -> None:
    arguments = {
        "name": "items",
        "description": "Item API",
        "entity": "item",
        "languages": ("python",),
        argument: value,
    }
    with pytest.raises(ValueError, match=reason):
        create_draft(**arguments)


@pytest.mark.parametrize("auth_mode", ["jwt", "oidc"])
def test_python_enterprise_profile_renders_durable_auth_enforcement(auth_mode: str) -> None:
    draft = create_draft(
        name="enterprise-orders",
        description="Durable authenticated order API",
        entities=(
            {
                "singular": "customer",
                "plural": "customers",
                "fields": [{"name": "name", "type": "string", "required": True}],
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
        languages=("python",),
        persistence="postgresql",
        auth_mode=auth_mode,
        permissions=tuple({**permission, "actor": "admin"} for permission in allow_crud("customer", "order")),
    )
    files = render_workspace(SynthesisRequest.from_mapping(approve_request(draft, actor="user:enterprise-reviewer")))

    assert "database/migrations/001_initial.sql" in files
    assert "database/apply-migrations.sh" in files
    migration = files["database/migrations/001_initial.sql"]
    assert '"total" numeric(20,6) NOT NULL' in migration
    assert '"customer_id" uuid NOT NULL' in migration
    assert 'FOREIGN KEY ("tenant_id", "customer_id")' in migration
    assert 'REFERENCES "app"."customers" ("tenant_id", "id")' in migration
    assert 'CREATE POLICY "tenant_isolation"' in migration
    assert "FORCE ROW LEVEL SECURITY" in migration
    expected_algorithms = '["HS256"]' if auth_mode == "jwt" else '["RS256", "ES256"]'
    security = files["python/src/enterprise_orders/security.py"]
    assert f"algorithms = {expected_algorithms}" in security
    assert 'tenant_id = claims.get("tenant_id")' in security
    assert '"allow" not in decisions' in security
    assert ("ELMOS_JWT_HMAC_SECRET_FILE" if auth_mode == "jwt" else "ELMOS_OIDC_JWKS_FILE") in security
    assert 'authorize("order", "create")' in files["python/src/enterprise_orders/app.py"]
    integration = files["python/tests/test_postgresql_integration.py"]
    assert '"roles": ["admin"]' in integration
    assert "client.put(" in integration
    assert "client.delete(" in integration
    assert "set_config('app.tenant_id', %s, true)" in files["python/src/enterprise_orders/repository.py"]
    assert "ELMOS_DATABASE_URL_FILE_UNSAFE" in files["python/src/enterprise_orders/repository.py"]
    assert "PASSWORD=" not in files["python/.env.example"]
    assert "PRIVATE_KEY=" not in files["python/.env.example"]
    assert "working-directory: python" in files[".github/workflows/python-ci.yml"]
    workflow = yaml.safe_load(files[".github/workflows/python-ci.yml"])
    assert isinstance(workflow, dict)
    assert workflow["jobs"]["test"]["services"]["postgres"]["image"].startswith("postgres:17.5-alpine@sha256:")
    assert json.loads(files["security/policy-contract.json"])["default_decision"] == "deny"
    assert json.loads(files["operations/slo-contract.json"])["status"] == "DEFINED_NOT_EVIDENCED"
    assert (
        json.loads(files["observability/observability-contract.json"])["metrics"]["implementation_status"]
        == "GENERATED"
    )
    assert "pg_dump" in files["operations/backup.sh"]
    assert "sha256sum" in files["operations/backup.sh"]
    assert "sha256sum -c" in files["operations/restore.sh"]
    assert "pg_restore" in files["operations/restore.sh"]
    assert files["database/postgres-image.txt"].startswith("postgres:17.5-alpine@sha256:")
    deployment = files["deploy/kubernetes.yaml"]
    assert "readOnlyRootFilesystem: true" in deployment
    assert "runAsNonRoot: true" in deployment
    assert "kind: NetworkPolicy" in deployment
    assert "policyTypes:" in deployment
    assert "- Egress" in deployment
    assert "kind: PodDisruptionBudget" in deployment
    assert "defaultMode: 256" in deployment
    dockerfile = files["python/Dockerfile"]
    assert "USER 10001:10001" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    tomllib.loads(files["python/pyproject.toml"])
    for path, content in files.items():
        if path.startswith("python/") and path.endswith(".py"):
            ast.parse(content, filename=path)


def test_python_enterprise_profile_rejects_unexercisable_permission_matrix() -> None:
    draft = create_draft(
        name="partial-orders",
        description="Durable authenticated order API",
        entity="order",
        languages=("python",),
        persistence="postgresql",
        auth_mode="jwt",
        permissions=(
            {
                "actor": "reader",
                "action": "read",
                "resource": "order",
                "effect": "allow",
            },
        ),
    )
    approved = approve_request(draft, actor="user:enterprise-reviewer")
    with pytest.raises(
        ValueError,
        match="PRODUCTION_INTEGRATION_IDENTITY_UNSATISFIABLE",
    ):
        render_workspace(SynthesisRequest.from_mapping(approved))


def test_enterprise_profile_rejects_unevidenced_target_combinations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Every shipped target now has PostgreSQL-backed integration evidence, so
    # this exercises the gate itself against a withheld target rather than
    # naming a language that happens to be unfinished today. Written the other
    # way, the test would quietly stop testing anything the moment the last
    # target was implemented.
    withheld = "python"
    closed = {
        key: (value - {withheld}) if persistence != "in-memory" else value
        for key, value in models.SUPPORTED_PROFILE_TARGETS.items()
        for persistence in (key[0],)
    }
    monkeypatch.setattr(models, "SUPPORTED_PROFILE_TARGETS", closed)
    monkeypatch.setattr(intake_module, "SUPPORTED_PROFILE_TARGETS", closed)

    # Closed on its own...
    with pytest.raises(ValueError, match="PROFILE_TARGET_COMBINATION_UNSUPPORTED"):
        create_draft(
            name="items",
            description="Item API",
            entity="item",
            languages=(withheld,),
            persistence="postgresql",
            auth_mode="oidc",
        )
    # ...and still closed when paired with an evidenced target.
    with pytest.raises(ValueError, match="PROFILE_TARGET_COMBINATION_UNSUPPORTED"):
        create_draft(
            name="items",
            description="Item API",
            entity="item",
            languages=(withheld, "go"),
            persistence="postgresql",
            auth_mode="jwt",
        )


def test_every_shipped_target_has_a_production_profile() -> None:
    # The corollary of the test above: nothing is silently left behind. If a
    # new language is added to SUPPORTED_LANGUAGES without an evidenced
    # production profile, this fails and names it.
    for auth_mode in ("jwt", "oidc"):
        opened = models.SUPPORTED_PROFILE_TARGETS[("postgresql", auth_mode)]
        assert set(SUPPORTED_LANGUAGES) - set(opened) == set()
    with pytest.raises(ValueError, match="PROFILE_COMBINATION_UNSUPPORTED"):
        create_draft(
            name="items",
            description="Item API",
            entity="item",
            languages=("python",),
            persistence="in-memory",
            auth_mode="jwt",
        )


def test_all_eight_production_targets_render_distinct_deployment_manifests() -> None:
    draft = create_draft(
        name="all-target-orders",
        description="Authenticated durable order API in every bundled target.",
        entity="order",
        languages=SUPPORTED_LANGUAGES,
        persistence="postgresql",
        auth_mode="jwt",
        permissions=allow_crud("order"),
    )
    files = render_workspace(SynthesisRequest.from_mapping(approve_request(draft, actor="user:reviewer")))

    expected = {f"deploy/{language}-kubernetes.yaml" for language in SUPPORTED_LANGUAGES}
    assert expected <= set(files)
    assert "deploy/kubernetes.yaml" not in files
    for path in expected:
        assert "kind: Deployment" in files[path]
        assert "runAsNonRoot: true" in files[path]


def test_production_profile_compiles_business_rules_and_blocks_ambiguous_relations() -> None:
    draft = create_draft(
        name="inventory-api",
        description="Inventory API",
        entities=(
            {
                "singular": "inventory",
                "plural": "inventories",
                "fields": [{"name": "quantity", "type": "integer", "required": True}],
            },
        ),
        business_rules=("inventory.quantity must be non-negative",),
        languages=("python",),
        persistence="postgresql",
        auth_mode="jwt",
        permissions=allow_crud("inventory"),
    )
    files = render_workspace(SynthesisRequest.from_mapping(approve_request(draft, actor="user:reviewer")))
    assert 'CHECK ("quantity" >= 0)' in files["database/migrations/001_initial.sql"]
    assert "quantity: int = Field(ge=0)" in files["python/src/inventory_api/models.py"]

    ambiguous = create_draft(
        name="ambiguous-api",
        description="Ambiguous relationship",
        entities=(
            {
                "singular": "parent",
                "plural": "parents",
                "fields": [{"name": "name", "type": "string", "required": True}],
            },
            {
                "singular": "child",
                "plural": "children",
                "fields": [{"name": "parent_id", "type": "string", "required": True}],
            },
        ),
        relations=(
            {
                "source": "parent",
                "target": "child",
                "kind": "one-to-many",
                "required": True,
            },
        ),
        languages=("python",),
        persistence="postgresql",
        auth_mode="jwt",
        permissions=allow_crud("parent", "child"),
    )
    assert [item["id"] for item in ambiguous["open_questions"]] == ["Q-RELATION-PRODUCTION-001"]
    with pytest.raises(ValueError, match="OPEN_QUESTIONS_BLOCK_APPROVAL"):
        approve_request(ambiguous, actor="user:reviewer")


def test_production_profile_blocks_uncompiled_manual_rule() -> None:
    draft = create_draft(
        name="manual-rule-api",
        description="Manual business policy",
        entity="record",
        business_rules=("A reviewer should decide whether this feels acceptable.",),
        languages=("python",),
        persistence="postgresql",
        auth_mode="jwt",
        permissions=allow_crud("record"),
    )
    assert [item["id"] for item in draft["open_questions"]] == ["Q-RULE-001"]
    with pytest.raises(ValueError, match="OPEN_QUESTIONS_BLOCK_APPROVAL"):
        approve_request(draft, actor="user:reviewer")


def test_toolchain_version_mismatch_remains_not_run() -> None:
    matched, results = _check_exact_toolchain(
        "test-runtime",
        [
            {
                "tool": "python3",
                "arguments": ["--version"],
                "expected": "an intentionally unavailable exact version",
                "pattern": r"^ELMOS-NO-SUCH-RUNTIME$",
            }
        ],
    )
    assert matched is False
    assert results[0]["status"] == "NOT_RUN"
    assert "EXPECTED:" in results[0]["output"]


def test_native_verification_timeout_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def time_out(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(["native-build"], 30, output="partial output")

    monkeypatch.setattr(verification.subprocess, "run", time_out)
    result = verification._run(
        ["native-build"],
        tmp_path,
        language="test-runtime",
        timeout_seconds=30,
    )

    assert result["status"] == "FAILED"
    assert result["exit_code"] is None
    assert "COMMAND_TIMEOUT:30s" in result["output"]
    assert "partial output" in result["output"]


def test_acceptance_cleanup_retries_transient_directory_not_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    temporary = Path(tempfile.mkdtemp(prefix="elmos-project-synthesis-test-"))
    (temporary / "artifact.txt").write_text("bounded fixture", encoding="utf-8")
    original_rmtree = cleanup.shutil.rmtree
    attempts = 0

    def transient_rmtree(path: Path) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError(66, "Directory not empty")
        original_rmtree(path)

    monkeypatch.setattr(cleanup.shutil, "rmtree", transient_rmtree)
    monkeypatch.setattr(cleanup.time, "sleep", lambda _: None)

    assert (
        cleanup.cleanup_acceptance_directory(
            temporary,
            expected_prefix="elmos-project-synthesis-test-",
        )
        is None
    )
    assert attempts == 2
    assert not temporary.exists()


def test_acceptance_cleanup_rejects_unowned_or_unbounded_targets(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="ACCEPTANCE_CLEANUP_PATH_UNSAFE"):
        cleanup.cleanup_acceptance_directory(
            tmp_path,
            expected_prefix="elmos-project-synthesis-",
        )
    with pytest.raises(ValueError, match="ACCEPTANCE_CLEANUP_PATH_UNSAFE"):
        cleanup.cleanup_acceptance_directory(
            Path(tempfile.gettempdir()) / "elmos-project-synthesis-bounded",
            expected_prefix="elmos-project-synthesis-",
            attempts=11,
        )


def test_python_lock_cache_is_content_addressed_and_owner_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "python"
    workspace.mkdir()
    (workspace / "pyproject.toml").write_text("[project]\nname='cached-project'\n", encoding="utf-8")
    expected = "version = 1\nrevision = 3\n"
    (workspace / "uv.lock").write_text(expected, encoding="utf-8")
    cache = tmp_path / "lock-cache"
    monkeypatch.setenv("ELMOS_PROJECT_SYNTHESIS_LOCK_CACHE", str(cache))

    verification._store_cached_python_lock(workspace)
    entries = list(cache.glob("*.lock"))
    assert len(entries) == 1
    assert entries[0].stat().st_mode & 0o077 == 0

    (workspace / "uv.lock").unlink()
    assert verification._restore_cached_python_lock(workspace) is True
    assert (workspace / "uv.lock").read_text(encoding="utf-8") == expected


def test_python_lock_cache_rejects_permissive_entries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "python"
    workspace.mkdir()
    (workspace / "pyproject.toml").write_text("[project]\nname='cached-project'\n", encoding="utf-8")
    cache = tmp_path / "lock-cache"
    monkeypatch.setenv("ELMOS_PROJECT_SYNTHESIS_LOCK_CACHE", str(cache))
    entry = verification._python_lock_cache_path(workspace)
    entry.write_text("tampered", encoding="utf-8")
    entry.chmod(0o644)

    with pytest.raises(RuntimeError, match="PYTHON_LOCK_CACHE_ENTRY_UNSAFE"):
        verification._restore_cached_python_lock(workspace)


def test_toolchain_selection_uses_an_exact_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path_runtime = tmp_path / "path-runtime"
    exact_runtime = tmp_path / "exact-runtime"
    path_runtime.write_text("#!/bin/sh\nprintf 'runtime 99.0\\n'\n", encoding="utf-8")
    exact_runtime.write_text("#!/bin/sh\nprintf 'runtime 1.2.3\\n'\n", encoding="utf-8")
    path_runtime.chmod(0o700)
    exact_runtime.chmod(0o700)
    monkeypatch.setattr(verification.shutil, "which", lambda _: str(path_runtime))

    matched, results = _check_exact_toolchain(
        "test-runtime",
        [
            {
                "tool": "runtime",
                "arguments": ["--version"],
                "expected": "runtime 1.2.3",
                "pattern": r"^runtime 1\.2\.3$",
                "fallback": str(exact_runtime),
            }
        ],
    )

    assert matched is True
    assert results[0]["status"] == "PASSED"
    assert results[0]["command"][0] == str(exact_runtime)
    assert str(path_runtime) in results[0]["output"]


def test_runtime_plan_uses_the_same_exact_toolchain_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path_runtime = tmp_path / "path-runtime"
    exact_runtime = tmp_path / "exact-runtime"
    path_runtime.write_text("#!/bin/sh\nprintf 'runtime 99.0\\n'\n", encoding="utf-8")
    exact_runtime.write_text("#!/bin/sh\nprintf 'runtime 1.2.3\\n'\n", encoding="utf-8")
    path_runtime.chmod(0o700)
    exact_runtime.chmod(0o700)
    monkeypatch.setattr(verification.shutil, "which", lambda _: str(path_runtime))
    monkeypatch.setitem(
        verification.EXACT_TOOLCHAIN_REQUIREMENTS,
        "test-runtime",
        [
            {
                "tool": "runtime",
                "arguments": ["--version"],
                "expected": "runtime 1.2.3",
                "pattern": r"^runtime 1\.2\.3$",
                "fallback": str(exact_runtime),
            }
        ],
    )

    assert verification._runtime_tool("test-runtime", "runtime") == str(exact_runtime)


def test_native_build_uses_the_same_exact_toolchain_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path_runtime = tmp_path / "path-runtime"
    exact_runtime = tmp_path / "exact-runtime"
    path_runtime.write_text("#!/bin/sh\nprintf 'runtime 99.0\\n'\n", encoding="utf-8")
    exact_runtime.write_text("#!/bin/sh\nprintf 'runtime 1.2.3\\n'\n", encoding="utf-8")
    path_runtime.chmod(0o700)
    exact_runtime.chmod(0o700)
    monkeypatch.setattr(verification.shutil, "which", lambda _: str(path_runtime))
    monkeypatch.setitem(
        verification.EXACT_TOOLCHAIN_REQUIREMENTS,
        "test-runtime",
        [
            {
                "tool": "runtime",
                "arguments": ["--version"],
                "expected": "runtime 1.2.3",
                "pattern": r"^runtime 1\.2\.3$",
                "fallback": str(exact_runtime),
            }
        ],
    )
    results: list[dict[str, object]] = []

    assert verification._run_if_available(
        results,
        language="test-runtime",
        tool_name="runtime",
        commands=[["check"]],
        cwd=tmp_path,
    )
    assert results[0]["command"][0] == str(exact_runtime)


def test_kotlin_build_and_runtime_bind_the_matched_java_home(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    java = tmp_path / "jdk-21" / "bin" / "java"
    java.parent.mkdir(parents=True)
    java.write_text("#!/bin/sh\nprintf 'openjdk version \"21.0.11\"\\n'\n", encoding="utf-8")
    java.chmod(0o700)
    monkeypatch.setattr(verification.shutil, "which", lambda _: None)
    monkeypatch.setitem(
        verification.EXACT_TOOLCHAIN_REQUIREMENTS,
        "kotlin",
        [
            {
                "tool": "java",
                "arguments": ["-version"],
                "expected": "Java 21",
                "pattern": r'version "21(?:[.\-"]|$)',
                "fallback": str(java),
            }
        ],
    )
    monkeypatch.setenv(
        "ELMOS_PROJECT_SYNTHESIS_GRADLE_USER_HOME",
        str(tmp_path / "gradle-home"),
    )

    environment = verification._toolchain_environment("kotlin")

    assert environment["JAVA_HOME"] == str(java.parent.parent)
    assert environment["PATH"].split(os.pathsep)[0] == str(java.parent)
    assert environment["GRADLE_USER_HOME"] == str((tmp_path / "gradle-home").resolve())


def test_kotlin_toolchain_ignores_ambient_shell_proxy_for_gradle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    java = tmp_path / "jdk-21" / "bin" / "java"
    java.parent.mkdir(parents=True)
    java.write_text("#!/bin/sh\nprintf 'openjdk version \"21.0.11\"\\n'\n", encoding="utf-8")
    java.chmod(0o700)
    monkeypatch.setattr(verification.shutil, "which", lambda _: None)
    monkeypatch.setitem(
        verification.EXACT_TOOLCHAIN_REQUIREMENTS,
        "kotlin",
        [
            {
                "tool": "java",
                "arguments": ["-version"],
                "expected": "Java 21",
                "pattern": r'version "21(?:[.\-"]|$)',
                "fallback": str(java),
            }
        ],
    )
    monkeypatch.delenv("HTTP_PROXY", raising=False)
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:7890")
    monkeypatch.setenv("https_proxy", "http://127.0.0.1:7890")

    options = verification._gradle_proxy_system_properties()
    assert "-Djava.net.useSystemProxies=false" in options
    assert "-Dhttp.proxyHost=" in options
    assert "-Dhttps.proxyHost=" in options
    assert not any("proxyPort" in option for option in options)


def test_kotlin_toolchain_rejects_proxy_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    java = tmp_path / "jdk-21" / "bin" / "java"
    java.parent.mkdir(parents=True)
    java.write_text("#!/bin/sh\nprintf 'openjdk version \"21.0.11\"\\n'\n", encoding="utf-8")
    java.chmod(0o700)
    monkeypatch.setattr(verification.shutil, "which", lambda _: None)
    monkeypatch.setitem(
        verification.EXACT_TOOLCHAIN_REQUIREMENTS,
        "kotlin",
        [
            {
                "tool": "java",
                "arguments": ["-version"],
                "expected": "Java 21",
                "pattern": r'version "21(?:[.\-"]|$)',
                "fallback": str(java),
            }
        ],
    )
    monkeypatch.delenv("HTTP_PROXY", raising=False)
    monkeypatch.setenv(
        "ELMOS_PROJECT_SYNTHESIS_GRADLE_PROXY",
        "http://user:secret@127.0.0.1:7890",
    )

    with pytest.raises(ValueError, match="KOTLIN_HTTP_PROXY_INVALID"):
        verification._gradle_proxy_system_properties()


def test_kotlin_toolchain_accepts_explicit_controlled_gradle_proxy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    java = tmp_path / "jdk-21" / "bin" / "java"
    java.parent.mkdir(parents=True)
    java.write_text("#!/bin/sh\nprintf 'openjdk version \"21.0.11\"\\n'\n", encoding="utf-8")
    java.chmod(0o700)
    monkeypatch.setattr(verification.shutil, "which", lambda _: None)
    monkeypatch.setitem(
        verification.EXACT_TOOLCHAIN_REQUIREMENTS,
        "kotlin",
        [
            {
                "tool": "java",
                "arguments": ["-version"],
                "expected": "Java 21",
                "pattern": r'version "21(?:[.\-"]|$)',
                "fallback": str(java),
            }
        ],
    )
    monkeypatch.delenv("HTTP_PROXY", raising=False)
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    monkeypatch.delenv("http_proxy", raising=False)
    monkeypatch.delenv("https_proxy", raising=False)
    monkeypatch.setenv(
        "ELMOS_PROJECT_SYNTHESIS_GRADLE_PROXY",
        "http://127.0.0.1:7890",
    )

    options = " ".join(verification._gradle_proxy_system_properties())

    assert "-Dhttp.proxyHost=127.0.0.1" in options
    assert "-Dhttps.proxyHost=127.0.0.1" in options


def test_kotlin_toolchain_accepts_explicit_https_gradle_repository(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "ELMOS_PROJECT_SYNTHESIS_GRADLE_REPOSITORY",
        "https://maven.example.test/repository/central/",
    )

    assert verification._gradle_repository_property() == [
        "-PelmosMavenRepository=https://maven.example.test/repository/central"
    ]


@pytest.mark.parametrize(
    "repository",
    [
        "http://maven.example.test/repository/central",
        "https://user:secret@maven.example.test/repository/central",
        "https://maven.example.test/repository/central?mutable=true",
    ],
)
def test_kotlin_toolchain_rejects_unsafe_gradle_repository(
    repository: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ELMOS_PROJECT_SYNTHESIS_GRADLE_REPOSITORY", repository)

    with pytest.raises(ValueError, match="KOTLIN_GRADLE_REPOSITORY_INVALID"):
        verification._gradle_repository_property()


def test_kotlin_toolchain_rejects_ambient_gradle_home_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    configured = tmp_path / "gradle-home"
    configured.symlink_to(target, target_is_directory=True)
    monkeypatch.setenv(
        "ELMOS_PROJECT_SYNTHESIS_GRADLE_USER_HOME",
        str(configured),
    )

    with pytest.raises(ValueError, match="GRADLE_USER_HOME_UNSAFE"):
        verification._gradle_user_home()


def test_health_probe_rejects_a_different_service_on_the_same_port() -> None:
    assert verification._health_response_matches(
        200,
        {"status": "UP", "service": "expected-service"},
        expected_service="expected-service",
    )
    assert not verification._health_response_matches(
        200,
        {"status": "UP", "service": "other-service"},
        expected_service="expected-service",
    )


def test_loopback_runtime_environment_removes_ambient_proxies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy"):
        monkeypatch.setenv(name, "http://proxy.invalid:7890")

    environment = verification._loopback_environment({"PORT": "43210"})

    assert environment["PORT"] == "43210"
    assert environment["NO_PROXY"] == "127.0.0.1,localhost"
    assert environment["no_proxy"] == "127.0.0.1,localhost"
    assert not any(name in environment for name in verification._PROXY_ENVIRONMENT_NAMES)


def test_archive_includes_verified_lockfiles(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    generate_workspace(multi_entity_request(languages=("python", "typescript")), workspace)
    (workspace / "python" / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    (workspace / "typescript" / "pnpm-lock.yaml").write_text(
        "lockfileVersion: '9.0'\n",
        encoding="utf-8",
    )
    evidence = tmp_path / "verification.json"
    evidence.write_text('{"status":"PARTIAL"}\n', encoding="utf-8")
    archive_path = tmp_path / "generated.zip"

    result = _archive_workspace(workspace, archive_path, evidence=evidence)

    assert result["status"] == "ARCHIVED"
    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
    assert "workspace/python/uv.lock" in names
    assert "workspace/typescript/pnpm-lock.yaml" in names
    assert "workspace/.elmos/verification.json" in names


def test_runtime_plan_is_allowlisted_and_workspace_confined(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    generate_workspace(multi_entity_request(languages=("python", "typescript")), workspace)
    plans = runtime_commands(workspace)
    assert {plan["language"] for plan in plans} == {"python", "typescript"}
    for plan in plans:
        assert Path(plan["cwd"]).is_relative_to(workspace.resolve())
        assert Path(plan["command"][0]).name in {"uv", "pnpm"}
        assert all("\n" not in argument and "\x00" not in argument for argument in plan["command"])
        assert plan["environment"]["HOST"] == "127.0.0.1"


def test_every_profile_open_target_declares_an_integration_command() -> None:
    # A target opened in SUPPORTED_PROFILE_TARGETS but absent from the harness
    # tables would boot, answer /health and never run the tenant isolation
    # scenario -- which is exactly how an unverified target used to collect a
    # green acceptance.
    assert verification.undeclared_integration_targets() == frozenset()


_HEALTH_SERVER = """
import json, sys
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"status": "UP", "service": sys.argv[2]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


HTTPServer(("127.0.0.1", int(sys.argv[1])), Handler).serve_forever()
"""


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def test_probe_refuses_to_pass_when_a_required_scenario_did_not_run(tmp_path: Path) -> None:
    # A server that answers /health correctly but owes a production scenario
    # that never runs. Health alone must not be reported as a pass -- this is
    # the exact shape that let an unregistered target collect a green result.
    server = tmp_path / "health_server.py"
    server.write_text(_HEALTH_SERVER, encoding="utf-8")
    port = _free_port()
    probe = verification._probe(
        [sys.executable, str(server), str(port), "demo-service"],
        tmp_path,
        port,
        language="rust",
        expected_service="demo-service",
        requires_integration=True,
        startup_timeout_seconds=15,
    )
    assert probe["integration_status"] == "NOT_RUN"
    assert probe["status"] == "FAILED"
    assert "INTEGRATION_SCENARIO_REQUIRED_BUT_NOT_EXECUTED" in probe["output"]


def test_probe_degrades_to_not_run_when_the_toolchain_is_the_blocker(tmp_path: Path) -> None:
    # Environmental blockers are not defects: they must not be reported as a
    # pass either, but they degrade to NOT_RUN (overall PARTIAL) rather than
    # claiming the target is broken.
    server = tmp_path / "health_server.py"
    server.write_text(_HEALTH_SERVER, encoding="utf-8")
    port = _free_port()
    probe = verification._probe(
        [sys.executable, str(server), str(port), "demo-service"],
        tmp_path,
        port,
        language="rust",
        expected_service="demo-service",
        requires_integration=True,
        blocking_reason="EXACT_TOOLCHAIN_NOT_AVAILABLE:rust:cargo",
        startup_timeout_seconds=15,
    )
    assert probe["status"] == "NOT_RUN"
    assert "INTEGRATION_SCENARIO_NOT_RUN" in probe["output"]


def test_production_plans_record_the_integration_obligation() -> None:
    # The obligation has to be carried on the plan, including the blocked one,
    # or the probe cannot tell "no scenario applies" from "scenario skipped".
    request = approve_request(
        create_draft(
            name="obligation-service",
            description="Durable authenticated and tenant-isolated order API.",
            entities=(
                {
                    "singular": "order",
                    "plural": "orders",
                    "fields": [{"name": "reference", "type": "string", "required": True}],
                },
            ),
            relations=(),
            languages=("python",),
            persistence="postgresql",
            auth_mode="jwt",
            permissions=allow_crud("order"),
        ),
        actor="user:test",
        approved_at="2026-07-26T00:00:00+00:00",
    )
    with tempfile.TemporaryDirectory() as directory:
        workspace = Path(directory) / "workspace"
        generate_workspace(request, workspace)
        plans = [plan for plan in runtime_commands(workspace) if plan["language"] == "python"]
    assert plans
    assert all(plan.get("requires_integration") is True for plan in plans)


def test_postgres_durability_defaults_to_the_certifying_tier() -> None:
    """The tier that backs an equivalence claim must not move by accident.

    fsync and synchronous_commit are what make a verification run say anything
    about a real deployment, and they are also the slowest thing in that run.
    Relaxing them has to be something a run asks for, never something a default
    drifts into, so the emitted fallback is pinned here.
    """
    runtime = render_local_runtime(
        auth_mode="jwt",
        app_command=["go", "run", "."],
        verify_command=["go", "test", "./..."],
    )
    assert "'certifying': ('fsync=on', 'synchronous_commit=on')" in runtime
    assert "os.environ.get('ELMOS_POSTGRES_DURABILITY', 'certifying')" in runtime
    assert 'raise RuntimeError("UNSUPPORTED_POSTGRES_DURABILITY:" + durability)' in runtime


def test_postgres_durability_is_chosen_at_run_time_and_records_itself() -> None:
    """The tier is a property of a run, not of the workspace that was generated.

    ``generate_workspace`` refuses to reuse an output whose ``request_sha256``
    moved and the manifest digests every file, so a generation-time knob would
    let one approved request produce two different workspaces. Selecting at
    startup keeps the workspace a function of its request, and writing the tier
    beside the cluster keeps the result attributable without having to remember
    how it was launched.
    """
    runtime = render_local_runtime(
        auth_mode="jwt",
        app_command=["go", "run", "."],
        verify_command=["go", "test", "./..."],
    )
    assert (
        "'fast-feedback': ('fsync=off', 'synchronous_commit=off', 'full_page_writes=off')"
        in runtime
    )
    assert 'durability_file.write_text(durability, encoding="utf-8")' in runtime
    assert (
        '*[argument for setting in durability_profiles[durability] '
        'for argument in ("-c", setting)]'
    ) in runtime

    with pytest.raises(ValueError, match="UNSUPPORTED_DURABILITY"):
        render_local_runtime(
            auth_mode="jwt",
            app_command=["go", "run", "."],
            verify_command=["go", "test", "./..."],
            durability="relaxed",
        )


def test_php_production_runtime_honors_the_verified_port_override(tmp_path: Path) -> None:
    request = approve_request(
        create_draft(
            name="php-port-service",
            description="Durable authenticated and tenant-isolated order API.",
            entities=(
                {
                    "singular": "order",
                    "plural": "orders",
                    "fields": [{"name": "reference", "type": "string", "required": True}],
                },
            ),
            relations=(),
            languages=("php",),
            persistence="postgresql",
            auth_mode="jwt",
            permissions=allow_crud("order"),
        ),
        actor="user:test",
        approved_at="2026-07-26T00:00:00+00:00",
    )
    workspace = tmp_path / "workspace"

    generate_workspace(request, workspace)

    runtime = (workspace / "php" / "scripts" / "local_runtime.py").read_text(encoding="utf-8")
    assert "APP_PORT_ARGUMENT_INDEX = 2" in runtime
    assert 'command[APP_PORT_ARGUMENT_INDEX] = f"127.0.0.1:{port}"' in runtime
    assert 'environment["NO_PROXY"] = "127.0.0.1,localhost"' in runtime
    assert "environment.pop(proxy_name, None)" in runtime

from __future__ import annotations

import ast
import json
import re
import tomllib
import zipfile
from pathlib import Path
from xml.etree import ElementTree

import pytest
import yaml

import elmos_project_synthesis.verification as verification
from elmos_project_synthesis.cli import _archive_workspace, main
from elmos_project_synthesis.intake import approve_request, create_draft
from elmos_project_synthesis.models import (
    SUPPORTED_LANGUAGES,
    TARGET_PROFILES,
    RequestValidationError,
    SynthesisRequest,
)
from elmos_project_synthesis.verification import _check_exact_toolchain, runtime_commands
from elmos_project_synthesis.workspace import WorkspaceConflictError, generate_workspace, render_workspace


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
        "kotlin/Dockerfile",
        "php/composer.json",
        "php/Dockerfile",
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
    json.loads(files["typescript/package.json"])
    json.loads(files["php/composer.json"])
    assert '"""' in json.loads(files["requirements/psir.json"])["project"]["description"]
    assert "&quot;&quot;&quot;" in files["java/pom.xml"]
    assert "__doc__ = " in files["python/src/commerce_service/__init__.py"]


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
    tomllib.loads(files["python/pyproject.toml"])
    for path, content in files.items():
        if path.startswith("python/") and path.endswith(".py"):
            ast.parse(content, filename=path)


def test_enterprise_profile_rejects_unimplemented_target_combinations() -> None:
    with pytest.raises(ValueError, match="PROFILE_TARGET_COMBINATION_UNSUPPORTED"):
        create_draft(
            name="items",
            description="Item API",
            entity="item",
            languages=("java", "python"),
            persistence="postgresql",
            auth_mode="jwt",
        )
    with pytest.raises(ValueError, match="PROFILE_COMBINATION_UNSUPPORTED"):
        create_draft(
            name="items",
            description="Item API",
            entity="item",
            languages=("python",),
            persistence="in-memory",
            auth_mode="jwt",
        )


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

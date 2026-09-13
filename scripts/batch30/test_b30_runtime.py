"""Test suite verifying all 20 Batch 30 Framework skills in B30SkillRuntime."""

from __future__ import annotations

import pytest
from scripts.batch30.b30_skill_runtime import B30SkillRuntime


@pytest.fixture
def runtime():
    return B30SkillRuntime()


def test_runtime_skill_enumeration(runtime):
    assert len(runtime.SKILLS) == 20
    for s in runtime.SKILLS:
        assert s.startswith("b30-")


def test_b30_framework_factory(runtime):
    res = runtime.dispatch("b30-framework-factory", "init_pack", {
        "source_framework": "django",
        "target_framework": "fastapi",
        "mode": "migration",
    })
    assert res["pack_key"] == "django-to-fastapi"
    assert "source_fingerprint" in res["pipeline_stages"]
    assert res["status"] == "INITIALIZED"
    assert res["ready_for_orchestration"] is True


def test_b30_source_framework_fingerprint(runtime):
    res = runtime.dispatch("b30-source-framework-fingerprint", "fingerprint", {
        "dependencies": ["org.springframework.boot:spring-boot-starter-web:2.7.14"],
        "source_files": ["UserController.java", "UserService.java", "UserRepository.java"],
    })
    assert res["status"] == "FINGERPRINTED"
    assert res["detected_framework"] == "spring-boot"
    assert res["detected_version"] == "2.7.14"
    assert "UserController.java" in res["active_components"]["controllers"]
    assert res["source_coverage"] == 1.0


def test_b30_target_framework_profile(runtime):
    res = runtime.dispatch("b30-target-framework-profile", "resolve_profile", {
        "target_framework": "spring-boot-3",
        "runtime": "java-21",
    })
    assert res["profile_valid"] is True
    assert res["target_framework"] == "spring-boot-3"
    assert res["toolchain"] == "maven-3.9"
    assert res["security_baseline"]["csrf_protection"] is True


def test_b30_framework_contract_meta_model(runtime):
    res = runtime.dispatch("b30-framework-contract-meta-model", "normalize_fcm", {
        "endpoints": [{"path": "/health", "method": "GET", "handler": "healthCheck"}],
        "di_bindings": [{"interface": "HealthCheck", "implementation": "HealthCheckImpl"}],
    })
    assert res["status"] == "FCM_NORMALIZED"
    assert res["is_valid"] is True
    assert "fcm_digest" in res


def test_b30_framework_certification_gate(runtime):
    res_pass = runtime.dispatch("b30-framework-certification-gate", "evaluate", {
        "evidence": {
            "critical_unknowns": 0,
            "source_runtime_verified": True,
            "target_startup_verified": True,
            "test_failures": 0,
            "holdout_passed": True,
        }
    })
    assert res_pass["gate_decision"] == "PASSED"
    assert res_pass["certification_status"] == "CERTIFIED"

    res_fail = runtime.dispatch("b30-framework-certification-gate", "evaluate", {
        "evidence": {
            "critical_unknowns": 2,
            "test_failures": 1,
        }
    })
    assert res_fail["gate_decision"] == "REJECTED"
    assert res_fail["certification_status"] == "NOT_CERTIFIED"


def test_b30_framework_version_lifecycle(runtime):
    res = runtime.dispatch("b30-framework-version-lifecycle", "query", {
        "framework": "spring-boot",
        "version": "2.7.18",
    })
    assert res["lifecycle_state"] == "EOL"
    assert res["upgrade_target"] == "3.2.0"
    assert res["requires_immediate_upgrade"] is True


def test_b30_framework_coexistence_strangler(runtime):
    res = runtime.dispatch("b30-framework-coexistence-strangler", "configure", {
        "routes": [{"path": "/api/v1/orders", "target": "MODERN_APP"}],
    })
    assert res["strangler_facade"] == "ACTIVE"
    assert res["routed_paths"] == 1
    assert res["cutover_phase"] == "INCREMENTAL_MIGRATION"


def test_b30_spring_boot_upgrade(runtime):
    res = runtime.dispatch("b30-spring-boot-upgrade", "plan_upgrade", {
        "source_version": "2.7.14",
        "target_version": "3.2.0",
    })
    assert res["jakarta_namespace_applied"] is True
    assert res["status"] == "UPGRADE_READY"


def test_b30_aspnet_to_spring(runtime):
    res = runtime.dispatch("b30-aspnet-to-spring", "map_controllers", {
        "controllers": [{
            "name": "CustomerController",
            "actions": [{"name": "GetCustomer", "http_method": "HttpGet"}]
        }]
    })
    assert res["direction"] == "ASP.NET Core -> Spring Boot"
    assert res["controllers_mapped"] == 1
    assert "@RestController" in res["spring_controllers"][0]["spring_annotations"]


def test_b30_django_migration(runtime):
    res = runtime.dispatch("b30-django-migration", "migrate_app", {
        "models": ["Author", "Book"],
        "urlpatterns": ["path('books/', BookListView.as_view())"],
    })
    assert res["source_framework"] == "Django"
    assert res["models_migrated"] == 2
    assert res["routes_migrated"] == 1
    assert res["status"] == "MIGRATION_STRUCTURED"


def test_b30_dotnet_framework_modernization(runtime):
    res = runtime.dispatch("b30-dotnet-framework-modernization", "modernize", {
        "target_version": "net8.0",
    })
    assert res["project_format"] == "SDK_STYLE_CONVERTED"
    assert res["status"] == "MODERNIZED"


def test_b30_express_node_migration(runtime):
    res = runtime.dispatch("b30-express-node-migration", "extract_pipeline", {
        "routes": [{"method": "GET", "path": "/api/ping"}],
    })
    assert res["source"] == "Express"
    assert res["routes_extracted"] == 1
    assert res["status"] == "EXPRESS_MIGRATED"


def test_b30_fastapi_migration(runtime):
    res = runtime.dispatch("b30-fastapi-migration", "parse_endpoints", {
        "endpoints": [{"path": "/users", "method": "GET"}],
    })
    assert res["framework"] == "FastAPI"
    assert res["async_endpoints_count"] == 1
    assert res["status"] == "FASTAPI_PARSED"


def test_b30_flask_migration(runtime):
    res = runtime.dispatch("b30-flask-migration", "inspect_app", {
        "blueprints": ["main_bp", "admin_bp"],
    })
    assert res["framework"] == "Flask"
    assert res["blueprints_count"] == 2
    assert res["status"] == "FLASK_MIGRATED"


def test_b30_jakarta_ee_modernization(runtime):
    res = runtime.dispatch("b30-jakarta-ee-modernization", "modernize", {
        "ejbs": ["OrderBean"],
        "jax_rs_resources": ["CustomerResource"],
    })
    assert res["source"] == "Java EE / Jakarta EE"
    assert res["appserver_eliminated"] is True
    assert res["status"] == "JAKARTA_MODERNIZED"


def test_b30_micronaut_migration(runtime):
    res = runtime.dispatch("b30-micronaut-migration", "inspect_di", {
        "controllers": ["InvoiceController"],
        "aot_beans": ["InvoiceService"],
    })
    assert res["framework"] == "Micronaut"
    assert res["aot_compile_time_di"] is True
    assert res["status"] == "MICRONAUT_VERIFIED"


def test_b30_nestjs_migration(runtime):
    res = runtime.dispatch("b30-nestjs-migration", "analyze_modules", {
        "modules": ["RootModule", "AuthModule"],
    })
    assert res["framework"] == "NestJS"
    assert res["modules_count"] == 2
    assert res["dependency_tree_valid"] is True
    assert res["status"] == "NESTJS_VALIDATED"


def test_b30_python_background_jobs(runtime):
    res = runtime.dispatch("b30-python-background-jobs", "map_jobs", {
        "backend": "Celery",
        "tasks": [{"name": "process_video", "queue": "media"}],
    })
    assert res["job_runner"] == "Celery"
    assert res["tasks_mapped"] == 1
    assert res["status"] == "JOBS_MIGRATED"


def test_b30_quarkus_migration(runtime):
    res = runtime.dispatch("b30-quarkus-migration", "check_native", {
        "panache_entities": ["Item"],
        "native_build_enabled": True,
    })
    assert res["framework"] == "Quarkus"
    assert res["graalvm_native_ready"] is True
    assert res["status"] == "QUARKUS_ANALYZED"


def test_b30_sqlalchemy_persistence(runtime):
    res = runtime.dispatch("b30-sqlalchemy-persistence", "map_orm", {
        "models": ["users", "profiles"],
        "async_session": True,
    })
    assert res["orm"] == "SQLAlchemy 2.0"
    assert res["declarative_models"] == 2
    assert res["async_session_enabled"] is True
    assert res["status"] == "PERSISTENCE_VALIDATED"


def test_unknown_skill_raises(runtime):
    with pytest.raises(KeyError):
        runtime.dispatch("b30-nonexistent-skill", "op")

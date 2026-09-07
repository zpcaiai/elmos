from __future__ import annotations

import json
import subprocess
import sys

from elmos_project_synthesis.intake import approve_request, create_draft
from elmos_project_synthesis.models import SynthesisRequest
from elmos_project_synthesis.workspace import generate_workspace, render_workspace


def _request(*, languages: tuple[str, ...] = ("java", "python")) -> SynthesisRequest:
    draft = create_draft(
        name="deployment-guide-service",
        description="管理订单并提供健康检查。",
        entity="order",
        languages=languages,
    )
    return SynthesisRequest.from_mapping(approve_request(draft, actor="user:deployment-reviewer"))


def _secured_request() -> SynthesisRequest:
    draft = create_draft(
        name="secured-deployment-guide",
        description="管理受租户隔离的订单并提供健康检查。",
        entity="order",
        languages=("python",),
        persistence="postgresql",
        auth_mode="jwt",
        permissions=tuple(
            {
                "actor": "api_user",
                "action": action,
                "resource": "order",
                "effect": "allow",
            }
            for action in ("create", "read", "update", "delete")
        ),
    )
    return SynthesisRequest.from_mapping(approve_request(draft, actor="user:security-reviewer"))


def test_generated_workspace_contains_exact_local_and_cloud_guidance() -> None:
    rendered = render_workspace(_request(languages=("java", "python", "rust")))

    local = rendered["docs/LOCAL_RUN.md"]
    cloud = rendered["docs/CLOUD_DEPLOYMENT.md"]
    readme = rendered["README.md"]
    contract = json.loads(rendered["deploy/deployment-options.json"])
    manifest = json.loads(rendered[".elmos/generation-manifest.json"])

    assert "Java 21 / Maven 3.9.10" in local
    assert "Python 3.12 / uv 0.11.16" in local
    assert "Rust 1.89.0 / Cargo 1.89.0" in local
    assert "cd java" in local
    assert "curl --fail http://127.0.0.1:8088/health" in local

    assert "Google Cloud Run" in cloud
    assert "--no-allow-unauthenticated" in cloud
    assert "cloud-run-control.py" in cloud
    assert "IMAGE_NAME@$IMAGE_DIGEST" in cloud
    assert "不得直接开放公网" in cloud
    assert "`NOT_RUN`" in cloud
    assert "`docs/LOCAL_RUN.md`" in readme
    assert "`docs/CLOUD_DEPLOYMENT.md`" in readme

    assert contract["status"] == "CONFIGURATION_REQUIRED"
    assert contract["external_execution_evidence"] == "NOT_RUN"
    assert contract["cloud"]["recommended_platform"] == "google-cloud-run"
    assert contract["cloud"]["apply_status"] == "NOT_RUN"
    assert [target["id"] for target in contract["local"]["targets"]] == ["java", "python", "rust"]
    assert contract["local"]["aggregate_hardware"]["concurrent_recommended"] == {
        "cpu": 16,
        "memory_gb": 32,
        "disk_gb": 38,
    }

    manifest_paths = {entry["path"] for entry in manifest["files"]}
    assert {
        "docs/LOCAL_RUN.md",
        "docs/CLOUD_DEPLOYMENT.md",
        "deploy/deployment-options.json",
        "deploy/cloud-run-control.py",
        "deploy/cloud-run-request.example.json",
        "deploy/cloud-run-authorization.example.json",
    } <= manifest_paths

    cloud_request = json.loads(rendered["deploy/cloud-run-request.example.json"])
    assert cloud_request["ingress"] == "internal"
    assert "@sha256:" in cloud_request["image"]
    assert cloud_request["secrets"] == []
    assert cloud_request["timeout_seconds"] == 300
    assert cloud_request["health"]["expected_json"] == {
        "service": "deployment-guide-service",
        "status": "UP",
    }
    assert cloud_request["environment"] == {
        "APP_ENV": "production",
        "APP_NAME": "deployment-guide-service",
    }
    authorization = json.loads(rendered["deploy/cloud-run-authorization.example.json"])
    assert authorization["approved"] is False
    assert authorization["action"].startswith("replace-")


def test_generated_cloud_run_controller_is_fail_closed(tmp_path) -> None:
    rendered = render_workspace(_request(languages=("python",)))
    controller = tmp_path / "cloud-run-control.py"
    config = tmp_path / "cloud-run-request.json"
    controller.write_text(rendered["deploy/cloud-run-control.py"], encoding="utf-8")
    cloud_request = json.loads(rendered["deploy/cloud-run-request.example.json"])
    cloud_request.update(
        {
            "project_id": "approved-project-1",
            "release_id": "release-01",
            "image": "asia-east1-docker.pkg.dev/approved-project-1/apps/api@sha256:" + "a" * 64,
            "runtime_service_account": (
                "deployment-guide-service-runtime@approved-project-1.iam.gserviceaccount.com"
            ),
        }
    )
    config.write_text(json.dumps(cloud_request), encoding="utf-8")

    validated = subprocess.run(  # noqa: S603 - fixed interpreter and generated local test asset.
        [sys.executable, str(controller), "validate", "--config", str(config)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert validated.returncode == 0, validated.stderr

    planned = subprocess.run(  # noqa: S603 - fixed interpreter and generated local test asset.
        [sys.executable, str(controller), "plan", "--config", str(config)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert planned.returncode == 0, planned.stderr
    plan = json.loads(planned.stdout)
    assert "--no-allow-unauthenticated" in plan["deploy"]
    assert "--no-traffic" in plan["deploy"]
    assert plan["external_execution_evidence"] == "NOT_RUN"

    refused = subprocess.run(  # noqa: S603 - fixed interpreter and generated local test asset.
        [sys.executable, str(controller), "deploy", "--config", str(config)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert refused.returncode == 2
    assert "MUTATION_REQUIRES_EXECUTE_AUTHORIZATION_AND_EXECUTOR" in refused.stderr

    failed_receipt = tmp_path / "failed-receipt.json"
    refused_execution = subprocess.run(  # noqa: S603 - fixed interpreter and generated local test asset.
        [
            sys.executable,
            str(controller),
            "deploy",
            "--config",
            str(config),
            "--execute",
            "--receipt",
            str(failed_receipt),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert refused_execution.returncode == 2
    failure = json.loads(failed_receipt.read_text(encoding="utf-8"))
    assert failure["status"] == "failed"
    assert failure["provider_mutation_status"] == "UNKNOWN_RECONCILIATION_REQUIRED"
    assert failure["orphan_and_billing_review"] == "REQUIRED"


def test_cloud_guidance_keeps_stateful_and_identity_work_fail_closed() -> None:
    request = _secured_request()
    rendered = render_workspace(request)
    cloud = rendered["docs/CLOUD_DEPLOYMENT.md"]

    assert "Cloud SQL for PostgreSQL" in cloud
    assert "JWT/OIDC" in cloud
    assert "database-url:REQUIRED_VERSION" in cloud
    assert "ELMOS_DATABASE_URL_FILE=/run/secrets/database-url" in cloud
    assert "latest" in cloud
    cloud_request = json.loads(rendered["deploy/cloud-run-request.example.json"])
    assert cloud_request["environment"]["ELMOS_DATABASE_URL_FILE"] == "/run/secrets/database-url"
    assert cloud_request["environment"]["ELMOS_JWT_HMAC_SECRET_FILE"] == "/run/secrets/jwt-hmac-secret"  # noqa: S105
    assert {secret["mount_path"] for secret in cloud_request["secrets"]} == {
        "/run/secrets/database-url",
        "/run/secrets/jwt-hmac-secret",
    }


def test_local_controller_refuses_partial_compose_for_production_profiles(tmp_path) -> None:
    request = _secured_request()
    workspace = tmp_path / "workspace"
    generate_workspace(request.raw, workspace)

    refused = subprocess.run(  # noqa: S603 - fixed interpreter and generated local test asset.
        [sys.executable, str(workspace / "scripts" / "projectctl.py"), "up", "--timeout", "5"],
        cwd=workspace,
        check=False,
        capture_output=True,
        text=True,
    )

    assert refused.returncode == 2
    assert "COMPOSE_DEVELOPMENT_PROFILE_UNAVAILABLE_USE_NATIVE_RUN:python" in refused.stderr

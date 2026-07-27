from __future__ import annotations

import json

from elmos_project_synthesis.intake import approve_request, create_draft
from elmos_project_synthesis.models import SynthesisRequest
from elmos_project_synthesis.workspace import render_workspace


def _request(*, languages: tuple[str, ...] = ("java", "python")) -> SynthesisRequest:
    draft = create_draft(
        name="deployment-guide-service",
        description="管理订单并提供健康检查。",
        entity="order",
        languages=languages,
    )
    return SynthesisRequest.from_mapping(approve_request(draft, actor="user:deployment-reviewer"))


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
    } <= manifest_paths


def test_cloud_guidance_keeps_stateful_and_identity_work_fail_closed() -> None:
    draft = create_draft(
        name="secured-deployment-guide",
        description="管理受租户隔离的订单并提供健康检查。",
        entity="order",
        languages=("python",),
        persistence="postgresql",
        auth_mode="jwt",
    )
    request = SynthesisRequest.from_mapping(approve_request(draft, actor="user:security-reviewer"))
    rendered = render_workspace(request)
    cloud = rendered["docs/CLOUD_DEPLOYMENT.md"]

    assert "Cloud SQL for PostgreSQL" in cloud
    assert "JWT/OIDC" in cloud
    assert "database-url:REQUIRED_VERSION" in cloud
    assert "ELMOS_DATABASE_URL_FILE=/run/secrets/database-url" in cloud
    assert "latest" in cloud

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from elmos_project_synthesis.cloud_run_control import (
    ControlError,
    _authorization,
    _canonical_digest,
    candidate_probe_endpoints,
    deploy_command,
    plan,
    validate_config,
)

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / "cloud-packs" / "elmos-project-generation-cloud-run-handoff" / "corpus"


def config() -> dict[str, object]:
    return {
        "schema_version": 1,
        "project_id": "approved-project-1",
        "region": "asia-east1",
        "service_name": "generated-api",
        "release_id": "release-01",
        "image": "asia-east1-docker.pkg.dev/approved-project-1/apps/api@sha256:" + "a" * 64,
        "runtime_service_account": "generated-api-runtime@approved-project-1.iam.gserviceaccount.com",
        "port": 8082,
        "cpu": "1",
        "memory": "512Mi",
        "concurrency": 40,
        "min_instances": 0,
        "max_instances": 10,
        "ingress": "internal",
        "health": {"path": "/health", "expected_json": {"status": "UP"}},
        "secrets": [{"mount_path": "/run/secrets/database-url", "name": "database-url", "version": "7"}],
    }


def test_plan_is_private_digest_pinned_and_no_traffic() -> None:
    deployment = config()
    assert validate_config(deployment) == []
    result = plan(deployment)
    command = result["deploy"]
    assert "--no-allow-unauthenticated" in command
    assert "--no-traffic" in command
    assert "--ingress=internal" in command
    assert "--set-secrets=/run/secrets/database-url=database-url:7" in command
    assert result["external_execution_evidence"] == "NOT_RUN"


def test_candidate_probe_uses_service_url_as_token_audience() -> None:
    endpoint, audience = candidate_probe_endpoints(
        {
            "status": {
                "url": "https://generated-api-project.asia-east1.run.app",
                "traffic": [
                    {
                        "tag": "candidate-release-01",
                        "uri": "https://candidate-release-01---generated-api-project.asia-east1.run.app",
                    }
                ],
            }
        },
        "candidate-release-01",
    )
    assert endpoint.startswith("https://candidate-release-01---")
    assert audience == "https://generated-api-project.asia-east1.run.app"


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("image", "asia-east1-docker.pkg.dev/approved-project-1/apps/api:latest", "image must"),
        ("ingress", "all", "ingress must remain private"),
        ("runtime_service_account", "1-compute@developer.gserviceaccount.com", "service account"),
        ("min_instances", 11, "must not exceed"),
    ],
)
def test_invalid_or_broad_configuration_is_rejected(field: str, value: object, message: str) -> None:
    deployment = config()
    deployment[field] = value
    assert any(message in error for error in validate_config(deployment))
    with pytest.raises(ControlError, match="CONFIG_INVALID"):
        deploy_command(deployment)


def test_latest_secret_alias_is_rejected() -> None:
    deployment = config()
    deployment["secrets"] = [
        {"mount_path": "/run/secrets/database-url", "name": "database-url", "version": "latest"}
    ]
    assert any("immutable numeric version" in error for error in validate_config(deployment))


def test_repository_negative_and_holdout_corpora() -> None:
    negative = json.loads((CORPUS / "negative" / "cases.json").read_text(encoding="utf-8"))
    for case in negative["cases"]:
        deployment = deepcopy(config())
        deployment.update(case["patch"])
        assert any(case["expected_error"] in error for error in validate_config(deployment)), case["id"]

    holdout = json.loads((CORPUS / "holdout" / "cases.json").read_text(encoding="utf-8"))
    for case in holdout["cases"]:
        deployment = deepcopy(config())
        deployment.update(case["patch"])
        assert validate_config(deployment) == [], case["id"]


def test_authorization_is_exact_expiring_and_separates_approver(tmp_path) -> None:
    deployment = config()
    authorization = {
        "schema_version": 1,
        "approved": True,
        "action": "deploy",
        "config_digest": _canonical_digest(deployment),
        "project_id": deployment["project_id"],
        "region": deployment["region"],
        "service_name": deployment["service_name"],
        "approver": "user:cloud-approver",
        "expires_at": (datetime.now(UTC) + timedelta(minutes=10)).isoformat(),
    }
    path = tmp_path / "authorization.json"
    path.write_text(json.dumps(authorization), encoding="utf-8")
    assert _authorization(path, "deploy", deployment, "user:operator")["approved"] is True

    authorization["approver"] = "user:operator"
    path.write_text(json.dumps(authorization), encoding="utf-8")
    with pytest.raises(ControlError, match="SEPARATE_APPROVER"):
        _authorization(path, "deploy", deployment, "user:operator")


def test_authorization_cannot_be_reused_for_rollback(tmp_path) -> None:
    deployment = config()
    path = tmp_path / "authorization.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "approved": True,
                "action": "deploy",
                "config_digest": _canonical_digest(deployment),
                "project_id": deployment["project_id"],
                "region": deployment["region"],
                "service_name": deployment["service_name"],
                "approver": "user:cloud-approver",
                "expires_at": (datetime.now(UTC) + timedelta(minutes=10)).isoformat(),
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ControlError, match="SCOPE_MISMATCH:action"):
        _authorization(path, "rollback", deployment, "user:operator")

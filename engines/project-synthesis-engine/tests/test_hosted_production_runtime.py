from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from elmos_project_synthesis.hosted_dispatcher import (
    JobDispatcher,
    PLAN_LIMITS,
    clamp_limits,
    reject_local_token_in_production,
    write_isolation_assertion,
)
from elmos_project_synthesis.hosted_identity import (
    IdentityError,
    OrganizationDirectory,
    require_oidc_configuration,
)
from elmos_project_synthesis.hosted_independent_replay import build_independent_replay_bundle
from elmos_project_synthesis.hosted_job_token import (
    JobTokenClaims,
    JobTokenError,
    ReplayCache,
    generate_ed25519_keypair,
    issue_job_token,
    verify_job_token,
)
from elmos_project_synthesis.hosted_postgres import (
    HostedPostgresError,
    assert_no_database_credentials_on_runner,
    read_url_file,
)

IMAGE = (
    "ghcr.io/elmos/generation-runner@sha256:"
    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
)


@pytest.fixture
def keys(tmp_path: Path) -> tuple[Path, Path]:
    private, public = generate_ed25519_keypair(tmp_path / "keys")
    return private, public


def _claims(now: int, **overrides: object) -> JobTokenClaims:
    payload = {
        "jti": "jti-0123456789abcdef",
        "tenant": "tenant-alpha",
        "actor": "actor-one",
        "job": "job-0123456789abcdef",
        "scope": ("generate", "build", "probe"),
        "image": IMAGE,
        "cpu_millis": 1000,
        "memory_mib": 512,
        "pids": 64,
        "wallclock_seconds": 600,
        "issued_at": now,
        "expires_at": now + 600,
    }
    payload.update(overrides)
    return JobTokenClaims(**payload)  # type: ignore[arg-type]


def test_job_token_round_trip_and_replay(keys: tuple[Path, Path], tmp_path: Path) -> None:
    private, public = keys
    now = 1_700_000_000
    token = issue_job_token(_claims(now), private_key=private, key_id="dispatcher-1", now=now)
    replay = ReplayCache(tmp_path / "replay")
    claims = verify_job_token(
        token,
        public_key=public,
        key_id="dispatcher-1",
        replay=replay,
        required_scope="generate",
        expected_tenant="tenant-alpha",
        expected_job="job-0123456789abcdef",
        now=now + 1,
        scratch=tmp_path,
    )
    assert claims.tenant == "tenant-alpha"
    with pytest.raises(JobTokenError, match="JOB_TOKEN_REPLAYED"):
        verify_job_token(
            token,
            public_key=public,
            key_id="dispatcher-1",
            replay=replay,
            required_scope="generate",
            now=now + 2,
            scratch=tmp_path,
        )


def test_job_token_rejects_mutable_image_and_expiry(keys: tuple[Path, Path], tmp_path: Path) -> None:
    private, public = keys
    now = 1_700_000_000
    with pytest.raises(JobTokenError, match="JOB_TOKEN_IMAGE_NOT_DIGEST_PINNED"):
        issue_job_token(
            _claims(now, image="ghcr.io/elmos/generation-runner:latest"),
            private_key=private,
            key_id="dispatcher-1",
            now=now,
        )
    token = issue_job_token(_claims(now), private_key=private, key_id="dispatcher-1", now=now)
    with pytest.raises(JobTokenError, match="JOB_TOKEN_EXPIRED"):
        verify_job_token(
            token,
            public_key=public,
            key_id="dispatcher-1",
            replay=ReplayCache(tmp_path / "replay"),
            required_scope="generate",
            now=now + 601,
            scratch=tmp_path,
        )


def test_dispatcher_queues_per_tenant_without_starvation(keys: tuple[Path, Path]) -> None:
    private, _public = keys
    dispatcher = JobDispatcher(private_key=private, key_id="dispatcher-1")
    first = dispatcher.enqueue(
        tenant="tenant-a",
        actor="actor-a",
        plan="trial",
        scope=("generate",),
        image=IMAGE,
        now=1_700_000_000,
    )
    second = dispatcher.enqueue(
        tenant="tenant-a",
        actor="actor-a",
        plan="trial",
        scope=("generate",),
        image=IMAGE,
        now=1_700_000_001,
    )
    other = dispatcher.enqueue(
        tenant="tenant-b",
        actor="actor-b",
        plan="trial",
        scope=("generate",),
        image=IMAGE,
        now=1_700_000_002,
    )
    assert first["status"] == "GRANTED" and first["token"]
    assert second["status"] == "QUEUED" and second["queue_position"] == 1
    assert other["status"] == "GRANTED" and other["token"]
    dispatcher.complete("tenant-a", first["job_id"], now=1_700_000_010)
    snapshot = dispatcher.snapshot()
    assert second["job_id"] in snapshot["tenant-a"]["running"]
    assert PLAN_LIMITS["trial"]["concurrent_jobs"] == 1


def test_production_rejects_local_token_and_single_tenant() -> None:
    with pytest.raises(JobTokenError, match="LOCAL_RUNNER_TOKEN_FORBIDDEN_IN_PRODUCTION"):
        reject_local_token_in_production(
            {
                "ELMOS_ENVIRONMENT": "production",
                "ELMOS_HOSTED_RUNNER_ENABLED": "true",
                "ELMOS_LOCAL_RUNNER_AUTH_TOKEN": "x" * 32,
            }
        )
    with pytest.raises(JobTokenError, match="TRUSTED_SINGLE_TENANT_FORBIDDEN_IN_PRODUCTION"):
        reject_local_token_in_production(
            {
                "ELMOS_ENVIRONMENT": "production",
                "ELMOS_HOSTED_RUNNER_ENABLED": "true",
                "ELMOS_TRUSTED_SINGLE_TENANT_ORGANIZATION_ID": "only-one",
            }
        )


def test_isolation_assertion_is_mandatory(tmp_path: Path) -> None:
    path = tmp_path / "isolation.json"
    write_isolation_assertion(
        path,
        {
            "job_id": "job-1",
            "image": IMAGE,
            "network": "none",
            "read_only_root": True,
            "cap_drop": "ALL",
            "no_new_privileges": True,
            "user": "65532:65532",
            "pids_limit": 256,
            "memory": "2048m",
            "cpus": "2.00",
            "exit_code": 0,
        },
    )
    assert json.loads(path.read_text(encoding="utf-8"))["network"] == "none"
    with pytest.raises(Exception, match="ISOLATION_ASSERTION_FAILED"):
        write_isolation_assertion(
            path,
            {
                "job_id": "job-1",
                "image": IMAGE,
                "network": "bridge",
                "read_only_root": True,
                "cap_drop": "ALL",
                "no_new_privileges": True,
                "user": "65532:65532",
                "pids_limit": 256,
                "memory": "2048m",
                "cpus": "2.00",
                "exit_code": 0,
            },
        )


def test_limits_are_clamped_to_runner_hard_caps() -> None:
    assert clamp_limits({"cpu_millis": 99_000, "memory_mib": 99_000})["cpu_millis"] == 2000


def test_hosted_postgres_url_file_and_runner_ban(tmp_path: Path) -> None:
    url_file = tmp_path / "pg.url"
    url_file.write_text("postgresql://app:secret@db.example:5432/app_db?sslmode=require\n", encoding="utf-8")
    os.chmod(url_file, 0o600)
    assert "db.example" in read_url_file(url_file)
    with pytest.raises(HostedPostgresError, match="RUNNER_HOST_HOLDS_DATABASE_CREDENTIALS"):
        assert_no_database_credentials_on_runner(
            {"ELMOS_RUNNER_ROLE": "runner-agent", "ELMOS_HOSTED_POSTGRES_URL_FILE": str(url_file)}
        )
    assert_no_database_credentials_on_runner({"ELMOS_RUNNER_ROLE": "control-plane"})


def test_organization_self_service_and_oidc_gate() -> None:
    directory = OrganizationDirectory()
    organization = directory.provision(
        name="Acme Generation",
        subject="user-founder",
        email="founder@example.com",
        now=1_700_000_000,
    )
    invitation = directory.invite(
        organization.organization_id,
        actor="user-founder",
        email="dev@example.com",
        role="DEVELOPER",
        now=1_700_000_001,
    )
    directory.accept(
        invitation["token"],
        subject="user-dev",
        email="dev@example.com",
        now=1_700_000_002,
    )
    member = directory.authorize_generation(organization.organization_id, "user-dev")
    assert member.role == "DEVELOPER"
    with pytest.raises(IdentityError, match="TRUSTED_SINGLE_TENANT_FORBIDDEN"):
        require_oidc_configuration(
            {
                "ELMOS_OIDC_ISSUER_URI": "https://idp.example/realms/elmos",
                "ELMOS_OIDC_AUTHORIZATION_ENDPOINT": "https://idp.example/auth",
                "ELMOS_OIDC_TOKEN_ENDPOINT": "https://idp.example/token",
                "ELMOS_OIDC_JWKS_URI": "https://idp.example/jwks",
                "ELMOS_OIDC_CLIENT_ID": "elmos-web",
                "ELMOS_OIDC_CLIENT_SECRET": "x" * 16,
                "ELMOS_OIDC_REDIRECT_URI": "https://app.example/login/callback",
                "ELMOS_OIDC_AUDIENCE": "elmos-api",
                "ELMOS_TRUSTED_SINGLE_TENANT_ORGANIZATION_ID": "nope",
            }
        )


def test_independent_replay_bundle_stays_unsigned(tmp_path: Path) -> None:
    matrix = {
        "case_count": 16,
        "passed_count": 16,
        "cases": [
            {"entity_shape": "multi-entity", "language": "java"},
            {"entity_shape": "multi-entity", "language": "rust"},
        ],
    }
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(json.dumps(matrix), encoding="utf-8")
    bundle = build_independent_replay_bundle(
        matrix_path=matrix_path,
        output_dir=tmp_path / "bundle",
        producer="executor@local",
    )
    assert bundle["independent_verification_status"] == "NOT_RUN"
    assert bundle["certification_status"] == "NOT_CERTIFIED"
    assert bundle["signature"] is None
    assert bundle["entity_shapes"] == ["multi-entity"]

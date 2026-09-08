from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "control_plane_cloud_run",
    ROOT / "scripts/deploy/control_plane_cloud_run.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def environment_file(tmp_path: Path, **overrides: str) -> Path:
    values = {
        "NEXT_PUBLIC_DESCOPE_BASE_URL": "https://api.descope.com",
        "NEXT_PUBLIC_DESCOPE_PROJECT_ID": "P2ExampleProject123",
        "PGHOST_UNPOOLED": "ep-example.ap-southeast-1.aws.neon.tech",
        "PGDATABASE": "neondb",
        "PGUSER": "elmos_runtime",
        "PGPASSWORD": "not-a-real-secret",
        **overrides,
    }
    path = tmp_path / ".env.production.local"
    path.write_text("\n".join(f'{key}="{value}"' for key, value in values.items()) + "\n")
    return path


def profile() -> object:
    value = MODULE.DeploymentProfile(json.loads((ROOT / "deploy/cloud-run/control-plane/profile.json").read_text()))
    value.validate()
    return value


def test_production_profile_is_exact_and_public_ingress_is_justified() -> None:
    value = profile()
    assert value.project_id == "gen-lang-client-0684615336"
    assert value.region == "asia-east1"
    assert value.service_name == "elmos-control-plane"
    assert value.image_base.endswith("/elmos-control-plane/elmos-control-plane")
    assert value.raw["network"]["allow_unauthenticated_invocation"] is True
    assert "Spring Security" in value.raw["network"]["justification"]


def test_environment_parser_never_sources_shell_syntax(tmp_path: Path) -> None:
    path = environment_file(tmp_path, PGPASSWORD="$(touch /tmp/elmos-must-not-run)")
    values = MODULE.parse_environment_file(path)
    assert values["PGPASSWORD"] == "$(touch /tmp/elmos-must-not-run)"
    assert not Path("/tmp/elmos-must-not-run").exists()


def test_environment_parser_rejects_duplicate_required_key(tmp_path: Path) -> None:
    path = environment_file(tmp_path)
    path.write_text(path.read_text() + 'PGUSER="second"\n')
    with pytest.raises(MODULE.DeploymentError, match="duplicate environment key"):
        MODULE.parse_environment_file(path)


def test_environment_parser_rejects_missing_secret(tmp_path: Path) -> None:
    path = environment_file(tmp_path)
    path.write_text(path.read_text().replace('PGPASSWORD="not-a-real-secret"\n', ""))
    with pytest.raises(MODULE.DeploymentError, match="PGPASSWORD"):
        MODULE.parse_environment_file(path)


def test_identity_and_database_are_derived_without_secret_in_plan(tmp_path: Path) -> None:
    value = profile()
    env = MODULE.parse_environment_file(environment_file(tmp_path))
    identity = MODULE.identity_configuration(value, env)
    secrets = MODULE.database_secrets(value, env)
    plan = MODULE.display_plan(value, "a" * 40)
    assert identity == {
        "ELMOS_OIDC_ISSUER_URI": "https://api.descope.com/P2ExampleProject123",
        "ELMOS_OIDC_JWKS_URI": "https://api.descope.com/P2ExampleProject123/.well-known/jwks.json",
        "ELMOS_OIDC_AUDIENCE": "P2ExampleProject123",
    }
    assert secrets["elmos-control-plane-database-url"].startswith(b"jdbc:postgresql://")
    assert "not-a-real-secret" not in json.dumps(plan)
    assert plan["secret_references"] == [
        "elmos-control-plane-database-password",
        "elmos-control-plane-database-url",
        "elmos-control-plane-database-user",
    ]


@pytest.mark.parametrize(
    "base_url",
    [
        "http://api.descope.com",
        "https://user@example.com",
        "https://api.descope.com/path",
        "https://api.descope.com?token=x",
    ],
)
def test_identity_rejects_untrusted_descope_base_url(tmp_path: Path, base_url: str) -> None:
    value = profile()
    env = MODULE.parse_environment_file(
        environment_file(tmp_path, NEXT_PUBLIC_DESCOPE_BASE_URL=base_url)
    )
    with pytest.raises(MODULE.DeploymentError, match="HTTPS origin"):
        MODULE.identity_configuration(value, env)


def test_database_rejects_host_injection(tmp_path: Path) -> None:
    value = profile()
    env = MODULE.parse_environment_file(
        environment_file(tmp_path, PGHOST_UNPOOLED="db.example.com/?x=y")
    )
    with pytest.raises(MODULE.DeploymentError, match="database host"):
        MODULE.database_secrets(value, env)


class FakeGcloud:
    def __init__(self, current: bytes):
        self.current = current
        self.calls: list[tuple[str, ...]] = []

    def run(self, *args: str, input_bytes=None, capture=False, check=True):
        del capture, check
        self.calls.append(args)
        if args[:2] == ("secrets", "describe"):
            return type("Result", (), {"returncode": 0, "stdout": b""})()
        if args[:3] == ("secrets", "versions", "access"):
            return type("Result", (), {"returncode": 0, "stdout": self.current})()
        if args[:3] == ("secrets", "versions", "add"):
            self.current = input_bytes
        return type("Result", (), {"returncode": 0, "stdout": b""})()


def test_secret_promotion_is_idempotent_when_value_is_unchanged() -> None:
    gcloud = FakeGcloud(b"same-value")
    MODULE.ensure_secret(gcloud, profile(), "elmos-control-plane-database-user", b"same-value")
    assert not any(call[:3] == ("secrets", "versions", "add") for call in gcloud.calls)
    assert any(call[:2] == ("secrets", "add-iam-policy-binding") for call in gcloud.calls)


def test_secret_promotion_appends_version_only_when_value_changes() -> None:
    gcloud = FakeGcloud(b"old-value")
    MODULE.ensure_secret(gcloud, profile(), "elmos-control-plane-database-user", b"new-value")
    assert sum(call[:3] == ("secrets", "versions", "add") for call in gcloud.calls) == 1
    assert gcloud.current == b"new-value"

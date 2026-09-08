#!/usr/bin/env python3
"""Fail-closed deployment control for the ELMOS Java Control Plane on Cloud Run."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROFILE = REPOSITORY_ROOT / "deploy/cloud-run/control-plane/profile.json"
GCLOUD_IMAGE = (
    "gcr.io/google.com/cloudsdktool/google-cloud-cli"
    "@sha256:87eaf69da735ab8dfc1c640df1e85a467a4feedf2256d35dad368f970d9cd35f"
)
REVISION = re.compile(r"^[0-9a-f]{40}$")
DNS_LABEL = re.compile(r"^[a-z][a-z0-9-]{1,61}[a-z0-9]$")
PROJECT_ID = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")
REGION = re.compile(r"^[a-z]+-[a-z]+[0-9]+$")
SECRET_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,254}$")
ALLOWED_VERCEL_KEYS = {
    "NEXT_PUBLIC_DESCOPE_BASE_URL",
    "NEXT_PUBLIC_DESCOPE_PROJECT_ID",
    "PGHOST_UNPOOLED",
    "PGDATABASE",
    "PGUSER",
    "PGPASSWORD",
}


class DeploymentError(RuntimeError):
    pass


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DeploymentError(f"invalid profile: {path}") from exc
    if not isinstance(value, dict):
        raise DeploymentError("profile root must be an object")
    return value


def parse_environment_file(path: Path) -> dict[str, str]:
    """Parse a Vercel dotenv file without sourcing or evaluating it."""
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise DeploymentError(f"cannot read environment file: {path}") from exc
    for number, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise DeploymentError(f"invalid environment line {number}")
        key, raw_value = line.split("=", 1)
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise DeploymentError(f"invalid environment key on line {number}")
        if key in values:
            raise DeploymentError(f"duplicate environment key: {key}")
        try:
            parsed = shlex.split(raw_value, posix=True)
        except ValueError as exc:
            raise DeploymentError(f"invalid environment value on line {number}") from exc
        if len(parsed) > 1:
            raise DeploymentError(f"environment value must be a single token on line {number}")
        values[key] = parsed[0] if parsed else ""
    missing = sorted(key for key in ALLOWED_VERCEL_KEYS if not values.get(key))
    if missing:
        raise DeploymentError("missing required Vercel keys: " + ", ".join(missing))
    return {key: values[key] for key in ALLOWED_VERCEL_KEYS}


def require_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DeploymentError(f"{field} must be a non-empty string")
    return value.strip()


def validate_https_origin(value: str, field: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise DeploymentError(f"{field} must be an HTTPS origin")
    return f"https://{parsed.netloc}"


@dataclass(frozen=True)
class DeploymentProfile:
    raw: Mapping[str, Any]

    @property
    def project_id(self) -> str:
        return require_string(self.raw.get("project_id"), "project_id")

    @property
    def region(self) -> str:
        return require_string(self.raw.get("region"), "region")

    @property
    def service_name(self) -> str:
        return require_string(self.raw.get("service_name"), "service_name")

    @property
    def repository(self) -> str:
        return require_string(self.raw.get("artifact_repository"), "artifact_repository")

    @property
    def image_name(self) -> str:
        return require_string(self.raw.get("image_name"), "image_name")

    @property
    def service_account_name(self) -> str:
        return require_string(self.raw.get("runtime_service_account"), "runtime_service_account")

    @property
    def service_account_email(self) -> str:
        return f"{self.service_account_name}@{self.project_id}.iam.gserviceaccount.com"

    @property
    def image_base(self) -> str:
        return (
            f"{self.region}-docker.pkg.dev/{self.project_id}/"
            f"{self.repository}/{self.image_name}"
        )

    @property
    def container(self) -> Mapping[str, Any]:
        value = self.raw.get("container")
        if not isinstance(value, dict):
            raise DeploymentError("container must be an object")
        return value

    @property
    def secrets(self) -> Mapping[str, str]:
        value = self.raw.get("secrets")
        if not isinstance(value, dict) or set(value) != {
            "ELMOS_DATABASE_URL", "ELMOS_DATABASE_USER", "ELMOS_DATABASE_PASSWORD"
        }:
            raise DeploymentError("secrets must contain the exact database mapping")
        result = {str(key): require_string(item, f"secrets.{key}") for key, item in value.items()}
        if any(not SECRET_NAME.fullmatch(item) for item in result.values()):
            raise DeploymentError("invalid Secret Manager identifier")
        return result

    def validate(self) -> None:
        if self.raw.get("schema_version") != 1:
            raise DeploymentError("unsupported profile schema_version")
        if not PROJECT_ID.fullmatch(self.project_id):
            raise DeploymentError("invalid project_id")
        if not REGION.fullmatch(self.region):
            raise DeploymentError("invalid region")
        for field, value in (
            ("service_name", self.service_name),
            ("artifact_repository", self.repository),
            ("image_name", self.image_name),
            ("runtime_service_account", self.service_account_name),
        ):
            if not DNS_LABEL.fullmatch(value):
                raise DeploymentError(f"invalid {field}")
        dockerfile = REPOSITORY_ROOT / require_string(self.container.get("dockerfile"), "container.dockerfile")
        if not dockerfile.is_file():
            raise DeploymentError("control-plane Dockerfile is missing")
        if self.container.get("min_instances") != 0:
            raise DeploymentError("production profile must scale to zero until a budget is approved")
        if not 1 <= int(self.container.get("max_instances", 0)) <= 10:
            raise DeploymentError("max_instances must be between 1 and 10")
        network = self.raw.get("network")
        if not isinstance(network, dict) or network.get("ingress") != "all":
            raise DeploymentError("Vercel integration requires exact public Cloud Run ingress")
        if network.get("allow_unauthenticated_invocation") is not True:
            raise DeploymentError("Vercel integration requires public invocation with application JWT enforcement")
        if len(require_string(network.get("justification"), "network.justification")) < 40:
            raise DeploymentError("public ingress justification is incomplete")
        self.secrets


def identity_configuration(profile: DeploymentProfile, env: Mapping[str, str]) -> dict[str, str]:
    identity = profile.raw.get("identity")
    if not isinstance(identity, dict):
        raise DeploymentError("identity must be an object")
    base_key = require_string(identity.get("base_url_key"), "identity.base_url_key")
    project_key = require_string(identity.get("project_id_key"), "identity.project_id_key")
    base_url = validate_https_origin(require_string(env.get(base_key), base_key), base_key)
    project_id = require_string(env.get(project_key), project_key)
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", project_id):
        raise DeploymentError("Descope project id has an invalid format")
    return {
        "ELMOS_OIDC_ISSUER_URI": f"{base_url}/{project_id}",
        "ELMOS_OIDC_JWKS_URI": f"{base_url}/{project_id}/.well-known/jwks.json",
        "ELMOS_OIDC_AUDIENCE": project_id,
    }


def database_secrets(profile: DeploymentProfile, env: Mapping[str, str]) -> dict[str, bytes]:
    database = profile.raw.get("database")
    if not isinstance(database, dict):
        raise DeploymentError("database must be an object")
    host = require_string(env.get(require_string(database.get("host_key"), "database.host_key")), "database host")
    name = require_string(env.get(require_string(database.get("database_key"), "database.database_key")), "database name")
    user = require_string(env.get(require_string(database.get("user_key"), "database.user_key")), "database user")
    password = require_string(env.get(require_string(database.get("password_key"), "database.password_key")), "database password")
    if any(character in host for character in "/?#@") or not re.fullmatch(r"[A-Za-z0-9.-]+(?::[0-9]{1,5})?", host):
        raise DeploymentError("database host has an invalid format")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,63}", name):
        raise DeploymentError("database name has an invalid format")
    parameters = require_string(database.get("jdbc_parameters"), "database.jdbc_parameters")
    jdbc = f"jdbc:postgresql://{host}/{name}?{parameters}"
    return {
        profile.secrets["ELMOS_DATABASE_URL"]: jdbc.encode(),
        profile.secrets["ELMOS_DATABASE_USER"]: user.encode(),
        profile.secrets["ELMOS_DATABASE_PASSWORD"]: password.encode(),
    }


class Gcloud:
    def __init__(self, config_dir: Path | None):
        self.config_dir = config_dir
        self.binary = shutil_which("gcloud") if config_dir is None else None
        if not self.binary and config_dir is None:
            raise DeploymentError("gcloud is unavailable; provide --gcloud-config-dir for the pinned SDK container")
        if config_dir is not None:
            config_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            if config_dir.is_symlink() or (config_dir.stat().st_mode & 0o077):
                raise DeploymentError("gcloud config directory must be private and not a symlink")

    def command(self, *args: str) -> list[str]:
        if self.binary:
            return [self.binary, *args]
        assert self.config_dir is not None
        return [
            "docker", "run", "--rm", "-i",
            "-v", f"{self.config_dir}:/root/.config/gcloud",
            "-v", f"{REPOSITORY_ROOT}:/workspace:ro",
            "-w", "/workspace",
            GCLOUD_IMAGE,
            "gcloud", *args,
        ]

    def run(
        self,
        *args: str,
        input_bytes: bytes | None = None,
        capture: bool = False,
        check: bool = True,
    ) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            self.command(*args),
            input=input_bytes,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE if capture else None,
            check=check,
        )


def shutil_which(binary: str) -> str | None:
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        candidate = Path(directory) / binary
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def exact_revision(expected: str | None) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPOSITORY_ROOT,
        check=True, stdout=subprocess.PIPE, text=True,
    )
    revision = completed.stdout.strip()
    if not REVISION.fullmatch(revision):
        raise DeploymentError("repository HEAD is not an exact Git revision")
    if expected and revision != expected:
        raise DeploymentError("repository revision does not match --expected-revision")
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"], cwd=REPOSITORY_ROOT,
        check=True, stdout=subprocess.PIPE, text=True,
    ).stdout
    if dirty:
        raise DeploymentError("tracked repository changes must be committed before apply")
    return revision


def display_plan(profile: DeploymentProfile, revision: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "project_id": profile.project_id,
        "region": profile.region,
        "service_name": profile.service_name,
        "image_tag": f"{profile.image_base}:{revision}",
        "runtime_service_account": profile.service_account_email,
        "secret_references": sorted(profile.secrets.values()),
        "public_ingress": True,
        "application_authentication": "Descope JWT issuer, JWKS, audience",
        "readiness_path": profile.raw["health"]["path"],
        "vercel_variable": profile.raw["vercel"]["environment_variable"],
    }


def ensure_gcloud_identity(gcloud: Gcloud, profile: DeploymentProfile) -> None:
    account = gcloud.run("auth", "list", "--filter=status:ACTIVE", "--format=value(account)", capture=True)
    if not account.stdout.strip():
        raise DeploymentError("no active Google Cloud account")
    project = gcloud.run("config", "get-value", "project", capture=True, check=False)
    configured = project.stdout.decode().strip()
    if configured and configured != "(unset)" and configured != profile.project_id:
        raise DeploymentError("active gcloud project conflicts with the production profile")
    gcloud.run("config", "set", "project", profile.project_id, capture=True)


def ensure_secret(gcloud: Gcloud, profile: DeploymentProfile, name: str, value: bytes) -> None:
    exists = gcloud.run(
        "secrets", "describe", name, "--project", profile.project_id,
        capture=True, check=False,
    ).returncode == 0
    if not exists:
        gcloud.run(
            "secrets", "create", name, "--project", profile.project_id,
            "--replication-policy=automatic",
        )
    current = gcloud.run(
        "secrets", "versions", "access", "latest", "--secret", name,
        "--project", profile.project_id, capture=True, check=False,
    )
    if current.returncode != 0 or not hmac.compare_digest(current.stdout, value):
        gcloud.run(
            "secrets", "versions", "add", name, "--project", profile.project_id,
            "--data-file=-", input_bytes=value,
        )
    gcloud.run(
        "secrets", "add-iam-policy-binding", name,
        "--project", profile.project_id,
        f"--member=serviceAccount:{profile.service_account_email}",
        "--role=roles/secretmanager.secretAccessor",
        "--condition=None",
        capture=True,
    )


def docker_login(gcloud: Gcloud, profile: DeploymentProfile, docker_config: Path) -> None:
    token = gcloud.run("auth", "print-access-token", capture=True).stdout.strip()
    if len(token) < 64:
        raise DeploymentError("Google access token was not issued")
    subprocess.run(
        [
            "docker", "login", "-u", "oauth2accesstoken", "--password-stdin",
            f"https://{profile.region}-docker.pkg.dev",
        ],
        input=token,
        stdout=subprocess.DEVNULL,
        env={**os.environ, "DOCKER_CONFIG": str(docker_config)},
        check=True,
    )


def deploy(profile: DeploymentProfile, env_file: Path, gcloud_dir: Path | None, expected: str | None) -> dict[str, Any]:
    revision = exact_revision(expected)
    environment = parse_environment_file(env_file)
    identity = identity_configuration(profile, environment)
    secrets = database_secrets(profile, environment)
    gcloud = Gcloud(gcloud_dir)
    ensure_gcloud_identity(gcloud, profile)
    gcloud.run(
        "services", "enable",
        "run.googleapis.com", "artifactregistry.googleapis.com", "secretmanager.googleapis.com",
        "--project", profile.project_id,
    )
    repository_exists = gcloud.run(
        "artifacts", "repositories", "describe", profile.repository,
        "--project", profile.project_id, "--location", profile.region,
        capture=True, check=False,
    ).returncode == 0
    if not repository_exists:
        gcloud.run(
            "artifacts", "repositories", "create", profile.repository,
            "--project", profile.project_id, "--location", profile.region,
            "--repository-format=docker", "--immutable-tags",
            "--description=ELMOS Java Control Plane production images",
        )
    account_exists = gcloud.run(
        "iam", "service-accounts", "describe", profile.service_account_email,
        "--project", profile.project_id, capture=True, check=False,
    ).returncode == 0
    if not account_exists:
        gcloud.run(
            "iam", "service-accounts", "create", profile.service_account_name,
            "--project", profile.project_id,
            "--display-name=ELMOS Control Plane runtime",
        )
    for name, value in secrets.items():
        ensure_secret(gcloud, profile, name, value)
    tag = f"{profile.image_base}:{revision}"
    existing_image = gcloud.run(
        "artifacts", "docker", "images", "describe", tag,
        "--project", profile.project_id, "--format=value(image_summary.digest)",
        capture=True, check=False,
    )
    digest = existing_image.stdout.decode().strip() if existing_image.returncode == 0 else ""
    if not digest:
        with tempfile.TemporaryDirectory(prefix="elmos-docker-auth-") as docker_config_raw:
            docker_config = Path(docker_config_raw)
            docker_login(gcloud, profile, docker_config)
            subprocess.run(
                [
                    "docker", "build", "--platform=linux/amd64",
                    "--file", str(REPOSITORY_ROOT / profile.container["dockerfile"]),
                    "--tag", tag, str(REPOSITORY_ROOT),
                ],
                check=True,
            )
            subprocess.run(
                ["docker", "push", tag],
                env={**os.environ, "DOCKER_CONFIG": str(docker_config)},
                check=True,
            )
        digest = gcloud.run(
            "artifacts", "docker", "images", "describe", tag,
            "--project", profile.project_id, "--format=value(image_summary.digest)",
            capture=True,
        ).stdout.decode().strip()
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise DeploymentError("Artifact Registry did not return an immutable image digest")
    image = f"{profile.image_base}@{digest}"
    env_values = {
        "SPRING_PROFILES_ACTIVE": "prod",
        "ELMOS_CONTROL_PLANE_PORT": str(profile.container["port"]),
        "ELMOS_LOCAL_IDENTITY_ENABLED": "false",
        **identity,
    }
    env_argument = ",".join(f"{key}={value}" for key, value in sorted(env_values.items()))
    secret_argument = ",".join(
        f"{variable}={secret}:latest" for variable, secret in sorted(profile.secrets.items())
    )
    labels = profile.raw.get("labels")
    if not isinstance(labels, dict) or not labels:
        raise DeploymentError("labels must be a non-empty object")
    label_argument = ",".join(f"{key}={value}" for key, value in sorted(labels.items()))
    gcloud.run(
        "run", "deploy", profile.service_name,
        "--project", profile.project_id,
        "--region", profile.region,
        "--platform=managed",
        f"--image={image}",
        f"--service-account={profile.service_account_email}",
        f"--port={profile.container['port']}",
        f"--cpu={profile.container['cpu']}",
        f"--memory={profile.container['memory']}",
        f"--min={profile.container['min_instances']}",
        f"--max={profile.container['max_instances']}",
        f"--concurrency={profile.container['concurrency']}",
        f"--timeout={profile.container['timeout_seconds']}",
        f"--execution-environment={profile.container['execution_environment']}",
        "--ingress=all",
        "--allow-unauthenticated",
        f"--set-env-vars={env_argument}",
        f"--set-secrets={secret_argument}",
        f"--labels={label_argument}",
        "--quiet",
    )
    service_url = gcloud.run(
        "run", "services", "describe", profile.service_name,
        "--project", profile.project_id, "--region", profile.region,
        "--format=value(status.url)", capture=True,
    ).stdout.decode().strip()
    validate_https_origin(service_url, "Cloud Run service URL")
    check_readiness(service_url, profile)
    return {
        "schema_version": 1,
        "status": "DEPLOYED",
        "project_id": profile.project_id,
        "region": profile.region,
        "service_name": profile.service_name,
        "service_url": service_url,
        "image_digest": digest,
        "revision": revision,
        "profile_sha256": hashlib.sha256(json.dumps(profile.raw, sort_keys=True).encode()).hexdigest(),
    }


def check_readiness(base_url: str, profile: DeploymentProfile) -> None:
    health = profile.raw.get("health")
    if not isinstance(health, dict):
        raise DeploymentError("health must be an object")
    path = require_string(health.get("path"), "health.path")
    expected = require_string(health.get("expected_status"), "health.expected_status")
    request = urllib.request.Request(f"{base_url}{path}", headers={"User-Agent": "elmos-cloud-run-gate/1"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.load(response)
            status = response.status
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise DeploymentError("Cloud Run readiness request failed") from exc
    if status != 200 or not isinstance(payload, dict) or payload.get("status") != expected:
        raise DeploymentError("Cloud Run readiness did not report UP")


def previous_revision(gcloud: Gcloud, profile: DeploymentProfile) -> str:
    result = gcloud.run(
        "run", "revisions", "list", "--project", profile.project_id,
        "--region", profile.region, f"--service={profile.service_name}",
        "--sort-by=~metadata.creationTimestamp", "--limit=2",
        "--format=value(metadata.name)", capture=True,
    ).stdout.decode().splitlines()
    if len(result) < 2 or not DNS_LABEL.fullmatch(result[1].strip()):
        raise DeploymentError("no previous Cloud Run revision is available")
    return result[1].strip()


def rollback(profile: DeploymentProfile, gcloud_dir: Path | None) -> None:
    gcloud = Gcloud(gcloud_dir)
    ensure_gcloud_identity(gcloud, profile)
    revision = previous_revision(gcloud, profile)
    gcloud.run(
        "run", "services", "update-traffic", profile.service_name,
        "--project", profile.project_id, "--region", profile.region,
        f"--to-revisions={revision}=100", "--quiet",
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    result.add_argument("--gcloud-config-dir", type=Path)
    subcommands = result.add_subparsers(dest="command", required=True)
    subcommands.add_parser("validate")
    plan = subcommands.add_parser("plan")
    plan.add_argument("--expected-revision")
    apply = subcommands.add_parser("apply")
    apply.add_argument("--vercel-env-file", type=Path, required=True)
    apply.add_argument("--expected-revision", required=True)
    subcommands.add_parser("rollback")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        profile = DeploymentProfile(read_json(args.profile))
        profile.validate()
        if args.command == "validate":
            print(f"OK: {profile.raw['profile_key']}")
        elif args.command == "plan":
            revision = exact_revision(args.expected_revision)
            print(json.dumps(display_plan(profile, revision), indent=2))
        elif args.command == "apply":
            receipt = deploy(
                profile, args.vercel_env_file, args.gcloud_config_dir,
                args.expected_revision,
            )
            print(json.dumps(receipt, indent=2))
        elif args.command == "rollback":
            rollback(profile, args.gcloud_config_dir)
            print("OK: rollback traffic update completed")
        return 0
    except (DeploymentError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

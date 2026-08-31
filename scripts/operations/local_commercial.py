#!/usr/bin/env python3
"""Start and verify the bounded local ELMOS commercial-management core."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import secrets
import shutil
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / ".elmos" / "local-commercial"
ENV_FILE = STATE_DIR / "runtime.env"
RESULT_FILE = STATE_DIR / "smoke-result.json"
LOCK_FILE = STATE_DIR / "operation.lock"
COMPOSE_FILE = ROOT / "deploy" / "compose" / "docker-compose.local-commercial.yml"
PROJECT_NAME = "elmos-local-commercial"
DATABASE_VOLUME_NAME = f"{PROJECT_NAME}_local-commercial-postgres"
LOCAL_ORGANIZATION_ID = "local-commercial"
LOCAL_ACTOR_ID = "local-commercial-admin"
LOCAL_ORGANIZATION_DISPLAY_NAME = "ELMOS Local Commercial"
LEASE_HOURS = 8
RUNTIME_ENVIRONMENT_KEYS = (
    "LOCAL_DATABASE_PASSWORD",
    "LOCAL_OPERATIONS_API_KEY",
    "LOCAL_REJECTED_ADMIN_TOKEN",
    "LOCAL_WORKSPACE_API_KEY",
    "LOCAL_SESSION_SECRET",
    "LOCAL_CREDENTIAL_EXPIRES_AT",
)
LEGACY_RUNTIME_ENVIRONMENT_KEY = "LOCAL_ADMIN_TOKEN"
JAVA_ARTIFACTS = (
    ROOT / "apps" / "control-plane" / "target" / "elmos-control-plane-0.1.0-SNAPSHOT-exec.jar",
    ROOT / "apps" / "commercial-api" / "target" / "elmos-commercial-api-0.1.0-SNAPSHOT-exec.jar",
    ROOT / "apps" / "workspace-service" / "target" / "elmos-workspace-service-0.1.0-SNAPSHOT-exec.jar",
)
PNPM_VERSION = "10.12.4"
PNPM_DIST_SHA256 = "f9d2e9260ca62b43f3e2dcd5ca2af0a062be584e230b8414fecdc0730c246859"
LOCAL_PNPM_DIR = ROOT / "apps" / "web-console" / ".local-pnpm"


class LocalCommercialError(RuntimeError):
    pass


def assert_local_docker_context() -> None:
    configured_host = os.environ.get("DOCKER_HOST", "").strip()
    if configured_host:
        endpoint = configured_host
    else:
        configured_context = os.environ.get("DOCKER_CONTEXT", "").strip()
        try:
            if not configured_context:
                shown = subprocess.run(
                    ["docker", "context", "show"],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=10,
                )
                configured_context = shown.stdout.strip()
            inspected = subprocess.run(
                [
                    "docker", "context", "inspect", configured_context,
                    "--format", "{{json .Endpoints.docker.Host}}",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )
            endpoint = json.loads(inspected.stdout)
        except FileNotFoundError as error:
            raise LocalCommercialError("Docker CLI 未安装或不在 PATH 中。") from error
        except (
            json.JSONDecodeError,
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
        ) as error:
            raise LocalCommercialError("无法确认 Docker context；本地商业入口已拒绝执行。") from error
    if not isinstance(endpoint, str) or not endpoint.startswith("unix:///"):
        raise LocalCommercialError(
            "本地商业入口只允许当前机器的 Unix Docker socket；"
            "TCP、SSH、npipe 或无法识别的远程 context 均被拒绝。"
        )


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso8601(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_env() -> dict[str, str]:
    try:
        metadata = ENV_FILE.lstat()
    except FileNotFoundError:
        return {}
    if (
        not stat.S_ISREG(metadata.st_mode)
        or ENV_FILE.is_symlink()
        or metadata.st_uid != os.getuid()
        or metadata.st_mode & 0o077
        or metadata.st_size > 16 * 1024
    ):
        raise LocalCommercialError(
            "runtime.env 必须是当前用户拥有、非符号链接、至多 16 KiB 且权限不宽于 0600 的普通文件。"
        )
    try:
        content = ENV_FILE.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise LocalCommercialError("runtime.env 无法安全读取或不是 UTF-8 文本。") from error
    values: dict[str, str] = {}
    for raw in content.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key not in (*RUNTIME_ENVIRONMENT_KEYS, LEGACY_RUNTIME_ENVIRONMENT_KEY) or key in values:
            raise LocalCommercialError("runtime.env 包含未知或重复配置键。")
        values[key] = value
    legacy_admin_token = values.pop(LEGACY_RUNTIME_ENVIRONMENT_KEY, "")
    if legacy_admin_token and "LOCAL_REJECTED_ADMIN_TOKEN" not in values:
        values["LOCAL_REJECTED_ADMIN_TOKEN"] = legacy_admin_token
    return values


def credentials_valid(values: dict[str, str]) -> bool:
    try:
        expires = datetime.fromisoformat(
            values["LOCAL_CREDENTIAL_EXPIRES_AT"].replace("Z", "+00:00")
        )
        if expires.tzinfo is None or expires.utcoffset() is None:
            return False
    except (KeyError, TypeError, ValueError):
        return False
    required = (
        "LOCAL_DATABASE_PASSWORD",
        "LOCAL_OPERATIONS_API_KEY",
        "LOCAL_REJECTED_ADMIN_TOKEN",
        "LOCAL_WORKSPACE_API_KEY",
        "LOCAL_SESSION_SECRET",
    )
    return all(len(values.get(name, "")) >= 32 for name in required) \
        and expires > utc_now() + timedelta(minutes=10) \
        and expires <= utc_now() + timedelta(hours=24)


def docker_volume_metadata() -> dict[str, Any] | None:
    assert_local_docker_context()
    try:
        result = subprocess.run(
            ["docker", "volume", "inspect", DATABASE_VOLUME_NAME],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except FileNotFoundError as error:
        raise LocalCommercialError("Docker CLI 未安装或不在 PATH 中。") from error
    except subprocess.TimeoutExpired as error:
        raise LocalCommercialError("Docker 数据卷检查超时；请先检查 Docker daemon。") from error
    if result.returncode == 0:
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise LocalCommercialError("Docker 返回了无法解析的数据卷信息。") from error
        if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
            raise LocalCommercialError("Docker 返回了不受支持的数据卷信息。")
        return payload[0]
    if "no such volume" in result.stderr.lower():
        return None
    raise LocalCommercialError("无法确认本地 PostgreSQL 数据卷状态；请先检查 Docker daemon。")


def docker_volume_exists() -> bool:
    return docker_volume_metadata() is not None


@contextmanager
def exclusive_operation_lock():
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(
        LOCK_FILE,
        os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    os.fchmod(descriptor, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise LocalCommercialError(
                "另一个本地商业核心操作正在执行；请等待其完成后再重试。"
            ) from error
        yield
    finally:
        os.close(descriptor)


def ensure_credentials(*, rotate: bool = False) -> dict[str, str]:
    values = parse_env()
    if not rotate and credentials_valid(values):
        return values
    # PostgreSQL only applies POSTGRES_PASSWORD when initializing an empty
    # volume. Keep that password stable while rotating the short-lived service
    # leases, otherwise an expired service lease would make a healthy retained
    # local database impossible to reconnect to.
    database_password = values.get("LOCAL_DATABASE_PASSWORD", "")
    if len(database_password) < 32:
        if docker_volume_exists():
            raise LocalCommercialError(
                "检测到保留的本地 PostgreSQL 数据卷，但找不到与其匹配的数据库密码。"
                "请从备份恢复 .elmos/local-commercial/runtime.env；若确认可以删除本地数据，"
                "请显式执行 python3 scripts/operations/local_commercial.py reset-data "
                "--confirm-local-data-loss。"
            )
        database_password = secrets.token_urlsafe(36)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    expires = utc_now() + timedelta(hours=LEASE_HOURS)
    values = {
        "LOCAL_DATABASE_PASSWORD": database_password,
        "LOCAL_OPERATIONS_API_KEY": secrets.token_urlsafe(36),
        # Negative fixture only: the Web admin BFF must reject this Bearer value.
        "LOCAL_REJECTED_ADMIN_TOKEN": secrets.token_urlsafe(36),
        "LOCAL_WORKSPACE_API_KEY": secrets.token_urlsafe(36),
        "LOCAL_SESSION_SECRET": secrets.token_urlsafe(48),
        "LOCAL_CREDENTIAL_EXPIRES_AT": iso8601(expires),
    }
    secure_atomic_write(
        ENV_FILE,
        "# Generated local-only credentials; never commit this file.\n"
        + "\n".join(f"{key}={value}" for key, value in values.items())
        + "\n",
    )
    return values


def active_credentials() -> dict[str, str]:
    """Return credentials known to match the running stack, never rotate them silently."""
    values = parse_env()
    if not credentials_valid(values):
        raise LocalCommercialError(
            "本地短期凭据已过期或无效；请重新执行 "
            "make local-commercial-up 以轮换凭据并重建相关容器。"
        )
    return values


def compose(
    *arguments: str,
    check: bool = True,
    capture_output: bool = False,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    assert_local_docker_context()
    command = [
        "docker", "compose",
        "--project-name", PROJECT_NAME,
        "--env-file", str(ENV_FILE),
        "-f", str(COMPOSE_FILE),
        *arguments,
    ]
    runtime_environment = os.environ.copy()
    values = parse_env()
    missing = [key for key in RUNTIME_ENVIRONMENT_KEYS if not values.get(key)]
    if missing:
        raise LocalCommercialError(
            "本地 Compose 运行配置不完整，缺少：" + ", ".join(missing)
        )
    # Compose gives shell variables precedence over --env-file. Remove any
    # ambient copies so the protected runtime.env is the single credential
    # source, without exposing its values through the Compose process environment.
    for key in RUNTIME_ENVIRONMENT_KEYS:
        runtime_environment.pop(key, None)
    # The core has several independent images, but unrestricted parallel builds
    # are unreliable on ordinary 8 GiB developer machines. Two workers still
    # overlap useful I/O while keeping Maven/Next compilation memory bounded.
    runtime_environment["COMPOSE_PARALLEL_LIMIT"] = "2"
    try:
        return subprocess.run(
            command,
            cwd=ROOT,
            env=runtime_environment,
            text=True,
            check=check,
            capture_output=capture_output,
            timeout=timeout,
        )
    except FileNotFoundError as error:
        raise LocalCommercialError("Docker CLI 未安装或不在 PATH 中。") from error
    except subprocess.CalledProcessError as error:
        raise LocalCommercialError(
            f"Docker Compose 执行失败（退出码 {error.returncode}）。"
        ) from error
    except subprocess.TimeoutExpired as error:
        raise LocalCommercialError("Docker Compose 执行超过允许时间。") from error


def local_tenant_bootstrap_sql() -> str:
    """Return the fixed local deployment seed; no user or service authority is created."""
    return f"""
DO $elmos_local_tenant$
DECLARE
    tenant organizations%ROWTYPE;
BEGIN
    INSERT INTO organizations (
        organization_id,
        display_name,
        status,
        isolation_class,
        data_region,
        encryption_context_id,
        schema_version,
        payload
    ) VALUES (
        '{LOCAL_ORGANIZATION_ID}',
        '{LOCAL_ORGANIZATION_DISPLAY_NAME}',
        'ACTIVE',
        'T1_SHARED_SAAS',
        'local',
        'key-{LOCAL_ORGANIZATION_ID}',
        '1.0',
        '{{}}'::jsonb
    ) ON CONFLICT (organization_id) DO NOTHING;

    SELECT * INTO tenant
      FROM organizations
     WHERE organization_id = '{LOCAL_ORGANIZATION_ID}'
     FOR UPDATE;
    IF NOT FOUND
       OR tenant.display_name IS DISTINCT FROM '{LOCAL_ORGANIZATION_DISPLAY_NAME}'
       OR tenant.status IS DISTINCT FROM 'ACTIVE'
       OR tenant.isolation_class IS DISTINCT FROM 'T1_SHARED_SAAS'
       OR tenant.data_region IS DISTINCT FROM 'local'
       OR tenant.encryption_context_id IS DISTINCT FROM 'key-{LOCAL_ORGANIZATION_ID}'
    THEN
        RAISE EXCEPTION 'ELMOS_LOCAL_TENANT_CONFLICT';
    END IF;
END
$elmos_local_tenant$;
""".strip()


def run_local_tenant_sql(
    sql: str,
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    # Execute as a deployment bootstrap inside the database container. The
    # command contains no credential, psql never prompts, and both output
    # streams stay in memory so database details cannot reach the terminal or
    # smoke evidence.
    return compose(
        "exec",
        "--user", "postgres",
        "-T",
        "postgres",
        "psql",
        "--username", "elmos",
        "--dbname", "elmos",
        "--no-psqlrc",
        "--no-password",
        "--set", "ON_ERROR_STOP=1",
        "--quiet",
        "--command", sql,
        check=check,
        capture_output=True,
        timeout=30,
    )


def bootstrap_local_tenant() -> None:
    """Idempotently establish only the local tenant root required by foreign keys."""
    run_local_tenant_sql(local_tenant_bootstrap_sql())


def command_bootstrap_self_test(_: argparse.Namespace) -> None:
    """Exercise real idempotency and a rolled-back conflict without leaking DB output."""
    bootstrap_local_tenant()
    bootstrap_local_tenant()
    negative = run_local_tenant_sql(
        f"""
BEGIN;
UPDATE organizations
   SET display_name = 'ELMOS Local Commercial Conflict Fixture'
 WHERE organization_id = '{LOCAL_ORGANIZATION_ID}';
{local_tenant_bootstrap_sql()}
COMMIT;
""".strip(),
        check=False,
    )
    if (
        negative.returncode == 0
        or "ELMOS_LOCAL_TENANT_CONFLICT" not in (negative.stderr or "")
    ):
        raise LocalCommercialError("本地租户 bootstrap 负向冲突测试未按预期失效。")
    # ON_ERROR_STOP closes the failed psql session and PostgreSQL rolls the
    # transaction back. Rechecking the canonical contract proves the fixture
    # did not escape the transaction.
    bootstrap_local_tenant()
    print("本地租户 bootstrap 幂等与负向回滚测试：PASS")


def build_java_artifacts() -> None:
    maven = shutil.which("mvn")
    if maven is None:
        raise LocalCommercialError(
            "本地商业核心构建需要 Java 21 与 Maven 3.9；当前 PATH 中没有 mvn。"
        )
    build_environment = os.environ.copy()
    build_environment["MAVEN_OPTS"] = "-Xmx2048m -Djava.awt.headless=true"
    command = [
        maven,
        "-B",
        "-pl", "apps/control-plane,apps/commercial-api,apps/workspace-service",
        "-am",
        "package",
        "-DskipTests",
    ]
    try:
        subprocess.run(
            command,
            cwd=ROOT,
            env=build_environment,
            text=True,
            check=True,
            timeout=900,
        )
    except subprocess.CalledProcessError as error:
        raise LocalCommercialError(
            f"本地 Java 商业核心构建失败（退出码 {error.returncode}）。"
        ) from error
    except subprocess.TimeoutExpired as error:
        raise LocalCommercialError("本地 Java 商业核心构建超过 15 分钟上限。") from error
    for artifact in JAVA_ARTIFACTS:
        try:
            metadata = artifact.lstat()
        except FileNotFoundError as error:
            raise LocalCommercialError(f"本地构建未生成预期产物：{artifact.name}") from error
        if (
            not stat.S_ISREG(metadata.st_mode)
            or artifact.is_symlink()
            or metadata.st_size < 1024
            or metadata.st_size > 512 * 1024 * 1024
        ):
            raise LocalCommercialError(f"本地构建产物不符合安全边界：{artifact.name}")


def prepare_local_pnpm() -> None:
    executable = shutil.which("pnpm")
    if executable is None:
        raise LocalCommercialError(
            f"Web 容器构建需要本机已安装且可校验的 pnpm {PNPM_VERSION}。"
        )
    resolved = Path(executable).resolve()
    package_root: Path | None = None
    for candidate in resolved.parents:
        package_file = candidate / "package.json"
        distribution = candidate / "dist" / "pnpm.cjs"
        if not package_file.is_file() or not distribution.is_file():
            continue
        try:
            package = json.loads(package_file.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if package.get("name") == "pnpm" and package.get("version") == PNPM_VERSION:
            package_root = candidate
            break
    if package_root is None:
        raise LocalCommercialError(
            f"无法定位 pnpm {PNPM_VERSION} 的可移植安装目录。"
        )
    distribution = package_root / "dist" / "pnpm.cjs"
    digest = hashlib.sha256(distribution.read_bytes()).hexdigest()
    if digest != PNPM_DIST_SHA256:
        raise LocalCommercialError("本机 pnpm 内容摘要与固定版本不匹配。")
    total_bytes = 0
    for path in package_root.rglob("*"):
        if path.is_symlink():
            raise LocalCommercialError("本机 pnpm 安装目录包含符号链接，拒绝打包到容器。")
        if path.is_file():
            total_bytes += path.stat().st_size
    if total_bytes < 1024 * 1024 or total_bytes > 64 * 1024 * 1024:
        raise LocalCommercialError("本机 pnpm 安装目录大小超出允许边界。")
    existing_distribution = LOCAL_PNPM_DIR / "dist" / "pnpm.cjs"
    if existing_distribution.is_file():
        existing_digest = hashlib.sha256(existing_distribution.read_bytes()).hexdigest()
        if existing_digest == PNPM_DIST_SHA256:
            return
    if LOCAL_PNPM_DIR.is_symlink():
        LOCAL_PNPM_DIR.unlink()
    elif LOCAL_PNPM_DIR.exists():
        shutil.rmtree(LOCAL_PNPM_DIR)
    shutil.copytree(package_root, LOCAL_PNPM_DIR, symlinks=False)


def direct_open(request: urllib.request.Request, timeout: float = 8.0) -> tuple[int, bytes]:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.status, response.read(1_048_576)
    except urllib.error.HTTPError as error:
        return error.code, error.read(65_536)


def probe_json(
    name: str,
    url: str,
    *,
    token: str | None = None,
    attempts: int = 40,
) -> dict[str, Any]:
    headers = {"Accept": "application/json", "User-Agent": "elmos-local-smoke/1"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    last_error = "NETWORK_UNREACHABLE"
    for attempt in range(attempts):
        request = urllib.request.Request(url, headers=headers, method="GET")
        started = time.monotonic()
        try:
            status, body = direct_open(request)
            if status == 200:
                payload = json.loads(body.decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("response is not a JSON object")
                return {
                    "name": name,
                    "status": "PASS",
                    "http_status": status,
                    "duration_ms": round((time.monotonic() - started) * 1_000, 2),
                    "body": payload,
                }
            # An upstream error body may contain implementation details or
            # sensitive operational context. Keep it out of terminal output
            # and smoke-result.json; the status is sufficient for this gate.
            last_error = f"HTTP_{status}"
        except (UnicodeError, ValueError):
            last_error = "INVALID_JSON_RESPONSE"
        except OSError:
            last_error = "NETWORK_UNREACHABLE"
        if attempt + 1 < attempts:
            time.sleep(2)
    raise LocalCommercialError(f"{name} 冒烟失败：{last_error}")


def probe_text(
    name: str,
    url: str,
    *,
    contains: str,
    attempts: int = 40,
) -> dict[str, Any]:
    last_error = "NETWORK_UNREACHABLE"
    for attempt in range(attempts):
        request = urllib.request.Request(
            url,
            headers={"Accept": "text/html", "User-Agent": "elmos-local-smoke/1"},
            method="GET",
        )
        started = time.monotonic()
        try:
            status, body = direct_open(request)
            text = body.decode("utf-8", errors="replace")
            if status == 200 and contains in text:
                return {
                    "name": name,
                    "status": "PASS",
                    "http_status": status,
                    "duration_ms": round((time.monotonic() - started) * 1_000, 2),
                    "assertion": f"contains:{contains}",
                }
            last_error = f"HTTP_{status}_OR_MARKER_MISSING"
        except OSError:
            last_error = "NETWORK_UNREACHABLE"
        if attempt + 1 < attempts:
            time.sleep(2)
    raise LocalCommercialError(f"{name} 冒烟失败：{last_error}")


def probe_expected_status(
    name: str,
    url: str,
    *,
    expected: int,
    headers: dict[str, str] | None = None,
    assertion: str | None = None,
) -> dict[str, Any]:
    request_headers = {
        "Accept": "application/json",
        "User-Agent": "elmos-local-smoke/1",
        **(headers or {}),
    }
    request = urllib.request.Request(url, headers=request_headers, method="GET")
    started = time.monotonic()
    try:
        status, _ = direct_open(request)
    except OSError as error:
        raise LocalCommercialError(f"{name} 冒烟失败：NETWORK_UNREACHABLE") from error
    if status != expected:
        raise LocalCommercialError(
            f"{name} 冒烟失败：期望 HTTP {expected}，实际 HTTP {status}。"
        )
    return {
        "name": name,
        "status": "PASS",
        "http_status": status,
        "duration_ms": round((time.monotonic() - started) * 1_000, 2),
        "assertion": assertion or f"expected-status:{expected}",
    }


def smoke_evidence(check: dict[str, Any]) -> dict[str, Any]:
    """Return the allowlisted, response-body-free form persisted as evidence."""
    return {
        "name": check["name"],
        "status": check["status"],
        "http_status": check["http_status"],
        "duration_ms": check["duration_ms"],
        "assertion": check.get("assertion", "response-contract-validated"),
    }


def smoke(values: dict[str, str]) -> dict[str, Any]:
    checks = [
        probe_json("control-plane", "http://127.0.0.1:18080/actuator/health/readiness"),
        probe_json("commercial-api", "http://127.0.0.1:18085/actuator/health/readiness"),
        probe_json("workspace-service", "http://127.0.0.1:18082/actuator/health/readiness"),
        probe_json("web-liveness", "http://127.0.0.1:3000/api/health?probe=liveness"),
        probe_json("web-readiness", "http://127.0.0.1:3000/api/health?probe=readiness"),
        probe_text(
            "admin-login-page",
            "http://127.0.0.1:3000/admin",
            contains="管理员登录",
        ),
        probe_expected_status(
            "admin-operations-auth-required",
            "http://127.0.0.1:3000/api/admin/operations?hours=1&limit=5"
            "&businessLine=ALL&result=ALL",
            expected=401,
            assertion="administrator-session-required",
        ),
        probe_expected_status(
            "workspace-service-auth-required",
            "http://127.0.0.1:18082/api/v1/workspaces/smoke-missing",
            expected=401,
            assertion="workspace-credential-required",
        ),
        probe_expected_status(
            "workspace-service-tenant-bound",
            "http://127.0.0.1:18082/api/v1/workspaces/smoke-missing",
            expected=403,
            headers={
                "X-ELMOS-Repository-Key": values["LOCAL_WORKSPACE_API_KEY"],
                "X-ELMOS-Organization-ID": "wrong-local-tenant",
                "X-ELMOS-Actor-ID": LOCAL_ACTOR_ID,
            },
            assertion="workspace-credential-tenant-bound",
        ),
        probe_expected_status(
            "workspace-service-credential-accepted",
            "http://127.0.0.1:18082/api/v1/workspaces/smoke-missing",
            expected=405,
            headers={
                "X-ELMOS-Repository-Key": values["LOCAL_WORKSPACE_API_KEY"],
                "X-ELMOS-Organization-ID": LOCAL_ORGANIZATION_ID,
                "X-ELMOS-Actor-ID": LOCAL_ACTOR_ID,
            },
            assertion="workspace-credential-accepted-without-mutation",
        ),
        probe_expected_status(
            "admin-operations-rejects-bearer",
            "http://127.0.0.1:3000/api/admin/operations?hours=1&limit=5"
            "&businessLine=ALL&result=ALL",
            expected=401,
            headers={"Authorization": f"Bearer {values['LOCAL_REJECTED_ADMIN_TOKEN']}"},
            assertion="administrator-email-session-required",
        ),
        probe_expected_status(
            "admin-jobs-rejects-bearer",
            "http://127.0.0.1:3000/api/admin/jobs?limit=5",
            expected=401,
            headers={"Authorization": f"Bearer {values['LOCAL_REJECTED_ADMIN_TOKEN']}"},
            assertion="administrator-email-session-required",
        ),
        probe_expected_status(
            "admin-runner-fleet-rejects-bearer",
            "http://127.0.0.1:3000/api/admin/runners?limit=5",
            expected=401,
            headers={"Authorization": f"Bearer {values['LOCAL_REJECTED_ADMIN_TOKEN']}"},
            assertion="administrator-email-session-required",
        ),
    ]
    for service_name in (
        "control-plane",
        "commercial-api",
        "workspace-service",
        "web-liveness",
    ):
        service_health = next(
            check["body"] for check in checks if check["name"] == service_name
        )
        if service_health.get("status") != "UP":
            raise LocalCommercialError(f"{service_name} 未报告明确的 UP 状态。")
        next(check for check in checks if check["name"] == service_name)[
            "assertion"
        ] = "health-status:UP"
    readiness_check = next(check for check in checks if check["name"] == "web-readiness")
    readiness = readiness_check["body"]
    dependencies = readiness.get("dependencies") if isinstance(readiness, dict) else None
    if (
        readiness.get("status") != "UP"
        or not isinstance(dependencies, list)
        or {item.get("dependency") for item in dependencies}
        != {"control-plane", "commercial-api", "workspace-service"}
        or any(item.get("status") != "UP" for item in dependencies)
    ):
        raise LocalCommercialError("Web readiness 未证明三个核心依赖全部 UP。")
    readiness_check["assertion"] = "health-and-core-dependencies:UP"
    result = {
        "schema": "elmos.local-commercial-smoke/1",
        "status": "LOCAL_PASS",
        "executed_at": iso8601(utc_now()),
        "project": PROJECT_NAME,
        # Full response bodies are used only for the in-memory assertions
        # above. Persisting operations data, source previews, or future secret
        # fields would make a smoke artifact an unnecessary data-exfiltration
        # surface even though the file is mode 0600.
        "checks": [smoke_evidence(check) for check in checks],
        "commercial_scope": "local-management-core",
        "external_evidence": {
            "oidc_provider": "NOT_RUN",
            "payment_provider": "NOT_RUN",
            "private_runner": "NOT_RUN",
            "production_deployment": "NOT_RUN",
            "customer_acceptance": "NOT_RUN",
            "production_tls": "NOT_RUN",
            "backup_restore": "NOT_RUN",
            "alert_delivery": "NOT_RUN",
            "capacity_load": "NOT_RUN",
            "tax_reconciliation": "NOT_RUN",
        },
    }
    write_result(result)
    return result


def write_result(result: dict[str, Any]) -> None:
    secure_atomic_write(
        RESULT_FILE,
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
    )


def secure_atomic_write(destination: Path, content: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(
        f".{destination.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp"
    )
    descriptor = os.open(
        temporary,
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            descriptor = -1
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(destination)
        os.chmod(destination, 0o600)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def record_attempt(
    status: str,
    mode: str,
    error: LocalCommercialError | None = None,
    *,
    failure_code: str = "LOCAL_COMMERCIAL_ATTEMPT_FAILED",
) -> None:
    result: dict[str, Any] = {
        "schema": "elmos.local-commercial-smoke/1",
        "status": status,
        "executed_at": iso8601(utc_now()),
        "project": PROJECT_NAME,
        "commercial_scope": "local-management-core",
        "attempt": mode,
        "checks": [],
        "external_evidence": {
            "oidc_provider": "NOT_RUN",
            "payment_provider": "NOT_RUN",
            "private_runner": "NOT_RUN",
            "production_deployment": "NOT_RUN",
            "customer_acceptance": "NOT_RUN",
            "production_tls": "NOT_RUN",
            "backup_restore": "NOT_RUN",
            "alert_delivery": "NOT_RUN",
            "capacity_load": "NOT_RUN",
            "tax_reconciliation": "NOT_RUN",
        },
    }
    if error is not None:
        result["failure"] = {
            "code": failure_code,
            "message": str(error)[:512],
        }
    write_result(result)


def command_up(args: argparse.Namespace) -> None:
    try:
        record_attempt("RUNNING", "up")
        values = ensure_credentials(rotate=args.rotate_credentials)
        compose("config", "--quiet")
        build_java_artifacts()
        prepare_local_pnpm()
        compose("up", "-d", "--build", "--wait", "--wait-timeout", "600")
        bootstrap_local_tenant()
        result = smoke(values)
    except LocalCommercialError as error:
        record_attempt("LOCAL_FAIL", "up", error)
        raise
    except KeyboardInterrupt:
        interrupted = LocalCommercialError(
            "本地商业核心启动已由用户中断；本次证据已失效。"
        )
        record_attempt(
            "LOCAL_FAIL",
            "up",
            interrupted,
            failure_code="LOCAL_COMMERCIAL_ATTEMPT_INTERRUPTED",
        )
        raise
    except Exception as error:
        unexpected = LocalCommercialError(
            "本地商业核心启动发生未分类内部错误；"
            "本次证据已失效，请检查本地服务日志。"
        )
        record_attempt(
            "LOCAL_FAIL",
            "up",
            unexpected,
            failure_code="LOCAL_COMMERCIAL_UNEXPECTED_FAILURE",
        )
        raise unexpected from error
    print(f"本地商业管理核心已启动：{result['status']}")
    print("管理员入口：http://127.0.0.1:3000/admin/login（本地栈未配置 OIDC，失败关闭）")
    print(f"服务短期凭据到期时间：{values['LOCAL_CREDENTIAL_EXPIRES_AT']}")
    print(f"本地证据：{RESULT_FILE}")
    print("真实 OIDC、支付商户、私有 Runner、生产部署与客户验收仍为 NOT_RUN。")


def command_smoke(_: argparse.Namespace) -> None:
    try:
        record_attempt("RUNNING", "smoke")
        values = active_credentials()
        result = smoke(values)
    except LocalCommercialError as error:
        record_attempt("LOCAL_FAIL", "smoke", error)
        raise
    except KeyboardInterrupt:
        interrupted = LocalCommercialError(
            "本地商业核心冒烟已由用户中断；本次证据已失效。"
        )
        record_attempt(
            "LOCAL_FAIL",
            "smoke",
            interrupted,
            failure_code="LOCAL_COMMERCIAL_ATTEMPT_INTERRUPTED",
        )
        raise
    except Exception as error:
        unexpected = LocalCommercialError(
            "本地商业核心冒烟发生未分类内部错误；"
            "本次证据已失效，请检查本地服务日志。"
        )
        record_attempt(
            "LOCAL_FAIL",
            "smoke",
            unexpected,
            failure_code="LOCAL_COMMERCIAL_UNEXPECTED_FAILURE",
        )
        raise unexpected from error
    print(f"冒烟结果：{result['status']}（{RESULT_FILE}）")


def command_status(_: argparse.Namespace) -> None:
    values = parse_env()
    if not values:
        print("本地商业管理核心没有已生成的运行配置。")
        return
    print(f"短期凭据到期：{values.get('LOCAL_CREDENTIAL_EXPIRES_AT', 'UNKNOWN')}")
    compose("ps", check=False)
    if RESULT_FILE.is_file():
        try:
            result = json.loads(RESULT_FILE.read_text(encoding="utf-8"))
            print(f"最近冒烟：{result.get('status', 'UNKNOWN')} @ {result.get('executed_at', 'UNKNOWN')}")
        except (OSError, ValueError):
            print("最近冒烟证据无法解析。")


def command_token(_: argparse.Namespace) -> None:
    raise LocalCommercialError(
        "共享管理员令牌入口已移除；管理员必须使用已验证邮箱的 OIDC 专用入口。"
    )


def command_down(_: argparse.Namespace) -> None:
    if not ENV_FILE.is_file():
        print("本地商业管理核心没有已生成的运行配置。")
        return
    compose("down", "--remove-orphans")
    print("服务与容器已停止；数据库卷保留，便于下次继续。")


def command_reset_data(args: argparse.Namespace) -> None:
    if not args.confirm_local_data_loss:
        raise LocalCommercialError(
            "reset-data 会永久删除本项目的本地 PostgreSQL 数据；"
            "确认后必须附加 --confirm-local-data-loss。"
        )
    metadata = docker_volume_metadata()
    if metadata is not None:
        labels = metadata.get("Labels")
        if (
            not isinstance(labels, dict)
            or labels.get("com.docker.compose.project") != PROJECT_NAME
            or labels.get("com.docker.compose.volume") != "local-commercial-postgres"
        ):
            raise LocalCommercialError(
                "同名数据卷缺少本项目的 Compose 身份标签；为避免误删，reset-data 已拒绝执行。"
            )
    reset_environment = os.environ.copy()
    for key in RUNTIME_ENVIRONMENT_KEYS:
        reset_environment.pop(key, None)
    reset_environment.update({
        "LOCAL_DATABASE_PASSWORD": "reset-only-placeholder-not-a-credential",
        "LOCAL_OPERATIONS_API_KEY": "reset-only-placeholder-not-a-credential",
        "LOCAL_REJECTED_ADMIN_TOKEN": "reset-only-placeholder-not-a-credential",
        "LOCAL_WORKSPACE_API_KEY": "reset-only-placeholder-not-a-credential",
        "LOCAL_SESSION_SECRET": "reset-only-placeholder-not-a-credential",
        "LOCAL_CREDENTIAL_EXPIRES_AT": "1970-01-01T00:00:00Z",
    })
    reset_command = [
        "docker", "compose",
        "--project-name", PROJECT_NAME,
        "-f", str(COMPOSE_FILE),
        "down", "--volumes", "--remove-orphans",
    ]
    try:
        subprocess.run(
            reset_command,
            cwd=ROOT,
            env=reset_environment,
            text=True,
            check=True,
        )
    except FileNotFoundError as error:
        raise LocalCommercialError("Docker CLI 未安装或不在 PATH 中。") from error
    except subprocess.CalledProcessError as error:
        raise LocalCommercialError("本地 PostgreSQL 数据卷删除失败。") from error
    if docker_volume_exists():
        raise LocalCommercialError("Docker Compose 返回成功，但本地 PostgreSQL 数据卷仍然存在。")
    for path in (
        ENV_FILE,
        ENV_FILE.with_suffix(".tmp"),
        RESULT_FILE,
        RESULT_FILE.with_suffix(".tmp"),
    ):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    for pattern in (f".{ENV_FILE.name}.*.tmp", f".{RESULT_FILE.name}.*.tmp"):
        for path in STATE_DIR.glob(pattern):
            path.unlink(missing_ok=True)
    print("已删除本项目的本地 PostgreSQL 数据卷、运行凭据和冒烟状态；不可恢复。")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    up = commands.add_parser("up", help="构建、启动、等待并执行真实本地冒烟")
    up.add_argument(
        "--rotate-credentials",
        action="store_true",
        help="启动前轮换本地短期凭据（已有容器会重建）",
    )
    up.set_defaults(handler=command_up)
    smoke_command = commands.add_parser("smoke", help="重新执行核心健康与管理端冒烟")
    smoke_command.set_defaults(handler=command_smoke)
    status = commands.add_parser("status", help="显示容器与最近冒烟状态")
    status.set_defaults(handler=command_status)
    token = commands.add_parser("token", help="报告共享管理员令牌入口已移除")
    token.set_defaults(handler=command_token)
    down = commands.add_parser("down", help="停止容器但保留本地数据库卷")
    down.set_defaults(handler=command_down)
    reset = commands.add_parser("reset-data", help="显式删除本项目的本地 PostgreSQL 数据")
    reset.add_argument(
        "--confirm-local-data-loss",
        action="store_true",
        help="确认永久删除 elmos-local-commercial 的本地数据库卷",
    )
    reset.set_defaults(handler=command_reset_data)
    bootstrap_test = commands.add_parser(
        "bootstrap-self-test",
        help="对当前本地卷执行租户 bootstrap 幂等与回滚负向测试",
    )
    bootstrap_test.set_defaults(handler=command_bootstrap_self_test)
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        with exclusive_operation_lock():
            args.handler(args)
        return 0
    except LocalCommercialError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("ERROR: 本地商业核心操作已由用户中断。", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())

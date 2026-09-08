#!/usr/bin/env python3
"""Validate the production Runner contract without executing customer code."""

from __future__ import annotations

import argparse
import datetime as dt
import grp
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import stat
import sys
from typing import Any, Mapping


HERE = Path(__file__).resolve().parent
REPOSITORY_ROOT = HERE.parents[1]
CONTRACT_PATH = HERE / "production-contract.json"
MAX_CONTRACT_BYTES = 256 * 1024


class ContractError(RuntimeError):
    pass


def _load_contract() -> dict[str, Any]:
    if CONTRACT_PATH.is_symlink() or not CONTRACT_PATH.is_file():
        raise ContractError("RUNNER_CONTRACT_FILE_UNSAFE")
    if CONTRACT_PATH.stat().st_size > MAX_CONTRACT_BYTES:
        raise ContractError("RUNNER_CONTRACT_FILE_TOO_LARGE")
    value = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ContractError("RUNNER_CONTRACT_OBJECT_REQUIRED")
    return value


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _required_lines(path: Path, expected: set[str]) -> None:
    if path.is_symlink() or not path.is_file():
        raise ContractError(f"SYSTEMD_UNIT_UNSAFE:{path.name}")
    observed = {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    missing = sorted(expected - observed)
    if missing:
        raise ContractError(f"SYSTEMD_UNIT_CONTRACT_MISSING:{path.name}:{','.join(missing)}")


def _exact_directive(path: Path, directive: str, expected: str) -> None:
    observed = [
        line.strip().removeprefix(f"{directive}=")
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith(f"{directive}=")
    ]
    if observed != [expected]:
        raise ContractError(f"SYSTEMD_UNIT_DIRECTIVE_INVALID:{path.name}:{directive}")


def validate_static_contract() -> dict[str, Any]:
    contract = _load_contract()
    if contract.get("schema_version") != "elmos.generation-runner-production.v1":
        raise ContractError("RUNNER_CONTRACT_SCHEMA_INVALID")
    identity = contract.get("service_identity")
    if not isinstance(identity, dict) or identity.get("user") != "elmos-runner":
        raise ContractError("RUNNER_SERVICE_IDENTITY_INVALID")
    if identity.get("group") != "elmos-runner" or identity.get("non_root_required") is not True:
        raise ContractError("RUNNER_SERVICE_IDENTITY_INVALID")
    if identity.get("repository_path") != "/opt/elmos" or identity.get("state_path") != "/var/lib/elmos-generation-runner":
        raise ContractError("RUNNER_SERVICE_PATH_CONTRACT_INVALID")
    authentication = contract.get("authentication")
    if (
        not isinstance(authentication, dict)
        or authentication.get("mode") != "ONE_TIME_HS256_SERVICE_CREDENTIAL"
        or authentication.get("static_bearer_forbidden_in_production") is not True
        or authentication.get("maximum_credential_seconds") != 300
        or authentication.get("replay_rejected") is not True
    ):
        raise ContractError("RUNNER_AUTHENTICATION_CONTRACT_INVALID")

    systemd = contract.get("systemd")
    if not isinstance(systemd, dict):
        raise ContractError("RUNNER_SYSTEMD_CONTRACT_INVALID")
    runner_unit = HERE / str(systemd.get("runner_unit", ""))
    reaper_unit = HERE / str(systemd.get("reaper_unit", ""))
    common = {
        "User=elmos-runner",
        "Group=elmos-runner",
        "EnvironmentFile=/etc/elmos/generation-runner.env",
        "NoNewPrivileges=true",
        "CapabilityBoundingSet=",
        "AmbientCapabilities=",
        "PrivateTmp=true",
        "PrivateDevices=true",
        "ProtectSystem=full",
        "ReadOnlyPaths=/opt/elmos",
        "ReadWritePaths=/var/lib/elmos-generation-runner",
        "ProtectHome=true",
        "LockPersonality=true",
        "RestrictSUIDSGID=true",
        "UMask=0077",
    }
    _required_lines(runner_unit, common | {
        "Requires=elmos-generation-runtime-reaper.service",
        "Restart=on-failure",
        "TimeoutStopSec=45",
        "KillMode=mixed",
        "CPUQuota=200%",
        "MemoryMax=2G",
        "TasksMax=768",
    })
    _required_lines(reaper_unit, common | {
        "Restart=always",
        "TimeoutStopSec=45",
        "KillMode=mixed",
        "IPAddressDeny=any",
        "IPAddressAllow=localhost",
        "CPUQuota=25%",
        "MemoryMax=256M",
        "TasksMax=64",
    })
    for path, directive, key in (
        (runner_unit, "ExecStartPre", "runner_exec_start_pre"),
        (runner_unit, "ExecStart", "runner_exec_start"),
        (reaper_unit, "ExecStartPre", "reaper_exec_start_pre"),
        (reaper_unit, "ExecStart", "reaper_exec_start"),
    ):
        expected = systemd.get(key)
        if not isinstance(expected, str) or not expected:
            raise ContractError("RUNNER_SYSTEMD_EXEC_CONTRACT_INVALID")
        _exact_directive(path, directive, expected)

    bindings = contract.get("source_bindings")
    if not isinstance(bindings, list) or len(bindings) != 7:
        raise ContractError("RUNNER_SOURCE_BINDINGS_INVALID")
    for binding in bindings:
        if not isinstance(binding, dict):
            raise ContractError("RUNNER_SOURCE_BINDING_INVALID")
        relative = binding.get("path")
        expected = binding.get("sha256")
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise ContractError("RUNNER_SOURCE_BINDING_INVALID")
        candidate = REPOSITORY_ROOT / relative
        source = candidate.resolve(strict=True)
        if (
            candidate.is_symlink()
            or source != candidate
            or not source.is_relative_to(REPOSITORY_ROOT)
            or not source.is_file()
        ):
            raise ContractError("RUNNER_SOURCE_BINDING_UNSAFE")
        if _digest(source) != expected:
            raise ContractError(f"RUNNER_SOURCE_BINDING_DRIFT:{relative}")

    isolation = contract.get("job_isolation")
    if not isinstance(isolation, dict) or isolation.get("executor") != "ROOTLESS_CONTAINER":
        raise ContractError("RUNNER_ISOLATION_CONTRACT_INVALID")
    rootless_source = (REPOSITORY_ROOT / "scripts/operations/rootless_project_runner.py").read_text(
        encoding="utf-8"
    )
    fragments = isolation.get("required_source_fragments")
    if not isinstance(fragments, list) or not fragments:
        raise ContractError("RUNNER_ISOLATION_FRAGMENTS_INVALID")
    if any(not isinstance(fragment, str) or fragment not in rootless_source for fragment in fragments):
        raise ContractError("RUNNER_ISOLATION_IMPLEMENTATION_DRIFT")

    runtime_executables = contract.get("runtime_executables")
    expected_executables = {
        ("ELMOS_UV_PATH", "ELMOS_UV_SHA256"),
        ("ELMOS_LOCAL_RUNNER_PNPM_PATH", "ELMOS_LOCAL_RUNNER_PNPM_SHA256"),
        ("ELMOS_LOCAL_RUNNER_CONTAINER_ENGINE", "ELMOS_LOCAL_RUNNER_CONTAINER_ENGINE_SHA256"),
    }
    if (
        not isinstance(runtime_executables, list)
        or {
            (item.get("path_environment"), item.get("sha256_environment"))
            for item in runtime_executables
            if isinstance(item, dict)
        }
        != expected_executables
        or len(runtime_executables) != len(expected_executables)
    ):
        raise ContractError("RUNNER_EXECUTABLE_CONTRACT_INVALID")

    evidence = contract.get("evidence")
    if not isinstance(evidence, dict):
        raise ContractError("RUNNER_EVIDENCE_BOUNDARY_INVALID")
    for key in (
        "linux_systemd",
        "rootless_engine",
        "cancel_timeout_restart_drill",
        "multi_tenant_cleanup_drill",
        "independent_verification",
    ):
        if evidence.get(key) != "NOT_RUN":
            raise ContractError(f"RUNNER_EXTERNAL_EVIDENCE_MUST_REMAIN_NOT_RUN:{key}")
    if evidence.get("certification") != "NOT_CERTIFIED":
        raise ContractError("RUNNER_CERTIFICATION_MUST_REMAIN_NOT_CERTIFIED")
    return contract


def _required(environment: Mapping[str, str], name: str) -> str:
    value = environment.get(name, "").strip()
    if not value:
        raise ContractError(f"RUNNER_ENVIRONMENT_REQUIRED:{name}")
    return value


def _canonical_path(raw: str, *, kind: str) -> Path:
    candidate = Path(raw)
    if not candidate.is_absolute() or candidate.is_symlink():
        raise ContractError(f"RUNNER_{kind}_PATH_INVALID")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as error:
        raise ContractError(f"RUNNER_{kind}_PATH_INVALID") from error
    if resolved != candidate:
        raise ContractError(f"RUNNER_{kind}_PATH_INVALID")
    return resolved


def _owner_only(path: Path, uid: int, gid: int, *, kind: str, socket: bool = False) -> None:
    info = path.stat()
    expected_kind = stat.S_ISSOCK(info.st_mode) if socket else stat.S_ISDIR(info.st_mode)
    if not expected_kind or info.st_uid != uid or info.st_gid != gid or info.st_mode & 0o077:
        raise ContractError(f"RUNNER_{kind}_OWNERSHIP_OR_MODE_INVALID")


def _service_can_write(info: os.stat_result, uid: int, gid: int) -> bool:
    return bool(
        (info.st_uid == uid and info.st_mode & stat.S_IWUSR)
        or (info.st_gid == gid and info.st_mode & stat.S_IWGRP)
        or info.st_mode & stat.S_IWOTH
    )


def _not_service_writable(path: Path, uid: int, gid: int, *, kind: str) -> None:
    if _service_can_write(path.stat(), uid, gid):
        raise ContractError(f"RUNNER_{kind}_WRITABLE_BY_SERVICE")


def _repository_tree_read_only(repository_root: Path, uid: int, gid: int) -> None:
    for directory, names, files in os.walk(repository_root, followlinks=False):
        base = Path(directory)
        _not_service_writable(base, uid, gid, kind="REPOSITORY")
        for name in (*names, *files):
            candidate = base / name
            info = candidate.lstat()
            if stat.S_ISLNK(info.st_mode):
                try:
                    resolved = candidate.resolve(strict=True)
                except OSError as error:
                    raise ContractError("RUNNER_REPOSITORY_SYMLINK_INVALID") from error
                if not resolved.is_relative_to(repository_root):
                    raise ContractError("RUNNER_REPOSITORY_SYMLINK_ESCAPES_ROOT")
                _not_service_writable(resolved, uid, gid, kind="REPOSITORY")
                continue
            if _service_can_write(info, uid, gid):
                raise ContractError("RUNNER_REPOSITORY_WRITABLE_BY_SERVICE")


def _executable_immutable_to_service(path: Path, uid: int, gid: int, *, name: str) -> None:
    if path.stat().st_nlink != 1:
        raise ContractError(f"RUNNER_EXECUTABLE_HARDLINK_FORBIDDEN:{name}")
    current = path
    while True:
        if _service_can_write(current.stat(), uid, gid):
            raise ContractError(f"RUNNER_EXECUTABLE_REPLACEABLE_BY_SERVICE:{name}")
        if current.parent == current:
            break
        current = current.parent


def _validate_lease_expiry(raw: str, *, now: dt.datetime | None = None) -> None:
    try:
        expiry = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as error:
        raise ContractError("RUNNER_AUTH_LEASE_INVALID") from error
    if expiry.tzinfo is None or expiry.utcoffset() is None:
        raise ContractError("RUNNER_AUTH_LEASE_TIMEZONE_REQUIRED")
    observed = now or dt.datetime.now(dt.timezone.utc)
    if observed.tzinfo is None or observed.utcoffset() is None:
        raise ContractError("RUNNER_AUTH_LEASE_CLOCK_INVALID")
    remaining = expiry.astimezone(dt.timezone.utc) - observed.astimezone(dt.timezone.utc)
    if remaining < dt.timedelta(minutes=5):
        raise ContractError("RUNNER_AUTH_LEASE_SAFETY_MARGIN_REQUIRED")
    if remaining > dt.timedelta(hours=24):
        raise ContractError("RUNNER_AUTH_LEASE_EXCEEDS_MAXIMUM")


def validate_runtime_environment(environment: Mapping[str, str] = os.environ) -> None:
    contract = validate_static_contract()
    identity = contract["service_identity"]
    expected_user = str(identity["user"])
    expected_group = str(identity["group"])
    expected_uid_raw = _required(environment, str(identity["uid_environment"]))
    if not expected_uid_raw.isdigit() or int(expected_uid_raw) < 1:
        raise ContractError("RUNNER_SERVICE_UID_INVALID")
    expected_uid = int(expected_uid_raw)
    try:
        account = pwd.getpwnam(expected_user)
        group = grp.getgrnam(expected_group)
    except KeyError as error:
        raise ContractError("RUNNER_SERVICE_ACCOUNT_NOT_FOUND") from error
    if (
        os.geteuid() == 0
        or os.geteuid() != expected_uid
        or account.pw_uid != expected_uid
        or account.pw_gid != group.gr_gid
        or os.getegid() != group.gr_gid
    ):
        raise ContractError("RUNNER_SERVICE_IDENTITY_MISMATCH")

    if environment.get("NODE_ENV") != "production":
        raise ContractError("RUNNER_NODE_ENV_MUST_BE_PRODUCTION")
    if environment.get("ELMOS_LOCAL_RUNNER_ENABLED") != "true":
        raise ContractError("RUNNER_MUST_BE_ENABLED")
    if environment.get("ELMOS_LOCAL_RUNNER_EXECUTOR") != "ROOTLESS_CONTAINER":
        raise ContractError("RUNNER_EXECUTOR_MUST_BE_ROOTLESS_CONTAINER")
    if environment.get("ELMOS_LOCAL_RUNNER_BUILD_NETWORK", "none") != "none":
        raise ContractError("RUNNER_BUILD_NETWORK_MUST_DEFAULT_DENY")
    if environment.get("ELMOS_LOCAL_GITHUB_PUBLISH_ENABLED", "false") != "false":
        raise ContractError("RUNNER_GITHUB_PUBLICATION_FORBIDDEN_BY_BASELINE")

    runner_root = _canonical_path(_required(environment, "ELMOS_LOCAL_RUNNER_ROOT"), kind="ROOT")
    repository_root = _canonical_path(_required(environment, "ELMOS_REPOSITORY_ROOT"), kind="REPOSITORY")
    signing_key_file = _canonical_path(
        _required(environment, "ELMOS_LOCAL_RUNNER_AUTH_SIGNING_KEY_FILE"), kind="AUTH_SIGNING_KEY"
    )
    if repository_root != Path(str(contract["service_identity"]["repository_path"])):
        raise ContractError("RUNNER_REPOSITORY_PATH_NOT_SYSTEMD_BOUND")
    if runner_root != Path(str(contract["service_identity"]["state_path"])):
        raise ContractError("RUNNER_STATE_PATH_NOT_SYSTEMD_BOUND")
    if runner_root == repository_root or runner_root.is_relative_to(repository_root) or repository_root.is_relative_to(runner_root):
        raise ContractError("RUNNER_ROOT_REPOSITORY_OVERLAP")
    _owner_only(runner_root, expected_uid, group.gr_gid, kind="ROOT")
    token_info = signing_key_file.stat()
    if (
        not stat.S_ISREG(token_info.st_mode)
        or token_info.st_uid != expected_uid
        or token_info.st_gid != group.gr_gid
        or token_info.st_mode & 0o077
        or token_info.st_size < 32
        or token_info.st_size > 4096
    ):
        raise ContractError("RUNNER_AUTH_SIGNING_KEY_OWNERSHIP_OR_MODE_INVALID")
    key_id = _required(environment, "ELMOS_LOCAL_RUNNER_AUTH_KEY_ID")
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{2,127}", key_id) is None:
        raise ContractError("RUNNER_AUTH_KEY_ID_INVALID")
    _validate_lease_expiry(_required(environment, "ELMOS_LOCAL_RUNNER_AUTH_TOKEN_EXPIRES_AT"))
    if environment.get("ELMOS_LOCAL_RUNNER_AUTH_TOKEN", "").strip() or environment.get(
        "ELMOS_LOCAL_RUNNER_AUTH_TOKEN_FILE", ""
    ).strip():
        raise ContractError("RUNNER_STATIC_BEARER_FORBIDDEN_IN_PRODUCTION")
    if not repository_root.is_dir():
        raise ContractError("RUNNER_REPOSITORY_PATH_INVALID")
    _repository_tree_read_only(repository_root, expected_uid, group.gr_gid)

    for executable_contract in contract["runtime_executables"]:
        name = str(executable_contract["path_environment"])
        digest_name = str(executable_contract["sha256_environment"])
        executable = _canonical_path(_required(environment, name), kind="EXECUTABLE")
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise ContractError(f"RUNNER_EXECUTABLE_INVALID:{name}")
        _executable_immutable_to_service(executable, expected_uid, group.gr_gid, name=name)
        expected_digest = _required(environment, digest_name)
        if re.fullmatch(r"[0-9a-f]{64}", expected_digest) is None:
            raise ContractError(f"RUNNER_EXECUTABLE_DIGEST_INVALID:{name}")
        if _digest(executable) != expected_digest:
            raise ContractError(f"RUNNER_EXECUTABLE_DIGEST_MISMATCH:{name}")

    xdg = environment.get("ELMOS_LOCAL_RUNNER_ENGINE_XDG_RUNTIME_DIR", "").strip()
    if xdg:
        _owner_only(_canonical_path(xdg, kind="XDG_RUNTIME"), expected_uid, group.gr_gid, kind="XDG_RUNTIME")
    socket_path = environment.get("ELMOS_LOCAL_RUNNER_DOCKER_UNIX_SOCKET", "").strip()
    if socket_path:
        _owner_only(
            _canonical_path(socket_path, kind="DOCKER_SOCKET"),
            expected_uid,
            group.gr_gid,
            kind="DOCKER_SOCKET",
            socket=True,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", action="store_true", help="also validate the live service identity and paths")
    args = parser.parse_args()
    try:
        contract = validate_static_contract()
        if args.runtime:
            validate_runtime_environment()
        print(json.dumps({
            "status": "PASSED",
            "schema_version": contract["schema_version"],
            "runtime_validation": "PASSED" if args.runtime else "NOT_RUN",
            "linux_systemd_evidence": "NOT_RUN",
            "rootless_engine_evidence": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        }, sort_keys=True))
        return 0
    except (ContractError, OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({
            "status": "BLOCKED",
            "reason": str(error).split(":", 1)[0],
            "runtime_validation": "NOT_RUN",
            "linux_systemd_evidence": "NOT_RUN",
            "rootless_engine_evidence": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        }, sort_keys=True))
        return 2


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Run retro-game's fixed Linux source baseline as local engineering evidence.

This is deliberately not the protected Batch 30 qualification path.  It uses
an explicit opt-in, a content-addressed linux/amd64 build runner, and a
temporary nested daemon whose outer network is made internal before any
untrusted Maven execution.  The resulting receipt is always
``LOCAL_NON_CERTIFYING`` and can never satisfy Rootless Runner, customer,
independent-verifier, promotion, or certification gates.

Starting the nested daemon requires a separate, explicit authorization because
Docker Desktop implements this path with a privileged outer container.  The
ordinary local opt-in does not grant that authority.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import signal
import shutil
import sys
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Callable


SCRIPT_DIRECTORY = Path(__file__).resolve().parent
if str(SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIRECTORY))

import qualify_spring_public_repository as protected  # noqa: E402
from replay_spring_public_repository_local import (  # noqa: E402
    LOCAL_EVIDENCE_CLASS,
    LOCAL_START_FREE_BYTES,
    apply_cleanup_gate,
    capacity_check,
    docker_runtime_audit,
    run_capacity_bounded_command,
)


ROOT = protected.ROOT
DEFAULT_MANIFEST = protected.DEFAULT_MANIFEST
DEFAULT_RUNNER_DOCKERFILE = (
    ROOT
    / "framework-packs/spring-boot-2-7-18-to-3-5-3/runners"
    / "retro-game-linux-amd64.Dockerfile"
)
LINUX_RUNNER_PLATFORM = "linux/amd64"
LINUX_RUNNER_BASE_REFERENCE = (
    "mirror.gcr.io/library/maven@sha256:"
    "fa7aa19829157d299ff05f631b51697a388dcd2f6955e84249ecc652015f217b"
)
NESTED_DAEMON_PLATFORM = "linux/arm64"
NESTED_DAEMON_REFERENCE = (
    "mirror.gcr.io/library/docker@sha256:"
    "b7282888b57955edf6b213da6bf179039f09b8335526966f704566321945415a"
)
NESTED_DAEMON_SOCKET = "unix:///run/user/1000/docker.sock"
EXPECTED_REPOSITORY_ID = "retro-game"
EXPECTED_COMMIT = "3d08c4b2ca814acfd873fc7874f724089e5b1d85"
EXPECTED_TESTS = 22
PRIVILEGED_AUTHORIZATION_REQUIRED_STATUS = (
    "BLOCKED_PRIVILEGED_RUNNER_AUTHORIZATION_REQUIRED"
)


def _termination_signal_handler(signum: int, _frame: object) -> None:
    """Convert cooperative process termination into the normal cleanup path."""

    raise KeyboardInterrupt(f"received {signal.Signals(signum).name}")


def install_termination_signal_handlers() -> None:
    """Make PTY/session termination persist evidence and run exact cleanup."""

    signal.signal(signal.SIGTERM, _termination_signal_handler)
    signal.signal(signal.SIGHUP, _termination_signal_handler)


def require_opt_in(enabled: bool) -> None:
    protected.require(enabled, "LOCAL_LINUX_BASELINE_EXPLICIT_OPT_IN_REQUIRED")


def _docker() -> str:
    executable = shutil.which("docker")
    protected.require(executable is not None, "LOCAL_DOCKER_CLI_NOT_AVAILABLE")
    assert executable is not None
    return executable


def _run(
    command: list[str],
    *,
    cwd: Path,
    timeout_seconds: int,
    environment: dict[str, str] | None = None,
    capacity_path: Path | None = None,
    operation: str | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    if capacity_path is not None:
        protected.require(operation is not None, "LOCAL_BOUNDED_OPERATION_REQUIRED")
        assert operation is not None
        return run_capacity_bounded_command(
            command,
            cwd=cwd,
            environment=environment,
            timeout_seconds=timeout_seconds,
            capacity_path=capacity_path,
            operation=operation,
            progress_callback=progress_callback,
        )
    return protected.run_command(
        command,
        cwd=cwd,
        timeout_seconds=timeout_seconds,
        environment=environment,
    )


def _stage_progress_callback(
    callback: Callable[[str, dict[str, Any]], None] | None, stage: str
) -> Callable[[dict[str, Any]], None] | None:
    if callback is None:
        return None
    return lambda payload: callback(stage, payload)


def image_audit(reference: str, expected_platform: str, cwd: Path) -> dict[str, Any]:
    execution = _run(
        [_docker(), "image", "inspect", reference], cwd=cwd, timeout_seconds=30
    )
    protected.require(
        execution["exit_code"] == 0 and not execution["timed_out"],
        f"LOCAL_LINUX_IMAGE_INSPECT_FAILED:{reference}",
    )
    payload = json.loads(execution["output"])[0]
    platform_value = f"{payload.get('Os', '')}/{payload.get('Architecture', '')}"
    repo_digests = payload.get("RepoDigests", [])
    matched = reference in repo_digests and platform_value == expected_platform
    protected.require(matched, f"LOCAL_LINUX_IMAGE_IDENTITY_DRIFT:{reference}")
    return {
        "reference": reference,
        "id": payload.get("Id"),
        "repo_digests": repo_digests,
        "platform": platform_value,
        "size": payload.get("Size"),
        "matched": matched,
        "execution": execution,
    }


def derived_image_audit(reference: str, cwd: Path) -> dict[str, Any]:
    execution = _run(
        [_docker(), "image", "inspect", reference], cwd=cwd, timeout_seconds=30
    )
    protected.require(
        execution["exit_code"] == 0 and not execution["timed_out"],
        "LOCAL_LINUX_DERIVED_RUNNER_INSPECT_FAILED",
    )
    payload = json.loads(execution["output"])[0]
    platform_value = f"{payload.get('Os', '')}/{payload.get('Architecture', '')}"
    labels = payload.get("Config", {}).get("Labels") or {}
    image_id = payload.get("Id")
    matched = bool(
        isinstance(image_id, str)
        and re.fullmatch(r"sha256:[0-9a-f]{64}", image_id)
        and platform_value == LINUX_RUNNER_PLATFORM
        and labels.get("io.elmos.evidence-class") == LOCAL_EVIDENCE_CLASS
        and labels.get("io.elmos.repository") == EXPECTED_REPOSITORY_ID
        and labels.get("io.elmos.source-commit") == EXPECTED_COMMIT
    )
    protected.require(matched, "LOCAL_LINUX_DERIVED_RUNNER_IDENTITY_DRIFT")
    return {
        "reference": reference,
        "id": image_id,
        "repo_digests": payload.get("RepoDigests", []),
        "platform": platform_value,
        "size": payload.get("Size"),
        "labels": labels,
        "matched": matched,
        "execution": execution,
    }


def optional_image_audit(reference: str, cwd: Path) -> dict[str, Any]:
    execution = _run(
        [_docker(), "image", "inspect", reference], cwd=cwd, timeout_seconds=30
    )
    if execution["exit_code"] != 0 or execution["timed_out"]:
        return {"available": False, "reference": reference, "execution": execution}
    try:
        payload = json.loads(execution["output"])[0]
    except (IndexError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise protected.QualificationError(
            f"LOCAL_LINUX_IMAGE_INSPECT_INVALID:{reference}"
        ) from exc
    labels = payload.get("Config", {}).get("Labels") or {}
    image_id = payload.get("Id")
    platform_value = f"{payload.get('Os', '')}/{payload.get('Architecture', '')}"
    derived_identity_matched = bool(
        isinstance(image_id, str)
        and re.fullmatch(r"sha256:[0-9a-f]{64}", image_id)
        and platform_value == LINUX_RUNNER_PLATFORM
        and labels.get("io.elmos.evidence-class") == LOCAL_EVIDENCE_CLASS
        and labels.get("io.elmos.repository") == EXPECTED_REPOSITORY_ID
        and labels.get("io.elmos.source-commit") == EXPECTED_COMMIT
    )
    return {
        "available": True,
        "reference": reference,
        "id": image_id,
        "repo_tags": payload.get("RepoTags", []),
        "repo_digests": payload.get("RepoDigests", []),
        "platform": platform_value,
        "labels": labels,
        "derived_identity_matched": derived_identity_matched,
        "execution": execution,
    }


def local_image_ids(cwd: Path) -> dict[str, Any]:
    execution = _run(
        [_docker(), "image", "ls", "--no-trunc", "--quiet"],
        cwd=cwd,
        timeout_seconds=30,
    )
    protected.require(
        execution["exit_code"] == 0 and not execution["timed_out"],
        "LOCAL_LINUX_PREBUILD_IMAGE_SNAPSHOT_FAILED",
    )
    return {
        "ids": sorted(set(execution["output"].splitlines())),
        "execution": execution,
    }


def cleanup_derived_runner(
    *,
    runner_tag: str,
    build_attempted: bool,
    tag_preexisting: bool,
    preexisting_image_ids: set[str],
    expected_image_id: str | None,
    cwd: Path,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "resource": runner_tag,
        "kind": "temporary-runner-tag-and-derived-image",
        "build_attempted": build_attempted,
        "tag_preexisting": tag_preexisting,
        "expected_image_id": expected_image_id,
        "removed": True,
    }
    if not build_attempted:
        record["status"] = "NOT_CREATED_THIS_RUN"
        return record
    if tag_preexisting:
        record.update(
            {
                "status": "FAILED_PREEXISTING_RUNNER_TAG",
                "removed": False,
            }
        )
        return record

    candidate = optional_image_audit(runner_tag, cwd)
    record["identity_before_cleanup"] = candidate
    if not candidate["available"]:
        record["status"] = "ALREADY_ABSENT"
        return record
    candidate_id = candidate.get("id")
    identity_matches = bool(
        candidate["derived_identity_matched"]
        and (
            expected_image_id is None
            or candidate_id == expected_image_id
        )
    )
    record["identity_matched"] = identity_matches
    if not identity_matches:
        record.update(
            {"status": "FAILED_RUNNER_IDENTITY_MISMATCH", "removed": False}
        )
        return record

    created_image_this_run = candidate_id not in preexisting_image_ids
    record["derived_image_created_this_run"] = created_image_this_run
    other_tags = [tag for tag in candidate["repo_tags"] if tag != runner_tag]
    if (
        not created_image_this_run
        and not other_tags
        and not candidate["repo_digests"]
    ):
        record.update(
            {
                "status": (
                    "FAILED_PREEXISTING_IMAGE_HAS_ONLY_TEMPORARY_TAG"
                ),
                "removed": False,
            }
        )
        return record
    tag_remove = _run(
        [_docker(), "image", "rm", runner_tag], cwd=cwd, timeout_seconds=60
    )
    record["tag_remove"] = tag_remove
    if tag_remove["exit_code"] != 0 or tag_remove["timed_out"]:
        record.update({"status": "FAILED_RUNNER_TAG_REMOVE", "removed": False})
        return record

    if not created_image_this_run:
        record["status"] = "RETAINED_PREEXISTING_DERIVED_IMAGE"
        return record

    assert isinstance(candidate_id, str)
    remaining = optional_image_audit(candidate_id, cwd)
    record["derived_image_after_tag_remove"] = remaining
    if not remaining["available"]:
        record["status"] = "REMOVED_RUNNER_TAG_AND_DERIVED_IMAGE"
        return record
    if remaining["repo_tags"] or remaining["repo_digests"]:
        record.update(
            {
                "status": "FAILED_DERIVED_IMAGE_GAINED_SHARED_REFERENCE",
                "removed": False,
            }
        )
        return record
    image_remove = _run(
        [_docker(), "image", "rm", candidate_id], cwd=cwd, timeout_seconds=60
    )
    record["derived_image_remove"] = image_remove
    after_remove = optional_image_audit(candidate_id, cwd)
    record["derived_image_after_cleanup"] = after_remove
    removed = bool(
        image_remove["exit_code"] == 0
        and not image_remove["timed_out"]
        and not after_remove["available"]
    )
    record["removed"] = removed
    record["status"] = (
        "REMOVED_RUNNER_TAG_AND_DERIVED_IMAGE"
        if removed
        else "FAILED_DERIVED_IMAGE_REMOVE"
    )
    return record


def tree_identity(root: Path) -> dict[str, Any]:
    protected.require(root.is_dir(), f"LOCAL_TREE_MISSING:{root}")
    digest = hashlib.sha256()
    files: list[dict[str, Any]] = []
    total = 0
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        file_digest = protected.sha256_file(path)
        size = path.stat().st_size
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(size).encode("ascii"))
        digest.update(b"\0")
        digest.update(file_digest.encode("ascii"))
        digest.update(b"\n")
        total += size
        files.append({"path": relative, "sha256": file_digest, "bytes": size})
    protected.require(bool(files), f"LOCAL_TREE_EMPTY:{root}")
    return {
        "algorithm": "sha256(path\\0bytes\\0file_sha256\\n)",
        "sha256": digest.hexdigest(),
        "files": len(files),
        "bytes": total,
        "entries": files,
    }


def test_source_identity(source: Path) -> dict[str, str]:
    return {
        path.relative_to(source).as_posix(): protected.sha256_file(path)
        for path in sorted((source / "src/test").rglob("*"))
        if path.is_file()
    }


def source_owned_file_identity(source: Path) -> dict[str, str]:
    return {
        path.relative_to(source).as_posix(): protected.sha256_file(path)
        for path in sorted(source.rglob("*"))
        if path.is_file()
    }


def upstream_contract(source: Path) -> dict[str, Any]:
    workflow = source / ".github/workflows/ci.yml"
    dockerfile = source / "Dockerfile"
    workflow_text = workflow.read_text(encoding="utf-8")
    dockerfile_text = dockerfile.read_text(encoding="utf-8")
    return {
        "workflow": {
            "path": ".github/workflows/ci.yml",
            "sha256": protected.sha256_file(workflow),
            "bytes": workflow.stat().st_size,
            "ubuntu_latest_declared": "runs-on: ubuntu-latest" in workflow_text,
            "arm64_declared": bool(re.search(r"arm64|aarch64", workflow_text, re.I)),
            "maven_command": "mvn -B -DskipTests package",
            "tests_executed": False,
            "native_matrix_builds_but_does_not_test": True,
        },
        "dockerfile": {
            "path": "Dockerfile",
            "sha256": protected.sha256_file(dockerfile),
            "bytes": dockerfile.stat().st_size,
            "debian_bullseye_declared": "debian:bullseye-slim" in dockerfile_text,
            "platform_override_declared": bool(
                re.search(r"^FROM\s+--platform=", dockerfile_text, re.MULTILINE)
            ),
        },
        "selected_baseline_platform": LINUX_RUNNER_PLATFORM,
        "selection_basis": (
            "UPSTREAM_UBUNTU_LATEST_AND_DEFAULT_DOCKER_PLATFORM_WITHOUT_ARM64_DECLARATION"
        ),
        "upstream_green_does_not_prove_tests": True,
    }


def fetch_upstream_actions(repository: dict[str, Any], cwd: Path) -> dict[str, Any]:
    url = (
        "https://api.github.com/repos/retro-game/retro-game/actions/runs"
        f"?head_sha={repository['commit_sha']}&per_page=100"
    )
    command = [
        "curl",
        "--proto",
        "=https",
        "--tlsv1.2",
        "--fail",
        "--location",
        "--silent",
        "--show-error",
        "--connect-timeout",
        "5",
        "--max-time",
        "30",
        "-H",
        "Accept: application/vnd.github+json",
        "-H",
        "X-GitHub-Api-Version: 2022-11-28",
        url,
    ]
    execution = _run(command, cwd=cwd, timeout_seconds=40)
    result: dict[str, Any] = {
        "url": url,
        "status": "NOT_AVAILABLE",
        "execution": execution,
        "qualification_effect": "NONE",
    }
    if execution["exit_code"] != 0 or execution["timed_out"]:
        return result
    try:
        payload = json.loads(execution["output"])
    except json.JSONDecodeError:
        result["status"] = "INVALID_RESPONSE"
        return result
    runs = [
        {
            key: item.get(key)
            for key in (
                "id",
                "name",
                "event",
                "status",
                "conclusion",
                "head_sha",
                "run_started_at",
                "updated_at",
                "html_url",
                "head_branch",
            )
        }
        for item in payload.get("workflow_runs", [])
    ]
    result.update({"status": "OBSERVED", "total_count": len(runs), "runs": runs})
    return result


def numerical_failure_diagnostics(source: Path) -> dict[str, Any]:
    reports = sorted((source / "target/surefire-reports").glob("TEST-*.xml"))
    failures: list[dict[str, Any]] = []
    field_pattern = re.compile(
        r"(numRemainingUnits|timesFired|timesWasShot|shieldDamageDealt|"
        r"hullDamageDealt|shieldDamageTaken|hullDamageTaken)="
        r"([-+]?\d+(?:\.\d+)?(?:E[-+]?\d+)?)"
    )
    for report in reports:
        root = ET.parse(report).getroot()
        for case in root.findall("testcase"):
            node = case.find("failure")
            if node is None:
                continue
            message = node.attrib.get("message", "")
            record: dict[str, Any] = {
                "test_case": f"{case.attrib.get('classname')}#{case.attrib.get('name')}",
                "type": node.attrib.get("type"),
                "report": {
                    "path": report.relative_to(source).as_posix(),
                    "sha256": protected.sha256_file(report),
                    "bytes": report.stat().st_size,
                },
                "message_sha256": hashlib.sha256(message.encode("utf-8")).hexdigest(),
                "message_bytes": len(message.encode("utf-8")),
            }
            delimiter = "> but was: <"
            if message.startswith("expected: <") and delimiter in message:
                expected, actual = message.removeprefix("expected: <").rsplit(
                    delimiter, 1
                )
                if actual.endswith(">"):
                    actual = actual[:-1]
                left = field_pattern.findall(expected)
                right = field_pattern.findall(actual)
                values: list[dict[str, Any]] = []
                if len(left) == len(right) and [x[0] for x in left] == [x[0] for x in right]:
                    for index, ((field, left_value), (_, right_value)) in enumerate(
                        zip(left, right)
                    ):
                        left_number = float(left_value)
                        right_number = float(right_value)
                        if left_number == right_number:
                            continue
                        absolute = abs(left_number - right_number)
                        relative = absolute / max(
                            abs(left_number), abs(right_number), 1e-300
                        )
                        values.append(
                            {
                                "index": index,
                                "field": field,
                                "expected": left_value,
                                "actual": right_value,
                                "absolute_delta": absolute,
                                "relative_delta": relative,
                            }
                        )
                if values:
                    integer_fields = {
                        "numRemainingUnits",
                        "timesFired",
                        "timesWasShot",
                    }
                    record["exact_value_differences"] = len(values)
                    record["integer_value_differences"] = sum(
                        item["field"] in integer_fields for item in values
                    )
                    record["first_differences"] = values[:10]
                    record["maximum_absolute_delta"] = max(
                        values, key=lambda item: item["absolute_delta"]
                    )
                    record["maximum_relative_delta"] = max(
                        values, key=lambda item: item["relative_delta"]
                    )
                    record["compared_numeric_fields"] = len(left)
            failures.append(record)
    return {"failures": failures, "failure_count": len(failures)}


def _nested_command(container: str, arguments: list[str]) -> list[str]:
    return [
        _docker(),
        "exec",
        container,
        "docker",
        "--host",
        NESTED_DAEMON_SOCKET,
        *arguments,
    ]


def wait_for_nested_daemon(container: str, cwd: Path) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    for _ in range(60):
        attempt = _run(
            _nested_command(container, ["info", "--format", "{{json .}}"]),
            cwd=cwd,
            timeout_seconds=10,
        )
        attempts.append(attempt)
        if attempt["exit_code"] == 0 and not attempt["timed_out"]:
            payload = json.loads(attempt["output"])
            security_options = payload.get("SecurityOptions", [])
            return {
                "status": "AVAILABLE",
                "attempts": attempts,
                "id": payload.get("ID"),
                "name": payload.get("Name"),
                "server_version": payload.get("ServerVersion"),
                "operating_system": payload.get("OperatingSystem"),
                "architecture": payload.get("Architecture"),
                "security_options": security_options,
                "nested_rootless_observed": any(
                    option == "name=rootless" or "rootless" in option
                    for option in security_options
                ),
                "protected_rootless_attestation": False,
                "qualification_effect": "NONE",
            }
        time.sleep(1)
    raise protected.QualificationError("LOCAL_NESTED_DAEMON_START_TIMEOUT")


def nested_image_audit(
    container: str,
    reference: str,
    expected_platform: str,
    cwd: Path,
) -> dict[str, Any]:
    execution = _run(
        _nested_command(container, ["image", "inspect", reference]),
        cwd=cwd,
        timeout_seconds=30,
    )
    protected.require(
        execution["exit_code"] == 0 and not execution["timed_out"],
        f"LOCAL_NESTED_IMAGE_INSPECT_FAILED:{reference}",
    )
    payload = json.loads(execution["output"])[0]
    platform_value = f"{payload.get('Os', '')}/{payload.get('Architecture', '')}"
    matched = reference in payload.get("RepoDigests", []) and platform_value == expected_platform
    protected.require(matched, f"LOCAL_NESTED_IMAGE_IDENTITY_DRIFT:{reference}")
    return {
        "reference": reference,
        "id": payload.get("Id"),
        "repo_digests": payload.get("RepoDigests", []),
        "platform": platform_value,
        "size": payload.get("Size"),
        "matched": matched,
        "execution": execution,
    }


def inspect_network(name: str, cwd: Path) -> dict[str, Any]:
    execution = _run(
        [_docker(), "network", "inspect", name], cwd=cwd, timeout_seconds=30
    )
    protected.require(
        execution["exit_code"] == 0 and not execution["timed_out"],
        f"LOCAL_NETWORK_INSPECT_FAILED:{name}",
    )
    payload = json.loads(execution["output"])[0]
    return {
        "id": payload.get("Id"),
        "name": payload.get("Name"),
        "driver": payload.get("Driver"),
        "internal": payload.get("Internal"),
        "attachable": payload.get("Attachable"),
        "labels": payload.get("Labels") or {},
        "containers": sorted((payload.get("Containers") or {}).keys()),
        "execution": execution,
    }


def container_networks(name: str, cwd: Path) -> dict[str, Any]:
    execution = _run(
        [_docker(), "container", "inspect", name], cwd=cwd, timeout_seconds=30
    )
    protected.require(
        execution["exit_code"] == 0 and not execution["timed_out"],
        f"LOCAL_CONTAINER_INSPECT_FAILED:{name}",
    )
    payload = json.loads(execution["output"])[0]
    networks = payload.get("NetworkSettings", {}).get("Networks", {})
    return {
        "container": name,
        "network_names": sorted(networks),
        "networks": networks,
        "privileged": payload.get("HostConfig", {}).get("Privileged"),
        "platform": payload.get("Platform"),
        "user": payload.get("Config", {}).get("User"),
        "execution": execution,
    }


def _container_not_found(execution: dict[str, Any], name: str) -> bool:
    """Accept only Docker's exact missing-container result for ``name``."""

    if execution["timed_out"] or execution["exit_code"] == 0:
        return False
    lines = [line.strip() for line in execution["output"].splitlines() if line.strip()]
    if lines and lines[0] == "[]":
        lines = lines[1:]
    return lines == [f"Error response from daemon: No such container: {name}"]


def _volume_not_found(execution: dict[str, Any], name: str) -> bool:
    """Accept only Docker's exact missing-volume result for ``name``."""

    if execution["timed_out"] or execution["exit_code"] == 0:
        return False
    lines = [line.strip() for line in execution["output"].splitlines() if line.strip()]
    if lines and lines[0] == "[]":
        lines = lines[1:]
    return lines == [f"Error response from daemon: get {name}: no such volume"]


def _network_not_found(execution: dict[str, Any], name: str) -> bool:
    """Accept only Docker's exact missing-network result for ``name``."""

    if execution["timed_out"] or execution["exit_code"] == 0:
        return False
    lines = [line.strip() for line in execution["output"].splitlines() if line.strip()]
    if lines and lines[0] == "[]":
        lines = lines[1:]
    return lines == [f"Error response from daemon: network {name} not found"]


def cleanup_nested_daemon(
    *, name: str, run_attempted: bool, cwd: Path
) -> dict[str, Any]:
    """Remove the unique privileged DinD container and every anonymous volume.

    Docker may create a container even when ``docker run`` times out or returns
    an error.  Cleanup therefore keys off the attempted unique name rather than
    a successful start flag.  A present container must carry this harness's
    exact evidence label and privileged runtime shape before it is removed.
    """

    if not run_attempted:
        return {
            "resource": name,
            "kind": "nested-daemon-container-and-anonymous-volumes",
            "removed": True,
            "status": "NOT_CREATED_THIS_RUN",
            "attached_volumes": [],
        }

    before = _run(
        [_docker(), "container", "inspect", name], cwd=cwd, timeout_seconds=30
    )
    attached_volumes: list[str] = []
    if before["exit_code"] == 0 and not before["timed_out"]:
        payload = json.loads(before["output"])[0]
        labels = payload.get("Config", {}).get("Labels") or {}
        protected.require(
            labels.get("io.elmos.evidence-class") == "LOCAL_NON_CERTIFYING"
            and payload.get("HostConfig", {}).get("Privileged") is True,
            "LOCAL_NESTED_DAEMON_CLEANUP_IDENTITY_MISMATCH",
        )
        attached_volumes = sorted(
            {
                str(mount["Name"])
                for mount in payload.get("Mounts", [])
                if mount.get("Type") == "volume" and mount.get("Name")
            }
        )
    else:
        protected.require(
            _container_not_found(before, name),
            "LOCAL_NESTED_DAEMON_PRE_CLEANUP_INSPECT_FAILED",
        )

    removal = _run(
        [_docker(), "container", "rm", "--force", "--volumes", name],
        cwd=cwd,
        timeout_seconds=60,
    )
    removal_ok = bool(
        (removal["exit_code"] == 0 and not removal["timed_out"])
        or _container_not_found(removal, name)
    )
    after = _run(
        [_docker(), "container", "inspect", name], cwd=cwd, timeout_seconds=30
    )
    container_absent = _container_not_found(after, name)

    volume_checks: list[dict[str, Any]] = []
    for volume in attached_volumes:
        inspection = _run(
            [_docker(), "volume", "inspect", volume], cwd=cwd, timeout_seconds=30
        )
        absent = _volume_not_found(inspection, volume)
        volume_checks.append(
            {"name": volume, "absent": absent, "inspection": inspection}
        )

    volumes_absent = all(check["absent"] for check in volume_checks)
    removed = removal_ok and container_absent and volumes_absent
    return {
        "resource": name,
        "kind": "nested-daemon-container-and-anonymous-volumes",
        "removed": removed,
        "status": "REMOVED_WITH_VOLUMES" if removed else "FAILED_ORPHAN_CHECK",
        "attached_volumes": attached_volumes,
        "before": before,
        "removal": removal,
        "after": after,
        "volume_checks": volume_checks,
    }


def cleanup_temporary_network(
    *, name: str, internal: bool, create_attempted: bool, cwd: Path
) -> dict[str, Any]:
    """Remove one unique run network even if create was interrupted.

    Docker can finish ``network create`` after the client has been interrupted.
    Cleanup therefore records intent before invoking Docker, validates any
    present object by its exact generated name, evidence label, driver and
    ``Internal`` policy, then removes it and proves it is absent.
    """

    if not create_attempted:
        return {
            "resource": name,
            "kind": "temporary-network",
            "removed": True,
            "status": "NOT_CREATED_THIS_RUN",
            "expected_internal": internal,
        }

    before = _run(
        [_docker(), "network", "inspect", name], cwd=cwd, timeout_seconds=30
    )
    if before["exit_code"] == 0 and not before["timed_out"]:
        payload = json.loads(before["output"])[0]
        labels = payload.get("Labels") or {}
        protected.require(
            payload.get("Name") == name
            and payload.get("Driver") == "bridge"
            and payload.get("Internal") is internal
            and labels.get("io.elmos.evidence-class")
            == "LOCAL_NON_CERTIFYING",
            "LOCAL_TEMPORARY_NETWORK_CLEANUP_IDENTITY_MISMATCH",
        )
    else:
        protected.require(
            _network_not_found(before, name),
            "LOCAL_TEMPORARY_NETWORK_PRE_CLEANUP_INSPECT_FAILED",
        )

    removal = _run(
        [_docker(), "network", "rm", name], cwd=cwd, timeout_seconds=30
    )
    removal_ok = bool(
        (removal["exit_code"] == 0 and not removal["timed_out"])
        or _network_not_found(removal, name)
    )
    after = _run(
        [_docker(), "network", "inspect", name], cwd=cwd, timeout_seconds=30
    )
    absent = _network_not_found(after, name)
    removed = removal_ok and absent
    return {
        "resource": name,
        "kind": "temporary-network",
        "removed": removed,
        "status": "REMOVED" if removed else "FAILED_ORPHAN_CHECK",
        "expected_internal": internal,
        "before": before,
        "removal": removal,
        "after": after,
    }


def cmake_cache_audit(source: Path) -> dict[str, Any]:
    cache = source / "qualification-linux-native-build/CMakeCache.txt"
    if not cache.is_file():
        return {
            "path": cache.relative_to(source).as_posix(),
            "status": "MISSING",
            "values": {},
            "expected": {},
            "mismatches": {"cache": "MISSING"},
            "matched": False,
        }
    values: dict[str, str] = {}
    for line in cache.read_text(encoding="utf-8").splitlines():
        if line.startswith("//") or line.startswith("#") or "=" not in line:
            continue
        key_and_type, value = line.split("=", 1)
        key = key_and_type.split(":", 1)[0]
        if key in {
            "CMAKE_CXX_COMPILER",
            "CMAKE_MAKE_PROGRAM",
            "JAVA_AWT_INCLUDE_PATH",
            "JAVA_INCLUDE_PATH",
            "JAVA_INCLUDE_PATH2",
            "JAVA_JVM_LIBRARY",
        }:
            values[key] = value
    expected = {
        "JAVA_INCLUDE_PATH": "/opt/java/openjdk/include",
        "JAVA_INCLUDE_PATH2": "/opt/java/openjdk/include/linux",
        "JAVA_JVM_LIBRARY": "/opt/java/openjdk/lib/server/libjvm.so",
    }
    mismatches = {
        key: {"expected": expected_value, "actual": values.get(key)}
        for key, expected_value in expected.items()
        if values.get(key) != expected_value
    }
    compiler = values.get("CMAKE_CXX_COMPILER", "")
    make_program = values.get("CMAKE_MAKE_PROGRAM", "")
    if not re.fullmatch(r"/usr/bin/(?:c\+\+|(?:x86_64-linux-gnu-)?g\+\+(?:-\d+)?)", compiler):
        mismatches["CMAKE_CXX_COMPILER"] = {
            "expected": "fixed runner /usr/bin c++ or g++ executable",
            "actual": compiler,
        }
    if make_program not in {"/usr/bin/make", "/usr/bin/gmake"}:
        mismatches["CMAKE_MAKE_PROGRAM"] = {
            "expected": ["/usr/bin/make", "/usr/bin/gmake"],
            "actual": make_program,
        }
    return {
        "path": cache.relative_to(source).as_posix(),
        "sha256": protected.sha256_file(cache),
        "bytes": cache.stat().st_size,
        "values": values,
        "expected": expected,
        "mismatches": mismatches,
        "matched": not mismatches,
    }


def _runner_common_arguments(
    runner_image: str,
    network: str,
    dind_name: str,
    *,
    name: str,
) -> list[str]:
    return [
        _docker(),
        "run",
        "--rm",
        "--name",
        name,
        "--platform",
        LINUX_RUNNER_PLATFORM,
        "--network",
        network,
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt",
        "no-new-privileges",
        "--pids-limit",
        "2048",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,exec,size=2g",
        "--env",
        f"DOCKER_HOST=tcp://{dind_name}:2375",
        "--env",
        f"TESTCONTAINERS_HOST_OVERRIDE={dind_name}",
        runner_image,
    ]


def parse_toolchain_probe(output: str) -> dict[str, Any]:
    tools: dict[str, dict[str, Any]] = {}
    packages: list[dict[str, str]] = []
    machine = None
    for line in output.splitlines():
        if line.startswith("ELMOS_TOOL\t"):
            fields = line.split("\t")
            protected.require(len(fields) == 7, "LOCAL_LINUX_TOOLCHAIN_PROBE_INVALID")
            _, name, requested, resolved, digest, byte_count, encoded = fields
            protected.require(
                re.fullmatch(r"[0-9a-f]{64}", digest) is not None,
                f"LOCAL_LINUX_TOOLCHAIN_DIGEST_INVALID:{name}",
            )
            try:
                version_output = base64.b64decode(encoded, validate=True).decode(
                    "utf-8", errors="replace"
                )
            except (ValueError, base64.binascii.Error) as exc:
                raise protected.QualificationError(
                    f"LOCAL_LINUX_TOOLCHAIN_VERSION_INVALID:{name}"
                ) from exc
            tools[name] = {
                "requested_path": requested,
                "resolved_path": resolved,
                "sha256": digest,
                "bytes": int(byte_count),
                "version_output": version_output,
                "version_output_sha256": hashlib.sha256(
                    version_output.encode("utf-8")
                ).hexdigest(),
                "version_first_line": version_output.splitlines()[0],
            }
        elif line.startswith("ELMOS_DPKG\t"):
            fields = line.split("\t")
            protected.require(len(fields) == 4, "LOCAL_LINUX_DPKG_PROBE_INVALID")
            _, name, version, architecture = fields
            packages.append(
                {"package": name, "version": version, "architecture": architecture}
            )
        elif line.startswith("ELMOS_UNAME\t"):
            machine = line.split("\t", 1)[1]
    expected_tools = {"java", "javac", "mvn", "cmake", "c++", "make"}
    protected.require(set(tools) == expected_tools, "LOCAL_LINUX_TOOLCHAIN_SET_INCOMPLETE")
    package_names = {item["package"].split(":", 1)[0] for item in packages}
    protected.require(
        {"build-essential", "cmake", "g++", "make"}.issubset(package_names),
        "LOCAL_LINUX_DPKG_SET_INCOMPLETE",
    )
    protected.require(machine == "x86_64", "LOCAL_LINUX_RUNNER_MACHINE_MISMATCH")
    return {
        "tools": tools,
        "dpkg_packages": sorted(packages, key=lambda item: item["package"]),
        "machine": machine,
        "derived_image_id_required": True,
        "actual_bytes_bound_by_derived_image_id": True,
        "rebuild_inputs_fully_version_locked": False,
        "qualification_effect": "LOCAL_ENGINEERING_ONLY",
    }


def runner_toolchain_probe(
    *,
    runner_image: str,
    network: str,
    dind_name: str,
    cwd: Path,
) -> dict[str, Any]:
    protected.require(
        re.fullmatch(r"sha256:[0-9a-f]{64}", runner_image) is not None,
        "LOCAL_LINUX_RUNNER_IMAGE_ID_REQUIRED",
    )
    name = f"elmos-retro-toolchain-{uuid.uuid4().hex[:10]}"
    command = _runner_common_arguments(
        runner_image, network, dind_name, name=name
    )
    command[-1:-1] = ["--env", "HOME=/tmp"]
    shell = r'''set -euo pipefail
emit_tool() {
  tool_name="$1"
  shift
  requested="$(command -v "$tool_name")"
  resolved="$(readlink -f "$requested")"
  digest="$(sha256sum "$resolved" | awk '{print $1}')"
  byte_count="$(wc -c < "$resolved" | tr -d ' ')"
  encoded="$("$@" 2>&1 | base64 -w0)"
  printf 'ELMOS_TOOL\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$tool_name" "$requested" "$resolved" "$digest" "$byte_count" "$encoded"
}
emit_tool java java -version
emit_tool javac javac -version
emit_tool mvn mvn -version
emit_tool cmake cmake --version
emit_tool c++ c++ --version
emit_tool make make --version
dpkg-query -W -f='ELMOS_DPKG\t${binary:Package}\t${Version}\t${Architecture}\n' \
  build-essential cmake g++ make
printf 'ELMOS_UNAME\t%s\n' "$(uname -m)"
'''
    command.extend(["bash", "-lc", shell])
    execution = _run(command, cwd=cwd, timeout_seconds=120)
    protected.require(
        execution["exit_code"] == 0 and not execution["timed_out"],
        "LOCAL_LINUX_TOOLCHAIN_PROBE_FAILED",
    )
    return {
        "status": "OBSERVED_AND_CONTENT_BOUND_LOCAL_NON_CERTIFYING",
        "execution": execution,
        **parse_toolchain_probe(execution["output"]),
    }


def execute_linux_source(
    *,
    source: Path,
    maven_repository: Path,
    runner_image: str,
    network: str,
    dind_name: str,
    ryuk_reference: str,
    repository: dict[str, Any],
    cwd: Path,
    progress_callback: Callable[[str, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    suffix = uuid.uuid4().hex[:10]
    probe_name = f"elmos-retro-probe-{suffix}"
    probe_command = _runner_common_arguments(
        runner_image, network, dind_name, name=probe_name
    )
    probe_command.extend(
        [
            "bash",
            "-lc",
            "set -eu; "
            "getent hosts '" + dind_name + "'; "
            "if timeout 5 bash -c '</dev/null >/dev/tcp/1.1.1.1/443' 2>/dev/null; "
            "then echo UNEXPECTED_EXTERNAL_EGRESS; exit 42; "
            "else echo EXTERNAL_EGRESS_BLOCKED; fi",
        ]
    )
    probe = _run(probe_command, cwd=cwd, timeout_seconds=60)
    protected.require(
        probe["exit_code"] == 0
        and not probe["timed_out"]
        and "EXTERNAL_EGRESS_BLOCKED" in probe["output"]
        and "UNEXPECTED_EXTERNAL_EGRESS" not in probe["output"],
        "LOCAL_LINUX_RUNTIME_NETWORK_ISOLATION_FAILED",
    )
    toolchain = runner_toolchain_probe(
        runner_image=runner_image,
        network=network,
        dind_name=dind_name,
        cwd=cwd,
    )

    run_name = f"elmos-retro-source-{suffix}"
    uid = os.getuid()
    gid = os.getgid()
    home = source / ".elmos-linux-home"
    home.mkdir(mode=0o700)
    command = _runner_common_arguments(
        runner_image, network, dind_name, name=run_name
    )
    command[command.index("--read-only"):command.index("--read-only")] = [
        "--user",
        f"{uid}:{gid}",
    ]
    command[-1:-1] = [
        "--mount",
        f"type=bind,source={source},target=/workspace",
        "--mount",
        f"type=bind,source={maven_repository},target=/m2,readonly",
        "--workdir",
        "/workspace",
        "--env",
        "HOME=/workspace/.elmos-linux-home",
        "--env",
        f"TESTCONTAINERS_RYUK_CONTAINER_IMAGE={ryuk_reference}",
        "--env",
        "TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE=/run/user/1000/docker.sock",
        "--env",
        "TESTCONTAINERS_REUSE_ENABLE=false",
        "--env",
        "DOCKER_API_VERSION=1.40",
        "--env",
        "api.version=1.40",
    ]
    jdbc = repository["source_test_properties"]
    shell = (
        "set -eux; "
        "uname -a; uname -m; java -version; javac -version; mvn -version; "
        "cmake --version; c++ --version; make --version | head -1; "
        "cmake -S battle-engine -B qualification-linux-native-build "
        "-G 'Unix Makefiles' -DCMAKE_BUILD_TYPE=Release "
        "-DCMAKE_CXX_COMPILER=/usr/bin/c++ -DCMAKE_MAKE_PROGRAM=/usr/bin/make "
        "-DJAVA_AWT_INCLUDE_PATH=/opt/java/openjdk/include "
        "-DJAVA_INCLUDE_PATH=/opt/java/openjdk/include "
        "-DJAVA_INCLUDE_PATH2=/opt/java/openjdk/include/linux "
        "-DJAVA_JVM_LIBRARY=/opt/java/openjdk/lib/server/libjvm.so; "
        "cmake --build qualification-linux-native-build --config Release; "
        "mvn --offline --strict-checksums -B -ntp "
        "-Duser.home=/workspace/.elmos-linux-home -Dmaven.repo.local=/m2 "
        "-f qualification-pom.xml "
        "-DargLine='-Djava.library.path=/workspace/qualification-linux-native-build "
        "-Dapi.version=1.40' "
        f"-Dspring.datasource.url='{jdbc['spring.datasource.url']}' "
        f"-Dspring.datasource.driver-class-name='{jdbc['spring.datasource.driver-class-name']}' "
        "verify"
    )
    command.extend(["bash", "-lc", shell])
    execution = _run(
        command,
        cwd=cwd,
        timeout_seconds=repository["timeouts_seconds"]["source_tests"] + 600,
        capacity_path=source,
        operation="linux-amd64-source-native-and-tests",
        progress_callback=_stage_progress_callback(
            progress_callback, "linux-amd64-source-native-and-tests"
        ),
    )
    runner_cleanup = _run(
        [_docker(), "container", "rm", "--force", run_name],
        cwd=cwd,
        timeout_seconds=60,
    )
    cleanup_removed = runner_cleanup["exit_code"] == 0 and not runner_cleanup["timed_out"]
    cleanup_already_removed = bool(
        runner_cleanup["exit_code"] != 0
        and not runner_cleanup["timed_out"]
        and "No such container" in runner_cleanup["output"]
    )
    runner_cleanup["status"] = (
        "REMOVED_AFTER_INTERRUPTED_OR_FAILED_EXECUTION"
        if cleanup_removed
        else (
            "ALREADY_REMOVED_BY_DOCKER_RUN_RM"
            if cleanup_already_removed
            else "FAILED_TO_REMOVE_RUNNER"
        )
    )
    protected.require(
        cleanup_removed or cleanup_already_removed,
        "LOCAL_LINUX_RUNNER_CLEANUP_FAILED",
    )
    try:
        summary = protected.surefire_summary(source)
        summary["status"] = "AVAILABLE"
    except protected.QualificationError as exc:
        summary = {
            "status": "MISSING_OR_INVALID",
            "error": str(exc),
            "reports": [],
            "test_cases": [],
            "tests": 0,
            "failures": 0,
            "errors": 0,
            "skipped": 0,
        }
    native = source / "qualification-linux-native-build/libBattleEngine.so"
    cache = cmake_cache_audit(source)
    passed = bool(
        execution["exit_code"] == 0
        and not execution["timed_out"]
        and summary["tests"] == EXPECTED_TESTS
        and len(summary["test_cases"]) == EXPECTED_TESTS
        and summary["failures"] == 0
        and summary["errors"] == 0
        and summary["skipped"] == 0
        and native.is_file()
        and cache["matched"]
    )
    return {
        "status": (
            "PASSED_LOCAL_NON_CERTIFYING_LINUX_SOURCE_22_TESTS"
            if passed
            else "FAILED_LOCAL_NON_CERTIFYING_LINUX_SOURCE"
        ),
        "evidence_class": LOCAL_EVIDENCE_CLASS,
        "capacity_check": execution["capacity_samples"][0],
        "network_egress_probe": probe,
        "toolchain": toolchain,
        "execution": execution,
        "runner_cleanup": runner_cleanup,
        "surefire": summary,
        "failure_diagnostics": numerical_failure_diagnostics(source),
        "native_artifact": (
            {
                "path": native.relative_to(source).as_posix(),
                "sha256": protected.sha256_file(native),
                "bytes": native.stat().st_size,
            }
            if native.is_file()
            else None
        ),
        "cmake_cache": cache,
        "passed": passed,
    }


def replay(
    *,
    manifest_path: Path,
    repository_id: str,
    archive: Path,
    workspace: Path,
    output: Path,
    maven_repository: Path,
    runner_dockerfile: Path,
    opt_in: bool,
    privileged_nested_daemon_authorized: bool,
) -> dict[str, Any]:
    require_opt_in(opt_in)
    protected.require(repository_id == EXPECTED_REPOSITORY_ID, "LOCAL_LINUX_REPOSITORY_NOT_ALLOWED")
    manifest = protected.load_manifest(manifest_path)
    repository = protected.repository_by_id(manifest, repository_id)
    protected.require(repository["commit_sha"] == EXPECTED_COMMIT, "LOCAL_LINUX_COMMIT_DRIFT")
    protected.require(
        repository["test_inventory"]["total_tests"] == EXPECTED_TESTS,
        "LOCAL_LINUX_TEST_COUNT_DRIFT",
    )
    protected.require(archive.is_file(), "LOCAL_LINUX_ARCHIVE_MISSING")
    protected.require(maven_repository.is_dir(), "LOCAL_LINUX_MAVEN_REPOSITORY_MISSING")
    protected.require(runner_dockerfile.is_file(), "LOCAL_LINUX_RUNNER_DOCKERFILE_MISSING")
    protected.check_workspace(workspace, LOCAL_START_FREE_BYTES)
    checks = [capacity_check(workspace, "local-linux-replay-start")]

    copied_archive = workspace / "source.tar.gz"
    shutil.copy2(archive, copied_archive)
    protected.require(
        protected.sha256_file(copied_archive) == repository["archive"]["sha256"]
        and copied_archive.stat().st_size == repository["archive"]["bytes"],
        "LOCAL_LINUX_ARCHIVE_IDENTITY_DRIFT",
    )
    source = protected.extract_archive(
        copied_archive, workspace, repository["archive"]["root"]
    )
    verified_files = protected.verify_required_files(source, repository)
    pom = protected.pom_audit(source, repository)
    inventory = protected.test_inventory(source, repository)
    source_owned_before = source_owned_file_identity(source)
    overlay = protected.create_vintage_overlay(source, repository)
    original_tests = test_source_identity(source)
    protected.require(
        original_tests == overlay["test_source_hashes_after_overlay"],
        "LOCAL_LINUX_TEST_SOURCE_DRIFT_AFTER_OVERLAY",
    )
    isolated_maven = workspace / "maven-repository"
    checks.append(capacity_check(workspace, "local-linux-copy-maven-repository"))
    shutil.copytree(maven_repository, isolated_maven, copy_function=shutil.copy2)
    maven_identity = tree_identity(isolated_maven)
    dockerfile_text = runner_dockerfile.read_text(encoding="utf-8")
    protected.require(
        f"FROM {LINUX_RUNNER_BASE_REFERENCE}" in dockerfile_text,
        "LOCAL_LINUX_RUNNER_BASE_DRIFT",
    )

    receipt: dict[str, Any] = {
        "schema_version": 1,
        "record_type": "PUBLIC_REPOSITORY_LINUX_BASELINE_LOCAL_NON_CERTIFYING",
        "evidence_class": LOCAL_EVIDENCE_CLASS,
        "certification_eligible": False,
        "certification_status": "NOT_CERTIFIED",
        "rootless": False,
        "rootless_attested": False,
        "customer_repository": False,
        "customer_acceptance": "NOT_RUN",
        "independent_verification": False,
        "independent_external_validation": "NOT_RUN",
        "external_execution_status": "NOT_RUN",
        "migration_success_rate": "NOT_EVALUATED",
        "overall_status": "LOCAL_NON_CERTIFYING_PRECONDITIONS",
        "observed_at": protected.utc_now(),
        "repository": {
            "id": repository_id,
            "url": repository["repository_url"],
            "commit_sha": repository["commit_sha"],
            "tree_sha": repository["tree_sha"],
            "archive_sha256": protected.sha256_file(copied_archive),
            "archive_bytes": copied_archive.stat().st_size,
        },
        "source_tuple": repository["source_tuple"],
        "verified_files": verified_files,
        "pom_audit": pom,
        "test_inventory": inventory,
        "test_discovery_overlay": overlay,
        "source_owned_file_hashes_before_execution": source_owned_before,
        "test_source_hashes_before_execution": original_tests,
        "upstream_contract": upstream_contract(source),
        "upstream_actions": fetch_upstream_actions(repository, workspace),
        "platform": {
            "selected": LINUX_RUNNER_PLATFORM,
            "daemon_service_platform": NESTED_DAEMON_PLATFORM,
            "host_machine": os.uname().machine,
            "emulation_expected": os.uname().machine in {"arm64", "aarch64"},
            "selection_is_source_semantic_not_host_convenience": True,
        },
        "runner": {
            "dockerfile": {
                "path": (
                    runner_dockerfile.relative_to(ROOT).as_posix()
                    if runner_dockerfile.is_relative_to(ROOT)
                    else str(runner_dockerfile)
                ),
                "sha256": protected.sha256_file(runner_dockerfile),
                "bytes": runner_dockerfile.stat().st_size,
            },
            "base_reference": LINUX_RUNNER_BASE_REFERENCE,
            "platform": LINUX_RUNNER_PLATFORM,
        },
        "nested_daemon": {
            "reference": NESTED_DAEMON_REFERENCE,
            "platform": NESTED_DAEMON_PLATFORM,
            "requires_privileged_outer_container": True,
            "explicit_privileged_authorization": (
                privileged_nested_daemon_authorized
            ),
            "protected_runner": False,
            "attested": False,
            "qualification_effect": "NONE",
        },
        "maven_repository": maven_identity,
        "capacity_checks": checks,
        "target_execution": {
            "status": "NOT_RUN_SOURCE_ALL_22_TESTS_GREEN_REQUIRED",
            "source_green_required": True,
        },
    }
    protected.atomic_json(output, receipt)

    if not privileged_nested_daemon_authorized:
        receipt["overall_status"] = PRIVILEGED_AUTHORIZATION_REQUIRED_STATUS
        receipt["docker_operations_executed"] = False
        receipt["cleanup"] = []
        receipt["failure"] = {
            "type": "AuthorizationRequired",
            "message": PRIVILEGED_AUTHORIZATION_REQUIRED_STATUS,
            "observed_at": protected.utc_now(),
        }
        receipt["target_execution"] = {
            "status": "NOT_RUN_SOURCE_ALL_22_TESTS_GREEN_REQUIRED",
            "source_green_required": True,
            "source_green_observed": False,
        }
        receipt["finished_at"] = protected.utc_now()
        receipt["free_bytes_after_run"] = shutil.disk_usage(workspace).free
        protected.atomic_json(output, receipt)
        return receipt

    def persist_stage(stage: str, execution: dict[str, Any]) -> None:
        receipt.setdefault("stage_evidence", {})[stage] = execution
        protected.atomic_json(output, receipt)

    suffix = uuid.uuid4().hex[:10]
    runner_tag = (
        "elmos-local/retro-game-linux-amd64:"
        f"{receipt['runner']['dockerfile']['sha256'][:16]}-{suffix}"
    )
    dind_name = f"elmos-retro-dind-{suffix}"
    staging_network = f"elmos-retro-stage-{suffix}"
    internal_network = f"elmos-retro-internal-{suffix}"
    network_create_attempts: list[tuple[str, bool]] = []
    dind_run_attempted = False
    runner_build_attempted = False
    runner_tag_preexisting = False
    preexisting_image_ids: set[str] = set()
    expected_derived_image_id: str | None = None
    cleanup: list[dict[str, Any]] = []
    try:
        receipt["host_docker_runtime"] = docker_runtime_audit(workspace)
        runner_pull = _run(
            [
                _docker(),
                "pull",
                "--platform",
                LINUX_RUNNER_PLATFORM,
                LINUX_RUNNER_BASE_REFERENCE,
            ],
            cwd=workspace,
            timeout_seconds=1800,
            capacity_path=workspace,
            operation="pull-linux-amd64-runner-base",
            progress_callback=_stage_progress_callback(
                persist_stage, "pull-linux-amd64-runner-base"
            ),
        )
        checks.append(runner_pull["capacity_samples"][0])
        receipt["runner"]["base_pull"] = runner_pull
        protected.atomic_json(output, receipt)
        protected.require(
            runner_pull["exit_code"] == 0 and not runner_pull["timed_out"],
            "LOCAL_LINUX_RUNNER_BASE_PULL_FAILED",
        )
        receipt["runner"]["base_image"] = image_audit(
            LINUX_RUNNER_BASE_REFERENCE, LINUX_RUNNER_PLATFORM, workspace
        )

        dind_pull = _run(
            [
                _docker(),
                "pull",
                "--platform",
                NESTED_DAEMON_PLATFORM,
                NESTED_DAEMON_REFERENCE,
            ],
            cwd=workspace,
            timeout_seconds=1800,
            capacity_path=workspace,
            operation="pull-rootless-dind-arm64",
            progress_callback=_stage_progress_callback(
                persist_stage, "pull-rootless-dind-arm64"
            ),
        )
        checks.append(dind_pull["capacity_samples"][0])
        receipt["nested_daemon"]["pull"] = dind_pull
        protected.atomic_json(output, receipt)
        protected.require(
            dind_pull["exit_code"] == 0 and not dind_pull["timed_out"],
            "LOCAL_NESTED_DAEMON_PULL_FAILED",
        )
        receipt["nested_daemon"]["image"] = image_audit(
            NESTED_DAEMON_REFERENCE, NESTED_DAEMON_PLATFORM, workspace
        )

        prebuild_tag = optional_image_audit(runner_tag, workspace)
        runner_tag_preexisting = bool(prebuild_tag["available"])
        prebuild_ids = local_image_ids(workspace)
        preexisting_image_ids = set(prebuild_ids["ids"])
        receipt["runner"]["prebuild_identity"] = {
            "generated_tag": runner_tag,
            "tag": prebuild_tag,
            "image_ids": prebuild_ids,
        }
        protected.atomic_json(output, receipt)
        protected.require(
            not runner_tag_preexisting,
            "LOCAL_LINUX_GENERATED_RUNNER_TAG_PREEXISTED",
        )
        runner_build_attempted = True
        runner_build = _run(
            [
                _docker(),
                "build",
                "--platform",
                LINUX_RUNNER_PLATFORM,
                "--pull=false",
                "--no-cache",
                "--file",
                str(runner_dockerfile),
                "--tag",
                runner_tag,
                str(runner_dockerfile.parent),
            ],
            cwd=ROOT,
            timeout_seconds=3600,
            capacity_path=workspace,
            operation="build-linux-amd64-runner",
            progress_callback=_stage_progress_callback(
                persist_stage, "build-linux-amd64-runner"
            ),
        )
        checks.append(runner_build["capacity_samples"][0])
        receipt["runner"]["build"] = runner_build
        protected.atomic_json(output, receipt)
        protected.require(
            runner_build["exit_code"] == 0 and not runner_build["timed_out"],
            "LOCAL_LINUX_RUNNER_BUILD_FAILED",
        )
        derived = derived_image_audit(runner_tag, workspace)
        expected_derived_image_id = derived["id"]
        receipt["runner"].update(
            {
                "derived_image": derived,
                "execution_reference": derived["id"],
                "content_addressed_execution": True,
            }
        )
        protected.atomic_json(output, receipt)

        for name, internal in ((staging_network, False), (internal_network, True)):
            command = [
                _docker(),
                "network",
                "create",
                "--driver",
                "bridge",
                "--label",
                "io.elmos.evidence-class=LOCAL_NON_CERTIFYING",
            ]
            if internal:
                command.append("--internal")
            command.append(name)
            network_create_attempts.append((name, internal))
            execution = _run(command, cwd=workspace, timeout_seconds=30)
            protected.require(
                execution["exit_code"] == 0 and not execution["timed_out"],
                f"LOCAL_NETWORK_CREATE_FAILED:{name}",
            )

        checks.append(capacity_check(workspace, "start-rootless-dind-arm64"))
        dind_run_attempted = True
        dind_start = _run(
            [
                _docker(),
                "run",
                "--detach",
                "--name",
                dind_name,
                "--privileged",
                "--platform",
                NESTED_DAEMON_PLATFORM,
                "--network",
                staging_network,
                "--env",
                "DOCKER_TLS_CERTDIR=",
                "--label",
                "io.elmos.evidence-class=LOCAL_NON_CERTIFYING",
                NESTED_DAEMON_REFERENCE,
                "--host=tcp://0.0.0.0:2375",
                "--host=unix:///run/user/1000/docker.sock",
            ],
            cwd=workspace,
            timeout_seconds=60,
        )
        protected.require(
            dind_start["exit_code"] == 0 and not dind_start["timed_out"],
            "LOCAL_NESTED_DAEMON_CONTAINER_START_FAILED",
        )
        receipt["nested_daemon"]["start"] = dind_start
        receipt["nested_daemon"]["runtime"] = wait_for_nested_daemon(
            dind_name, workspace
        )

        nested_services: list[dict[str, Any]] = []
        for service in repository["service_images"]:
            stage = f"nested-pull-{service['role']}"
            pull = _run(
                _nested_command(
                    dind_name,
                    [
                        "pull",
                        "--platform",
                        service["platform"],
                        service["execution_reference"],
                    ],
                ),
                cwd=workspace,
                timeout_seconds=1800,
                capacity_path=workspace,
                operation=stage,
                progress_callback=_stage_progress_callback(
                    persist_stage, stage
                ),
            )
            checks.append(pull["capacity_samples"][0])
            receipt.setdefault("nested_service_pull_evidence", {})[
                service["role"]
            ] = pull
            protected.atomic_json(output, receipt)
            protected.require(
                pull["exit_code"] == 0 and not pull["timed_out"],
                f"LOCAL_NESTED_SERVICE_PULL_FAILED:{service['role']}",
            )
            exact = nested_image_audit(
                dind_name,
                service["execution_reference"],
                service["platform"],
                workspace,
            )
            tag = None
            alias = None
            if service["role"] != "testcontainers-resource-reaper":
                tag = _run(
                    _nested_command(
                        dind_name,
                        [
                            "image",
                            "tag",
                            service["execution_reference"],
                            service["source_reference"],
                        ],
                    ),
                    cwd=workspace,
                    timeout_seconds=30,
                )
                protected.require(
                    tag["exit_code"] == 0 and not tag["timed_out"],
                    f"LOCAL_NESTED_SERVICE_TAG_FAILED:{service['role']}",
                )
                alias_execution = _run(
                    _nested_command(
                        dind_name, ["image", "inspect", service["source_reference"]]
                    ),
                    cwd=workspace,
                    timeout_seconds=30,
                )
                alias_payload = json.loads(alias_execution["output"])[0]
                alias = {
                    "reference": service["source_reference"],
                    "id": alias_payload.get("Id"),
                    "platform": (
                        f"{alias_payload.get('Os', '')}/"
                        f"{alias_payload.get('Architecture', '')}"
                    ),
                    "matches_exact_id": alias_payload.get("Id") == exact["id"],
                    "execution": alias_execution,
                }
                protected.require(
                    alias["matches_exact_id"]
                    and alias["platform"] == service["platform"],
                    f"LOCAL_NESTED_SERVICE_ALIAS_DRIFT:{service['role']}",
                )
            nested_services.append(
                {
                    "role": service["role"],
                    "source_reference": service["source_reference"],
                    "execution_reference": service["execution_reference"],
                    "pull": pull,
                    "exact_image": exact,
                    "temporary_alias_tag": tag,
                    "temporary_alias": alias,
                }
            )
        receipt["nested_service_images"] = nested_services

        connect = _run(
            [_docker(), "network", "connect", internal_network, dind_name],
            cwd=workspace,
            timeout_seconds=30,
        )
        protected.require(
            connect["exit_code"] == 0 and not connect["timed_out"],
            "LOCAL_INTERNAL_NETWORK_CONNECT_FAILED",
        )
        disconnect = _run(
            [_docker(), "network", "disconnect", staging_network, dind_name],
            cwd=workspace,
            timeout_seconds=30,
        )
        protected.require(
            disconnect["exit_code"] == 0 and not disconnect["timed_out"],
            "LOCAL_STAGING_NETWORK_DISCONNECT_FAILED",
        )
        stage_remove = _run(
            [_docker(), "network", "rm", staging_network],
            cwd=workspace,
            timeout_seconds=30,
        )
        internal = inspect_network(internal_network, workspace)
        dind_networks = container_networks(dind_name, workspace)
        isolated = bool(
            internal["internal"]
            and dind_networks["network_names"] == [internal_network]
        )
        protected.require(isolated, "LOCAL_NESTED_DAEMON_NETWORK_NOT_ISOLATED")
        receipt["network_isolation"] = {
            "status": "ENFORCED_FOR_UNTRUSTED_EXECUTION",
            "internal_network": internal,
            "nested_daemon_networks": dind_networks,
            "staging_network_removed_before_untrusted_execution": (
                stage_remove["exit_code"] == 0 and not stage_remove["timed_out"]
            ),
            "external_egress_expected": False,
            "rootless_or_certification_effect": "NONE",
        }

        execution = execute_linux_source(
            source=source,
            maven_repository=isolated_maven,
            runner_image=derived["id"],
            network=internal_network,
            dind_name=dind_name,
            ryuk_reference=next(
                item["execution_reference"]
                for item in repository["service_images"]
                if item["role"] == "testcontainers-resource-reaper"
            ),
            repository=repository,
            cwd=workspace,
            progress_callback=persist_stage,
        )
        checks.append(execution["execution"]["capacity_samples"][0])
        receipt["source_execution"] = execution
        protected.atomic_json(output, receipt)
        source_owned_after = source_owned_file_identity(source)
        source_owned_changes = {
            path: {
                "before": digest,
                "after": source_owned_after.get(path),
            }
            for path, digest in source_owned_before.items()
            if source_owned_after.get(path) != digest
        }
        receipt["source_owned_files_unchanged"] = not source_owned_changes
        receipt["source_owned_file_changes"] = source_owned_changes
        protected.require(
            receipt["source_owned_files_unchanged"],
            "LOCAL_LINUX_SOURCE_OWNED_FILE_CHANGED_DURING_EXECUTION",
        )
        maven_after = tree_identity(isolated_maven)
        receipt["maven_repository_after_execution"] = {
            "algorithm": maven_after["algorithm"],
            "sha256": maven_after["sha256"],
            "files": maven_after["files"],
            "bytes": maven_after["bytes"],
        }
        receipt["maven_repository_unchanged"] = bool(
            maven_after["sha256"] == maven_identity["sha256"]
            and maven_after["files"] == maven_identity["files"]
            and maven_after["bytes"] == maven_identity["bytes"]
        )
        protected.require(
            receipt["maven_repository_unchanged"],
            "LOCAL_LINUX_MAVEN_REPOSITORY_CHANGED_DURING_EXECUTION",
        )
        receipt["test_source_hashes_after_execution"] = test_source_identity(source)
        receipt["test_sources_unchanged"] = (
            receipt["test_source_hashes_after_execution"] == original_tests
        )
        protected.require(
            receipt["test_sources_unchanged"],
            "LOCAL_LINUX_TEST_SOURCE_CHANGED_DURING_EXECUTION",
        )

        nested_events = _run(
            _nested_command(
                dind_name,
                [
                    "events",
                    "--since",
                    execution["execution"]["started_at"],
                    "--until",
                    execution["execution"]["finished_at"],
                    "--filter",
                    "type=container",
                    "--format",
                    "{{json .}}",
                ],
            ),
            cwd=workspace,
            timeout_seconds=60,
        )
        receipt["nested_container_events"] = nested_events
        if execution["passed"]:
            receipt["overall_status"] = execution["status"]
            receipt["target_execution"] = {
                "status": "NOT_RUN_PENDING_SEPARATE_JAVA21_LINUX_TARGET_REPLAY",
                "source_green_required": True,
                "source_green_observed": True,
            }
        else:
            receipt["overall_status"] = execution["status"]
            receipt["target_execution"] = {
                "status": "NOT_RUN_SOURCE_ALL_22_TESTS_GREEN_REQUIRED",
                "source_green_required": True,
                "source_green_observed": False,
            }
        return receipt
    except (Exception, KeyboardInterrupt) as exc:
        receipt["overall_status"] = "FAILED_LOCAL_NON_CERTIFYING"
        interrupted = isinstance(exc, KeyboardInterrupt)
        receipt["failure"] = {
            "type": type(exc).__name__,
            "message": str(exc) or "operation interrupted",
            "interrupted": interrupted,
            "observed_at": protected.utc_now(),
        }
        receipt["target_execution"] = {
            "status": "NOT_RUN_SOURCE_ALL_22_TESTS_GREEN_REQUIRED",
            "source_green_required": True,
            "source_green_observed": False,
        }
        receipt["interrupted"] = interrupted
        receipt["finished_at"] = protected.utc_now()
        protected.atomic_json(output, receipt)
        raise
    finally:
        try:
            cleanup.append(
                cleanup_nested_daemon(
                    name=dind_name,
                    run_attempted=dind_run_attempted,
                    cwd=workspace,
                )
            )
        except Exception as exc:
            cleanup.append(
                {
                    "resource": dind_name,
                    "kind": "nested-daemon-container-and-anonymous-volumes",
                    "removed": False,
                    "cleanup_error": str(exc),
                }
            )
        for network, internal in reversed(network_create_attempts):
            try:
                cleanup.append(
                    cleanup_temporary_network(
                        name=network,
                        internal=internal,
                        create_attempted=True,
                        cwd=workspace,
                    )
                )
            except Exception as exc:
                cleanup.append(
                    {
                        "resource": network,
                        "kind": "temporary-network",
                        "removed": False,
                        "expected_internal": internal,
                        "cleanup_error": str(exc),
                    }
                )
        try:
            cleanup.append(
                cleanup_derived_runner(
                    runner_tag=runner_tag,
                    build_attempted=runner_build_attempted,
                    tag_preexisting=runner_tag_preexisting,
                    preexisting_image_ids=preexisting_image_ids,
                    expected_image_id=expected_derived_image_id,
                    cwd=workspace,
                )
            )
        except Exception as exc:
            cleanup.append(
                {
                    "resource": runner_tag,
                    "kind": "temporary-runner-tag-and-derived-image",
                    "removed": False,
                    "cleanup_error": str(exc),
                }
            )
        receipt["cleanup"] = cleanup
        apply_cleanup_gate(receipt, cleanup)
        receipt["finished_at"] = protected.utc_now()
        receipt["free_bytes_after_run"] = shutil.disk_usage(workspace).free
        receipt["certification_eligible"] = False
        receipt["certification_status"] = "NOT_CERTIFIED"
        receipt["rootless"] = False
        receipt["rootless_attested"] = False
        receipt["customer_acceptance"] = "NOT_RUN"
        receipt["independent_external_validation"] = "NOT_RUN"
        receipt["external_execution_status"] = "NOT_RUN"
        receipt["migration_success_rate"] = "NOT_EVALUATED"
        protected.atomic_json(output, receipt)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--repository-id", default=EXPECTED_REPOSITORY_ID)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--maven-repository", type=Path, required=True)
    parser.add_argument(
        "--runner-dockerfile", type=Path, default=DEFAULT_RUNNER_DOCKERFILE
    )
    parser.add_argument(
        "--local-engineering-non-certifying",
        action="store_true",
        help=(
            "Required opt-in. The receipt remains LOCAL_NON_CERTIFYING and "
            "cannot satisfy protected or external gates."
        ),
    )
    parser.add_argument(
        "--authorize-privileged-nested-daemon",
        action="store_true",
        help=(
            "Declare that the user explicitly authorized this run to start a "
            "privileged Docker Desktop outer container for the nested rootless "
            "daemon. Never infer this from the local-engineering opt-in."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        receipt = replay(
            manifest_path=args.manifest.resolve(),
            repository_id=args.repository_id,
            archive=args.archive.resolve(),
            workspace=args.workspace.resolve(),
            output=args.output.resolve(),
            maven_repository=args.maven_repository.resolve(),
            runner_dockerfile=args.runner_dockerfile.resolve(),
            opt_in=args.local_engineering_non_certifying,
            privileged_nested_daemon_authorized=(
                args.authorize_privileged_nested_daemon
            ),
        )
    except KeyboardInterrupt:
        print("FAIL: interrupted", file=sys.stderr)
        return 130
    except (
        protected.QualificationError,
        OSError,
        ValueError,
        ET.ParseError,
        json.JSONDecodeError,
    ) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"{receipt['overall_status']}: {args.repository_id}")
    return 0 if receipt["overall_status"].startswith("PASSED_") else 2


if __name__ == "__main__":
    install_termination_signal_handlers()
    raise SystemExit(main())

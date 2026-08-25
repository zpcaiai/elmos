#!/usr/bin/env python3
"""Explicit local, non-certifying replay for a fixed Spring public repository.

This module is intentionally separate from the protected qualification path.
It executes untrusted repository build files on the current host only after the
operator supplies ``--local-engineering-non-certifying`` to the main harness.
Its receipt can never satisfy Rootless, independent, customer, or certification
gates.
"""
from __future__ import annotations

import json
import hashlib
import os
import signal
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable


SCRIPT_DIRECTORY = Path(__file__).resolve().parent
if str(SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIRECTORY))

import qualify_spring_public_repository as protected  # noqa: E402


LOCAL_EVIDENCE_CLASS = "LOCAL_NON_CERTIFYING"
LOCAL_START_FREE_BYTES = 12 * 1024**3
LOCAL_HARD_STOP_FREE_BYTES = 8 * 1024**3
CAPACITY_POLL_INTERVAL_SECONDS = 2.0
PROCESS_GROUP_TERMINATION_GRACE_SECONDS = 5.0


def capacity_observation(path: Path, operation: str) -> dict[str, Any]:
    """Observe capacity without raising so an in-flight process can be stopped."""

    free = shutil.disk_usage(path).free
    status = "PASSED"
    if free <= LOCAL_HARD_STOP_FREE_BYTES:
        status = "HARD_STOP"
    elif free < LOCAL_START_FREE_BYTES:
        status = "BELOW_START_THRESHOLD"
    return {
        "operation": operation,
        "observed_at": protected.utc_now(),
        "free_bytes": free,
        "start_minimum_bytes": LOCAL_START_FREE_BYTES,
        "hard_stop_bytes": LOCAL_HARD_STOP_FREE_BYTES,
        "status": status,
    }


def capacity_check(path: Path, operation: str) -> dict[str, Any]:
    record = capacity_observation(path, operation)
    protected.require(
        record["status"] == "PASSED",
        f"LOCAL_CAPACITY_{record['status']}:{operation}:{record['free_bytes']}",
    )
    return record


def _terminate_process_group(
    process: subprocess.Popen[bytes], reason: str
) -> dict[str, Any]:
    """Terminate only the fresh session created for one bounded command."""

    record: dict[str, Any] = {
        "reason": reason,
        "process_group_id": process.pid,
        "sigterm_sent": False,
        "sigkill_sent": False,
    }
    if process.poll() is not None:
        record["already_exited"] = True
        return record
    try:
        os.killpg(process.pid, signal.SIGTERM)
        record["sigterm_sent"] = True
    except ProcessLookupError:
        record["already_exited"] = True
        return record
    leader_timed_out = False
    try:
        process.wait(timeout=PROCESS_GROUP_TERMINATION_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        leader_timed_out = True
    try:
        os.killpg(process.pid, 0)
        group_still_exists = True
    except ProcessLookupError:
        group_still_exists = False
    record["group_exists_after_sigterm_grace"] = group_still_exists
    if leader_timed_out or group_still_exists:
        try:
            os.killpg(process.pid, signal.SIGKILL)
            record["sigkill_sent"] = True
        except ProcessLookupError:
            pass
        if process.poll() is None:
            process.wait(timeout=PROCESS_GROUP_TERMINATION_GRACE_SECONDS)
    record["exit_code_after_termination"] = process.returncode
    return record


def run_capacity_bounded_command(
    command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str] | None,
    timeout_seconds: int,
    capacity_path: Path,
    operation: str,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
    poll_interval_seconds: float = CAPACITY_POLL_INTERVAL_SECONDS,
) -> dict[str, Any]:
    """Run a command in a new process group with continuous capacity enforcement.

    Heavy stages must start with at least 12 GiB free. While the child is alive,
    capacity is sampled at most every two seconds. At or below 8 GiB the entire
    fresh process group is terminated. A callback can atomically persist each
    running sample and the final raw output before callers evaluate success.
    """

    protected.require(
        0 < poll_interval_seconds <= CAPACITY_POLL_INTERVAL_SECONDS,
        "LOCAL_CAPACITY_POLL_INTERVAL_INVALID",
    )
    started_at = protected.utc_now()
    started_monotonic = time.monotonic()
    initial_capacity = capacity_observation(capacity_path, f"{operation}:start")
    capacity_samples = [initial_capacity]
    if initial_capacity["status"] != "PASSED":
        blocked = {
            "command": command,
            "started_at": started_at,
            "finished_at": protected.utc_now(),
            "status": "NOT_STARTED_CAPACITY_GATE",
            "exit_code": None,
            "timed_out": False,
            "capacity_stopped": initial_capacity["status"] == "HARD_STOP",
            "capacity_poll_interval_seconds": poll_interval_seconds,
            "capacity_samples": capacity_samples,
            "process_group_id": None,
            "process_group_isolated": False,
            "termination": None,
            "output": "",
            "output_sha256": hashlib.sha256(b"").hexdigest(),
            "output_bytes": 0,
        }
        if progress_callback is not None:
            progress_callback(blocked)
        protected.require(
            False,
            "LOCAL_CAPACITY_"
            f"{initial_capacity['status']}:{operation}:"
            f"{initial_capacity['free_bytes']}",
        )
    termination: dict[str, Any] | None = None
    timed_out = False
    capacity_stopped = False

    with tempfile.TemporaryFile(mode="w+b") as output_handle:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=environment,
            stdout=output_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

        def publish_running() -> None:
            if progress_callback is None:
                return
            latest = capacity_samples[-1]
            progress_callback(
                {
                    "command": command,
                    "started_at": started_at,
                    "status": "RUNNING",
                    "process_group_id": process.pid,
                    "capacity_poll_interval_seconds": poll_interval_seconds,
                    "capacity_sample_count": len(capacity_samples),
                    "latest_capacity_sample": latest,
                }
            )

        try:
            publish_running()
            while process.poll() is None:
                elapsed = time.monotonic() - started_monotonic
                remaining = timeout_seconds - elapsed
                if remaining <= 0:
                    timed_out = True
                    termination = _terminate_process_group(process, "TIMEOUT")
                    break
                try:
                    process.wait(timeout=min(poll_interval_seconds, remaining))
                except subprocess.TimeoutExpired:
                    sample = capacity_observation(
                        capacity_path, f"{operation}:in-flight"
                    )
                    capacity_samples.append(sample)
                    publish_running()
                    if sample["free_bytes"] <= LOCAL_HARD_STOP_FREE_BYTES:
                        capacity_stopped = True
                        termination = _terminate_process_group(
                            process, "CAPACITY_HARD_STOP"
                        )
                        break
        except BaseException as exc:
            if process.poll() is None:
                termination = _terminate_process_group(
                    process, "CALLER_INTERRUPTED"
                )
            capacity_samples.append(
                capacity_observation(capacity_path, f"{operation}:interrupted")
            )
            output_handle.flush()
            output_handle.seek(0)
            interrupted_output = output_handle.read()
            if progress_callback is not None:
                progress_callback(
                    {
                        "command": command,
                        "started_at": started_at,
                        "finished_at": protected.utc_now(),
                        "status": "INTERRUPTED",
                        "exit_code": process.returncode,
                        "timed_out": False,
                        "capacity_stopped": False,
                        "capacity_poll_interval_seconds": poll_interval_seconds,
                        "capacity_samples": capacity_samples,
                        "process_group_id": process.pid,
                        "process_group_isolated": True,
                        "termination": termination,
                        "interruption": {
                            "type": type(exc).__name__,
                            "message": str(exc) or "operation interrupted",
                        },
                        "output": interrupted_output.decode(
                            "utf-8", errors="replace"
                        ),
                        "output_sha256": hashlib.sha256(
                            interrupted_output
                        ).hexdigest(),
                        "output_bytes": len(interrupted_output),
                    }
                )
            raise

        if process.poll() is None:
            process.wait(timeout=PROCESS_GROUP_TERMINATION_GRACE_SECONDS)
        capacity_samples.append(
            capacity_observation(capacity_path, f"{operation}:finished")
        )
        output_handle.flush()
        output_handle.seek(0)
        output_bytes_value = output_handle.read()

    output_text = output_bytes_value.decode("utf-8", errors="replace")
    execution = {
        "command": command,
        "started_at": started_at,
        "finished_at": protected.utc_now(),
        "exit_code": process.returncode,
        "timed_out": timed_out,
        "capacity_stopped": capacity_stopped,
        "capacity_poll_interval_seconds": poll_interval_seconds,
        "capacity_samples": capacity_samples,
        "process_group_id": process.pid,
        "process_group_isolated": True,
        "termination": termination,
        "output": output_text,
        "output_sha256": hashlib.sha256(output_bytes_value).hexdigest(),
        "output_bytes": len(output_bytes_value),
    }
    if progress_callback is not None:
        progress_callback(execution)
    return execution


def docker_runtime_audit(cwd: Path) -> dict[str, Any]:
    docker = shutil.which("docker")
    protected.require(docker is not None, "LOCAL_DOCKER_CLI_NOT_AVAILABLE")
    assert docker is not None
    context = protected.run_command(
        [docker, "context", "show"], cwd=cwd, timeout_seconds=20
    )
    endpoint = protected.run_command(
        [docker, "context", "inspect", "--format", "{{json .Endpoints.docker.Host}}"],
        cwd=cwd,
        timeout_seconds=20,
    )
    info = protected.run_command(
        [
            docker,
            "info",
            "--format",
            "{{json .SecurityOptions}}|{{.OSType}}|{{.Architecture}}|{{.DockerRootDir}}",
        ],
        cwd=cwd,
        timeout_seconds=30,
    )
    version = protected.run_command(
        [
            docker,
            "version",
            "--format",
            "{{.Server.APIVersion}}|{{.Server.MinAPIVersion}}",
        ],
        cwd=cwd,
        timeout_seconds=30,
    )
    protected.require(
        all(
            item["exit_code"] == 0 and not item["timed_out"]
            for item in (context, endpoint, info, version)
        ),
        "LOCAL_DOCKER_RUNTIME_AUDIT_FAILED",
    )
    security_text, os_type, architecture, root_dir = info["output"].strip().split(
        "|", 3
    )
    security_options = json.loads(security_text)
    api_version, minimum_api_version = version["output"].strip().split("|", 1)
    rootless = any(option == "name=rootless" for option in security_options)
    return {
        "status": LOCAL_EVIDENCE_CLASS,
        "context": context["output"].strip(),
        "endpoint": json.loads(endpoint["output"]),
        "os": os_type,
        "architecture": architecture,
        "docker_root_dir": root_dir,
        "server_api_version": api_version,
        "server_minimum_api_version": minimum_api_version,
        "security_options": security_options,
        "rootless_observed": rootless,
        "rootless_attested": False,
        "protected_runner_receipt_verified": False,
        "independent_verifier": False,
        "qualification_effect": "NONE",
        "commands": {
            "context": context,
            "endpoint": endpoint,
            "info": info,
            "version": version,
        },
    }


def _image_inspect(reference: str, cwd: Path) -> dict[str, Any]:
    docker = shutil.which("docker")
    protected.require(docker is not None, "LOCAL_DOCKER_CLI_NOT_AVAILABLE")
    assert docker is not None
    execution = protected.run_command(
        [docker, "image", "inspect", reference], cwd=cwd, timeout_seconds=30
    )
    if execution["exit_code"] != 0 or execution["timed_out"]:
        return {"available": False, "reference": reference, "execution": execution}
    try:
        payload = json.loads(execution["output"])[0]
    except (IndexError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise protected.QualificationError(
            f"LOCAL_IMAGE_INSPECT_INVALID:{reference}"
        ) from exc
    return {
        "available": True,
        "reference": reference,
        "id": payload.get("Id"),
        "repo_digests": payload.get("RepoDigests", []),
        "platform": f"{payload.get('Os', '')}/{payload.get('Architecture', '')}",
        "size": payload.get("Size"),
        "execution": execution,
    }


def prepare_service_aliases(
    repository: dict[str, Any], cwd: Path
) -> tuple[list[dict[str, Any]], list[str], str]:
    """Bind source-owned mutable names to already-audited exact local images.

    PostgreSQL JDBC and the repository's Redis fixture hard-code tags. The
    aliases are temporary and accepted only when they resolve to the exact
    digest-pinned image identity before and after execution. Ryuk supports a
    direct digest override and therefore receives no mutable alias.
    """

    docker = shutil.which("docker")
    protected.require(docker is not None, "LOCAL_DOCKER_CLI_NOT_AVAILABLE")
    assert docker is not None
    records: list[dict[str, Any]] = []
    created: list[str] = []
    ryuk_reference = ""
    for image in repository["service_images"]:
        exact = _image_inspect(image["execution_reference"], cwd)
        protected.require(
            exact["available"],
            f"LOCAL_EXACT_SERVICE_IMAGE_MISSING:{image['role']}",
        )
        protected.require(
            image["execution_reference"] in exact["repo_digests"]
            and exact["platform"] == image["platform"],
            f"LOCAL_EXACT_SERVICE_IMAGE_DRIFT:{image['role']}",
        )
        record: dict[str, Any] = {
            "role": image["role"],
            "source_reference": image["source_reference"],
            "execution_reference": image["execution_reference"],
            "exact_identity": exact,
            "alias_created": False,
            "binding_status": "EXACT_DIGEST_DIRECT",
        }
        if image["role"] == "testcontainers-resource-reaper":
            ryuk_reference = image["execution_reference"]
            records.append(record)
            continue

        existing = _image_inspect(image["source_reference"], cwd)
        if existing["available"]:
            protected.require(
                existing["id"] == exact["id"]
                and existing["platform"] == exact["platform"],
                f"LOCAL_SOURCE_TAG_OCCUPIED_BY_DIFFERENT_IMAGE:{image['role']}",
            )
            record["binding_status"] = "EXISTING_ALIAS_MATCHED_EXACT_IMAGE"
            record["alias_identity_before"] = existing
        else:
            tag = protected.run_command(
                [
                    docker,
                    "image",
                    "tag",
                    image["execution_reference"],
                    image["source_reference"],
                ],
                cwd=cwd,
                timeout_seconds=30,
            )
            protected.require(
                tag["exit_code"] == 0 and not tag["timed_out"],
                f"LOCAL_SERVICE_ALIAS_CREATE_FAILED:{image['role']}",
            )
            created.append(image["source_reference"])
            record["alias_created"] = True
            record["tag_execution"] = tag
            record["binding_status"] = "TEMPORARY_ALIAS_BOUND_TO_EXACT_IMAGE"
        bound = _image_inspect(image["source_reference"], cwd)
        protected.require(
            bound["available"]
            and bound["id"] == exact["id"]
            and bound["platform"] == exact["platform"],
            f"LOCAL_SERVICE_ALIAS_BINDING_FAILED:{image['role']}",
        )
        record["alias_identity_after"] = bound
        records.append(record)
    protected.require(bool(ryuk_reference), "LOCAL_RYUK_EXACT_REFERENCE_MISSING")
    return records, created, ryuk_reference


def verify_service_aliases(
    repository: dict[str, Any], bindings: list[dict[str, Any]], cwd: Path
) -> list[dict[str, Any]]:
    expected_by_role = {item["role"]: item for item in bindings}
    results: list[dict[str, Any]] = []
    for image in repository["service_images"]:
        exact = _image_inspect(image["execution_reference"], cwd)
        prior = expected_by_role[image["role"]]["exact_identity"]
        matched = bool(
            exact["available"]
            and exact["id"] == prior["id"]
            and exact["platform"] == image["platform"]
            and image["execution_reference"] in exact["repo_digests"]
        )
        alias = None
        if image["role"] != "testcontainers-resource-reaper":
            alias = _image_inspect(image["source_reference"], cwd)
            matched = bool(
                matched
                and alias["available"]
                and alias["id"] == exact["id"]
                and alias["platform"] == exact["platform"]
            )
        results.append(
            {
                "role": image["role"],
                "matched": matched,
                "exact_identity": exact,
                "source_alias_identity": alias,
            }
        )
    protected.require(
        all(item["matched"] for item in results),
        "LOCAL_SERVICE_IMAGE_BINDING_DRIFT",
    )
    return results


def cleanup_service_aliases(created: list[str], cwd: Path) -> list[dict[str, Any]]:
    docker = shutil.which("docker")
    if docker is None:
        return [
            {"reference": reference, "status": "FAILED_DOCKER_CLI_MISSING"}
            for reference in created
        ]
    results = []
    for reference in reversed(created):
        execution = protected.run_command(
            [docker, "image", "rm", reference], cwd=cwd, timeout_seconds=30
        )
        results.append(
            {
                "reference": reference,
                "status": (
                    "REMOVED_TEMPORARY_ALIAS"
                    if execution["exit_code"] == 0 and not execution["timed_out"]
                    else "FAILED_TO_REMOVE_TEMPORARY_ALIAS"
                ),
                "execution": execution,
            }
        )
    return results


def cleanup_record_succeeded(record: dict[str, Any]) -> bool:
    if "removed" in record:
        return bool(record["removed"])
    return record.get("status") in {
        "REMOVED_TEMPORARY_ALIAS",
        "ALREADY_ABSENT",
        "ALREADY_REMOVED_BY_DOCKER_RUN_RM",
        "NOT_CREATED_THIS_RUN",
        "RETAINED_PREEXISTING_DERIVED_IMAGE",
    }


def apply_cleanup_gate(
    receipt: dict[str, Any], cleanup: list[dict[str, Any]]
) -> bool:
    failed = [item for item in cleanup if not cleanup_record_succeeded(item)]
    if failed:
        if receipt.get("overall_status") != "FAILED_CLEANUP":
            receipt["pre_cleanup_overall_status"] = receipt.get("overall_status")
        receipt["overall_status"] = "FAILED_CLEANUP"
        receipt["cleanup_status"] = "FAILED_CLEANUP"
        receipt["cleanup_failures"] = failed
        return False
    receipt["cleanup_status"] = "PASSED" if cleanup else "NOT_REQUIRED"
    receipt["cleanup_failures"] = []
    return True


def _stage_progress_callback(
    callback: Callable[[str, dict[str, Any]], None] | None, stage: str
) -> Callable[[dict[str, Any]], None] | None:
    if callback is None:
        return None
    return lambda payload: callback(stage, payload)


def local_native_build(
    source: Path,
    java_home: Path,
    repository: dict[str, Any],
    *,
    cmake: Path,
    cxx: Path,
    make: Path,
    stage_prefix: str,
    progress_callback: Callable[[str, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    capacity: list[dict[str, Any]] = []
    build = source / "qualification-native-build"
    protected.require(not build.exists(), "LOCAL_NATIVE_BUILD_PATH_ALREADY_EXISTS")
    try:
        jni_toolchain = protected.exact_jni_toolchain(java_home)
    except (OSError, protected.QualificationError) as exc:
        return {
            "status": "FAILED_EXACT_JNI_TOOLCHAIN",
            "evidence_class": LOCAL_EVIDENCE_CLASS,
            "error": str(exc),
            "capacity_checks": capacity,
            "library_directory": str(build),
        }
    environment = os.environ.copy()
    for key in (
        "CMAKE_INCLUDE_PATH",
        "CMAKE_LIBRARY_PATH",
        "CMAKE_PREFIX_PATH",
        "CPATH",
        "CPLUS_INCLUDE_PATH",
        "JAVA_TOOL_OPTIONS",
        "JDK_JAVA_OPTIONS",
        "JDK_HOME",
        "JRE_HOME",
        "_JAVA_OPTIONS",
    ):
        environment.pop(key, None)
    environment["JAVA_HOME"] = str(jni_toolchain["JAVA_HOME"])
    configure = run_capacity_bounded_command(
        protected.cmake_configure_command(
            cmake=cmake,
            cxx=cxx,
            make=make,
            source=source,
            build=build,
            jni_toolchain=jni_toolchain,
        ),
        cwd=source,
        environment=environment,
        timeout_seconds=repository["timeouts_seconds"]["native_configure"],
        capacity_path=source,
        operation=f"{stage_prefix}-native-configure",
        progress_callback=_stage_progress_callback(
            progress_callback, f"{stage_prefix}-native-configure"
        ),
    )
    capacity.extend(configure["capacity_samples"])
    toolchain_audit = None
    compile_record = None
    artifact = None
    if configure["exit_code"] == 0 and not configure["timed_out"]:
        toolchain_audit = protected.audit_cmake_jni_cache(
            build / "CMakeCache.txt",
            jni_toolchain,
            {
                "CMAKE_CXX_COMPILER": cxx.resolve(strict=True),
                "CMAKE_MAKE_PROGRAM": make.resolve(strict=True),
            },
        )
        if toolchain_audit["matched"]:
            compile_record = run_capacity_bounded_command(
                [str(cmake), "--build", str(build), "--config", "Release"],
                cwd=source,
                environment=environment,
                timeout_seconds=repository["timeouts_seconds"]["native_build"],
                capacity_path=source,
                operation=f"{stage_prefix}-native-build",
                progress_callback=_stage_progress_callback(
                    progress_callback, f"{stage_prefix}-native-build"
                ),
            )
            capacity.extend(compile_record["capacity_samples"])
            candidates = [build / name for name in repository["native_artifacts"]]
            match = next((candidate for candidate in candidates if candidate.is_file()), None)
            if match is not None:
                artifact = {
                    "path": str(match.relative_to(source)),
                    "sha256": protected.sha256_file(match),
                    "bytes": match.stat().st_size,
                }
    passed = bool(
        configure["exit_code"] == 0
        and not configure["timed_out"]
        and toolchain_audit
        and toolchain_audit["matched"]
        and compile_record
        and compile_record["exit_code"] == 0
        and not compile_record["timed_out"]
        and artifact
    )
    return {
        "status": "PASSED_LOCAL_NON_CERTIFYING" if passed else "FAILED_LOCAL_NATIVE",
        "evidence_class": LOCAL_EVIDENCE_CLASS,
        "capacity_checks": capacity,
        "configure": configure,
        "toolchain_audit": toolchain_audit,
        "build": compile_record,
        "artifact": artifact,
        "library_directory": str(build),
    }


def local_test_execution(
    source: Path,
    maven: Path,
    java_home: Path,
    native: dict[str, Any],
    repository: dict[str, Any],
    maven_isolation: dict[str, Path],
    ryuk_reference: str,
    docker_runtime: dict[str, Any],
    *,
    timeout_key: str,
    stage: str,
    progress_callback: Callable[[str, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    environment = protected.exact_maven_environment(java_home, maven_isolation)
    for key in (
        "DOCKER_API_VERSION",
        "DOCKER_CERT_PATH",
        "DOCKER_CONFIG",
        "DOCKER_CONTEXT",
        "DOCKER_HOST",
        "DOCKER_TLS_VERIFY",
        "TESTCONTAINERS_CHECKS_DISABLE",
        "TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE",
        "TESTCONTAINERS_HOST_OVERRIDE",
        "TESTCONTAINERS_RYUK_CONTAINER_IMAGE",
        "TESTCONTAINERS_RYUK_DISABLED",
        "api.version",
    ):
        environment.pop(key, None)
    environment["TESTCONTAINERS_RYUK_CONTAINER_IMAGE"] = ryuk_reference
    environment["TESTCONTAINERS_REUSE_ENABLE"] = "false"
    environment["DOCKER_HOST"] = docker_runtime["endpoint"]
    environment["DOCKER_API_VERSION"] = docker_runtime[
        "server_minimum_api_version"
    ]
    # The docker-java version shaded into Testcontainers 1.21.3 reads the
    # literal `api.version` key (not only Docker CLI's DOCKER_API_VERSION).
    environment["api.version"] = docker_runtime["server_minimum_api_version"]
    environment["TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE"] = "/var/run/docker.sock"
    jdbc = repository["source_test_properties"]
    command = [
        str(maven),
        "-B",
        "-ntp",
        *protected.exact_maven_arguments(maven_isolation),
        "-f",
        str(source / "qualification-pom.xml"),
        "-DargLine="
        f"-Djava.library.path={native['library_directory']} "
        f"-Dapi.version={docker_runtime['server_minimum_api_version']}",
        f"-Dspring.datasource.url={jdbc['spring.datasource.url']}",
        f"-Dspring.datasource.driver-class-name={jdbc['spring.datasource.driver-class-name']}",
        "verify",
    ]
    execution = run_capacity_bounded_command(
        command,
        cwd=source,
        environment=environment,
        timeout_seconds=repository["timeouts_seconds"][timeout_key],
        capacity_path=source,
        operation=stage,
        progress_callback=_stage_progress_callback(progress_callback, stage),
    )
    execution["evidence_class"] = LOCAL_EVIDENCE_CLASS
    execution["capacity_check"] = execution["capacity_samples"][0]
    execution["ryuk_execution_reference"] = ryuk_reference
    execution["docker_client_binding"] = {
        "docker_host": docker_runtime["endpoint"],
        "docker_api_version": docker_runtime["server_minimum_api_version"],
        "docker_java_api_version_property": docker_runtime[
            "server_minimum_api_version"
        ],
        "daemon_socket_override": "/var/run/docker.sock",
        "rootless_attested": False,
        "evidence_class": LOCAL_EVIDENCE_CLASS,
    }
    return execution


def docker_service_events(
    cwd: Path,
    started_at: str,
    finished_at: str,
    repository: dict[str, Any],
) -> dict[str, Any]:
    docker = shutil.which("docker")
    if docker is None:
        return {"status": "NOT_AVAILABLE", "reason": "DOCKER_CLI_NOT_AVAILABLE"}
    execution = protected.run_command(
        [
            docker,
            "events",
            "--since",
            started_at,
            "--until",
            finished_at,
            "--filter",
            "type=container",
            "--format",
            "{{json .}}",
        ],
        cwd=cwd,
        timeout_seconds=30,
    )
    expected = {
        item["source_reference"] for item in repository["service_images"]
    } | {item["execution_reference"] for item in repository["service_images"]}
    events = []
    for line in execution["output"].splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        attributes = item.get("Actor", {}).get("Attributes", {})
        if attributes.get("image") in expected or item.get("from") in expected:
            events.append(item)
    return {
        "status": "CAPTURED" if execution["exit_code"] == 0 else "FAILED",
        "expected_image_names": sorted(expected),
        "events": events,
        "execution": execution,
    }


def local_transform_target(
    source: Path,
    target: Path,
    repository: dict[str, Any],
    maven: Path,
    target_java_home: Path,
    maven_isolation: dict[str, Path],
    progress_callback: Callable[[str, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    protected.require(not target.exists(), "LOCAL_TARGET_PATH_ALREADY_EXISTS")
    shutil.copytree(
        source,
        target,
        ignore=shutil.ignore_patterns(
            ".git",
            ".elmos",
            "target",
            "qualification-pom.xml",
            "qualification-native-build",
        ),
    )
    target_profile = repository["target"]
    recipe = protected.ROOT / target_profile["recipe_path"]
    installed_recipe = target / ".elmos/openrewrite.yml"
    installed_recipe.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(recipe, installed_recipe)
    command = [
        str(maven),
        "-B",
        "-ntp",
        *protected.exact_maven_arguments(maven_isolation),
        f"org.openrewrite.maven:rewrite-maven-plugin:{target_profile['rewrite_maven_plugin']}:run",
        "-Drewrite.configLocation=.elmos/openrewrite.yml",
        f"-Drewrite.activeRecipes={target_profile['recipe_id']}",
        "-Drewrite.recipeArtifactCoordinates="
        f"org.openrewrite.recipe:rewrite-spring:{target_profile['rewrite_spring']}",
        "-Drewrite.exportDatatables=true",
    ]
    execution = run_capacity_bounded_command(
        command,
        cwd=target,
        environment=protected.exact_maven_environment(
            target_java_home, maven_isolation
        ),
        timeout_seconds=repository["timeouts_seconds"]["target_transform"],
        capacity_path=target,
        operation="target-openrewrite-transform",
        progress_callback=_stage_progress_callback(
            progress_callback, "target-openrewrite-transform"
        ),
    )
    pom = (
        protected.target_pom_audit(target, repository)
        if (target / "pom.xml").is_file()
        else None
    )
    recipe_validation_error = "Recipe validation error" in execution["output"]
    passed = bool(
        execution["exit_code"] == 0
        and not execution["timed_out"]
        and not recipe_validation_error
        and pom
        and pom["matched"]
    )
    return {
        "status": "PASSED_LOCAL_NON_CERTIFYING" if passed else "FAILED_TRANSFORMATION",
        "evidence_class": LOCAL_EVIDENCE_CLASS,
        "capacity_check": execution["capacity_samples"][0],
        "execution": execution,
        "recipe": {
            "path": target_profile["recipe_path"],
            "id": target_profile["recipe_id"],
            "sha256": protected.sha256_file(recipe),
            "bytes": recipe.stat().st_size,
            "rewrite_maven_plugin": target_profile["rewrite_maven_plugin"],
            "rewrite_spring": target_profile["rewrite_spring"],
        },
        "recipe_validation_error": recipe_validation_error,
        "pom": pom,
    }


def _test_sources(source: Path) -> dict[str, str]:
    return {
        str(path.relative_to(source)): protected.sha256_file(path)
        for path in sorted((source / "src/test").rglob("*"))
        if path.is_file()
    }


def _tests_passed(summary: dict[str, Any], expected: int, execution: dict[str, Any]) -> bool:
    return bool(
        execution["exit_code"] == 0
        and not execution["timed_out"]
        and summary["tests"] == expected
        and len(summary["test_cases"]) == expected
        and summary["failures"] == 0
        and summary["errors"] == 0
        and summary["skipped"] == 0
    )


def replay(
    *,
    manifest_path: Path,
    repository_id: str,
    archive_input: Path | None,
    workspace: Path,
    output: Path,
    java_home: Path,
    maven: Path,
    cmake: Path,
    cxx: Path,
    make: Path,
    target_java_home: Path | None,
) -> dict[str, Any]:
    evidence = protected.qualification(
        manifest_path=manifest_path,
        repository_id=repository_id,
        archive_input=archive_input,
        workspace=workspace,
        output=output,
        java_home=java_home,
        maven=maven,
        cmake=cmake,
        cxx=cxx,
        make=make,
        target_java_home=target_java_home,
    )
    manifest = protected.load_manifest(manifest_path)
    repository = protected.repository_by_id(manifest, repository_id)
    source = workspace / repository["archive"]["root"]
    isolation_root = workspace / ".elmos-maven-isolation"
    isolation = {
        "root": isolation_root.resolve(strict=True),
        "user_home": (isolation_root / "user-home").resolve(strict=True),
        "local_repository": (isolation_root / "repository").resolve(strict=True),
    }
    local: dict[str, Any] = {
        "status": "PRECONDITIONS",
        "evidence_class": LOCAL_EVIDENCE_CLASS,
        "certification_eligible": False,
        "rootless_attestation_accepted": False,
        "customer_evidence": False,
        "independent_verification": False,
        "protected_gate_unchanged": protected.ROOTLESS_EXECUTION_STATUS,
        "operator_opt_in": "--local-engineering-non-certifying",
        "capacity_checks": [capacity_check(workspace, "local-replay-start")],
    }
    evidence["schema_version"] = 2
    evidence["record_type"] = "PUBLIC_REPOSITORY_LOCAL_NON_CERTIFYING_REPLAY"
    evidence["evidence_class"] = LOCAL_EVIDENCE_CLASS
    evidence["local_engineering_execution"] = local
    evidence["overall_status"] = "LOCAL_NON_CERTIFYING_PRECONDITIONS"
    protected.atomic_json(output, evidence)

    def persist_stage(stage: str, execution: dict[str, Any]) -> None:
        local.setdefault("stage_evidence", {})[stage] = execution
        protected.atomic_json(output, evidence)

    local["docker_runtime"] = docker_runtime_audit(source)
    protected.require(
        all(item["matched"] for item in evidence["toolchains"].values()),
        "LOCAL_EXACT_SOURCE_TOOLCHAIN_MISMATCH",
    )
    protected.require(target_java_home is not None, "LOCAL_TARGET_JAVA_HOME_REQUIRED")
    protected.require(
        all(
            item["status"] == "AVAILABLE_RESOLVED_DIGEST_LOCAL"
            for item in evidence["service_prerequisites"]
        ),
        "LOCAL_PINNED_SERVICE_IMAGES_NOT_AVAILABLE",
    )
    expected_tests = repository["test_inventory"]["total_tests"]
    original_test_hashes = evidence["test_discovery_overlay"][
        "test_source_hashes_after_overlay"
    ]
    protected.require(
        _test_sources(source) == original_test_hashes,
        "LOCAL_TEST_SOURCE_DRIFT_BEFORE_EXECUTION",
    )

    bindings: list[dict[str, Any]] = []
    created_aliases: list[str] = []
    try:
        bindings, created_aliases, ryuk_reference = prepare_service_aliases(
            repository, source
        )
        local["service_bindings_before"] = bindings

        native = local_native_build(
            source,
            java_home,
            repository,
            cmake=cmake,
            cxx=cxx,
            make=make,
            stage_prefix="source",
            progress_callback=persist_stage,
        )
        local["source_native"] = native
        if native["status"] != "PASSED_LOCAL_NON_CERTIFYING":
            local["status"] = "FAILED_LOCAL_SOURCE_NATIVE"
            evidence["overall_status"] = local["status"]
            return evidence

        source_execution = local_test_execution(
            source,
            maven,
            java_home,
            native,
            repository,
            isolation,
            ryuk_reference,
            local["docker_runtime"],
            timeout_key="source_tests",
            stage="source-maven-tests",
            progress_callback=persist_stage,
        )
        source_summary = protected.surefire_summary(source)
        source_execution["surefire"] = source_summary
        source_execution["service_events"] = docker_service_events(
            source,
            source_execution["started_at"],
            source_execution["finished_at"],
            repository,
        )
        source_passed = _tests_passed(
            source_summary, expected_tests, source_execution
        )
        source_execution["status"] = (
            "PASSED_LOCAL_NON_CERTIFYING"
            if source_passed
            else "FAILED_LOCAL_SOURCE_TESTS"
        )
        source_execution["test_source_hashes_unchanged"] = (
            _test_sources(source) == original_test_hashes
        )
        source_passed = bool(
            source_passed and source_execution["test_source_hashes_unchanged"]
        )
        local["source_tests"] = source_execution
        local["service_bindings_after_source"] = verify_service_aliases(
            repository, bindings, source
        )
        if not source_passed:
            local["status"] = "FAILED_LOCAL_SOURCE_TESTS"
            local["target_execution"] = {
                "status": "NOT_RUN_SOURCE_ALL_22_TESTS_GREEN_REQUIRED",
                "source_green_required": True,
            }
            evidence["overall_status"] = local["status"]
            return evidence

        identities = repository["toolchain_contract"]["executables"]
        target_java = protected.exact_executable_audit(
            name="target_java",
            executable=target_java_home / "bin/java",
            identity=identities["target_java"],
            cwd=source,
            required_root=target_java_home,
        )
        target_javac = protected.exact_executable_audit(
            name="target_javac",
            executable=target_java_home / "bin/javac",
            identity=identities["target_javac"],
            cwd=source,
            required_root=target_java_home,
        )
        target_environment = protected.exact_maven_environment(
            target_java_home, isolation
        )
        target_maven = protected.exact_executable_audit(
            name="maven",
            executable=maven,
            identity=identities["maven"],
            cwd=source,
            environment=target_environment,
            command_prefix=protected.exact_maven_arguments(isolation),
        )
        target_maven["java_home_matched"] = (
            f"runtime: {target_java_home.resolve(strict=True)}"
            in target_maven.get("execution", {}).get("output", "")
        )
        target_maven["matched"] = bool(
            target_maven["matched"] and target_maven["java_home_matched"]
        )
        target_toolchain = {
            "java": target_java,
            "javac": target_javac,
            "maven": target_maven,
        }
        local["target_toolchain"] = target_toolchain
        protected.require(
            all(item["matched"] for item in target_toolchain.values()),
            "LOCAL_EXACT_TARGET_TOOLCHAIN_MISMATCH",
        )

        target = workspace / "migrated"
        transformation = local_transform_target(
            source,
            target,
            repository,
            maven,
            target_java_home,
            isolation,
            progress_callback=persist_stage,
        )
        local["transformation"] = transformation
        if transformation["status"] != "PASSED_LOCAL_NON_CERTIFYING":
            local["status"] = "FAILED_LOCAL_TRANSFORMATION"
            evidence["overall_status"] = local["status"]
            return evidence
        target_overlay = protected.create_vintage_overlay(
            target, repository, target_profile=True
        )
        local["target_test_discovery_overlay"] = target_overlay
        target_test_hashes = target_overlay["test_source_hashes_after_overlay"]
        target_native = local_native_build(
            target,
            target_java_home,
            repository,
            cmake=cmake,
            cxx=cxx,
            make=make,
            stage_prefix="target",
            progress_callback=persist_stage,
        )
        local["target_native"] = target_native
        if target_native["status"] != "PASSED_LOCAL_NON_CERTIFYING":
            local["status"] = "FAILED_LOCAL_TARGET_NATIVE"
            evidence["overall_status"] = local["status"]
            return evidence
        target_execution = local_test_execution(
            target,
            maven,
            target_java_home,
            target_native,
            repository,
            isolation,
            ryuk_reference,
            local["docker_runtime"],
            timeout_key="target_tests",
            stage="target-maven-tests",
            progress_callback=persist_stage,
        )
        target_summary = protected.surefire_summary(target)
        target_execution["surefire"] = target_summary
        target_execution["service_events"] = docker_service_events(
            target,
            target_execution["started_at"],
            target_execution["finished_at"],
            repository,
        )
        same_oracle = target_summary["test_cases"] == source_summary["test_cases"]
        target_passed = bool(
            _tests_passed(target_summary, expected_tests, target_execution)
            and same_oracle
            and _test_sources(target) == target_test_hashes
        )
        target_execution["same_complete_test_oracle"] = same_oracle
        target_execution["test_source_hashes_unchanged_after_execution"] = (
            _test_sources(target) == target_test_hashes
        )
        target_execution["status"] = (
            "PASSED_LOCAL_NON_CERTIFYING"
            if target_passed
            else "FAILED_LOCAL_TARGET_TESTS"
        )
        local["target_execution"] = target_execution
        local["service_bindings_after_target"] = verify_service_aliases(
            repository, bindings, target
        )
        local["status"] = (
            "PASSED_LOCAL_NON_CERTIFYING_SOURCE_AND_TARGET_22_TEST_ORACLE"
            if target_passed
            else "FAILED_LOCAL_TARGET_TESTS"
        )
        evidence["overall_status"] = local["status"]
        if target_passed:
            evidence["claims"]["behavioral_equivalence"] = (
                "OBSERVED_COMPLETE_22_TEST_ORACLE_PARITY_LOCAL_NON_CERTIFYING"
            )
        return evidence
    finally:
        local["temporary_alias_cleanup"] = cleanup_service_aliases(
            created_aliases, source
        )
        if not apply_cleanup_gate(evidence, local["temporary_alias_cleanup"]):
            local["status_before_cleanup_failure"] = local.get("status")
            local["status"] = "FAILED_CLEANUP"
        local["finished_at"] = protected.utc_now()
        evidence["certification_eligible"] = False
        evidence["certification_status"] = "NOT_CERTIFIED"
        evidence["customer_repository"] = False
        evidence["independent_verification"] = False
        evidence["external_execution_status"] = "NOT_RUN"
        evidence["claims"]["migration_success_rate"] = "NOT_EVALUATED"
        evidence["claims"]["customer_acceptance"] = "NOT_RUN"
        evidence["claims"]["independent_external_validation"] = "NOT_RUN"
        protected.atomic_json(output, evidence)

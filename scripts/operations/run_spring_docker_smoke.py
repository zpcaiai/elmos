#!/usr/bin/env python3
"""Run fail-closed local smoke checks for the three Spring execution images.

The checks intentionally keep image construction separate from runtime evidence:
images must already exist locally (normally via ``docker buildx build --load``).
The script never pulls images, never prunes Docker state, and always removes only
the uniquely named containers and internal networks it creates. Service ports
are probed from inside the hardened container and are never published to the host.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


SOURCE_DIRTY_LABELS = {
    "CLEAN_SOURCE": "false",
    "DIRTY_SOURCE": "true",
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
READINESS_CONTENT_TYPE_RE = re.compile(
    r"^application/(?:vnd\.spring-boot\.actuator\.v[0-9]+\+)?json(?:\s*;.*)?$",
    re.IGNORECASE,
)
READINESS_META_PREFIX = "ELMOS_HTTP_META:"


@dataclass(frozen=True)
class ServiceImage:
    key: str
    image: str
    expected_image_id: str
    expected_context_digest: str
    expected_source_status_digest: str
    expected_source_state: str
    expected_user: str
    port: int
    writable_tmpfs: tuple[str, ...]
    secret_env_key: str


def run(
    command: Sequence[str],
    *,
    check: bool = True,
    timeout: int = 120,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        list(command),
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=None if env is None else dict(env),
    )
    if check and completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(f"command failed ({completed.returncode}): {' '.join(command)}\n{detail}")
    return completed


def image_inspect(image: str) -> dict[str, Any]:
    payload = run(["docker", "image", "inspect", image]).stdout
    records = json.loads(payload)
    if len(records) != 1:
        raise RuntimeError(f"expected one inspect record for {image}, got {len(records)}")
    return records[0]


def assert_image_contract(
    image: str,
    expected_user: str,
    expected_image_id: str,
    expected_revision: str,
    *,
    expected_context_digest: str,
    expected_source_status_digest: str,
    expected_source_state: str,
) -> dict[str, Any]:
    record = image_inspect(image)
    actual_user = str(record.get("Config", {}).get("User", ""))
    if actual_user != expected_user:
        raise RuntimeError(
            f"{image} must declare USER {expected_user}; image declares {actual_user!r}"
        )
    if record.get("Os") != "linux":
        raise RuntimeError(f"{image} is not a Linux image: {record.get('Os')!r}")
    image_id = str(record.get("Id", ""))
    if not image_id.startswith("sha256:"):
        raise RuntimeError(f"{image} does not have an immutable local image ID")
    if image_id != expected_image_id:
        raise RuntimeError(
            f"{image} resolved to {image_id}; expected immutable ID {expected_image_id}"
        )
    labels = record.get("Config", {}).get("Labels") or {}
    required_labels = {
        "org.opencontainers.image.revision": expected_revision,
        "io.elmos.evidence.scope": "spring-modernization-local",
    }
    source_contract = (
        expected_context_digest,
        expected_source_status_digest,
        expected_source_state,
    )
    if not all(isinstance(value, str) and value for value in source_contract):
        raise RuntimeError(
            "source contract requires non-empty context digest, status digest, and state"
        )
    if not SHA256_RE.fullmatch(expected_context_digest):
        raise RuntimeError("expected context digest must be 64 lowercase hex characters")
    if not SHA256_RE.fullmatch(expected_source_status_digest):
        raise RuntimeError(
            "expected source status digest must be 64 lowercase hex characters"
        )
    expected_source_dirty = SOURCE_DIRTY_LABELS.get(expected_source_state)
    if expected_source_dirty is None:
        raise RuntimeError(
            "expected source state must be CLEAN_SOURCE or DIRTY_SOURCE"
        )
    required_labels.update(
        {
            "io.elmos.build.source-status": expected_source_state,
            "io.elmos.build.source-dirty": expected_source_dirty,
            "io.elmos.build.context-sha256": expected_context_digest,
            "io.elmos.build.context-status-sha256": expected_source_status_digest,
            "io.elmos.evidence.class": "LOCAL_NON_CERTIFYING",
        }
    )
    for label, expected in required_labels.items():
        actual = labels.get(label)
        if actual != expected:
            raise RuntimeError(
                f"{image} label {label} is {actual!r}; expected {expected!r}"
            )
    return {
        "image": image,
        "image_id": image_id,
        "architecture": record.get("Architecture"),
        "declared_user": actual_user,
        "entrypoint": record.get("Config", {}).get("Entrypoint"),
        "verified_labels": required_labels,
    }


def hardened_run_prefix(image: str) -> list[str]:
    return [
        "docker",
        "run",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges:true",
        "--pids-limit=256",
        "--memory=1g",
        "--network=none",
        "--rm",
        image,
    ]


def smoke_runtime(
    image: str,
    expected_context_digest: str,
    expected_source_status_digest: str,
) -> dict[str, Any]:
    java21 = run([*hardened_run_prefix(image), "-version"], timeout=60)
    java17 = run(
        [
            "docker",
            "run",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges:true",
            "--pids-limit=256",
            "--memory=1g",
            "--network=none",
            "--rm",
            "--entrypoint=/opt/java/openjdk-17/bin/java",
            image,
            "-version",
        ],
        timeout=60,
    )
    invalid_probe = run(
        [
            *hardened_run_prefix(image),
            "-cp",
            "/runner",
            "io.elmos.runner.HealthProbe",
            "https://not-allowed.invalid/health",
        ],
        check=False,
        timeout=60,
    )
    if invalid_probe.returncode != 64:
        raise RuntimeError(
            f"HealthProbe must reject a non-loopback URL with exit 64; got {invalid_probe.returncode}"
        )
    embedded: dict[str, str] = {}
    for key, path, expected in (
        ("source_context_digest", "/opt/elmos/source-context.sha256", expected_context_digest),
        ("source_status_digest", "/opt/elmos/source-status.sha256", expected_source_status_digest),
    ):
        actual = run(
            [
                "docker",
                "run",
                "--read-only",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges:true",
                "--pids-limit=256",
                "--memory=1g",
                "--network=none",
                "--rm",
                "--entrypoint=/usr/bin/cat",
                image,
                path,
            ],
            timeout=60,
        ).stdout.strip()
        if actual != expected:
            raise RuntimeError(
                f"{image} embeds {key} {actual!r}; expected {expected!r}"
            )
        embedded[key] = actual
    return {
        "java21_version": (java21.stderr or java21.stdout).strip().splitlines()[0],
        "java17_version": (java17.stderr or java17.stdout).strip().splitlines()[0],
        "health_probe_negative_exit": invalid_probe.returncode,
        "read_only": True,
        "cap_drop_all": True,
        "no_new_privileges": True,
        "network": "none",
        **embedded,
    }


def readiness_probe_command(container: str, port: int) -> list[str]:
    return [
        "docker",
        "exec",
        container,
        "/usr/bin/curl",
        "--disable",
        "--silent",
        "--show-error",
        "--connect-timeout",
        "2",
        "--max-time",
        "3",
        "--max-filesize",
        "16384",
        "--proto",
        "=http",
        "--proto-redir",
        "=none",
        "--noproxy",
        "*",
        "--header",
        "Accept: application/json",
        "--write-out",
        f"\n{READINESS_META_PREFIX}%{{http_code}}:%{{content_type}}\n",
        f"http://127.0.0.1:{port}/actuator/health/readiness",
    ]


def parse_readiness_response(output: str) -> dict[str, Any]:
    body, marker, metadata = output.rstrip().rpartition(f"\n{READINESS_META_PREFIX}")
    if not marker:
        raise RuntimeError("readiness probe did not emit bounded HTTP metadata")
    status_code, separator, content_type = metadata.partition(":")
    if separator != ":" or status_code != "200":
        raise RuntimeError(f"readiness returned HTTP {status_code or 'unknown'}")
    if not READINESS_CONTENT_TYPE_RE.fullmatch(content_type):
        raise RuntimeError(
            f"readiness returned non-JSON content type {content_type!r}"
        )
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError("readiness returned malformed JSON") from exc
    if not isinstance(payload, dict) or payload.get("status") != "UP":
        raise RuntimeError(
            "readiness JSON must be an object with top-level status UP"
        )
    return payload


def wait_for_readiness(
    container: str,
    port: int,
    *,
    startup_secret: str,
    timeout_seconds: int = 90,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_error = "no probe attempted"
    while time.monotonic() < deadline:
        state = run(
            ["docker", "inspect", "--format", "{{.State.Running}}", container],
            check=False,
        )
        if state.returncode != 0 or state.stdout.strip() != "true":
            captured = run(["docker", "logs", container], check=False)
            logs = (captured.stdout + captured.stderr).replace(
                startup_secret, "[REDACTED]"
            )[-4000:]
            raise RuntimeError(f"{container} exited before readiness\n{logs}")
        probe = run(
            readiness_probe_command(container, port),
            check=False,
            timeout=10,
        )
        if probe.returncode in (126, 127):
            raise RuntimeError(
                f"{container} does not provide the audited /usr/bin/curl readiness tool"
            )
        if probe.returncode == 0:
            try:
                return parse_readiness_response(probe.stdout)
            except RuntimeError as exc:
                last_error = str(exc)
        else:
            last_error = (probe.stderr or probe.stdout).strip()[-1000:]
        time.sleep(1)
    raise RuntimeError(f"readiness did not pass within {timeout_seconds}s: {last_error}")


def service_run_command(
    spec: ServiceImage,
    *,
    container: str,
    network: str,
) -> list[str]:
    command = [
        "docker",
        "run",
        "--detach",
        "--name",
        container,
        "--label",
        "io.elmos.smoke.scope=spring-modernization-local",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges:true",
        "--pids-limit=512",
        "--memory=1536m",
        "--network",
        network,
        "--env",
        spec.secret_env_key,
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,nodev,size=64m,mode=1777",
    ]
    for mount in spec.writable_tmpfs:
        command.extend(["--tmpfs", f"{mount}:rw,noexec,nosuid,nodev,size=64m,mode=1777"])
    command.append(spec.image)
    return command


def _process_detail(completed: subprocess.CompletedProcess[str]) -> str:
    return (completed.stderr or completed.stdout).strip().replace("\n", " ")[-500:]


def _explicitly_absent(
    kind: str,
    name: str,
    completed: subprocess.CompletedProcess[str],
) -> bool:
    lines = {
        line.strip()
        for line in f"{completed.stdout}\n{completed.stderr}".splitlines()
        if line.strip()
    }
    if kind == "container":
        accepted = {
            f"Error response from daemon: No such container: {name}",
            f"Error: No such container: {name}",
        }
    elif kind == "network":
        accepted = {
            f"Error response from daemon: network {name} not found",
            f"Error response from daemon: No such network: {name}",
            f"Error: No such network: {name}",
        }
    else:
        raise ValueError(f"unsupported Docker resource kind: {kind}")
    return bool(lines & accepted) and lines <= accepted | {"[]"}


def cleanup_smoke_resources(container: str, network: str) -> list[str]:
    errors: list[str] = []
    resources = (
        (
            "container",
            container,
            ["docker", "rm", "--force", container],
            ["docker", "container", "inspect", container],
        ),
        (
            "network",
            network,
            ["docker", "network", "rm", network],
            ["docker", "network", "inspect", network],
        ),
    )
    for kind, name, remove_command, inspect_command in resources:
        try:
            removed = run(remove_command, check=False, timeout=45)
        except BaseException as exc:  # noqa: BLE001 - continue to the other resource.
            errors.append(f"{kind}={name} remove raised {type(exc).__name__}")
        else:
            if removed.returncode != 0 and not _explicitly_absent(kind, name, removed):
                errors.append(
                    f"{kind}={name} remove failed rc={removed.returncode}: "
                    f"{_process_detail(removed)}"
                )
        try:
            inspected = run(inspect_command, check=False, timeout=30)
        except BaseException as exc:  # noqa: BLE001 - continue to the other resource.
            errors.append(f"{kind}={name} inspect raised {type(exc).__name__}")
            continue
        if inspected.returncode == 0:
            errors.append(f"{kind}={name} still exists after cleanup")
        elif not _explicitly_absent(kind, name, inspected):
            errors.append(
                f"{kind}={name} absence unproven rc={inspected.returncode}: "
                f"{_process_detail(inspected)}"
            )
    return errors


def smoke_service(spec: ServiceImage) -> dict[str, Any]:
    container = f"elmos-spring-smoke-{spec.key}-{uuid.uuid4().hex[:10]}"
    network = f"elmos-spring-smoke-net-{spec.key}-{uuid.uuid4().hex[:10]}"
    startup_secret = f"{spec.key}.{secrets.token_urlsafe(32)}"
    service_environment = os.environ.copy()
    service_environment[spec.secret_env_key] = startup_secret
    command = service_run_command(spec, container=container, network=network)
    try:
        run(
            [
                "docker",
                "network",
                "create",
                "--internal",
                "--label",
                "io.elmos.smoke.scope=spring-modernization-local",
                network,
            ]
        )
        internal = run(
            ["docker", "network", "inspect", "--format", "{{.Internal}}", network]
        ).stdout.strip()
        if internal != "true":
            raise RuntimeError(f"{network} is not an internal Docker network")
        run(command, env=service_environment)
        service_environment.pop(spec.secret_env_key, None)
        readiness = wait_for_readiness(
            container,
            spec.port,
            startup_secret=startup_secret,
        )
        process_user = run(
            ["docker", "exec", container, "/usr/bin/id", "-u"], timeout=30
        ).stdout.strip()
        expected_uid = spec.expected_user.split(":", 1)[0]
        if process_user != expected_uid:
            raise RuntimeError(
                f"{spec.image} runs as UID {process_user}; expected {expected_uid}"
            )
        context_digest = run(
            [
                "docker",
                "exec",
                container,
                "/usr/bin/cat",
                "/opt/elmos/source-context.sha256",
            ],
            timeout=30,
        ).stdout.strip()
        if context_digest != spec.expected_context_digest:
            raise RuntimeError(
                f"{spec.image} embeds context digest {context_digest!r}; "
                f"expected {spec.expected_context_digest!r}"
            )
        source_status_digest = run(
            [
                "docker",
                "exec",
                container,
                "/usr/bin/cat",
                "/opt/elmos/source-status.sha256",
            ],
            timeout=30,
        ).stdout.strip()
        if source_status_digest != spec.expected_source_status_digest:
            raise RuntimeError(
                f"{spec.image} embeds source status digest {source_status_digest!r}; "
                f"expected {spec.expected_source_status_digest!r}"
            )
        run(["docker", "stop", "--time", "30", container], timeout=45)
        exit_code = int(
            run(
                ["docker", "inspect", "--format", "{{.State.ExitCode}}", container]
            ).stdout.strip()
        )
        if exit_code not in (0, 143):
            raise RuntimeError(f"{spec.image} exited with {exit_code} after SIGTERM")
        result = {
            "readiness": readiness,
            "runtime_uid": process_user,
            "source_context_digest": context_digest,
            "source_status_digest": source_status_digest,
            "sigterm_exit_code": exit_code,
            "read_only": True,
            "cap_drop_all": True,
            "no_new_privileges": True,
            "network_isolation": "unique_internal_bridge",
            "network_internal": True,
            "host_port_published": False,
            "startup_secret": {
                "provided": True,
                "source": "generated_in_process_ephemeral_container_env",
                "container_removed_in_finally": True,
                "value_recorded": False,
                "digest_recorded": False,
            },
        }
        return result
    finally:
        active_error = sys.exc_info()[1]
        service_environment.pop(spec.secret_env_key, None)
        cleanup_errors = cleanup_smoke_resources(container, network)
        if cleanup_errors:
            cleanup_message = "cleanup/orphan risk: " + ", ".join(cleanup_errors)
            if active_error is not None:
                raise RuntimeError(f"{active_error}; {cleanup_message}") from active_error
            raise RuntimeError(cleanup_message)


def engine_rootless_status() -> dict[str, Any]:
    raw = run(["docker", "info", "--format", "{{json .SecurityOptions}}"]).stdout.strip()
    options = json.loads(raw)
    return {
        "security_options": options,
        "rootless": any(option == "name=rootless" for option in options),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", required=True, help="locally loaded runtime-runner image")
    parser.add_argument("--transformer", required=True, help="locally loaded transformer image")
    parser.add_argument("--verifier", required=True, help="locally loaded verifier image")
    parser.add_argument("--runtime-image-id", required=True)
    parser.add_argument("--transformer-image-id", required=True)
    parser.add_argument("--verifier-image-id", required=True)
    parser.add_argument("--expected-revision", required=True)
    parser.add_argument("--runtime-context-digest", required=True)
    parser.add_argument("--transformer-context-digest", required=True)
    parser.add_argument("--verifier-context-digest", required=True)
    parser.add_argument("--runtime-source-status-digest", required=True)
    parser.add_argument("--transformer-source-status-digest", required=True)
    parser.add_argument("--verifier-source-status-digest", required=True)
    parser.add_argument(
        "--runtime-source-state",
        choices=tuple(SOURCE_DIRTY_LABELS),
        required=True,
    )
    parser.add_argument(
        "--transformer-source-state",
        choices=tuple(SOURCE_DIRTY_LABELS),
        required=True,
    )
    parser.add_argument(
        "--verifier-source-state",
        choices=tuple(SOURCE_DIRTY_LABELS),
        required=True,
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    services = (
        ServiceImage(
            "transformer",
            args.transformer,
            args.transformer_image_id,
            args.transformer_context_digest,
            args.transformer_source_status_digest,
            args.transformer_source_state,
            "10001:10001",
            8083,
            ("/workspace",),
            "ELMOS_TRANSFORMER_HMAC_SECRET_VALUE",
        ),
        ServiceImage(
            "verifier",
            args.verifier,
            args.verifier_image_id,
            args.verifier_context_digest,
            args.verifier_source_status_digest,
            args.verifier_source_state,
            "10002:10002",
            8082,
            ("/verification",),
            "ELMOS_VERIFIER_HMAC_SECRET_VALUE",
        ),
    )
    result: dict[str, Any] = {
        "schema_version": "1.0",
        "evidence_class": "LOCAL_NON_CERTIFYING_CONTAINER_SMOKE",
        "certification_eligible": False,
        "engine": engine_rootless_status(),
        "images": {},
    }
    try:
        result["images"]["runtime"] = {
            **assert_image_contract(
                args.runtime,
                "10003:10003",
                args.runtime_image_id,
                args.expected_revision,
                expected_context_digest=args.runtime_context_digest,
                expected_source_status_digest=args.runtime_source_status_digest,
                expected_source_state=args.runtime_source_state,
            ),
            "smoke": smoke_runtime(
                args.runtime,
                args.runtime_context_digest,
                args.runtime_source_status_digest,
            ),
        }
        for spec in services:
            result["images"][spec.key] = {
                **assert_image_contract(
                    spec.image,
                    spec.expected_user,
                    spec.expected_image_id,
                    args.expected_revision,
                    expected_context_digest=spec.expected_context_digest,
                    expected_source_status_digest=spec.expected_source_status_digest,
                    expected_source_state=spec.expected_source_state,
                ),
                "smoke": smoke_service(spec),
            }
    except Exception as exc:  # noqa: BLE001 - CLI must emit a fail-closed result.
        result["status"] = "FAILED"
        result["error"] = str(exc)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 1
    result["status"] = "PASSED_LOCAL"
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

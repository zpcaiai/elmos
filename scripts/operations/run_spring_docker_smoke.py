#!/usr/bin/env python3
"""Run fail-closed local smoke checks for the three Spring execution images.

The checks intentionally keep image construction separate from runtime evidence:
images must already exist locally (normally via ``docker buildx build --load``).
The script never pulls images, never prunes Docker state, and always removes only
the uniquely named containers and internal networks it creates.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Any, Sequence


SOURCE_DIRTY_LABELS = {
    "CLEAN_SOURCE": "false",
    "DIRTY_SOURCE": "true",
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


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


def run(
    command: Sequence[str],
    *,
    check: bool = True,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        list(command),
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
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
    expected_context_digest: str | None = None,
    expected_source_status_digest: str | None = None,
    expected_source_state: str | None = None,
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
    if any(value is not None for value in source_contract):
        if not all(isinstance(value, str) and value for value in source_contract):
            raise RuntimeError(
                "source contract requires non-empty context digest, status digest, and state"
            )
        assert expected_context_digest is not None
        assert expected_source_status_digest is not None
        assert expected_source_state is not None
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


def smoke_runtime(image: str) -> dict[str, Any]:
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
    return {
        "java21_version": (java21.stderr or java21.stdout).strip().splitlines()[0],
        "java17_version": (java17.stderr or java17.stdout).strip().splitlines()[0],
        "health_probe_negative_exit": invalid_probe.returncode,
        "read_only": True,
        "cap_drop_all": True,
        "no_new_privileges": True,
        "network": "none",
    }


def published_port(container: str, port: int) -> int:
    output = run(["docker", "port", container, f"{port}/tcp"]).stdout.strip()
    if not output:
        raise RuntimeError(f"Docker did not publish {container}:{port}")
    endpoint = output.splitlines()[0]
    return int(endpoint.rsplit(":", 1)[1])


def wait_for_readiness(container: str, host_port: int, timeout_seconds: int = 90) -> str:
    deadline = time.monotonic() + timeout_seconds
    url = f"http://127.0.0.1:{host_port}/actuator/health/readiness"
    last_error = "no probe attempted"
    while time.monotonic() < deadline:
        state = run(
            ["docker", "inspect", "--format", "{{.State.Running}}", container],
            check=False,
        )
        if state.returncode != 0 or state.stdout.strip() != "true":
            logs = run(["docker", "logs", container], check=False).stdout[-4000:]
            raise RuntimeError(f"{container} exited before readiness\n{logs}")
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                body = response.read(4096).decode("utf-8", errors="replace")
                if response.status == 200 and '"status":"UP"' in body:
                    return body
                last_error = f"HTTP {response.status}: {body}"
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = str(exc)
        time.sleep(1)
    raise RuntimeError(f"readiness did not pass within {timeout_seconds}s: {last_error}")


def smoke_service(spec: ServiceImage) -> dict[str, Any]:
    container = f"elmos-spring-smoke-{spec.key}-{uuid.uuid4().hex[:10]}"
    network = f"elmos-spring-smoke-net-{spec.key}-{uuid.uuid4().hex[:10]}"
    network_created = False
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
        "--publish",
        f"127.0.0.1::{spec.port}",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,nodev,size=64m,mode=1777",
    ]
    for mount in spec.writable_tmpfs:
        command.extend(["--tmpfs", f"{mount}:rw,noexec,nosuid,nodev,size=64m,mode=1777"])
    command.append(spec.image)
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
        network_created = True
        internal = run(
            ["docker", "network", "inspect", "--format", "{{.Internal}}", network]
        ).stdout.strip()
        if internal != "true":
            raise RuntimeError(f"{network} is not an internal Docker network")
        run(command)
        host_port = published_port(container, spec.port)
        readiness_body = wait_for_readiness(container, host_port)
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
        run(["docker", "stop", "--time", "30", container], timeout=45)
        exit_code = int(
            run(
                ["docker", "inspect", "--format", "{{.State.ExitCode}}", container]
            ).stdout.strip()
        )
        if exit_code not in (0, 143):
            raise RuntimeError(f"{spec.image} exited with {exit_code} after SIGTERM")
        return {
            "host_port": host_port,
            "readiness": json.loads(readiness_body),
            "runtime_uid": process_user,
            "source_context_digest": context_digest,
            "sigterm_exit_code": exit_code,
            "read_only": True,
            "cap_drop_all": True,
            "no_new_privileges": True,
            "network_isolation": "unique_internal_bridge",
            "network_internal": True,
        }
    finally:
        run(["docker", "rm", "--force", container], check=False, timeout=45)
        if network_created:
            run(["docker", "network", "rm", network], check=False, timeout=45)


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
    parser.add_argument("--transformer-context-digest", required=True)
    parser.add_argument("--verifier-context-digest", required=True)
    parser.add_argument("--transformer-source-status-digest", required=True)
    parser.add_argument("--verifier-source-status-digest", required=True)
    parser.add_argument(
        "--transformer-source-state",
        choices=tuple(SOURCE_DIRTY_LABELS),
        default="DIRTY_SOURCE",
        help="expected source-state label; defaults to DIRTY_SOURCE for compatibility",
    )
    parser.add_argument(
        "--verifier-source-state",
        choices=tuple(SOURCE_DIRTY_LABELS),
        default="DIRTY_SOURCE",
        help="expected source-state label; defaults to DIRTY_SOURCE for compatibility",
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
            ),
            "smoke": smoke_runtime(args.runtime),
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

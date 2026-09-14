#!/usr/bin/env python3
"""Run bounded Batch 40 controls in a hardened, content-addressed Docker image.

The resulting report is local self-attested engineering evidence. It cannot
represent an independent assessment, a production runner, or certification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROBE_SOURCE = ROOT / "scripts/batch40/docker_local_probe.go"
DOCKERFILE = ROOT / "scripts/batch40/Dockerfile.local-evidence"
DEFAULT_PACK = ROOT / "mature-product-packs/batch40/elmos-platform-supply-chain"
EXPECTED_USER = "65532:65532"
EXPECTED_MEMORY = 64 * 1024 * 1024
EXPECTED_NANO_CPUS = 500_000_000
EXPECTED_PIDS = 64


class EvidenceError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def run(command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        command,
        cwd=cwd or ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
        raise EvidenceError(f"{' '.join(command[:3])}: {detail}")
    return result.stdout.strip()


def git_revision() -> str:
    revision = run(["git", "rev-parse", "HEAD"])
    if len(revision) != 40:
        raise EvidenceError("repository HEAD is not a full Git revision")
    return revision


def daemon_architecture(server: dict[str, Any]) -> str:
    if server.get("Os") != "linux":
        raise EvidenceError("Batch 40 Docker probe requires a Linux Docker daemon")
    architecture = server.get("Arch")
    mapping = {"amd64": "amd64", "arm64": "arm64"}
    if architecture not in mapping:
        raise EvidenceError(f"unsupported Docker daemon architecture: {architecture}")
    return mapping[architecture]


def validate_runtime_inspect(inspect: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    config = inspect.get("Config") if isinstance(inspect.get("Config"), dict) else {}
    host = inspect.get("HostConfig") if isinstance(inspect.get("HostConfig"), dict) else {}
    security_options = host.get("SecurityOpt") or []
    cap_drop = host.get("CapDrop") or []
    tmpfs = host.get("Tmpfs") if isinstance(host.get("Tmpfs"), dict) else {}
    mounts = inspect.get("Mounts") or []
    checks = [
        ("B40-DOCKER-NONROOT", config.get("User") == EXPECTED_USER, f"user={config.get('User')}"),
        ("B40-DOCKER-NETWORK-NONE", host.get("NetworkMode") == "none", f"networkMode={host.get('NetworkMode')}"),
        ("B40-DOCKER-READONLY-ROOTFS", host.get("ReadonlyRootfs") is True, f"readOnly={host.get('ReadonlyRootfs')}"),
        ("B40-DOCKER-CAP-DROP", "ALL" in cap_drop, f"capDrop={cap_drop}"),
        ("B40-DOCKER-NO-NEW-PRIVILEGES", any(str(item).startswith("no-new-privileges") for item in security_options), f"securityOpt={security_options}"),
        ("B40-DOCKER-NO-HOST-MOUNTS", not mounts and not host.get("Binds"), f"mountCount={len(mounts)}"),
        ("B40-DOCKER-BOUNDED-PIDS", host.get("PidsLimit") == EXPECTED_PIDS, f"pidsLimit={host.get('PidsLimit')}"),
        ("B40-DOCKER-BOUNDED-MEMORY", host.get("Memory") == EXPECTED_MEMORY, f"memory={host.get('Memory')}"),
        ("B40-DOCKER-BOUNDED-CPU", host.get("NanoCpus") == EXPECTED_NANO_CPUS, f"nanoCpus={host.get('NanoCpus')}"),
        ("B40-DOCKER-EPHEMERAL-TMPFS", "/tmp" in tmpfs and "nosuid" in tmpfs.get("/tmp", "") and "nodev" in tmpfs.get("/tmp", "") and "noexec" in tmpfs.get("/tmp", ""), f"tmpfs={tmpfs}"),
    ]
    controls = [
        {"controlId": control_id, "status": "PASS" if passed else "FAIL", "details": [detail]}
        for control_id, passed, detail in checks
    ]
    observed = {
        "user": config.get("User"),
        "networkMode": host.get("NetworkMode"),
        "readOnlyRootFilesystem": host.get("ReadonlyRootfs"),
        "capDrop": cap_drop,
        "securityOptions": security_options,
        "hostMountCount": len(mounts),
        "pidsLimit": host.get("PidsLimit"),
        "memoryBytes": host.get("Memory"),
        "nanoCpus": host.get("NanoCpus"),
        "tmpfs": tmpfs,
    }
    return controls, observed


def validate_probe(report: dict[str, Any]) -> list[dict[str, Any]]:
    failures: list[str] = []
    if report.get("status") != "PASS":
        failures.append("probe status is not PASS")
    if report.get("independentVerification") != "NOT_RUN":
        failures.append("probe must preserve independentVerification=NOT_RUN")
    if report.get("certificationStatus") != "NOT_CERTIFIED":
        failures.append("probe must preserve certificationStatus=NOT_CERTIFIED")
    controls = report.get("controls")
    if not isinstance(controls, list) or not controls:
        failures.append("probe emitted no controls")
        controls = []
    failed = [item.get("controlId") for item in controls if item.get("status") != "PASS"]
    if failed:
        failures.append(f"probe controls failed: {failed}")
    corpora = report.get("corpora") if isinstance(report.get("corpora"), dict) else {}
    groups = [corpora.get(name) for name in ("development", "holdout", "representative")]
    if not all(isinstance(group, list) and group for group in groups):
        failures.append("probe corpora must be three non-empty lists")
    else:
        flattened = [item for group in groups for item in group]
        if len(flattened) != len(set(flattened)):
            failures.append("probe corpora overlap")
    if failures:
        raise EvidenceError("; ".join(failures))
    return controls


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def execute(pack: Path, output: Path) -> dict[str, Any]:
    started_at = utc_now()
    pack_record_path = pack / "pack.json"
    if not pack_record_path.is_file():
        raise EvidenceError(f"Batch 40 pack is missing: {pack_record_path}")
    pack_record = json.loads(pack_record_path.read_text(encoding="utf-8"))
    if pack_record.get("batch") != 40 or pack_record.get("packKey") != "elmos-platform-supply-chain":
        raise EvidenceError("Docker local evidence requires the exact elmos-platform-supply-chain pack")
    docker_version = json.loads(run(["docker", "version", "--format", "{{json .}}"]))
    server = docker_version.get("Server")
    if not isinstance(server, dict):
        raise EvidenceError("Docker daemon information is unavailable")
    go_arch = daemon_architecture(server)
    security_options = json.loads(run(["docker", "info", "--format", "{{json .SecurityOptions}}"]))
    if not isinstance(security_options, list):
        raise EvidenceError("Docker security options are not a list")
    buildx_version = run(["docker", "buildx", "version"])
    go_version = run(["go", "version"])
    repository_revision = git_revision()
    tool_digest = sha256_file(Path(__file__))
    probe_digest = sha256_file(PROBE_SOURCE)
    dockerfile_digest = sha256_file(DOCKERFILE)
    tag = f"elmos-b40-local-evidence:{probe_digest.split(':', 1)[1][:16]}"
    container_name = f"elmos-b40-local-{uuid.uuid4().hex[:12]}"
    image_id = ""
    container_id = ""
    probe_report: dict[str, Any]
    runtime_controls: list[dict[str, Any]]
    runtime_observed: dict[str, Any]

    with tempfile.TemporaryDirectory(prefix="elmos-b40-docker-") as directory:
        context = Path(directory)
        binary = context / "b40-docker-local-probe"
        build_environment = dict(os.environ)
        build_environment.update({"CGO_ENABLED": "0", "GOOS": "linux", "GOARCH": go_arch})
        run([
            "go", "build", "-trimpath", "-buildvcs=false",
            "-ldflags=-s -w -buildid=", "-o", str(binary), str(PROBE_SOURCE),
        ], env=build_environment)
        shutil.copyfile(DOCKERFILE, context / "Dockerfile")
        binary_digest = sha256_file(binary)
        run([
            "docker", "buildx", "build", "--load", "--network", "none",
            "--provenance=false", "--sbom=false", "--tag", tag, str(context),
        ])
        image_id = run(["docker", "image", "inspect", "--format", "{{.Id}}", tag])
        if not image_id.startswith("sha256:"):
            raise EvidenceError("built image has no content-addressed image ID")
        try:
            container_id = run([
                "docker", "create", "--name", container_name,
                "--network", "none", "--read-only", "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges:true", "--user", EXPECTED_USER,
                "--pids-limit", str(EXPECTED_PIDS), "--memory", "64m", "--cpus", "0.5",
                "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=16m", image_id,
            ])
            inspect = json.loads(run(["docker", "inspect", container_id]))[0]
            runtime_controls, runtime_observed = validate_runtime_inspect(inspect)
            probe_report = json.loads(run(["docker", "start", "--attach", container_id]))
            validate_probe(probe_report)
        finally:
            if container_id:
                subprocess.run(["docker", "rm", "-f", container_id], capture_output=True, check=False)
            subprocess.run(["docker", "image", "rm", tag], capture_output=True, check=False)

    all_controls = runtime_controls + probe_report["controls"]
    failed_controls = [item["controlId"] for item in all_controls if item["status"] != "PASS"]
    status = "PASS" if not failed_controls else "BLOCKED"
    daemon_rootless = any("rootless" in str(item).lower() for item in security_options)
    report = {
        "schemaVersion": 1,
        "id": "b40-docker-local-evidence",
        "batch": 40,
        "packKey": "elmos-platform-supply-chain",
        "status": status,
        "evidenceClass": "LOCAL_EXECUTED_SELF_ATTESTED",
        "startedAt": started_at,
        "finishedAt": utc_now(),
        "repositoryRevision": repository_revision,
        "replayCommand": (
            "python3 scripts/batch40_docker_local_evidence.py --pack "
            "mature-product-packs/batch40/elmos-platform-supply-chain"
        ),
        "toolDigest": tool_digest,
        "build": {
            "source": {"path": "scripts/batch40/docker_local_probe.go", "sha256": probe_digest},
            "dockerfile": {"path": "scripts/batch40/Dockerfile.local-evidence", "sha256": dockerfile_digest},
            "binarySha256": binary_digest,
            "imageId": image_id,
            "baseImage": "scratch",
            "networkMode": "none",
            "goVersion": go_version,
            "buildxVersion": buildx_version,
            "imageRetained": False,
        },
        "docker": {
            "clientVersion": docker_version.get("Client", {}).get("Version"),
            "serverVersion": server.get("Version"),
            "serverOs": server.get("Os"),
            "serverArch": server.get("Arch"),
            "securityOptions": security_options,
            "daemonRootlessAttested": daemon_rootless,
        },
        "scope": {
            "controlCount": len(all_controls),
            "localFixtureCount": sum(len(group) for group in probe_report["corpora"].values()),
            "productionArtifactsEvaluated": 0,
            "externalRunnersEvaluated": 0,
        },
        "runtime": runtime_observed,
        "corpora": probe_report["corpora"],
        "controls": all_controls,
        "failedControls": failed_controls,
        "productionEvidence": "NOT_RUN",
        "externalOperationExecuted": False,
        "independentVerification": "NOT_RUN",
        "certificationStatus": "NOT_CERTIFIED",
        "limitations": [
            "This run exercises synthetic local fixtures in one Docker daemon; it is self-attested engineering evidence only.",
            "The Docker daemon did not attest rootless operation; non-root container execution does not prove a rootless daemon or an independently isolated builder.",
            "The local HMAC key is an ephemeral fixture key, not a production signing key or an external trust anchor.",
            "The local holdout and representative fixture sets are code-owned negative tests, not independently authored or representative production corpora.",
            "No production artifact, hosted runner, provider scanner, external environment, independent assessor, approver, or certification authority was exercised.",
        ],
        "host": {"system": platform.system(), "machine": platform.machine()},
    }
    atomic_write_json(output, report)
    if status != "PASS":
        raise EvidenceError(f"Docker local evidence controls failed: {failed_controls}")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", type=Path, default=DEFAULT_PACK)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    pack = args.pack.resolve()
    output = args.output.resolve() if args.output else pack / "evidence/execution/b40-docker-local-evidence.json"
    try:
        report = execute(pack, output)
    except (EvidenceError, json.JSONDecodeError, OSError) as exc:
        print(f"ERROR: {exc}", file=os.sys.stderr)
        return 2
    print(json.dumps({
        "status": report["status"],
        "evidenceClass": report["evidenceClass"],
        "controlCount": report["scope"]["controlCount"],
        "productionEvidence": report["productionEvidence"],
        "independentVerification": report["independentVerification"],
        "certificationStatus": report["certificationStatus"],
        "output": str(output),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

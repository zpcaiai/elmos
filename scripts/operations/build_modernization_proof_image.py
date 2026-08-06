#!/usr/bin/env python3
"""Build, verify, scan and optionally publish the Batch 105-108 worker image.

The script deliberately refuses to print a production environment assignment
until a registry push returns a repository digest. A local image ID or a mutable
tag is useful engineering evidence, but is not a deployable runner identity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


IMMUTABLE_REFERENCE = re.compile(
    r"^[a-z0-9][a-z0-9._/-]*(?::[0-9]+)?/?[a-z0-9._/-]*@sha256:[0-9a-f]{64}$"
)
REPOSITORY = re.compile(r"^[a-z0-9][a-z0-9._/-]*(?::[0-9]+)?/?[a-z0-9._/-]*$")
TAG = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")
EXPECTED_USER = "65532:65532"
EXPECTED_ENTRYPOINT = ["java", "-jar", "/opt/elmos/modernization-proof-worker.jar"]
EXPECTED_CAPABILITY = "modernization:proof-loop"
RUNTIME_APKS = {
    "linux/arm64": [
        ("main", "ca-certificates-20260611-r0.apk", "6b491dcda951129c80e8d7b0f509253ab640b20653b208d3b0994d893189b3f5", 131113),
        ("community", "java-cacerts-1.1-r0.apk", "5247f58a64cee47ab679fec7919ad1f8f58feae4b127ea2aba5f37d0fb4851f6", 1899),
        ("community", "java-common-1.0-r0.apk", "9c8c93b3ebe61b4c223dbe04e1775e86335186d492509a684ff01ca9b436d1d6", 1992),
        ("main", "libffi-3.4.8-r0.apk", "9391f60a14c146655deaf65115563bc8dcd749cf0f93ec567e6443f2ed7d3bfc", 17599),
        ("main", "libtasn1-4.21.0-r0.apk", "c348eb9a293bbf1ff2d922fe200b525088e0038c0dd5154b68a4b22753e9385f", 34072),
        ("community", "openjdk21-jre-headless-21.0.11_p10-r0.apk", "ac058a82b572309893238fa1780841e7aa03a777e11b62b9110f6d445edac24b", 64180174),
        ("main", "p11-kit-0.26.2-r0.apk", "401078e81e024616fc61b7f631baeefe33b43865c638a12be5b8e9b20d1e1f88", 363721),
        ("main", "p11-kit-trust-0.26.2-r0.apk", "99ab18df98cef4ba2de4b4813911e4bf4349370bd17aac64b83de62ab26a6a12", 149465),
    ],
    "linux/amd64": [
        ("main", "ca-certificates-20260611-r0.apk", "a8ad8f04dfba1a2897388c4b420b698bf1ecd870be10f0127134a567d5e59896", 129495),
        ("community", "java-cacerts-1.1-r0.apk", "78e4c51f3baf82aa92bbf68e8bafedd24ca2c0ca284d333d3fa8f1d8a3e077ca", 1912),
        ("community", "java-common-1.0-r0.apk", "623babb08fee70774f215aa9189672aa4b44d800149f83ccd33ec70598da1ae4", 2011),
        ("main", "libffi-3.4.8-r0.apk", "9a75cb9024693c1e52c3d8d7c9afb7c79e6e20f6c08df28effdb8dd816095083", 18222),
        ("main", "libtasn1-4.21.0-r0.apk", "ce3d6b63c8fd8c4248028740095c83a6291c334f5f260003c3adc12fb810404e", 33393),
        ("community", "openjdk21-jre-headless-21.0.11_p10-r0.apk", "66487bbb57861b06482a53868c8c7a37ac7e838c748b2cf696f63df5154a6e09", 65261089),
        ("main", "p11-kit-0.26.2-r0.apk", "3acc0d16e7e73ce32cdd12f58979809bbaf0ff88f6fff73883307233aab5ce70", 407247),
        ("main", "p11-kit-trust-0.26.2-r0.apk", "c9979025e072bd4ca4c20a877022a506943ec35742a15f4222323af65077a5af", 145790),
    ],
}


class BuildFailure(RuntimeError):
    """A stable failure that can be reported without leaking command output."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_command(
    command: Sequence[str], *, cwd: Path, log_path: Path, allow_failure: bool = False
) -> subprocess.CompletedProcess[str]:
    process = subprocess.run(
        list(command), cwd=cwd, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, check=False,
    )
    log_path.write_text(process.stdout, encoding="utf-8")
    if process.returncode != 0 and not allow_failure:
        raise BuildFailure(
            f"command failed with exit code {process.returncode}; see {log_path}"
        )
    return process


def provision_runtime_apks(platform: str, *, root: Path, output: Path) -> list[Path]:
    architecture = "aarch64" if platform == "linux/arm64" else "x86_64"
    apk_dir = output / "runtime-apks"
    apk_dir.mkdir(parents=True, exist_ok=True)
    expected_names = {contract[1] for contract in RUNTIME_APKS[platform]}
    unexpected = {path.name for path in apk_dir.glob("*.apk")} - expected_names
    if unexpected:
        raise BuildFailure("runtime APK directory contains undeclared packages")
    result: list[Path] = []
    for repository, name, expected_sha, expected_bytes in RUNTIME_APKS[platform]:
        apk = apk_dir / name
        if not (apk.is_file() and apk.stat().st_size == expected_bytes
                and sha256_file(apk) == expected_sha):
            url = (
                f"https://dl-cdn.alpinelinux.org/alpine/v3.22/{repository}/"
                f"{architecture}/{name}"
            )
            run_command(
                [
                    "curl", "--noproxy", "dl-cdn.alpinelinux.org", "--fail", "--location",
                    "--retry", "5", "--retry-all-errors", "--continue-at", "-",
                    "--output", str(apk), url,
                ],
                cwd=root,
                log_path=output / f"runtime-apk-{name}.download.log",
            )
        if apk.stat().st_size != expected_bytes or sha256_file(apk) != expected_sha:
            raise BuildFailure(f"runtime APK failed exact verification: {name}")
        result.append(apk)
    return result


def validate_image_config(inspect: dict[str, Any]) -> None:
    config = inspect.get("Config") or {}
    if config.get("User") != EXPECTED_USER:
        raise BuildFailure(f"worker image user must be {EXPECTED_USER}")
    if config.get("Entrypoint") != EXPECTED_ENTRYPOINT:
        raise BuildFailure("worker image entrypoint does not match the reviewed contract")
    labels = config.get("Labels") or {}
    if labels.get("io.elmos.runner.capability") != EXPECTED_CAPABILITY:
        raise BuildFailure("worker image capability label is absent or incorrect")
    if inspect.get("Os") != "linux":
        raise BuildFailure("worker image must target Linux")
    if inspect.get("Architecture") not in {"amd64", "arm64"}:
        raise BuildFailure("worker image architecture is unsupported")


def select_repository_digest(inspect: dict[str, Any], repository: str) -> str:
    candidates = inspect.get("RepoDigests") or []
    for candidate in candidates:
        if candidate.startswith(repository + "@") and IMMUTABLE_REFERENCE.fullmatch(candidate):
            return candidate
    raise BuildFailure("registry push did not yield an immutable repository digest")


def inspect_image(reference: str, *, root: Path, log_path: Path) -> dict[str, Any]:
    result = run_command(
        ["docker", "image", "inspect", reference], cwd=root, log_path=log_path
    )
    parsed = json.loads(result.stdout)
    if not isinstance(parsed, list) or len(parsed) != 1:
        raise BuildFailure("docker inspect returned an unexpected document")
    image = parsed[0]
    validate_image_config(image)
    return image


def smoke_test(reference: str, *, root: Path, evidence_dir: Path) -> dict[str, Any]:
    fixture = root / "apps/modernization-proof-worker/src/test/resources/request.json"
    with tempfile.TemporaryDirectory(prefix="elmos-proof-image-") as temporary:
        work = Path(temporary)
        input_dir = work / "in"
        output_dir = work / "out"
        input_dir.mkdir(mode=0o755)
        output_dir.mkdir(mode=0o777)
        shutil.copyfile(fixture, input_dir / "request.json")
        os.chmod(input_dir / "request.json", 0o644)
        run_command(
            [
                "docker", "run", "--rm", "--network=none", "--read-only",
                "--cap-drop=ALL", "--security-opt=no-new-privileges",
                "--user", EXPECTED_USER, "--pids-limit", "128", "--memory", "512m",
                "--cpus", "1", "--tmpfs",
                "/tmp:rw,noexec,nosuid,size=64m,uid=65532,gid=65532",
                "--env", f"ELMOS_RUNNER_IMAGE_MODERNIZATION_PROOF={reference}",
                "--mount", f"type=bind,src={input_dir},dst=/elmos/in,readonly",
                "--mount", f"type=bind,src={output_dir},dst=/elmos/out",
                reference,
            ],
            cwd=root,
            log_path=evidence_dir / "container-smoke.log",
        )
        result_path = output_dir / "evidence/proof-loop-result.json"
        if not result_path.is_file():
            raise BuildFailure("container smoke test did not emit its result artifact")
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if result.get("externalOperationExecuted") is not False:
            raise BuildFailure("worker falsely reported an external operation")
        if result.get("productionApproved") is not False or result.get("certified") is not False:
            raise BuildFailure("worker falsely reported production approval or certification")
        persisted = evidence_dir / "container-smoke-result.json"
        persisted.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return {
            "status": "PASSED",
            "result_sha256": sha256_file(persisted),
            "external_operation_executed": False,
            "production_approved": False,
            "certified": False,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--platform", default="linux/arm64", choices=("linux/arm64", "linux/amd64"))
    parser.add_argument("--push", action="store_true")
    parser.add_argument("--scan", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not REPOSITORY.fullmatch(args.repository):
        raise SystemExit("invalid lowercase OCI repository")
    if not TAG.fullmatch(args.tag):
        raise SystemExit("invalid OCI tag")

    root = Path(__file__).resolve().parents[2]
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    mutable_reference = f"{args.repository}:{args.tag}"

    run_command(
        [
            "mvn", "-B", "-pl", "apps/modernization-proof-worker", "-am",
            "-DskipTests=false", "package",
        ],
        cwd=root,
        log_path=output / "maven-package.log",
    )
    jar = root / (
        "apps/modernization-proof-worker/target/"
        "modernization-proof-worker-0.1.0-SNAPSHOT-exec.jar"
    )
    if not jar.is_file():
        raise BuildFailure("Maven package did not produce the executable worker JAR")
    staged_jar = output / jar.name
    shutil.copyfile(jar, staged_jar)
    runtime_apks = provision_runtime_apks(args.platform, root=root, output=output)

    run_command(
        [
            "docker", "buildx", "build", "--load", "--pull=false",
            "--platform", args.platform,
            "--tag", mutable_reference,
            "--file", "apps/modernization-proof-worker/Dockerfile.runtime",
            str(output),
        ],
        cwd=root,
        log_path=output / "docker-build.log",
    )
    local_inspect = inspect_image(
        mutable_reference, root=root, log_path=output / "docker-inspect-local.json"
    )

    immutable_reference: str | None = None
    if args.push:
        run_command(
            ["docker", "push", mutable_reference],
            cwd=root,
            log_path=output / "docker-push.log",
        )
        pushed_inspect = inspect_image(
            mutable_reference, root=root, log_path=output / "docker-inspect-pushed.json"
        )
        immutable_reference = select_repository_digest(pushed_inspect, args.repository)

    runtime_environment = output / "modernization-proof-worker.env"
    if immutable_reference is not None:
        runtime_environment.write_text(
            f"ELMOS_RUNNER_IMAGE_MODERNIZATION_PROOF={immutable_reference}\n",
            encoding="utf-8",
        )
        runtime_environment.chmod(0o600)
        smoke = smoke_test(immutable_reference, root=root, evidence_dir=output)
    else:
        smoke = {
            "status": "NOT_RUN",
            "reason": "registry repository digest is required before execution",
            "external_operation_executed": False,
            "production_approved": False,
            "certified": False,
        }

    scan = {"status": "NOT_RUN"}
    if args.scan:
        scan_result = run_command(
            [
                "docker", "scout", "cves", "--format", "sarif", "--output",
                str(output / "vulnerabilities.sarif.json"),
                "--only-severity", "critical,high", f"local://{mutable_reference}",
            ],
            cwd=root,
            log_path=output / "docker-scout.log",
            allow_failure=True,
        )
        report = output / "vulnerabilities.sarif.json"
        scan = {
            "status": "PASSED" if scan_result.returncode == 0 and report.is_file() else "BLOCKED",
            "exit_code": scan_result.returncode,
            "report_sha256": sha256_file(report) if report.is_file() else None,
        }

    git_sha = run_command(
        ["git", "rev-parse", "HEAD"], cwd=root, log_path=output / "git-head.log"
    ).stdout.strip()
    receipt = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_commit": git_sha,
        "source_worktree_clean": subprocess.run(
            ["git", "diff", "--quiet"], cwd=root, check=False
        ).returncode == 0,
        "platform": args.platform,
        "jar_sha256": sha256_file(jar),
        "runtime_apks": [
            {"name": apk.name, "sha256": sha256_file(apk), "byte_count": apk.stat().st_size}
            for apk in runtime_apks
        ],
        "local_image_id": local_inspect.get("Id"),
        "mutable_reference": mutable_reference,
        "immutable_reference": immutable_reference,
        "environment_assignment": (
            f"ELMOS_RUNNER_IMAGE_MODERNIZATION_PROOF={immutable_reference}"
            if immutable_reference else None
        ),
        "runtime_environment": {
            "path": str(runtime_environment) if immutable_reference is not None else None,
            "sha256": sha256_file(runtime_environment) if immutable_reference is not None else None,
            "mode": "0600" if immutable_reference is not None else None,
            "status": "CONFIGURED" if immutable_reference is not None else "NOT_CONFIGURED",
        },
        "image_contract": {
            "status": "PASSED",
            "user": EXPECTED_USER,
            "entrypoint": EXPECTED_ENTRYPOINT,
            "capability": EXPECTED_CAPABILITY,
        },
        "container_smoke": smoke,
        "vulnerability_scan": scan,
        "external_boundaries": {
            "REAL_CLOUD_PROVIDER": "NOT_RUN",
            "SCM_DRAFT_PULL_REQUEST": "NOT_RUN",
            "CUSTOMER_ACCEPTANCE": "NOT_RUN",
            "INDEPENDENT_REVIEW": "NOT_RUN",
            "PRODUCTION_DEPLOYMENT": "NOT_RUN",
            "EXTERNAL_CERTIFICATION": "NOT_RUN",
        },
        "production_ready": False,
        "certified": False,
    }
    receipt_path = output / "image-build-receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "receipt": str(receipt_path),
        "receipt_sha256": sha256_file(receipt_path),
        "immutable_reference": immutable_reference,
        "environment_assignment": receipt["environment_assignment"],
        "scan_status": scan["status"],
        "production_ready": False,
        "certified": False,
    }, indent=2, sort_keys=True))
    return 0 if immutable_reference is not None else 3


if __name__ == "__main__":
    raise SystemExit(main())

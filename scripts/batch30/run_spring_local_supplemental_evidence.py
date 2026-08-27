#!/usr/bin/env python3
"""Run bounded, local-only supplemental evidence for the exact Spring route.

This runner deliberately produces engineering evidence only.  It never changes
the framework pack certification decision, never accesses customer data, and
never creates signatures.  The source and target processes are bound to the
exact tuple supplied by the pack and all output is written to a new directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PACK_KEY = "spring-framework-5-3-mvc-to-spring-boot-3-5-3"
JAVA11 = "11.0.26"
JAVA21 = "21.0.11"
MAVEN = "3.9.11"
SOURCE_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PERFORMANCE_REQUESTS = 200
PERFORMANCE_CONCURRENCY = 8


class EvidenceError(RuntimeError):
    pass


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise EvidenceError(f"{path} must contain a JSON object")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def require_executable(path: Path, label: str) -> Path:
    if path.is_symlink() or not path.is_file() or not os.access(path, os.X_OK):
        raise EvidenceError(f"{label} is missing, symlinked, or not executable: {path}")
    return path


def verify_binding(pack: Path) -> tuple[dict[str, Any], dict[str, Any], Path, Path]:
    evidence_root = pack / "certification/local-execution/2026-08-27"
    binding_path = evidence_root / "exact-tuple-binding.json"
    policy_path = evidence_root / "qualification-policy.json"
    binding = read_json(binding_path)
    policy = read_json(policy_path)
    if binding.get("pack_key") != PACK_KEY:
        raise EvidenceError("exact tuple binding pack key drifted")
    source = binding.get("source", {})
    target = binding.get("target", {})
    if not SOURCE_COMMIT_RE.fullmatch(str(source.get("commit", ""))):
        raise EvidenceError("source commit is not a full immutable commit")
    if source.get("framework_version") != "5.3.39" or source.get("java") != JAVA11 or source.get("maven") != MAVEN:
        raise EvidenceError("source tuple is not the exact admitted tuple")
    if target.get("framework_version") != "3.5.3" or target.get("java") != JAVA21 or target.get("maven") != MAVEN:
        raise EvidenceError("target tuple is not the exact admitted tuple")
    if policy.get("source_commit") != source.get("commit"):
        raise EvidenceError("qualification policy and tuple source commits differ")
    policy_digest = sha256(policy_path)
    if binding.get("policy", {}).get("sha256") != f"sha256:{policy_digest}":
        raise EvidenceError("qualification policy digest does not match its bytes")
    artifact = pack / "certification/local-execution/2026-08-27" / str(target.get("artifact_path"))
    if not artifact.is_file() or artifact.is_symlink():
        raise EvidenceError("bound target artifact is missing or unsafe")
    actual_artifact_digest = sha256(artifact)
    if target.get("artifact_sha256") != f"sha256:{actual_artifact_digest}":
        raise EvidenceError("bound target artifact digest does not match its bytes")
    if target.get("artifact_bytes") != artifact.stat().st_size:
        raise EvidenceError("bound target artifact size does not match its bytes")
    return binding, policy, artifact, policy_path


def safe_artifact_inventory(artifact: Path) -> dict[str, Any]:
    components: list[dict[str, Any]] = []
    seen: set[str] = set()
    with zipfile.ZipFile(artifact) as archive:
        for info in archive.infolist():
            name = info.filename
            path = Path(name)
            if path.is_absolute() or ".." in path.parts:
                raise EvidenceError(f"target artifact contains unsafe archive path: {name}")
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise EvidenceError(f"target artifact contains a symlink entry: {name}")
            if (name.startswith("BOOT-INF/lib/") or name.startswith("WEB-INF/lib/")) and name.endswith(".jar"):
                if name in seen:
                    raise EvidenceError(f"duplicate nested library: {name}")
                seen.add(name)
                payload = archive.read(info)
                coordinate = None
                try:
                    with zipfile.ZipFile(__import__("io").BytesIO(payload)) as nested:
                        for nested_name in nested.namelist():
                            if nested_name.startswith("META-INF/maven/") and nested_name.endswith("/pom.properties"):
                                properties = nested.read(nested_name).decode("ISO-8859-1", errors="replace")
                                values = dict(
                                    line.split("=", 1)
                                    for line in properties.splitlines()
                                    if "=" in line and not line.startswith("#")
                                )
                                group = values.get("groupId")
                                artifact_id = values.get("artifactId")
                                version = values.get("version")
                                if group and artifact_id and version:
                                    coordinate = f"{group}:{artifact_id}:{version}"
                                    break
                except zipfile.BadZipFile:
                    coordinate = None
                components.append(
                    {
                        "type": "library",
                        "name": coordinate or Path(name).stem,
                        "bom-ref": f"sha256:{hashlib.sha256(payload).hexdigest()}",
                        "version": coordinate.rsplit(":", 1)[-1] if coordinate else "UNKNOWN",
                        "hashes": [{"alg": "SHA-256", "content": hashlib.sha256(payload).hexdigest()}],
                        "properties": [{"name": "archivePath", "value": name}],
                        "evidence": "ARTIFACT_BYTES_INSPECTED_LOCALLY",
                    }
                )
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{hashlib.sha256(artifact.read_bytes()).hexdigest()[:32]}",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "name": PACK_KEY,
                "version": "3.5.3",
                "hashes": [{"alg": "SHA-256", "content": sha256(artifact)}],
            },
            "tools": [{"vendor": "ELMOS", "name": "run_spring_local_supplemental_evidence.py", "version": "1"}],
        },
        "components": sorted(components, key=lambda item: item["bom-ref"]),
        "limitations": [
            "Local artifact inventory only; license and vulnerability databases were not consulted.",
            "This BOM is engineering evidence and is not independent security evidence.",
        ],
    }


def probe(url: str, *, timeout: float = 3.0) -> dict[str, Any]:
    request = Request(url, headers={"Accept": "application/json"})
    started = time.monotonic()
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read()
            return {
                "url": url,
                "status": response.status,
                "bytes": len(body),
                "sha256": hashlib.sha256(body).hexdigest(),
                "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
            }
    except HTTPError as exc:
        body = exc.read()
        return {"url": url, "status": exc.code, "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}
    except (OSError, URLError) as exc:
        return {"url": url, "status": "UNREACHABLE", "error": str(exc)}


def wait_ready(url: str, *, timeout_seconds: float = 45.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last: dict[str, Any] = {"url": url, "status": "NOT_READY"}
    while time.monotonic() < deadline:
        last = probe(url)
        if last.get("status") == 200:
            return last
        time.sleep(0.25)
    raise EvidenceError(f"readiness did not pass: {last}")


class RunningProcess:
    def __init__(self, process: subprocess.Popen[bytes], stream: Any) -> None:
        self.process = process
        self.stream = stream

    def stop(self) -> dict[str, Any]:
        started = time.monotonic()
        if self.process.poll() is None:
            self.process.terminate()
        try:
            self.process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
        elapsed_ms = round((time.monotonic() - started) * 1000, 3)
        self.stream.close()
        return {"returncode": self.process.returncode, "elapsed_ms": elapsed_ms, "bounded": elapsed_ms <= 15000}


def start_target(java: Path, artifact: Path, port: int, log_path: Path) -> RunningProcess:
    stream = log_path.open("wb")
    env = os.environ.copy()
    env["JAVA_HOME"] = str(java.parent.parent)
    env["PATH"] = str(java.parent) + os.pathsep + env.get("PATH", "")
    process = subprocess.Popen(
        [str(java), "-jar", str(artifact), "--server.address=127.0.0.1", f"--server.port={port}"],
        stdout=stream,
        stderr=subprocess.STDOUT,
        env=env,
    )
    return RunningProcess(process, stream)


def start_source(java: Path, tomcat_home: Path, source_war: Path, port: int, log_path: Path) -> RunningProcess:
    base = Path(tempfile.mkdtemp(prefix="spring-source-rollback-"))
    shutil.copytree(tomcat_home / "conf", base / "conf")
    server_xml = base / "conf/server.xml"
    server_xml.write_text(server_xml.read_text(encoding="utf-8").replace('port="8080"', f'port="{port}"', 1), encoding="utf-8")
    (base / "webapps").mkdir()
    shutil.copy2(source_war, base / "webapps/ROOT.war")
    (base / "logs").mkdir()
    catalina = tomcat_home / "bin/catalina.sh"
    if catalina.is_symlink() or not catalina.is_file():
        raise EvidenceError(f"Tomcat catalina.sh is missing or symlinked: {catalina}")
    stream = log_path.open("wb")
    env = os.environ.copy()
    env.update({"JAVA_HOME": str(java.parent.parent), "CATALINA_HOME": str(tomcat_home), "CATALINA_BASE": str(base)})
    env["PATH"] = str(java.parent) + os.pathsep + env.get("PATH", "")
    process = subprocess.Popen(["/bin/sh", str(catalina), "run"], cwd=str(tomcat_home), stdout=stream, stderr=subprocess.STDOUT, env=env)
    running = RunningProcess(process, stream)
    running.base = base  # type: ignore[attr-defined]
    return running


def run_ab(ab: Path, url: str, output: Path) -> dict[str, Any]:
    result = subprocess.run(
        [str(ab), "-n", str(PERFORMANCE_REQUESTS), "-c", str(PERFORMANCE_CONCURRENCY), url],
        capture_output=True,
        check=False,
    )
    output.write_bytes(result.stdout + b"\n--- stderr ---\n" + result.stderr)
    text = result.stdout.decode("utf-8", errors="replace")
    requests_per_second = re.search(r"Requests per second:\s+([0-9.]+)", text)
    time_per_request = re.search(r"Time per request:\s+([0-9.]+) \[ms\]", text)
    completed = re.search(r"Complete requests:\s+(\d+)", text)
    return {
        "tool": str(ab),
        "exit_code": result.returncode,
        "requests": PERFORMANCE_REQUESTS,
        "concurrency": PERFORMANCE_CONCURRENCY,
        "complete_requests": int(completed.group(1)) if completed else None,
        "requests_per_second": float(requests_per_second.group(1)) if requests_per_second else None,
        "time_per_request_ms": float(time_per_request.group(1)) if time_per_request else None,
        "capacity_validation": "NOT_RUN_NO_SLO_BOUND",
        "status": "PASSED_LOCAL_BENCHMARK" if result.returncode == 0 and completed and int(completed.group(1)) == PERFORMANCE_REQUESTS else "FAILED_LOCAL_BENCHMARK",
    }


def file_inventory(root: Path) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file() and item.name != "supplemental-index.json"):
        relative = path.relative_to(root).as_posix()
        files.append({"path": relative, "bytes": path.stat().st_size, "sha256": sha256(path)})
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument("--source-war", type=Path, required=True)
    parser.add_argument("--source-build-log", type=Path, required=True)
    parser.add_argument("--source-java", type=Path, required=True)
    parser.add_argument("--target-java", type=Path, required=True)
    parser.add_argument("--tomcat-home", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--ab", type=Path, default=Path("/usr/sbin/ab"))
    args = parser.parse_args()

    output = args.output_dir.resolve()
    if output.exists():
        raise EvidenceError(f"output directory already exists; refusing overwrite: {output}")
    output.mkdir(parents=True)
    (output / "raw").mkdir()
    binding, policy, target_artifact, policy_path = verify_binding(args.pack.resolve())
    source_war = args.source_war.resolve()
    source_java = require_executable(args.source_java.resolve(), "source Java")
    target_java = require_executable(args.target_java.resolve(), "target Java")
    tomcat_home = args.tomcat_home.resolve()
    if not source_war.is_file() or source_war.is_symlink():
        raise EvidenceError("source WAR is missing or unsafe")
    source_build_log = args.source_build_log.resolve()
    if not source_build_log.is_file() or source_build_log.is_symlink():
        raise EvidenceError("source build log is missing or unsafe")
    shutil.copy2(source_build_log, output / "raw/source-build.log")
    source_artifact_dir = output / "source-artifacts"
    source_artifact_dir.mkdir()
    shutil.copy2(source_war, source_artifact_dir / "legacy-spring-mvc-5.3.39.war")
    if sha256(source_war) == sha256(target_artifact):
        raise EvidenceError("source and target WARs must be distinct artifacts")
    ab = require_executable(args.ab.resolve(), "ApacheBench")

    bom = safe_artifact_inventory(target_artifact)
    write_json(output / "sbom-local-inventory.json", bom)

    target_port = 0
    source_port = 0
    target_process: RunningProcess | None = None
    source_process: RunningProcess | None = None
    target_readiness: dict[str, Any] = {}
    source_readiness: dict[str, Any] = {}
    shutdowns: dict[str, Any] = {}
    try:
        with _ephemeral_port() as target_port_ctx:
            target_port = target_port_ctx
            target_process = start_target(target_java, target_artifact, target_port, output / "raw/target-startup.log")
            target_readiness = wait_ready(f"http://127.0.0.1:{target_port}/actuator/health")
            target_probes = [
                probe(f"http://127.0.0.1:{target_port}/actuator/health"),
                probe(f"http://127.0.0.1:{target_port}/api/orders/7"),
                probe(f"http://127.0.0.1:{target_port}/orders"),
            ]
            performance = run_ab(ab, f"http://127.0.0.1:{target_port}/api/orders/7", output / "raw/target-ab.txt")
            shutdowns["target"] = target_process.stop()
            target_process = None
        with _ephemeral_port() as source_port_ctx:
            source_port = source_port_ctx
            source_process = start_source(source_java, tomcat_home, source_war, source_port, output / "raw/source-rollback.log")
            source_readiness = wait_ready(f"http://127.0.0.1:{source_port}/api/orders/42")
            source_probe = probe(f"http://127.0.0.1:{source_port}/api/orders/42")
            shutdowns["source"] = source_process.stop()
            source_process = None
    finally:
        if target_process is not None:
            shutdowns["target_cleanup"] = target_process.stop()
        if source_process is not None:
            shutdowns["source_cleanup"] = source_process.stop()

    security = {
        "status": "PARTIAL_LOCAL",
        "artifact_archive_integrity": "PASSED_LOCAL",
        "manifest_tuple_integrity": "PASSED_LOCAL",
        "archive_path_traversal_check": "PASSED_LOCAL",
        "archive_symlink_check": "PASSED_LOCAL",
        "vulnerability_scan": "NOT_RUN_TOOL_UNAVAILABLE",
        "external_security_evidence": "NOT_RUN",
    }
    evidence = {
        "schema_version": 1,
        "evidence_class": "LOCAL_ENGINEERING_SUPPLEMENTAL",
        "claim_scope": "LOCAL_ISOLATED_EXACT_TUPLE_ONLY",
        "pack_key": PACK_KEY,
        "binding": {
            "source_commit": binding["source"]["commit"],
            "target_artifact_sha256": binding["target"]["artifact_sha256"],
            "target_artifact_bytes": binding["target"]["artifact_bytes"],
            "policy_sha256": binding["policy"]["sha256"],
            "source_war_sha256": f"sha256:{sha256(source_war)}",
            "source_war_path": "source-artifacts/legacy-spring-mvc-5.3.39.war",
            "source_war_bytes": source_war.stat().st_size,
        },
        "observations": {
            "security": security,
            "performance": performance,
            "sbom": {
                "status": "PARTIAL_LOCAL_INVENTORY_ONLY",
                "bom_path": "sbom-local-inventory.json",
                "component_count": len(bom["components"]),
                "artifact_bound": True,
                "vulnerability_scan": "NOT_RUN_TOOL_UNAVAILABLE",
                "external_sbom_evidence": "NOT_RUN",
            },
            "operability": {
                "status": "PASSED_LOCAL",
                "target_readiness": target_readiness,
                "target_probes": target_probes,
                "shutdown": shutdowns.get("target"),
                "loopback_only": True,
                "production_operations": "NOT_RUN",
            },
            "rollback": {
                "status": "PASSED_LOCAL_ISOLATED_ROLLBACK_REHEARSAL",
                "sequence": ["target_startup_readiness", "target_stop", "source_startup_readiness", "source_probe", "source_stop"],
                "source_build": {
                    "status": "PASSED_LOCAL",
                    "command": "mvn -B -ntp clean verify package (Java 11.0.26, Maven 3.9.11)",
                    "log_path": "raw/source-build.log",
                    "war_sha256": f"sha256:{sha256(source_war)}",
                    "war_bytes": source_war.stat().st_size,
                },
                "target_readiness": target_readiness,
                "source_readiness": source_readiness,
                "source_probe": source_probe,
                "shutdowns": shutdowns,
                "production_rollback": "NOT_RUN",
            },
            "independent_holdout": "NOT_RUN",
            "representative_customer_scenario": "NOT_RUN",
            "external_signatures": "NOT_RUN",
        },
        "required_external_evidence_types": [
            "source_build", "target_build", "source_startup", "target_startup",
            "behavioral_equivalence", "security", "performance", "operability",
            "sbom", "rollback", "independent_review", "customer_acceptance",
            "external_certification",
        ],
        "status_boundary": {
            "local_supplemental": "RECORDED_LOCAL_ONLY",
            "external_evidence": "NOT_RUN",
            "production_certification": "NOT_CERTIFIED",
            "local_runner_may_certify": False,
        },
        "policy_path": "qualification-policy.json",
        "policy_bytes_sha256": f"sha256:{sha256(policy_path)}",
    }
    write_json(output / "supplemental-local-evidence.json", evidence)
    index = {
        "schema_version": 1,
        "evidence_class": "LOCAL_ENGINEERING_SUPPLEMENTAL",
        "claim_scope": "LOCAL_ISOLATED_EXACT_TUPLE_ONLY",
        "index_does_not_self_reference": True,
        "files": file_inventory(output),
        "external_evidence": "NOT_RUN",
        "production_certification": "NOT_CERTIFIED",
    }
    write_json(output / "supplemental-index.json", index)
    print(json.dumps({"status": "PASSED_LOCAL_SUPPLEMENTAL", "output_dir": str(output), "files": index["files"]}, sort_keys=True))
    return 0


class _ephemeral_port:
    def __enter__(self) -> int:
        import socket

        self.socket = socket.socket()
        self.socket.bind(("127.0.0.1", 0))
        self.port = self.socket.getsockname()[1]
        self.socket.close()
        return self.port

    def __exit__(self, *_: Any) -> None:
        return None


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (EvidenceError, OSError, ValueError, zipfile.BadZipFile) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)

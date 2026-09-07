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
import uuid
import zipfile
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PACK_KEY = "spring-framework-5-3-mvc-to-spring-boot-3-5-3"
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.precision_migration.trust import read_regular_file_once  # noqa: E402

JAVA11 = "11.0.26"
JAVA21 = "21.0.11"
MAVEN = "3.9.11"
SOURCE_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SOURCE_GIT_TREE_SHA = "4e1a0354cb51cfb2479ea049063226d3a9df2b67"
PERFORMANCE_REQUESTS = 200
PERFORMANCE_CONCURRENCY = 8
MAX_JSON_BYTES = 8 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 10_000
MAX_ARCHIVE_ENTRY_BYTES = 256 * 1024 * 1024
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 1024 * 1024 * 1024
MAX_ARCHIVE_COMPRESSION_RATIO = 200
MAX_NESTED_COMPONENT_BYTES = 64 * 1024 * 1024
MAX_TOTAL_COMPONENT_BYTES = 512 * 1024 * 1024
MAX_POM_PROPERTIES_BYTES = 1024 * 1024


class EvidenceError(RuntimeError):
    pass


def read_json(path: Path) -> dict[str, Any]:
    try:
        raw = read_regular_file_once(path, max_bytes=MAX_JSON_BYTES, label=str(path))
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise EvidenceError(f"{path} is not bounded regular UTF-8 JSON: {exc}") from exc
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
    if path.exists() or path.is_symlink():
        raise EvidenceError(f"refusing to overwrite evidence JSON: {path}")
    raw = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def require_executable(path: Path, label: str) -> Path:
    if path.is_symlink() or not path.is_file() or not os.access(path, os.X_OK):
        raise EvidenceError(f"{label} is missing, symlinked, or not executable: {path}")
    return path


def resolve_input(path: Path, label: str, *, directory: bool = False) -> Path:
    supplied = path.expanduser()
    lexical = Path(os.path.abspath(supplied))
    current = Path(lexical.anchor)
    for part in lexical.parts[1:]:
        current /= part
        if current.is_symlink():
            raise EvidenceError(f"{label} path must not traverse a symlink: {current}")
    try:
        resolved = lexical.resolve(strict=True)
    except OSError as exc:
        raise EvidenceError(f"{label} does not exist: {supplied}") from exc
    if directory and not resolved.is_dir():
        raise EvidenceError(f"{label} must be a directory: {resolved}")
    if not directory and not resolved.is_file():
        raise EvidenceError(f"{label} must be a regular file: {resolved}")
    return resolved


def prepare_output_directory(path: Path) -> Path:
    supplied = path.expanduser()
    lexical = Path(os.path.abspath(supplied))
    if lexical.exists() or lexical.is_symlink():
        raise EvidenceError(
            f"output directory already exists; refusing overwrite: {lexical}"
        )
    parent = lexical.parent
    if not parent.is_dir() or parent.is_symlink():
        raise EvidenceError("output parent must be an existing real directory")
    current = Path(lexical.anchor)
    for part in parent.parts[1:]:
        current /= part
        if current.is_symlink():
            raise EvidenceError(
                f"output parent path must not traverse a symlink: {current}"
            )
    lexical.mkdir(mode=0o700)
    if lexical.is_symlink() or not lexical.is_dir():
        raise EvidenceError("output directory creation did not produce a real directory")
    return lexical


def verify_binding(
    pack: Path,
    evidence_root: Path,
) -> tuple[dict[str, Any], dict[str, Any], Path, Path, Path, dict[str, dict[str, Any]]]:
    if pack.is_symlink() or not pack.is_dir():
        raise EvidenceError("pack must be a real directory")
    if evidence_root.is_symlink() or not evidence_root.is_dir():
        raise EvidenceError("qualification directory must be a real directory")
    binding_path = evidence_root / "exact-tuple-binding.json"
    policy_path = evidence_root / "qualification-policy.json"
    binding = read_json(binding_path)
    policy = read_json(policy_path)
    receipt = read_json(evidence_root / "local-qualification.json")
    index = read_json(evidence_root / "evidence-index.json")
    if binding.get("pack_key") != PACK_KEY:
        raise EvidenceError("exact tuple binding pack key drifted")
    source = binding.get("source", {})
    target = binding.get("target", {})
    if not SOURCE_COMMIT_RE.fullmatch(str(source.get("commit", ""))):
        raise EvidenceError("source commit is not a full immutable commit")
    if (
        source.get("git_tree_sha") != SOURCE_GIT_TREE_SHA
        or receipt.get("source_git_tree_sha") != SOURCE_GIT_TREE_SHA
    ):
        raise EvidenceError("source Git tree is not the pinned exact corpus tree")
    expected_source = {
        "framework": "spring-framework-mvc",
        "framework_version": "5.3.39",
        "java": JAVA11,
        "maven": MAVEN,
        "servlet_namespace": "javax.servlet",
        "servlet_api": "4.0.1",
        "packaging": "war",
        "artifact_format": "spring-framework-mvc-war",
    }
    if any(source.get(name) != expected for name, expected in expected_source.items()):
        raise EvidenceError("source tuple is not the exact admitted tuple")
    expected_target = {
        "framework": "spring-boot",
        "framework_version": "3.5.3",
        "spring_framework_version": "6.2.8",
        "java": JAVA21,
        "maven": MAVEN,
        "servlet_namespace": "jakarta.servlet",
        "servlet_api": "6.1",
        "embedded_tomcat": "10.1.42",
        "packaging": "executable-war",
        "artifact_format": "spring-boot-executable-war",
    }
    if any(target.get(name) != expected for name, expected in expected_target.items()):
        raise EvidenceError("target tuple is not the exact admitted tuple")
    if policy.get("source_commit") != source.get("commit"):
        raise EvidenceError("qualification policy and tuple source commits differ")
    policy_digest = sha256(policy_path)
    if binding.get("policy", {}).get("sha256") != f"sha256:{policy_digest}":
        raise EvidenceError("qualification policy digest does not match its bytes")
    if binding.get("status_boundary") != {
        "local_execution": "PASSED_LOCAL",
        "external_evidence": "NOT_RUN",
        "production_certification": "NOT_CERTIFIED",
        "maximum_local_decision": "READY_FOR_EXTERNAL_GATE_REVIEW",
        "local_runner_may_certify": False,
    }:
        raise EvidenceError("exact tuple status boundary is not fail-closed")
    if policy.get("toolchain_bindings") != {
        "source-java": "sha256:09d5fffa5ad3de15dcfd603e747df1e6c9ecdb58f25d333e89661910064e884a",
        "source-maven": "sha256:0d7125e8c91097b36edb990ea5934e6c68b4440eef4ea96510a0f6815e7eeadb",
        "source-container": "sha256:93306f86baafe13186cc3e705c201040d68b0192a50be667a1f576ee4711db0d",
        "target-java": "sha256:7befd86565133fbebfa54138e55ec5b03bb59649ea5dda35d9f9b95265226756",
        "target-maven": "sha256:0d7125e8c91097b36edb990ea5934e6c68b4440eef4ea96510a0f6815e7eeadb",
        "target-container": "sha256:c0ca6acafe5ad63cd5de16ec8894318a7b53ea11e3db1bc217fd5f2a9746a790",
    }:
        raise EvidenceError("qualification policy toolchain identities drifted")
    if receipt.get("pack_key") != PACK_KEY or receipt.get("status") != "PASSED_LOCAL":
        raise EvidenceError("qualification receipt identity or status drifted")
    if (
        index.get("pack_key") != PACK_KEY
        or index.get("status") != "PASSED_LOCAL"
        or index.get("certification_eligible") is not False
        or index.get("external_execution_status") != "NOT_RUN"
    ):
        raise EvidenceError("qualification evidence index boundary drifted")
    artifact_relative = Path(str(target.get("artifact_path")))
    if artifact_relative.is_absolute() or ".." in artifact_relative.parts:
        raise EvidenceError("bound target artifact path is unsafe")
    artifact = evidence_root / artifact_relative
    if not artifact.is_file() or artifact.is_symlink():
        raise EvidenceError("bound target artifact is missing or unsafe")
    actual_artifact_digest = sha256(artifact)
    if target.get("artifact_sha256") != f"sha256:{actual_artifact_digest}":
        raise EvidenceError("bound target artifact digest does not match its bytes")
    if target.get("artifact_bytes") != artifact.stat().st_size:
        raise EvidenceError("bound target artifact size does not match its bytes")
    source_receipt = receipt.get("source", {}).get("executed_war", {})
    source_relative = Path(str(source_receipt.get("path")))
    if source_relative.is_absolute() or ".." in source_relative.parts:
        raise EvidenceError("bound source WAR path is unsafe")
    source_artifact = evidence_root / source_relative
    if source_artifact.is_symlink() or not source_artifact.is_file():
        raise EvidenceError("bound source WAR is missing or unsafe")
    if (
        source_receipt.get("format") != "spring-framework-mvc-war"
        or source_receipt.get("sha256") != sha256(source_artifact)
        or source_receipt.get("bytes") != source_artifact.stat().st_size
        or source.get("artifact_path") != source_receipt.get("path")
        or source.get("artifact_sha256") != f"sha256:{source_receipt.get('sha256')}"
        or source.get("artifact_bytes") != source_receipt.get("bytes")
    ):
        raise EvidenceError("source WAR does not match the exact tuple and qualification receipt")
    indexed = {
        item.get("path"): item
        for item in index.get("files", [])
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    }
    for candidate, label in ((artifact, "target artifact"), (source_artifact, "source WAR")):
        relative = candidate.relative_to(evidence_root).as_posix()
        record = indexed.get(relative)
        if record != {"path": relative, "bytes": candidate.stat().st_size, "sha256": sha256(candidate)}:
            raise EvidenceError(f"{label} is not identically bound by the qualification index")
    return binding, policy, artifact, source_artifact, policy_path, indexed


def safe_artifact_inventory(artifact: Path) -> dict[str, Any]:
    components: list[dict[str, Any]] = []
    seen: set[str] = set()
    seen_component_digests: set[str] = set()
    total_component_bytes = 0
    with zipfile.ZipFile(artifact) as archive:
        entries = archive.infolist()
        if len(entries) > MAX_ARCHIVE_ENTRIES:
            raise EvidenceError("target artifact exceeds the bounded archive entry budget")
        archive_names: set[str] = set()
        total_uncompressed = 0
        for info in entries:
            name = info.filename
            path = Path(name)
            if (
                not name
                or "\\" in name
                or "\x00" in name
                or path.is_absolute()
                or ".." in path.parts
            ):
                raise EvidenceError(f"target artifact contains unsafe archive path: {name}")
            if name in archive_names:
                raise EvidenceError(f"target artifact contains a duplicate entry: {name}")
            archive_names.add(name)
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise EvidenceError(f"target artifact contains a symlink entry: {name}")
            if info.flag_bits & 0x1:
                raise EvidenceError(f"target artifact contains an encrypted entry: {name}")
            if info.file_size < 0 or info.file_size > MAX_ARCHIVE_ENTRY_BYTES:
                raise EvidenceError(f"target artifact entry exceeds the byte budget: {name}")
            total_uncompressed += info.file_size
            if total_uncompressed > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
                raise EvidenceError("target artifact exceeds the uncompressed byte budget")
            if info.file_size and (
                info.compress_size <= 0
                or info.file_size > info.compress_size * MAX_ARCHIVE_COMPRESSION_RATIO
            ):
                raise EvidenceError(f"target artifact entry exceeds the compression-ratio budget: {name}")
        corrupt = archive.testzip()
        if corrupt is not None:
            raise EvidenceError(f"target artifact CRC verification failed: {corrupt}")
        for info in entries:
            name = info.filename
            if (
                name.startswith(("BOOT-INF/lib/", "WEB-INF/lib/", "WEB-INF/lib-provided/"))
                and name.endswith(".jar")
            ):
                if name in seen:
                    raise EvidenceError(f"duplicate nested library: {name}")
                if info.file_size <= 0 or info.file_size > MAX_NESTED_COMPONENT_BYTES:
                    raise EvidenceError(f"nested library exceeds the bounded component size: {name}")
                total_component_bytes += info.file_size
                if total_component_bytes > MAX_TOTAL_COMPONENT_BYTES:
                    raise EvidenceError("target artifact exceeds the total nested component byte budget")
                seen.add(name)
                payload = archive.read(info)
                coordinate = None
                try:
                    with zipfile.ZipFile(__import__("io").BytesIO(payload)) as nested:
                        nested_entries = nested.infolist()
                        if len(nested_entries) > MAX_ARCHIVE_ENTRIES:
                            raise EvidenceError(f"nested library exceeds the entry budget: {name}")
                        coordinates: set[str] = set()
                        nested_names: set[str] = set()
                        for nested_info in nested_entries:
                            nested_name = nested_info.filename
                            nested_path = Path(nested_name)
                            if (
                                not nested_name
                                or "\\" in nested_name
                                or "\x00" in nested_name
                                or nested_path.is_absolute()
                                or ".." in nested_path.parts
                            ):
                                raise EvidenceError(
                                    f"nested library contains an unsafe path: {name}!/{nested_name}"
                                )
                            if nested_name in nested_names:
                                raise EvidenceError(
                                    f"nested library contains a duplicate entry: {name}!/{nested_name}"
                                )
                            nested_names.add(nested_name)
                            if stat.S_ISLNK(nested_info.external_attr >> 16):
                                raise EvidenceError(
                                    f"nested library contains a symlink entry: {name}!/{nested_name}"
                                )
                            if nested_info.flag_bits & 0x1:
                                raise EvidenceError(
                                    f"nested library contains an encrypted entry: {name}!/{nested_name}"
                                )
                            if nested_name.startswith("META-INF/maven/") and nested_name.endswith("/pom.properties"):
                                if (
                                    nested_info.file_size <= 0
                                    or nested_info.file_size > MAX_POM_PROPERTIES_BYTES
                                ):
                                    raise EvidenceError(
                                        f"nested Maven metadata exceeds the byte budget: {name}!/{nested_name}"
                                    )
                                properties = nested.read(nested_info).decode("ISO-8859-1", errors="replace")
                                values = dict(
                                    line.split("=", 1)
                                    for line in properties.splitlines()
                                    if "=" in line and not line.startswith("#")
                                )
                                group = values.get("groupId")
                                artifact_id = values.get("artifactId")
                                version = values.get("version")
                                if all(
                                    isinstance(value, str)
                                    and re.fullmatch(r"[A-Za-z0-9_.+\-]{1,200}", value)
                                    for value in (group, artifact_id, version)
                                ):
                                    coordinates.add(f"{group}:{artifact_id}:{version}")
                        if len(coordinates) > 1:
                            raise EvidenceError(
                                f"nested library has conflicting Maven coordinates: {name}"
                            )
                        if coordinates:
                            coordinate = next(iter(coordinates))
                except zipfile.BadZipFile:
                    coordinate = None
                component_digest = hashlib.sha256(payload).hexdigest()
                if component_digest in seen_component_digests:
                    raise EvidenceError(
                        f"target artifact contains duplicate nested component bytes: {name}"
                    )
                seen_component_digests.add(component_digest)
                components.append(
                    {
                        "type": "library",
                        "name": coordinate or Path(name).stem,
                        "bom-ref": f"sha256:{component_digest}",
                        "version": coordinate.rsplit(":", 1)[-1] if coordinate else "UNKNOWN",
                        "hashes": [{"alg": "SHA-256", "content": component_digest}],
                        "properties": [{"name": "archivePath", "value": name}],
                        "evidence": "ARTIFACT_BYTES_INSPECTED_LOCALLY",
                    }
                )
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{uuid.UUID(sha256(artifact)[:32])}",
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
    def __init__(
        self,
        process: subprocess.Popen[bytes],
        stream: Any,
        cleanup: tempfile.TemporaryDirectory[str] | None = None,
    ) -> None:
        self.process = process
        self.stream = stream
        self.cleanup = cleanup

    def stop(self) -> dict[str, Any]:
        started = time.monotonic()
        forced = False
        if self.process.poll() is None:
            self.process.terminate()
        try:
            self.process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            forced = True
            self.process.kill()
            self.process.wait(timeout=5)
        elapsed_ms = round((time.monotonic() - started) * 1000, 3)
        self.stream.close()
        if self.cleanup is not None:
            self.cleanup.cleanup()
            self.cleanup = None
        return {
            "returncode": self.process.returncode,
            "elapsed_ms": elapsed_ms,
            "bounded": elapsed_ms <= 20_000,
            "forced": forced,
        }


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
    temporary = tempfile.TemporaryDirectory(prefix="spring-source-rollback-")
    base = Path(temporary.name)
    stream: Any | None = None
    try:
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
        return RunningProcess(process, stream, temporary)
    except Exception:
        if stream is not None:
            stream.close()
        temporary.cleanup()
        raise


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
    candidates = sorted(root.rglob("*"))
    if len(candidates) > MAX_ARCHIVE_ENTRIES:
        raise EvidenceError("supplemental output exceeds the file inventory budget")
    for path in candidates:
        if path.is_symlink():
            raise EvidenceError(f"supplemental output contains a symlink: {path}")
        if not path.is_file() or path.name == "supplemental-index.json":
            continue
        relative = path.relative_to(root).as_posix()
        files.append({"path": relative, "bytes": path.stat().st_size, "sha256": sha256(path)})
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument("--qualification-dir", type=Path, required=True)
    parser.add_argument("--source-war", type=Path, required=True)
    parser.add_argument("--source-build-log", type=Path, required=True)
    parser.add_argument("--source-java", type=Path, required=True)
    parser.add_argument("--target-java", type=Path, required=True)
    parser.add_argument("--tomcat-home", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--ab", type=Path, default=Path("/usr/sbin/ab"))
    args = parser.parse_args()

    pack = resolve_input(args.pack, "pack", directory=True)
    qualification = resolve_input(
        args.qualification_dir, "qualification directory", directory=True
    )
    binding, policy, target_artifact, bound_source_war, policy_path, indexed = verify_binding(
        pack,
        qualification,
    )
    source_war = resolve_input(args.source_war, "source WAR")
    if source_war != bound_source_war.resolve(strict=True):
        raise EvidenceError("source WAR must be the exact artifact bound by the qualification receipt")
    source_java = require_executable(
        resolve_input(args.source_java, "source Java"), "source Java"
    )
    target_java = require_executable(
        resolve_input(args.target_java, "target Java"), "target Java"
    )
    tomcat_home = resolve_input(args.tomcat_home, "Tomcat home", directory=True)
    source_build_log = resolve_input(args.source_build_log, "source build log")
    try:
        source_build_relative = source_build_log.relative_to(qualification).as_posix()
    except ValueError as exc:
        raise EvidenceError("source build log must be below the qualification directory") from exc
    if indexed.get(source_build_relative) != {
        "path": source_build_relative,
        "bytes": source_build_log.stat().st_size,
        "sha256": sha256(source_build_log),
    }:
        raise EvidenceError("source build log is not identically bound by the qualification index")
    ab = require_executable(resolve_input(args.ab, "ApacheBench"), "ApacheBench")
    output = prepare_output_directory(args.output_dir)
    (output / "raw").mkdir()
    shutil.copy2(source_build_log, output / "raw/source-build.log")
    source_artifact_dir = output / "source-artifacts"
    source_artifact_dir.mkdir()
    shutil.copy2(source_war, source_artifact_dir / "legacy-spring-mvc-5.3.39.war")
    if sha256(source_war) == sha256(target_artifact):
        raise EvidenceError("source and target WARs must be distinct artifacts")
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
            if any(item.get("status") != 200 for item in target_probes):
                raise EvidenceError(f"target operability probe failed: {target_probes}")
            performance = run_ab(ab, f"http://127.0.0.1:{target_port}/api/orders/7", output / "raw/target-ab.txt")
            if performance["status"] != "PASSED_LOCAL_BENCHMARK":
                raise EvidenceError(f"local performance benchmark failed: {performance}")
            shutdowns["target"] = target_process.stop()
            target_process = None
            if not shutdowns["target"]["bounded"] or shutdowns["target"]["forced"]:
                raise EvidenceError(f"target shutdown was not bounded and graceful: {shutdowns['target']}")
        with _ephemeral_port() as source_port_ctx:
            source_port = source_port_ctx
            source_process = start_source(source_java, tomcat_home, source_war, source_port, output / "raw/source-rollback.log")
            source_readiness = wait_ready(f"http://127.0.0.1:{source_port}/api/orders/42")
            source_probe = probe(f"http://127.0.0.1:{source_port}/api/orders/42")
            if source_probe.get("status") != 200:
                raise EvidenceError(f"source rollback probe failed: {source_probe}")
            shutdowns["source"] = source_process.stop()
            source_process = None
            if not shutdowns["source"]["bounded"] or shutdowns["source"]["forced"]:
                raise EvidenceError(f"source shutdown was not bounded and graceful: {shutdowns['source']}")
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

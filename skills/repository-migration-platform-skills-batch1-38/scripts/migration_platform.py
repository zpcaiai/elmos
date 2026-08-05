#!/usr/bin/env python3
"""Executable, fail-closed runtime for the Batch 1-38 Skill package.

The runtime performs repository discovery, creates content-addressed engineering
artifacts, records independently verifiable evidence, evaluates dependency-aware
local gates, and prepares external certification requests.  It deliberately does
not claim production execution or certification from static/local observations.
"""

from __future__ import annotations

import argparse
import fcntl
import fnmatch
import hashlib
import json
import os
import re
import signal
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


SCRIPT_DIRECTORY = Path(__file__).resolve().parent
PACKAGE_ROOT = SCRIPT_DIRECTORY if (SCRIPT_DIRECTORY / "manifest.json").is_file() else SCRIPT_DIRECTORY.parent
if str(SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIRECTORY))

from transaction_store import StoreConflict, TransactionStore
from actor_trust import ActorTrustStore
from oracle_registry import OracleRegistry

MANIFEST_PATH = PACKAGE_ROOT / "manifest.json"
TRUST_POLICY_PATH = PACKAGE_ROOT / "trust-policy.json"
RUNTIME_VERSION = "2.0.0"
MAX_SOURCE_FILES = 100_000
MAX_CAPTURE_BYTES = 2_000_000
FINAL_DECISIONS = {"LOCAL_TOOLKIT_PASS", "CERTIFIED"}
EVIDENCE_OUTCOMES = {"PASS", "FAIL", "INCONCLUSIVE", "BLOCKED", "NOT_RUN"}
VERIFICATION_OUTCOMES = {"PASS", "FAIL", "INCONCLUSIVE"}

LANGUAGES: dict[str, tuple[str, ...]] = {
    "csharp": (".cs",),
    "cpp": (".c", ".cc", ".cpp", ".cxx", ".h", ".hpp"),
    "go": (".go",),
    "java": (".java",),
    "javascript": (".js", ".jsx", ".mjs", ".cjs"),
    "kotlin": (".kt", ".kts"),
    "php": (".php",),
    "python": (".py",),
    "rust": (".rs",),
    "typescript": (".ts", ".tsx", ".mts", ".cts"),
}

CATEGORY_PATTERNS: dict[str, tuple[str, ...]] = {
    "admin": ("*admin*", "*control-plane*", "*console*", "*backoffice*"),
    "api": ("*openapi*", "*swagger*", "*.proto", "*graphql*", "*controller*", "*route*"),
    "architecture": ("*adr*", "*architecture*", "*design*", "*blueprint*"),
    "auth": ("*auth*", "*identity*", "*permission*", "*policy*", "*rbac*", "*oidc*", "*oauth*"),
    "build": ("pom.xml", "build.gradle*", "package.json", "pyproject.toml", "requirements*.txt", "go.mod", "cargo.toml", "*.sln", "*.csproj", "makefile"),
    "ci": (".github/workflows/*", ".gitlab-ci.yml", "jenkinsfile", "azure-pipelines.yml", "circle.yml"),
    "config": ("*.yaml", "*.yml", "*.toml", "*.properties", "*.ini", "*.conf", ".env.example"),
    "data": ("*migration*", "*.sql", "*schema*", "*database*", "*repository*", "*dao*", "*redis*", "*kafka*", "*outbox*", "*inbox*"),
    "deployment": ("dockerfile*", "docker-compose*", "compose*.yml", "compose*.yaml", "*kubernetes*", "*helm*", "*terraform*", "*.tf", "*deploy*"),
    "docs": ("*.md", "docs/*", "runbook*"),
    "formal": ("*.lean", "*.smt2", "*.tla", "*.alloy", "*proof*", "*invariant*"),
    "frontend": ("*.tsx", "*.jsx", "*.vue", "*.svelte", "*.html", "*page.*", "*screen*"),
    "observability": ("*metric*", "*telemetry*", "*prometheus*", "*grafana*", "*alert*", "*trace*"),
    "operations": ("*runbook*", "*incident*", "*oncall*", "*support*", "*backup*", "*restore*", "*slo*"),
    "performance": ("*benchmark*", "*load-test*", "*performance*", "*stress*", "*soak*", "*jmeter*", "*k6*"),
    "provider": ("*provider*", "*adapter*", "*webhook*", "*payment*", "*email*", "*sms*", "*connector*"),
    "security": ("*security*", "*threat*", "*secret*", "*crypto*", "*audit*", "*sast*", "*sbom*"),
    "skill": ("*/skill.md", "*skill*manifest*", "*agent-skills*", "*.agents/skills/*"),
    "test": ("*test*", "*spec*", "*fixture*", "*golden*", "*fuzz*", "*mutation*"),
    "workflow": ("*workflow*", "*saga*", "*job*", "*worker*", "*queue*", "*scheduler*"),
}

BATCH_CATEGORIES: dict[int, tuple[str, ...]] = {
    1: ("build", "config", "deployment", "docs"),
    2: ("build", "test", "config", "provider"),
    3: ("build",),
    4: ("build", "test"),
    5: ("build", "auth", "data", "workflow"),
    6: ("build", "security", "deployment"),
    7: ("data", "provider"),
    8: ("api", "auth", "deployment"),
    9: ("workflow", "test"),
    10: ("test", "ci"),
    11: ("api", "frontend", "data", "test"),
    12: ("deployment", "provider", "operations"),
    13: ("ci", "security", "test"),
    14: ("formal", "test"),
    15: ("test", "formal", "workflow"),
    16: ("architecture", "build", "deployment"),
    17: ("workflow", "operations", "ci"),
    18: ("build", "config", "ci", "deployment", "docs", "operations", "test"),
    19: ("build", "test", "ci"),
    20: ("skill", "security", "ci"),
    21: ("api", "frontend", "data", "admin", "test", "operations"),
    22: ("api", "data", "workflow", "admin", "test"),
    23: ("api", "workflow", "provider", "test"),
    24: ("data", "api", "provider"),
    25: ("data", "test", "operations"),
    26: ("admin", "frontend", "auth", "operations"),
    27: ("auth", "security", "admin"),
    28: ("frontend", "api", "admin", "operations", "docs"),
    29: ("test", "ci", "architecture"),
    30: ("deployment", "operations", "test"),
    31: ("data", "workflow", "test", "formal"),
    32: ("performance", "observability", "deployment"),
    33: ("security", "data", "deployment", "auth"),
    34: ("provider", "api", "operations", "test"),
    35: ("ci", "deployment", "operations", "security", "test"),
    36: ("operations", "observability", "docs"),
    37: ("operations", "data", "provider", "deployment"),
    38: ("operations", "security", "performance", "test", "data", "admin"),
}

EXTERNAL_EVIDENCE: dict[int, tuple[str, ...]] = {
    2: ("independent clean-environment replay",),
    4: ("real source and target toolchain execution for each claimed route",),
    7: ("real source and target database/messaging reconciliation",),
    11: ("representative domain journey execution",),
    12: ("authorized shadow/canary/rollback exercise",),
    13: ("independent verifier and certificate-authority review",),
    14: ("kernel-checked proof bound to exact artifacts",),
    19: ("real toolchain execution over independent route corpora",),
    30: ("authorized restore/failover/DR exercise",),
    32: ("representative production-equivalent workload evidence",),
    33: ("independent security assessment",),
    34: ("real provider sandbox or authorized endpoint evidence",),
    35: ("accountable production go/no-go approval",),
    36: ("real operational period, incident and support evidence",),
    37: ("authorized source retirement and final reconciliation evidence",),
    38: ("independent final assurance review and external CA decision",),
}

REDACTION_PATTERNS = (
    re.compile(r"(?i)(password|api[_-]?key|secret|token)\s*[:=]\s*([^\s,;]+)"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----.*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.S),
)


class RuntimeFailure(Exception):
    """A fail-closed, user-correctable runtime error."""


def utc_now() -> str:
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if epoch:
        return datetime.fromtimestamp(int(epoch), tz=timezone.utc).isoformat().replace("+00:00", "Z")
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeFailure(f"cannot read JSON object {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeFailure(f"{path} must contain a JSON object")
    return payload


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    os.replace(temporary, path)
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def write_json(path: Path, payload: Any) -> None:
    atomic_write(path, json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n")


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = canonical_bytes(payload)
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    descriptor = os.open(path, flags, 0o600)
    try:
        view = memoryview(line)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise RuntimeFailure(f"short append to {path}")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def manifest() -> dict[str, Any]:
    payload = load_json(MANIFEST_PATH)
    if payload.get("batch_skill_count") != 38:
        raise RuntimeFailure("manifest must own exactly 38 Batch Skills")
    return payload


def batch_entry(batch: int) -> dict[str, Any]:
    entries = [entry for entry in manifest()["skills"] if entry.get("batch") == batch]
    if len(entries) != 1:
        raise RuntimeFailure(f"manifest does not contain exactly one Batch {batch} entry")
    return entries[0]


def skill_text(entry: dict[str, Any]) -> str:
    path = PACKAGE_ROOT / entry["path"]
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeFailure(f"cannot read Skill contract {path}: {exc}") from exc


def section(text: str, heading: str) -> str:
    match = re.search(rf"^{re.escape(heading)}\s*$\n(.*?)(?=^##\s|\Z)", text, re.M | re.S)
    return match.group(1).strip() if match else ""


def list_items(block: str) -> list[str]:
    return [match.group(1).strip().rstrip("；;") for match in re.finditer(r"^-\s+(.+?)\s*$", block, re.M)]


def profile(batch: int) -> dict[str, Any]:
    entry = batch_entry(batch)
    text = skill_text(entry)
    return {
        "batch": batch,
        "skill": entry["name"],
        "title": entry["title"],
        "gate": entry["gate"],
        "dependencies": entry.get("dependencies", []),
        "objective": section(text, "## Objective"),
        "required_inputs": list_items(section(text, "## Required Inputs")),
        "required_outputs": list_items(section(text, "## Required Outputs")),
        "workflow": [re.sub(r"^\d+\.\s*", "", line.strip()).rstrip("；;") for line in section(text, "## Workflow").splitlines() if re.match(r"^\d+\.\s+", line.strip())],
        "required_tests": list_items(section(text, "## Required Tests")),
        "stop_conditions": list_items(section(text, "## Stop and Escalate")),
        "discovery_categories": list(BATCH_CATEGORIES[batch]),
        "external_evidence_required": list(EXTERNAL_EVIDENCE.get(batch, ())),
        "maximum_local_decision": "LOCAL_TOOLKIT_PASS",
    }


def relative_to_any(path: Path, roots: Iterable[Path]) -> bool:
    for root in roots:
        try:
            path.resolve().relative_to(root.resolve())
            return True
        except ValueError:
            continue
    return False


def git_value(source: Path, *args: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(source), *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return completed.stdout.strip() if completed.returncode == 0 else None


def source_files(source: Path, workspace: Path | None = None) -> list[Path]:
    if source.is_file():
        return [source]
    excluded_roots = [workspace.resolve()] if workspace and relative_to_any(workspace, [source]) else []
    files: list[Path] = []
    for current, directories, names in os.walk(source, followlinks=False):
        current_path = Path(current)
        directories[:] = sorted(
            name for name in directories
            if name not in {".git", ".hg", ".svn", "node_modules", "__pycache__", ".gradle", ".m2", "target", "dist", "build"}
            and not relative_to_any(current_path / name, excluded_roots)
        )
        for name in sorted(names):
            candidate = current_path / name
            if candidate.is_symlink() or not candidate.is_file():
                continue
            files.append(candidate)
            if len(files) > MAX_SOURCE_FILES:
                raise RuntimeFailure(f"source contains more than {MAX_SOURCE_FILES} files; create a scoped immutable snapshot")
    return files


def create_snapshot(source: Path, workspace: Path | None = None) -> dict[str, Any]:
    source = source.resolve()
    if not source.exists():
        raise RuntimeFailure(f"source does not exist: {source}")
    records: list[dict[str, Any]] = []
    language_counts = {name: 0 for name in LANGUAGES}
    extension_counts: dict[str, int] = {}
    total_bytes = 0
    initial_paths = source_files(source, workspace)
    initial_relative_paths = [path.name if source.is_file() else path.relative_to(source).as_posix() for path in initial_paths]
    for path in initial_paths:
        relative = path.name if source.is_file() else path.relative_to(source).as_posix()
        try:
            before = path.stat()
            suffix = path.suffix.lower()
            digest = sha256_file(path)
            after = path.stat()
        except OSError as exc:
            raise RuntimeFailure(f"source changed while snapshotting {relative}: {exc}") from exc
        stable_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        stable_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        if stable_before != stable_after:
            raise RuntimeFailure(f"source changed while snapshotting {relative}")
        size = after.st_size
        records.append({"path": relative, "bytes": size, "sha256": digest})
        total_bytes += size
        extension_counts[suffix or "<none>"] = extension_counts.get(suffix or "<none>", 0) + 1
        for language, suffixes in LANGUAGES.items():
            if suffix in suffixes:
                language_counts[language] += 1
                break
    final_paths = source_files(source, workspace)
    final_relative_paths = [path.name if source.is_file() else path.relative_to(source).as_posix() for path in final_paths]
    if initial_relative_paths != final_relative_paths:
        raise RuntimeFailure("source file set changed while snapshotting")
    commit = git_value(source if source.is_dir() else source.parent, "rev-parse", "HEAD")
    status = git_value(source if source.is_dir() else source.parent, "status", "--porcelain=v1", "--untracked-files=no")
    fingerprint_input = {
        "files": records,
        "git_commit": commit,
        "tracked_worktree_status": status,
    }
    return {
        "schema_version": "1.0",
        "source_root": str(source),
        "fingerprint": sha256_bytes(canonical_bytes(fingerprint_input)),
        "git_commit": commit,
        "tracked_worktree_dirty": bool(status),
        "file_count": len(records),
        "total_bytes": total_bytes,
        "language_counts": {key: value for key, value in language_counts.items() if value},
        "extension_counts": dict(sorted(extension_counts.items(), key=lambda item: (-item[1], item[0]))[:100]),
        "files": records,
        "unknowns": ([] if commit else ["source is not bound to a readable Git commit"]),
    }


def classify(snapshot: dict[str, Any]) -> dict[str, list[str]]:
    paths = [record["path"] for record in snapshot["files"]]
    classified: dict[str, list[str]] = {}
    for category, patterns in CATEGORY_PATTERNS.items():
        matched: list[str] = []
        for path in paths:
            lower = path.lower()
            name = Path(lower).name
            if any(fnmatch.fnmatch(lower, pattern) or fnmatch.fnmatch(name, pattern) for pattern in patterns):
                matched.append(path)
        classified[category] = matched[:500]
    return classified


def workspace_paths(workspace: Path) -> dict[str, Path]:
    workspace = workspace.resolve()
    return {
        "root": workspace,
        "metadata": workspace / "workspace.json",
        "snapshot": workspace / "source-snapshot.json",
        "objects": workspace / "objects" / "sha256",
        "batches": workspace / "batches",
        "ledger": workspace / "ledger",
        "requests": workspace / "certification-requests",
        "certificates": workspace / "certificates",
    }


def state_store(workspace: Path) -> TransactionStore:
    return TransactionStore(workspace_paths(workspace)["root"])


def initialize_workspace(
    source: Path,
    workspace: Path,
    target_objective: str,
    *,
    refresh: bool = False,
    actor_trust_store: Path | None = None,
) -> dict[str, Any]:
    if not target_objective.strip():
        raise RuntimeFailure("target objective must not be empty")
    paths = workspace_paths(workspace)
    if paths["root"] == source.resolve():
        raise RuntimeFailure("workspace must not be the source root")
    for path in paths.values():
        if path.suffix == "":
            path.mkdir(parents=True, exist_ok=True)
    store = state_store(workspace)
    lock_path = paths["root"] / ".workspace.lock"
    with lock_path.open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        existing = store.metadata()
        if existing:
            if Path(existing["source_root"]).resolve() != source.resolve():
                raise RuntimeFailure("workspace is already bound to a different source")
            if existing["target_objective"] != target_objective:
                raise RuntimeFailure("workspace is already bound to a different target objective")
            if actor_trust_store is not None:
                try:
                    supplied_trust = ActorTrustStore.load(actor_trust_store)
                except (OSError, ValueError, json.JSONDecodeError) as exc:
                    raise RuntimeFailure(f"actor trust store is invalid: {exc}") from exc
                if existing.get("actor_trust_store_sha256") != supplied_trust.digest:
                    raise RuntimeFailure("workspace is already bound to a different actor trust store")
            if refresh:
                raise RuntimeFailure("Source fingerprints are immutable; create a new workspace instead of refreshing")
            try:
                snapshot = store.snapshot()
            except StoreConflict:
                snapshot = load_json(paths["snapshot"]) if paths["snapshot"].is_file() else create_snapshot(source, paths["root"])
                try:
                    store.recover_snapshot(snapshot, utc_now())
                except StoreConflict as exc:
                    raise RuntimeFailure(str(exc)) from exc
            write_json(paths["snapshot"], snapshot)
            write_json(paths["metadata"], existing)
            return existing
        snapshot = create_snapshot(source, paths["root"])
        loaded_trust: ActorTrustStore | None = None
        if actor_trust_store is not None:
            try:
                loaded_trust = ActorTrustStore.load(actor_trust_store)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                raise RuntimeFailure(f"actor trust store is invalid: {exc}") from exc
        metadata = {
            "schema_version": "2.0",
            "runtime_version": RUNTIME_VERSION,
            "created_at": utc_now(),
            "source_root": str(source.resolve()),
            "source_fingerprint": snapshot["fingerprint"],
            "target_objective": target_objective,
            "external_evidence_state": "NOT_RUN",
            "certification_state": "DISABLED",
            "actor_trust_store_path": str(loaded_trust.path) if loaded_trust else None,
            "actor_trust_store_sha256": loaded_trust.digest if loaded_trust else None,
            "oracle_registry_sha256": OracleRegistry.load().digest,
        }
        try:
            bound = store.initialize_metadata(metadata, snapshot, metadata["created_at"])
        except StoreConflict as exc:
            raise RuntimeFailure(str(exc)) from exc
        write_json(paths["snapshot"], snapshot)
        write_json(paths["metadata"], bound)
        store_bytes(paths, canonical_bytes(snapshot))
        return bound


def workspace_actor_trust(workspace: Path) -> ActorTrustStore:
    metadata = state_store(workspace).metadata()
    path_value = metadata.get("actor_trust_store_path")
    expected = metadata.get("actor_trust_store_sha256")
    if not isinstance(path_value, str) or not path_value or not isinstance(expected, str):
        raise RuntimeFailure("workspace has no authenticated actor trust store")
    try:
        trust = ActorTrustStore.load(Path(path_value))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeFailure(f"workspace actor trust store is invalid: {exc}") from exc
    if trust.digest != expected:
        raise RuntimeFailure("workspace actor trust store changed after initialization")
    return trust


def assert_source_unchanged(workspace: Path) -> None:
    paths = workspace_paths(workspace)
    store = state_store(workspace)
    metadata = store.metadata()
    if not metadata:
        raise RuntimeFailure("workspace is not initialized")
    current = create_snapshot(Path(metadata["source_root"]), paths["root"])
    expected = store.snapshot()
    if current["fingerprint"] != metadata["source_fingerprint"] or expected["fingerprint"] != metadata["source_fingerprint"]:
        raise RuntimeFailure("source has changed since workspace initialization; create a new workspace")


def store_bytes(paths: dict[str, Path], data: bytes) -> dict[str, Any]:
    digest = sha256_bytes(data)
    object_path = paths["objects"] / digest.split(":", 1)[1]
    object_path.parent.mkdir(parents=True, exist_ok=True)
    if object_path.exists() and sha256_file(object_path) != digest:
        raise RuntimeFailure(f"content-addressed object is corrupt: {object_path}")
    if not object_path.exists():
        with tempfile.NamedTemporaryFile(dir=object_path.parent, prefix=".object.", delete=False) as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        temporary.chmod(0o444)
        try:
            os.link(temporary, object_path)
        except FileExistsError:
            if sha256_file(object_path) != digest:
                raise RuntimeFailure(f"content-addressed object race corrupted {object_path}")
        finally:
            temporary.unlink(missing_ok=True)
        directory = os.open(object_path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    return {"uri": f"artifact://{digest}", "sha256": digest, "bytes": len(data), "object_path": str(object_path.relative_to(paths["root"]))}


def store_file(paths: dict[str, Path], source: Path) -> dict[str, Any]:
    if not source.is_file():
        raise RuntimeFailure(f"evidence file does not exist: {source}")
    before = source.stat()
    digest = sha256_file(source)
    after_digest = source.stat()
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after_digest.st_dev, after_digest.st_ino, after_digest.st_size, after_digest.st_mtime_ns
    ):
        raise RuntimeFailure("artifact changed while hashing")
    size = after_digest.st_size
    object_path = paths["objects"] / digest.split(":", 1)[1]
    object_path.parent.mkdir(parents=True, exist_ok=True)
    if object_path.exists():
        if object_path.stat().st_size != size or sha256_file(object_path) != digest:
            raise RuntimeFailure(f"content-addressed object is corrupt: {object_path}")
    else:
        with tempfile.NamedTemporaryFile(dir=object_path.parent, prefix=".object.", delete=False) as handle:
            temporary = Path(handle.name)
            with source.open("rb") as input_stream:
                shutil.copyfileobj(input_stream, handle, length=1024 * 1024)
            handle.flush()
            os.fsync(handle.fileno())
        after_copy = source.stat()
        if (
            (after_digest.st_dev, after_digest.st_ino, after_digest.st_size, after_digest.st_mtime_ns)
            != (after_copy.st_dev, after_copy.st_ino, after_copy.st_size, after_copy.st_mtime_ns)
            or sha256_file(temporary) != digest
        ):
            temporary.unlink(missing_ok=True)
            raise RuntimeFailure("artifact changed while copying")
        temporary.chmod(0o444)
        try:
            os.link(temporary, object_path)
        except FileExistsError:
            if object_path.stat().st_size != size or sha256_file(object_path) != digest:
                raise RuntimeFailure(f"content-addressed object race corrupted {object_path}")
        finally:
            temporary.unlink(missing_ok=True)
        directory = os.open(object_path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    return {
        "uri": f"artifact://{digest}",
        "sha256": digest,
        "bytes": size,
        "object_path": str(object_path.relative_to(paths["root"])),
    }


def batch_dir(workspace: Path, batch: int) -> Path:
    return workspace_paths(workspace)["batches"] / f"batch-{batch:02d}"


def read_records(directory: Path) -> list[dict[str, Any]]:
    if not directory.is_dir():
        return []
    records: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        records.append(load_json(path))
    return records


def route_matrix(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    detected = set(snapshot.get("language_counts", {}))
    routes: list[dict[str, Any]] = []
    for source in LANGUAGES:
        for target in LANGUAGES:
            if source == target:
                continue
            routes.append({
                "route_id": f"{source}-to-{target}",
                "source": source,
                "target": target,
                "source_detected": source in detected,
                "target_toolchain_evidence": "NOT_RUN",
                "semantic_certification": "NOT_RUN",
            })
    return routes


def existing_gate_states(workspace: Path) -> dict[int, str]:
    return state_store(workspace).gate_states()


def batch_observation(batch: int, workspace: Path, snapshot: dict[str, Any], prof: dict[str, Any]) -> dict[str, Any]:
    classified = classify(snapshot)
    observation: dict[str, Any] = {
        "schema_version": "1.0",
        "batch": batch,
        "skill": prof["skill"],
        "source_fingerprint": snapshot["fingerprint"],
        "observed_at": utc_now(),
        "discovery": {category: classified[category] for category in prof["discovery_categories"]},
        "required_outputs": [{"index": index, "claim": claim, "state": "NOT_RUN"} for index, claim in enumerate(prof["required_outputs"])],
        "required_tests": [{"index": index, "claim": claim, "state": "NOT_RUN"} for index, claim in enumerate(prof["required_tests"])],
        "external_evidence": [{"claim": claim, "state": "NOT_RUN"} for claim in prof["external_evidence_required"]],
        "limitations": ["static discovery is engineering evidence only and does not satisfy runtime, production, formal-proof, customer, or certification gates"],
    }
    if batch in {4, 19}:
        observation["directional_routes"] = route_matrix(snapshot)
        observation["route_count"] = len(observation["directional_routes"])
    elif batch == 3:
        observation["semantic_frontends"] = [
            {"language": language, "source_files": count, "frontend_execution": "NOT_RUN", "unified_ir_validation": "NOT_RUN"}
            for language, count in sorted(snapshot.get("language_counts", {}).items())
        ]
    elif batch == 13:
        store = state_store(workspace)
        observation["evidence_graph"] = {
            "evidence_records": len(store.evidence()),
            "verification_records": len(store.verifications()),
            "event_chain_findings": store.verify_event_chain(),
            "external_ca_state": "NOT_RUN",
        }
    elif batch == 16:
        detected = sorted(snapshot.get("language_counts", {}))
        observation["candidate_portfolio"] = [
            {"candidate_id": f"retain-{language}", "language": language, "decision": "UNASSESSED", "real_build": "NOT_RUN"}
            for language in detected
        ]
    elif batch == 17:
        observation["workflow_dag"] = [
            {"batch": item["batch"], "dependencies": item.get("dependencies", [])}
            for item in manifest()["skills"] if item.get("batch") is not None
        ]
        observation["side_effect_ledger_entries"] = len(state_store(workspace).effects())
    elif batch == 18:
        observation["complete_project_inventory"] = {
            category: len(classified[category]) for category in ("build", "config", "ci", "deployment", "docs", "operations", "test")
        }
    elif batch == 20:
        observation["skill_registry"] = {
            "discovered_skill_files": classified["skill"],
            "runtime_permission_review": "NOT_RUN",
            "registry_signing": "NOT_RUN",
        }
    elif batch == 21:
        observation["capability_inventory"] = {
            category: len(classified[category]) for category in ("api", "frontend", "data", "admin", "test", "operations")
        }
    elif batch == 29:
        observation["change_impact_inputs"] = {
            "tracked_worktree_dirty": snapshot.get("tracked_worktree_dirty"),
            "test_assets": len(classified["test"]),
            "architecture_assets": len(classified["architecture"]),
        }
    elif batch == 38:
        observation["assurance_matrix"] = [
            {"batch": number, "decision": existing_gate_states(workspace).get(number, "NOT_RUN")}
            for number in range(21, 38)
        ]
        observation["sa_levels"] = {f"SA{level}": "NOT_RUN" for level in range(1, 6)}
    return observation


def prepare_batch(
    batch: int,
    source: Path,
    workspace: Path,
    target_objective: str,
    *,
    refresh: bool = False,
    actor_trust_store: Path | None = None,
) -> dict[str, Any]:
    initialize_workspace(source, workspace, target_objective, refresh=refresh, actor_trust_store=actor_trust_store)
    paths = workspace_paths(workspace)
    metadata = state_store(workspace).metadata()
    snapshot = load_json(paths["snapshot"])
    prof = profile(batch)
    destination = batch_dir(workspace, batch)
    observation = batch_observation(batch, workspace, snapshot, prof)
    observation_ref = store_bytes(paths, canonical_bytes(observation))
    dependencies = existing_gate_states(workspace)
    missing_dependencies = [
        dependency for dependency in prof["dependencies"]
        if dependencies.get(dependency) not in FINAL_DECISIONS
    ]
    plan = {
        "schema_version": "1.0",
        "batch": batch,
        "skill": prof["skill"],
        "source_fingerprint": metadata["source_fingerprint"],
        "target_objective": metadata["target_objective"],
        "workflow": prof["workflow"],
        "required_outputs": prof["required_outputs"],
        "required_tests": prof["required_tests"],
        "dependencies": prof["dependencies"],
        "missing_dependency_gates": missing_dependencies,
        "stop_conditions": prof["stop_conditions"],
        "external_evidence_required": prof["external_evidence_required"],
        "observation_ref": observation_ref,
        "execution_state": "BLOCKED" if missing_dependencies else "READY_FOR_IMPLEMENTATION",
    }
    execution_plan = {
        "schema_version": "1.0",
        "batch": batch,
        "source_fingerprint": metadata["source_fingerprint"],
        "target_objective": metadata["target_objective"],
        "steps": [],
        "required_claims": [
            *[{"type": "output", "index": index, "claim": claim} for index, claim in enumerate(prof["required_outputs"])],
            *[{"type": "test", "index": index, "claim": claim} for index, claim in enumerate(prof["required_tests"])],
        ],
        "external_claims": [
            {"type": "external", "index": index, "claim": claim, "state": "NOT_RUN"}
            for index, claim in enumerate(prof["external_evidence_required"])
        ],
        "execution_policy": {
            "argv_only": True,
            "shell": False,
            "source_or_workspace_cwd_only": True,
            "external_claims_allowed": False,
            "maximum_steps": 1000,
        },
    }
    report = {
        "schema_version": "2.0",
        "batch": batch,
        "skill": prof["skill"],
        "status": "BLOCKED" if missing_dependencies else "PARTIAL",
        "gate_decision": "BLOCKED" if missing_dependencies else "NOT_RUN",
        "artifacts": [observation_ref],
        "evidence": [],
        "findings": [],
        "certificates": [],
        "unknowns": ([f"dependency Batch {value} has no eligible gate" for value in missing_dependencies] + snapshot.get("unknowns", [])),
        "limitations": observation["limitations"],
        "next_batch_inputs": prof["required_outputs"],
        "external_evidence_state": "NOT_RUN",
        "certificate_ceiling": "LOCAL_TOOLKIT_PASS",
    }
    write_json(destination / "profile.json", prof)
    write_json(destination / "observation.json", observation)
    write_json(destination / "implementation-plan.json", plan)
    write_json(destination / "execution-plan.json", execution_plan)
    write_json(destination / "completion-report.json", report)
    return report


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RuntimeFailure(f"invalid JSONL at {path}:{line_number}: {exc}") from exc
        if not isinstance(item, dict):
            raise RuntimeFailure(f"invalid JSONL object at {path}:{line_number}")
        records.append(item)
    return records


def require_prepared(workspace: Path, batch: int) -> tuple[dict[str, Path], Path, dict[str, Any]]:
    paths = workspace_paths(workspace)
    destination = batch_dir(workspace, batch)
    profile_path = destination / "profile.json"
    if not profile_path.is_file():
        raise RuntimeFailure(f"Batch {batch} is not prepared")
    return paths, destination, load_json(profile_path)


def require_digest(value: object, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"sha256:[a-f0-9]{64}", value):
        raise RuntimeFailure(f"{label} must be a sha256 digest")
    return value


def semantic_record_digest(record: dict[str, Any]) -> str:
    return sha256_bytes(canonical_bytes({key: value for key, value in record.items() if key != "record_sha256"}))


def validate_evidence_envelope(
    payload: dict[str, Any],
    metadata: dict[str, Any],
    *,
    batch: int,
    claim_type: str,
    claim_index: int,
    producer_id: str,
    producer_role: str,
    environment: str,
    outcome: str,
) -> None:
    required = {"evidence_version", "batch", "claim", "producer", "environment", "subject", "scope", "observations", "replay"}
    allowed = required | {"assurance"}
    if not required.issubset(payload) or set(payload) - allowed:
        raise RuntimeFailure(f"typed Evidence envelope fields must contain {sorted(required)} and optional assurance")
    if payload["evidence_version"] != "1.0" or payload["batch"] != batch:
        raise RuntimeFailure("typed Evidence version or Batch does not match the invocation")
    claim = payload.get("claim")
    if not isinstance(claim, dict) or claim != {"type": claim_type, "index": claim_index}:
        raise RuntimeFailure("typed Evidence claim does not match the invocation")
    producer = payload.get("producer")
    if not isinstance(producer, dict) or producer != {"id": producer_id, "role": producer_role}:
        raise RuntimeFailure("typed Evidence producer does not match the invocation")
    environment_record = payload.get("environment")
    if not isinstance(environment_record, dict) or environment_record.get("id") != environment:
        raise RuntimeFailure("typed Evidence environment does not match the invocation")
    require_digest(environment_record.get("digest"), "environment.digest")
    subject = payload.get("subject")
    if not isinstance(subject, dict) or set(subject) != {"type", "sha256", "uri", "bytes"} or not isinstance(subject.get("type"), str) or not subject["type"]:
        raise RuntimeFailure("typed Evidence subject is invalid")
    require_digest(subject.get("sha256"), "subject.sha256")
    if subject.get("uri") != f"artifact://{subject['sha256']}" or not isinstance(subject.get("bytes"), int) or subject["bytes"] < 0:
        raise RuntimeFailure("typed Evidence subject reference is invalid")
    scope = payload.get("scope")
    if not isinstance(scope, dict) or set(scope) != {"source_fingerprint", "target_objective", "assumptions"}:
        raise RuntimeFailure("typed Evidence scope is invalid")
    if scope["source_fingerprint"] != metadata["source_fingerprint"] or scope["target_objective"] != metadata["target_objective"]:
        raise RuntimeFailure("typed Evidence scope does not match the workspace")
    if not isinstance(scope["assumptions"], list) or any(not isinstance(value, str) for value in scope["assumptions"]):
        raise RuntimeFailure("typed Evidence assumptions must be strings")
    observations = payload.get("observations")
    if not isinstance(observations, list) or not observations:
        raise RuntimeFailure("typed Evidence requires at least one observation")
    for observation in observations:
        if not isinstance(observation, dict) or set(observation) != {"name", "outcome", "oracle"}:
            raise RuntimeFailure("typed Evidence observation is invalid")
        if observation["outcome"] not in EVIDENCE_OUTCOMES or not observation["name"] or not observation["oracle"]:
            raise RuntimeFailure("typed Evidence observation values are invalid")
    if not any(observation["outcome"] == outcome for observation in observations):
        raise RuntimeFailure("typed Evidence outcome is not supported by its observations")
    replay = payload.get("replay")
    if not isinstance(replay, dict) or set(replay) != {"argv", "cwd", "command_digest"}:
        raise RuntimeFailure("typed Evidence replay contract is invalid")
    if not isinstance(replay["argv"], list) or not replay["argv"] or any(not isinstance(value, str) or not value for value in replay["argv"]):
        raise RuntimeFailure("typed Evidence replay argv is invalid")
    if not isinstance(replay["cwd"], str) or not replay["cwd"]:
        raise RuntimeFailure("typed Evidence replay cwd is invalid")
    require_digest(replay.get("command_digest"), "replay.command_digest")
    assurance = payload.get("assurance")
    if assurance is not None:
        assurance_fields = {"oracle_id", "claim_sha256", "corpus_role", "executor_attestation", "oracle_attestation"}
        if not isinstance(assurance, dict) or set(assurance) != assurance_fields:
            raise RuntimeFailure("typed Evidence assurance fields are invalid")
        if not isinstance(assurance.get("oracle_id"), str) or not assurance["oracle_id"]:
            raise RuntimeFailure("typed Evidence assurance oracle_id is invalid")
        require_digest(assurance.get("claim_sha256"), "assurance.claim_sha256")
        if assurance.get("corpus_role") not in {"development", "negative", "holdout", "representative", "production"}:
            raise RuntimeFailure("typed Evidence assurance corpus_role is invalid")
        for field in ("executor_attestation", "oracle_attestation"):
            if not isinstance(assurance.get(field), dict):
                raise RuntimeFailure(f"typed Evidence assurance {field} is invalid")


def record_evidence(
    workspace: Path,
    batch: int,
    evidence_file: Path,
    *,
    kind: str,
    claim_type: str,
    claim_index: int,
    producer_id: str,
    producer_role: str,
    environment: str,
    outcome: str,
    external: bool,
) -> dict[str, Any]:
    paths, destination, prof = require_prepared(workspace, batch)
    store = state_store(workspace)
    metadata = store.metadata()
    if outcome not in EVIDENCE_OUTCOMES:
        raise RuntimeFailure(f"invalid evidence outcome: {outcome}")
    if claim_type not in {"output", "test", "external"}:
        raise RuntimeFailure("claim type must be output, test, or external")
    if external != (claim_type == "external"):
        raise RuntimeFailure("external flag must be true exactly for external claims")
    claims_key = {"output": "required_outputs", "test": "required_tests", "external": "external_evidence_required"}[claim_type]
    claims = prof[claims_key]
    if claim_index < 0 or claim_index >= len(claims):
        raise RuntimeFailure(f"claim index {claim_index} is outside {claim_type} claims")
    if not producer_id.strip() or not producer_role.strip() or not environment.strip():
        raise RuntimeFailure("producer id, role, and environment are required")
    envelope = load_json(evidence_file.resolve())
    validate_evidence_envelope(
        envelope,
        metadata,
        batch=batch,
        claim_type=claim_type,
        claim_index=claim_index,
        producer_id=producer_id,
        producer_role=producer_role,
        environment=environment,
        outcome=outcome,
    )
    subject_digest = envelope["subject"]["sha256"]
    subject_path = paths["objects"] / subject_digest.split(":", 1)[1]
    if not subject_path.is_file():
        raise RuntimeFailure("typed Evidence subject is not present in the workspace content store")
    if subject_path.stat().st_size != envelope["subject"]["bytes"] or sha256_file(subject_path) != subject_digest:
        raise RuntimeFailure("typed Evidence subject bytes do not match its digest and size")
    assurance_receipt: dict[str, Any] | None = None
    assurance = envelope.get("assurance")
    if assurance is not None:
        try:
            registry = OracleRegistry.load()
            obligation = registry.resolve(batch, claim_type, claim_index)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeFailure(f"Claim Oracle registry is invalid: {exc}") from exc
        if claims[claim_index] != obligation.claim or assurance.get("claim_sha256") != obligation.claim_sha256:
            raise RuntimeFailure("typed Evidence Claim differs from its registered Oracle obligation")
        if assurance.get("oracle_id") != obligation.oracle_id or envelope["subject"].get("type") != obligation.subject_type:
            raise RuntimeFailure("typed Evidence is not produced by the registered Claim Oracle")
        corpus_role = str(assurance.get("corpus_role", ""))
        executor_role = "holdout-executor" if corpus_role == "holdout" else ("production-executor" if corpus_role == "production" else "executor")
        if producer_role != executor_role:
            raise RuntimeFailure(f"typed Evidence producer role must be {executor_role} for {corpus_role} corpus")
        if any(observation.get("oracle") != obligation.oracle_id for observation in envelope["observations"]):
            raise RuntimeFailure("typed Evidence observation does not use the registered Claim Oracle")
        try:
            oracle_subject = json.loads(subject_path.read_text(encoding="utf-8"))
            registry.validate_subject(oracle_subject, obligation, corpus_role, outcome)
            trust = workspace_actor_trust(workspace)
            bindings = {
                "batch": batch,
                "claim_type": claim_type,
                "claim_index": claim_index,
                "claim_sha256": obligation.claim_sha256,
                "subject_sha256": subject_digest,
                "source_fingerprint": metadata["source_fingerprint"],
                "corpus_role": corpus_role,
                "outcome": outcome,
                "oracle_id": obligation.oracle_id,
            }
            executor_receipt = trust.verify(
                assurance["executor_attestation"], executor_role,
                {**bindings, "actor_id": producer_id},
            )
            oracle_receipt = trust.verify(
                assurance["oracle_attestation"], "oracle-owner", bindings,
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeFailure(f"typed Evidence assurance failed: {exc}") from exc
        if oracle_receipt["actor_id"] == executor_receipt["actor_id"]:
            raise RuntimeFailure("executor cannot attest its own Claim Oracle result")
        assurance_receipt = {
            "oracle_id": obligation.oracle_id,
            "claim_sha256": obligation.claim_sha256,
            "corpus_role": corpus_role,
            "executor": executor_receipt,
            "oracle_owner": oracle_receipt,
            "oracle_registry_sha256": registry.digest,
        }
    object_ref = store_bytes(paths, canonical_bytes(envelope))
    identity_input = {
        "batch": batch,
        "claim_type": claim_type,
        "claim_index": claim_index,
        "claim": claims[claim_index],
        "kind": kind,
        "object_sha256": object_ref["sha256"],
        "subject_sha256": envelope["subject"]["sha256"],
        "producer_id": producer_id,
        "producer_role": producer_role,
        "environment": environment,
        "outcome": outcome,
        "external": external,
    }
    identity_sha256 = sha256_bytes(canonical_bytes(identity_input))
    evidence_id = "evidence-" + identity_sha256.split(":", 1)[1][:24]
    record = {
        "schema_version": "1.0",
        "evidence_id": evidence_id,
        "recorded_at": utc_now(),
        "batch": batch,
        "claim_type": claim_type,
        "claim_index": claim_index,
        "claim": claims[claim_index],
        "kind": kind,
        "producer_id": producer_id,
        "producer_role": producer_role,
        "environment": environment,
        "outcome": outcome,
        "external": external,
        "object": object_ref,
        "subject_sha256": envelope["subject"]["sha256"],
        "scope": envelope["scope"],
        "assurance": assurance_receipt,
    }
    record_sha256 = semantic_record_digest(record)
    record["record_sha256"] = record_sha256
    record_path = destination / "evidence" / f"{evidence_id}.json"
    write_json(record_path, record)
    try:
        stored, _ = store.record_evidence(record, identity_sha256, record_sha256)
    except StoreConflict as exc:
        raise RuntimeFailure(str(exc)) from exc
    return stored


def verify_object(paths: dict[str, Path], evidence: dict[str, Any]) -> None:
    object_ref = evidence.get("object", {})
    relative = Path(str(object_ref.get("object_path", "")))
    if relative.is_absolute() or ".." in relative.parts:
        raise RuntimeFailure("evidence object path escapes workspace")
    object_path = (paths["root"] / relative).resolve()
    if not relative_to_any(object_path, [paths["objects"]]) or not object_path.is_file():
        raise RuntimeFailure("evidence object is missing or outside content store")
    if object_path.stat().st_size != object_ref.get("bytes") or sha256_file(object_path) != object_ref.get("sha256"):
        raise RuntimeFailure(f"evidence object failed byte/digest verification: {evidence.get('evidence_id')}")


def verify_evidence(
    workspace: Path,
    batch: int,
    evidence_id: str,
    verifier_id: str,
    outcome: str,
    attestation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    paths, destination, _ = require_prepared(workspace, batch)
    store = state_store(workspace)
    if outcome not in VERIFICATION_OUTCOMES:
        raise RuntimeFailure(f"invalid verification outcome: {outcome}")
    row = store.evidence_row(evidence_id)
    if row is None:
        raise RuntimeFailure(f"evidence does not exist: {evidence_id}")
    evidence = json.loads(row["record_json"])
    if not isinstance(evidence, dict):
        raise RuntimeFailure("stored Evidence record is invalid")
    evidence_path = destination / "evidence" / f"{evidence_id}.json"
    if not evidence_path.is_file() or load_json(evidence_path) != evidence:
        raise RuntimeFailure("Evidence mirror is missing or differs from transactional state")
    evidence_digest = semantic_record_digest(evidence)
    if evidence_digest != row["record_sha256"] or evidence.get("record_sha256") != evidence_digest:
        raise RuntimeFailure("Evidence record digest is invalid")
    if not verifier_id.strip():
        raise RuntimeFailure("verifier id is required")
    if verifier_id == evidence["producer_id"]:
        raise RuntimeFailure("builder/producer cannot verify its own evidence")
    verify_object(paths, evidence)
    authentication: dict[str, Any] | None = None
    if attestation is not None:
        corpus_role = (evidence.get("assurance") or {}).get("corpus_role")
        required_role = "holdout-verifier" if corpus_role == "holdout" else ("production-verifier" if corpus_role == "production" else "verifier")
        try:
            authentication = workspace_actor_trust(workspace).verify(
                attestation,
                required_role,
                {
                    "actor_id": verifier_id,
                    "batch": batch,
                    "evidence_id": evidence_id,
                    "evidence_sha256": evidence_digest,
                    "outcome": outcome,
                    "corpus_role": corpus_role,
                },
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeFailure(f"Verifier authentication failed: {exc}") from exc
        assurance = evidence.get("assurance") or {}
        conflicting = {
            evidence.get("producer_id"),
            (assurance.get("oracle_owner") or {}).get("actor_id"),
        }
        if authentication["actor_id"] in conflicting:
            raise RuntimeFailure("Verifier role conflicts with executor or Oracle owner")
    record = {
        "schema_version": "1.0",
        "verification_id": "verification-" + hashlib.sha256(f"{evidence_id}\0{evidence_digest}\0{verifier_id}\0{outcome}".encode()).hexdigest()[:24],
        "verified_at": utc_now(),
        "batch": batch,
        "evidence_id": evidence_id,
        "evidence_sha256": evidence_digest,
        "verifier_id": verifier_id,
        "outcome": outcome,
        "authentication": authentication,
    }
    record_sha256 = semantic_record_digest(record)
    record["record_sha256"] = record_sha256
    record_path = destination / "verifications" / f"{record['verification_id']}.json"
    write_json(record_path, record)
    try:
        stored, _ = store.record_verification(record, record_sha256)
    except StoreConflict as exc:
        raise RuntimeFailure(str(exc)) from exc
    return stored


def verified_claims(
    workspace: Path,
    batch: int,
    evidence_records: list[dict[str, Any]] | None = None,
    verification_records: list[dict[str, Any]] | None = None,
) -> tuple[dict[tuple[str, int], bool], list[str], bool]:
    paths, destination, _ = require_prepared(workspace, batch)
    store = state_store(workspace)
    metadata = store.metadata()
    evidence_records = store.evidence(batch) if evidence_records is None else evidence_records
    verification_records = store.verifications(batch) if verification_records is None else verification_records
    verifications_by_evidence: dict[str, list[dict[str, Any]]] = {}
    for verification in verification_records:
        verifications_by_evidence.setdefault(verification["evidence_id"], []).append(verification)
    claims: dict[tuple[str, int], bool] = {}
    claim_corpora: dict[tuple[str, int], set[str]] = {}
    findings: list[str] = []
    external_seen = False
    subjects: dict[str, set[tuple[str, int]]] = {}
    registry = OracleRegistry.load()
    trust: ActorTrustStore | None = None
    if any(isinstance(evidence.get("assurance"), dict) for evidence in evidence_records):
        try:
            trust = workspace_actor_trust(workspace)
        except RuntimeFailure as exc:
            findings.append(f"workspace actor trust is invalid: {exc}")
    for evidence in evidence_records:
        try:
            mirror = load_json(destination / "evidence" / f"{evidence['evidence_id']}.json")
            if mirror != evidence:
                raise RuntimeFailure("mirror differs from transactional state")
            evidence_digest = semantic_record_digest(evidence)
            if evidence.get("record_sha256") != evidence_digest:
                raise RuntimeFailure("record digest mismatch")
            verify_object(paths, evidence)
            object_path = paths["root"] / evidence["object"]["object_path"]
            envelope = load_json(object_path)
            validate_evidence_envelope(
                envelope,
                metadata,
                batch=batch,
                claim_type=evidence["claim_type"],
                claim_index=evidence["claim_index"],
                producer_id=evidence["producer_id"],
                producer_role=evidence["producer_role"],
                environment=evidence["environment"],
                outcome=evidence["outcome"],
            )
            assurance = evidence.get("assurance")
            if isinstance(assurance, dict):
                obligation = registry.resolve(batch, evidence["claim_type"], evidence["claim_index"])
                corpus_role = assurance.get("corpus_role")
                executor_role = "holdout-executor" if corpus_role == "holdout" else ("production-executor" if corpus_role == "production" else "executor")
                if assurance.get("oracle_id") != obligation.oracle_id or assurance.get("claim_sha256") != obligation.claim_sha256:
                    raise RuntimeFailure("assurance is bound to another Claim Oracle")
                if assurance.get("oracle_registry_sha256") != registry.digest:
                    raise RuntimeFailure("assurance uses a stale Claim Oracle registry")
                if evidence.get("producer_role") != executor_role:
                    raise RuntimeFailure("assurance producer role is invalid for its corpus")
                executor = assurance.get("executor") or {}
                oracle_owner = assurance.get("oracle_owner") or {}
                expected_trust = trust.digest if trust is not None else None
                if (executor.get("actor_id") != evidence.get("producer_id") or executor.get("role") != executor_role or
                        executor.get("trust_store_sha256") != expected_trust):
                    raise RuntimeFailure("executor authentication receipt is invalid")
                if (oracle_owner.get("role") != "oracle-owner" or oracle_owner.get("trust_store_sha256") != expected_trust or
                        oracle_owner.get("actor_id") == executor.get("actor_id")):
                    raise RuntimeFailure("Oracle-owner authentication receipt is invalid")
        except RuntimeFailure as exc:
            findings.append(f"{evidence['evidence_id']}: Evidence integrity failure: {exc}")
            continue
        decisions = verifications_by_evidence.get(evidence["evidence_id"], [])
        valid_decisions: list[dict[str, Any]] = []
        for decision in decisions:
            mirror_path = destination / "verifications" / f"{decision['verification_id']}.json"
            try:
                if not mirror_path.is_file() or load_json(mirror_path) != decision:
                    raise RuntimeFailure("Verification mirror mismatch")
                if decision.get("record_sha256") != semantic_record_digest(decision):
                    raise RuntimeFailure("Verification record digest mismatch")
                if decision.get("evidence_sha256") != evidence_digest:
                    raise RuntimeFailure("Verification binds a stale Evidence digest")
                if decision.get("verifier_id") == evidence.get("producer_id"):
                    raise RuntimeFailure("producer self-verification")
                authentication = decision.get("authentication")
                if isinstance(authentication, dict):
                    corpus_role = (evidence.get("assurance") or {}).get("corpus_role")
                    verifier_role = "holdout-verifier" if corpus_role == "holdout" else ("production-verifier" if corpus_role == "production" else "verifier")
                    oracle_actor = ((evidence.get("assurance") or {}).get("oracle_owner") or {}).get("actor_id")
                    expected_trust = trust.digest if trust is not None else None
                    if (authentication.get("actor_id") != decision.get("verifier_id") or authentication.get("role") != verifier_role or
                            authentication.get("trust_store_sha256") != expected_trust or authentication.get("actor_id") == oracle_actor):
                        raise RuntimeFailure("Verifier authentication receipt is invalid")
                valid_decisions.append(decision)
            except RuntimeFailure as exc:
                findings.append(f"{decision.get('verification_id')}: {exc}")
        passes = [item for item in valid_decisions if item.get("outcome") == "PASS" and isinstance(item.get("authentication"), dict)]
        adverse = [item for item in valid_decisions if item.get("outcome") in {"FAIL", "INCONCLUSIVE"}]
        assurance = evidence.get("assurance")
        eligible = evidence.get("outcome") == "PASS" and isinstance(assurance, dict) and bool(passes) and not adverse
        key = (evidence["claim_type"], evidence["claim_index"])
        if eligible:
            claim_corpora.setdefault(key, set()).add(str(assurance.get("corpus_role")))
        elif evidence.get("outcome") == "PASS":
            findings.append(f"{evidence['evidence_id']}: PASS lacks authenticated Claim Oracle and Verifier assurance")
        subjects.setdefault(evidence["subject_sha256"], set()).add(key)
        external_seen = external_seen or (eligible and evidence.get("external", False) and assurance.get("corpus_role") == "production")
        if evidence.get("outcome") in {"FAIL", "BLOCKED"}:
            findings.append(f"{evidence['evidence_id']}: {evidence['outcome']} for {evidence['claim']}")
        if any(item.get("outcome") == "FAIL" for item in valid_decisions):
            findings.append(f"{evidence['evidence_id']}: independent verification failed")
    for subject, claim_keys in subjects.items():
        if len(claim_keys) > 1:
            findings.append(f"subject {subject} is reused across distinct claims: {sorted(claim_keys)}")
    for key, corpora in claim_corpora.items():
        obligation = registry.resolve(batch, key[0], key[1])
        claims[key] = set(obligation.required_corpora).issubset(corpora)
    return claims, findings, external_seen


def evaluate_gate(workspace: Path, batch: int, *, mode: str = "local") -> dict[str, Any]:
    paths, destination, prof = require_prepared(workspace, batch)
    store = state_store(workspace)
    metadata = store.metadata()
    snapshot = store.gate_snapshot(batch)
    claims, findings, external_seen = verified_claims(workspace, batch, snapshot["evidence"], snapshot["verifications"])
    states = snapshot["gate_states"]
    eligible_dependencies = {"LOCAL_TOOLKIT_PASS", "CERTIFIED"} if mode == "local" else {"CERTIFIED"}
    missing_dependencies = [dep for dep in prof["dependencies"] if states.get(dep) not in eligible_dependencies]
    missing_outputs = [index for index in range(len(prof["required_outputs"])) if not claims.get(("output", index), False)]
    missing_tests = [index for index in range(len(prof["required_tests"])) if not claims.get(("test", index), False)]
    missing_external = [index for index in range(len(prof["external_evidence_required"])) if not claims.get(("external", index), False)]
    evidence_count = len(snapshot["evidence"])
    if findings:
        decision = "BLOCKED"
    elif missing_dependencies:
        decision = "BLOCKED"
    elif evidence_count == 0:
        decision = "NOT_RUN"
    elif missing_outputs or missing_tests:
        decision = "INCOMPLETE"
    elif mode == "certification" and missing_external:
        decision = "INCOMPLETE"
    elif mode == "certification":
        decision = certificate_decision(workspace, batch)
    else:
        decision = "LOCAL_TOOLKIT_PASS"
    if decision == "LOCAL_TOOLKIT_PASS" and prof["external_evidence_required"] and missing_external:
        # Local engineering can be ready for the named external work, but external
        # execution remains explicitly absent.
        external_state = "NOT_RUN"
    elif prof["external_evidence_required"]:
        external_state = "OBSERVED" if external_seen else "NOT_RUN"
    else:
        external_state = "NOT_APPLICABLE"
    result = {
        "schema_version": "1.0",
        "batch": batch,
        "skill": prof["skill"],
        "gate": prof["gate"],
        "evaluated_at": utc_now(),
        "mode": mode,
        "source_fingerprint": metadata["source_fingerprint"],
        "decision": decision,
        "maximum_local_decision": "LOCAL_TOOLKIT_PASS",
        "evidence_root": snapshot["evidence_root"],
        "evaluated_revision": snapshot["revision"],
        "certificate_state_sha256": snapshot["certificate_state_sha256"],
        "missing_dependencies": missing_dependencies,
        "missing_output_indexes": missing_outputs,
        "missing_test_indexes": missing_tests,
        "missing_external_evidence_indexes": missing_external,
        "external_evidence_state": external_state,
        "findings": findings,
        "certified": decision == "CERTIFIED",
    }
    try:
        store.record_gate(result)
    except StoreConflict as exc:
        raise RuntimeFailure(str(exc)) from exc
    write_json(destination / "gate-result.json", result)
    report = load_json(destination / "completion-report.json")
    report.update({
        "status": "PASS" if decision in FINAL_DECISIONS else ("FAIL" if findings else ("BLOCKED" if decision == "BLOCKED" else "PARTIAL")),
        "gate_decision": decision,
        "evidence": [record["evidence_id"] for record in snapshot["evidence"]],
        "findings": findings,
        "unknowns": [
            *[f"dependency Batch {value} is not eligible for {mode} mode" for value in missing_dependencies],
            *[f"required output index {value} lacks verified PASS evidence" for value in missing_outputs],
            *[f"required test index {value} lacks verified PASS evidence" for value in missing_tests],
        ],
        "external_evidence_state": external_state,
    })
    write_json(destination / "completion-report.json", report)
    return result


def certificate_decision(workspace: Path, batch: int) -> str:
    policy = load_trust_policy()
    if not policy["certification_enabled"]:
        return "BLOCKED"
    certificate = state_store(workspace).certificate(batch)
    if certificate is None:
        return "NOT_RUN"
    if certificate.get("policy_id") != policy["policy_id"]:
        return "BLOCKED"
    keys = [item for item in policy["keys"] if item.get("key_id") == certificate.get("issuer_id")]
    if len(keys) != 1 or keys[0].get("revoked") or batch not in keys[0].get("authorized_batches", []):
        return "BLOCKED"
    current = state_store(workspace).gate_snapshot(batch)
    if certificate.get("evidence_root") != current["evidence_root"] or certificate.get("evaluated_revision") != current["revision"]:
        return "BLOCKED"
    expires_at = certificate.get("expires_at")
    if not isinstance(expires_at, str):
        return "BLOCKED"
    try:
        expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError:
        return "BLOCKED"
    if expiry.astimezone(timezone.utc) <= datetime.now(timezone.utc):
        return "BLOCKED"
    return "CERTIFIED" if certificate.get("decision") == "CERTIFIED" else "BLOCKED"


def load_trust_policy() -> dict[str, Any]:
    policy = load_json(TRUST_POLICY_PATH)
    required = {"schema_version", "policy_id", "certification_enabled", "maximum_certificate_days", "keys"}
    if set(policy) != required:
        raise RuntimeFailure("package trust policy has invalid fields")
    if policy["schema_version"] != "1.0" or not isinstance(policy["policy_id"], str) or not policy["policy_id"]:
        raise RuntimeFailure("package trust policy identity is invalid")
    if not isinstance(policy["certification_enabled"], bool):
        raise RuntimeFailure("package trust policy certification flag is invalid")
    if not isinstance(policy["maximum_certificate_days"], int) or policy["maximum_certificate_days"] < 1:
        raise RuntimeFailure("package trust policy maximum validity is invalid")
    if not isinstance(policy["keys"], list):
        raise RuntimeFailure("package trust policy keys must be an array")
    seen: set[str] = set()
    for key in policy["keys"]:
        key_fields = {"key_id", "public_key_path", "public_key_sha256", "authorized_batches", "revoked"}
        if not isinstance(key, dict) or set(key) != key_fields:
            raise RuntimeFailure("package trust policy key fields are invalid")
        if not isinstance(key["key_id"], str) or not key["key_id"] or key["key_id"] in seen:
            raise RuntimeFailure("package trust policy key ids must be non-empty and unique")
        seen.add(key["key_id"])
        require_digest(key["public_key_sha256"], "trust key digest")
        if not isinstance(key["public_key_path"], str) or not key["public_key_path"]:
            raise RuntimeFailure("package trust policy public key path is invalid")
        if (
            not isinstance(key["authorized_batches"], list)
            or not key["authorized_batches"]
            or any(not isinstance(value, int) or value not in range(1, 39) for value in key["authorized_batches"])
            or len(set(key["authorized_batches"])) != len(key["authorized_batches"])
            or not isinstance(key["revoked"], bool)
        ):
            raise RuntimeFailure("package trust policy key scope is invalid")
    if policy["certification_enabled"] and not policy["keys"]:
        raise RuntimeFailure("enabled certification policy requires at least one package-owned trust key")
    return policy


def request_certificate(workspace: Path, batch: int, requester_id: str) -> dict[str, Any]:
    paths, destination, prof = require_prepared(workspace, batch)
    store = state_store(workspace)
    gate = store.gate_result(batch, "local")
    if not gate or gate.get("decision") != "LOCAL_TOOLKIT_PASS":
        raise RuntimeFailure("local gate must be LOCAL_TOOLKIT_PASS before requesting external certification")
    current = store.gate_snapshot(batch)
    if gate.get("evidence_root") != current["evidence_root"] or gate.get("evaluated_revision") != current["revision"]:
        raise RuntimeFailure("local gate is stale; reevaluate before requesting certification")
    policy = load_trust_policy()
    if not policy["certification_enabled"]:
        raise RuntimeFailure("external certification requests are disabled by the package-owned trust policy")
    request = {
        "schema_version": "1.0",
        "batch": batch,
        "skill": prof["skill"],
        "gate": prof["gate"],
        "requested_at": utc_now(),
        "requester_id": requester_id,
        "source_fingerprint": store.metadata()["source_fingerprint"],
        "gate_result_sha256": sha256_bytes(canonical_bytes(gate)),
        "evidence_root": current["evidence_root"],
        "evaluated_revision": current["revision"],
        "trust_policy_id": policy["policy_id"],
        "status": "PENDING_EXTERNAL_CA",
    }
    request["request_id"] = "request-" + hashlib.sha256(canonical_bytes(request)).hexdigest()[:24]
    request_path = paths["requests"] / f"batch-{batch:02d}.json"
    write_json(request_path, request)
    store.store_certificate_request(request, sha256_bytes(canonical_bytes(request)))
    return request


def import_certificate(workspace: Path, batch: int, certificate_path: Path, signature_path: Path) -> dict[str, Any]:
    paths, destination, prof = require_prepared(workspace, batch)
    store = state_store(workspace)
    policy = load_trust_policy()
    if not policy["certification_enabled"]:
        raise RuntimeFailure("CERTIFIED is disabled by the package-owned trust policy")
    request_state = store.certificate_request(batch)
    if request_state is None:
        raise RuntimeFailure("certification request is missing")
    request, request_sha256 = request_state
    current = store.gate_snapshot(batch)
    if request.get("evidence_root") != current["evidence_root"] or request.get("evaluated_revision") != current["revision"]:
        raise RuntimeFailure("certification request is stale; reevaluate and request again")
    certificate = load_json(certificate_path)
    required = {"batch", "decision", "issuer_id", "request_sha256", "source_fingerprint", "evidence_root", "evaluated_revision", "policy_id", "issued_at", "expires_at"}
    if set(certificate) != required:
        raise RuntimeFailure(f"certificate fields must be exactly: {sorted(required)}")
    if certificate["batch"] != batch or certificate["decision"] != "CERTIFIED":
        raise RuntimeFailure("certificate scope or decision is invalid")
    if certificate["request_sha256"] != request_sha256:
        raise RuntimeFailure("certificate is not bound to the current request")
    if certificate["source_fingerprint"] != store.metadata()["source_fingerprint"]:
        raise RuntimeFailure("certificate source fingerprint does not match")
    if certificate["evidence_root"] != request["evidence_root"] or certificate["evaluated_revision"] != request["evaluated_revision"]:
        raise RuntimeFailure("certificate does not bind the requested Evidence revision")
    if certificate["policy_id"] != policy["policy_id"] or request["trust_policy_id"] != policy["policy_id"]:
        raise RuntimeFailure("certificate trust policy does not match the package policy")
    keys = [item for item in policy["keys"] if item.get("key_id") == certificate["issuer_id"]]
    if len(keys) != 1:
        raise RuntimeFailure("certificate issuer is missing or ambiguous in the package trust policy")
    key = keys[0]
    if key.get("revoked") or batch not in key.get("authorized_batches", []):
        raise RuntimeFailure("certificate issuer is revoked or unauthorized for this Batch")
    producer_ids = {record["producer_id"] for record in store.evidence(batch)}
    verifier_ids = {record["verifier_id"] for record in store.verifications(batch)}
    if certificate["issuer_id"] in producer_ids | verifier_ids:
        raise RuntimeFailure("certificate authority must be independent from producers and verifiers")
    public_key_relative = Path(str(key.get("public_key_path", "")))
    if public_key_relative.is_absolute() or ".." in public_key_relative.parts:
        raise RuntimeFailure("trusted public key path must stay inside the installed package")
    public_key = (PACKAGE_ROOT / public_key_relative).resolve()
    if not public_key.is_file() or not signature_path.is_file():
        raise RuntimeFailure("public key or certificate signature is missing")
    if not relative_to_any(public_key, [PACKAGE_ROOT]) or sha256_file(public_key) != key.get("public_key_sha256"):
        raise RuntimeFailure("trusted public key is outside policy scope or has drifted")
    now = datetime.now(timezone.utc)
    try:
        issued = datetime.fromisoformat(str(certificate["issued_at"]).replace("Z", "+00:00")).astimezone(timezone.utc)
        expires = datetime.fromisoformat(str(certificate["expires_at"]).replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError as exc:
        raise RuntimeFailure(f"certificate timestamps are invalid: {exc}") from exc
    if issued > now + timedelta(minutes=5) or expires <= now or expires - issued > timedelta(days=policy["maximum_certificate_days"]):
        raise RuntimeFailure("certificate validity window violates the trust policy")
    try:
        completed = subprocess.run(
            ["openssl", "dgst", "-sha256", "-verify", str(public_key), "-signature", str(signature_path), str(certificate_path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeFailure(f"certificate signature verifier is unavailable: {exc}") from exc
    if completed.returncode != 0:
        raise RuntimeFailure("certificate signature verification failed")
    verified = {**certificate, "verified_at": utc_now(), "signature_sha256": sha256_file(signature_path), "policy_id": policy["policy_id"]}
    write_json(paths["certificates"] / f"batch-{batch:02d}.verified.json", verified)
    store.record_certificate(verified, sha256_bytes(canonical_bytes(verified)), policy["policy_id"], verified["verified_at"])
    return verified


def redact(text: str) -> str:
    result = text
    for pattern in REDACTION_PATTERNS:
        result = pattern.sub(lambda match: (match.group(1) + "=[REDACTED]") if match.lastindex else "[REDACTED PRIVATE KEY]", result)
    return result


def redact_argv(argv: list[str]) -> list[str]:
    redacted: list[str] = []
    hide_next = False
    sensitive_flag = re.compile(r"(?i)^--?(?:password|passwd|api[_-]?key|secret|token|access[_-]?token)$")
    sensitive_assignment = re.compile(r"(?i)^(--?(?:password|passwd|api[_-]?key|secret|token|access[_-]?token))=(.*)$")
    for value in argv:
        if hide_next:
            redacted.append("[REDACTED]")
            hide_next = False
            continue
        assignment = sensitive_assignment.match(value)
        if assignment:
            redacted.append(f"{assignment.group(1)}=[REDACTED]")
            continue
        if sensitive_flag.match(value):
            redacted.append(value)
            hide_next = True
            continue
        redacted.append(redact(value))
    return redacted


def ingest_artifact(workspace: Path, artifact_path: Path) -> dict[str, Any]:
    paths = workspace_paths(workspace)
    if not state_store(workspace).metadata():
        raise RuntimeFailure("workspace is not initialized")
    artifact = artifact_path.resolve()
    if not artifact.is_file() or artifact.is_symlink():
        raise RuntimeFailure("artifact must be an existing regular file, not a symlink")
    reference = store_file(paths, artifact)
    return {**reference, "source_name": artifact.name}


def run_command(
    workspace: Path,
    batch: int,
    name: str,
    argv: list[str],
    cwd: str,
    producer_id: str,
    timeout: int,
    *,
    claim_type: str = "test",
    claim_index: int = 0,
) -> dict[str, Any]:
    paths, _, prof = require_prepared(workspace, batch)
    if not argv or any(not isinstance(value, str) or not value for value in argv):
        raise RuntimeFailure("command argv must be a non-empty JSON array of non-empty strings")
    if timeout < 1 or timeout > 86400:
        raise RuntimeFailure("command timeout must be between 1 and 86400 seconds")
    if claim_type not in {"output", "test"}:
        raise RuntimeFailure("local commands may produce only output or test Evidence")
    claim_list = prof["required_outputs" if claim_type == "output" else "required_tests"]
    if claim_index < 0 or claim_index >= len(claim_list):
        raise RuntimeFailure(f"claim index {claim_index} is outside {claim_type} claims")
    assert_source_unchanged(workspace)
    metadata = state_store(workspace).metadata()
    source = Path(metadata["source_root"])
    command_cwd = (source / cwd).resolve() if not Path(cwd).is_absolute() else Path(cwd).resolve()
    if not relative_to_any(command_cwd, [source, paths["root"]]) or not command_cwd.is_dir():
        raise RuntimeFailure("command cwd must be an existing directory inside source or workspace")
    environment = {key: value for key, value in os.environ.items() if key in {"PATH", "LANG", "LC_ALL", "TMPDIR", "SOURCE_DATE_EPOCH"}}
    started = utc_now()
    sanitized_argv = redact_argv(argv)
    raw_argv_digest = sha256_bytes(canonical_bytes(argv))
    try:
        process = subprocess.Popen(
            argv,
            cwd=command_cwd,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        raw_stdout, raw_stderr = process.communicate(timeout=timeout)
        return_code = process.returncode
        timed_out = False
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGTERM)
            raw_stdout, raw_stderr = process.communicate(timeout=2)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            raw_stdout, raw_stderr = process.communicate()
        return_code = None
        timed_out = True
    except OSError as exc:
        raise RuntimeFailure(f"command could not start: {exc}") from exc
    assert_source_unchanged(workspace)
    stdout = redact(raw_stdout[:MAX_CAPTURE_BYTES].decode("utf-8", errors="replace"))
    stderr = redact(raw_stderr[:MAX_CAPTURE_BYTES].decode("utf-8", errors="replace"))
    execution = {
        "schema_version": "1.0",
        "name": name,
        "argv": sanitized_argv,
        "argv_digest": raw_argv_digest,
        "cwd": str(command_cwd),
        "started_at": started,
        "finished_at": utc_now(),
        "timeout_seconds": timeout,
        "timed_out": timed_out,
        "return_code": return_code,
        "stdout": stdout,
        "stderr": stderr,
        "stdout_truncated": len(raw_stdout) > MAX_CAPTURE_BYTES,
        "stderr_truncated": len(raw_stderr) > MAX_CAPTURE_BYTES,
    }
    execution_ref = store_bytes(paths, canonical_bytes(execution))
    subject_digest = execution_ref["sha256"]
    envelope = {
        "evidence_version": "1.0",
        "batch": batch,
        "claim": {"type": claim_type, "index": claim_index},
        "producer": {"id": producer_id, "role": "executor"},
        "environment": {
            "id": "local-process-restricted-env",
            "digest": sha256_bytes(canonical_bytes({"environment": environment, "python": sys.version, "runtime": RUNTIME_VERSION})),
        },
        "subject": {"type": "command-execution", "sha256": subject_digest, "uri": execution_ref["uri"], "bytes": execution_ref["bytes"]},
        "scope": {
            "source_fingerprint": metadata["source_fingerprint"],
            "target_objective": metadata["target_objective"],
            "assumptions": [],
        },
        "observations": [
            {
                "name": name,
                "outcome": "PASS" if return_code == 0 and not timed_out else "FAIL",
                "oracle": "process-exit-code-and-timeout",
            }
        ],
        "replay": {
            "argv": sanitized_argv,
            "cwd": str(command_cwd),
            "command_digest": sha256_bytes(canonical_bytes({"argv": argv, "cwd": str(command_cwd), "timeout": timeout})),
        },
    }
    with tempfile.NamedTemporaryFile(dir=paths["root"], prefix=".command-evidence.", suffix=".json", delete=False) as handle:
        handle.write(canonical_bytes(envelope))
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    try:
        return record_evidence(
            workspace,
            batch,
            temporary,
            kind="execution",
            claim_type=claim_type,
            claim_index=claim_index,
            producer_id=producer_id,
            producer_role="executor",
            environment="local-process-restricted-env",
            outcome="PASS" if return_code == 0 and not timed_out else "FAIL",
            external=False,
        )
    finally:
        temporary.unlink(missing_ok=True)


def execute_plan(workspace: Path, batch: int, plan_path: Path) -> dict[str, Any]:
    _, _, prof = require_prepared(workspace, batch)
    metadata = state_store(workspace).metadata()
    plan = load_json(plan_path.resolve())
    required = {
        "schema_version", "batch", "source_fingerprint", "target_objective", "steps",
        "required_claims", "external_claims", "execution_policy",
    }
    if set(plan) != required or plan.get("schema_version") != "1.0" or plan.get("batch") != batch:
        raise RuntimeFailure("execution plan identity or fields are invalid")
    if plan.get("source_fingerprint") != metadata["source_fingerprint"] or plan.get("target_objective") != metadata["target_objective"]:
        raise RuntimeFailure("execution plan is not bound to this workspace source and target")
    policy = plan.get("execution_policy")
    expected_policy = {
        "argv_only": True,
        "shell": False,
        "source_or_workspace_cwd_only": True,
        "external_claims_allowed": False,
        "maximum_steps": 1000,
    }
    if policy != expected_policy:
        raise RuntimeFailure("execution plan policy may not be weakened")
    expected_claims = [
        *[{"type": "output", "index": index, "claim": claim} for index, claim in enumerate(prof["required_outputs"])],
        *[{"type": "test", "index": index, "claim": claim} for index, claim in enumerate(prof["required_tests"])],
    ]
    expected_external = [
        {"type": "external", "index": index, "claim": claim, "state": "NOT_RUN"}
        for index, claim in enumerate(prof["external_evidence_required"])
    ]
    if plan.get("required_claims") != expected_claims or plan.get("external_claims") != expected_external:
        raise RuntimeFailure("execution plan claim catalog differs from the prepared Batch contract")
    steps = plan.get("steps")
    if not isinstance(steps, list) or len(steps) > expected_policy["maximum_steps"]:
        raise RuntimeFailure("execution plan steps must be an array within the configured limit")
    step_fields = {"step_id", "name", "claim_type", "claim_index", "argv", "cwd", "producer_id", "timeout_seconds"}
    seen: set[str] = set()
    results: list[dict[str, Any]] = []
    for step in steps:
        if not isinstance(step, dict) or set(step) != step_fields:
            raise RuntimeFailure("execution plan step fields are invalid")
        step_id = step.get("step_id")
        if not isinstance(step_id, str) or not step_id or step_id in seen:
            raise RuntimeFailure("execution plan step ids must be non-empty and unique")
        seen.add(step_id)
        if (
            not isinstance(step.get("argv"), list)
            or not isinstance(step.get("timeout_seconds"), int)
            or not isinstance(step.get("claim_index"), int)
            or not isinstance(step.get("name"), str)
            or not step["name"]
            or not isinstance(step.get("producer_id"), str)
            or not step["producer_id"]
        ):
            raise RuntimeFailure(f"execution plan step {step_id} argv or timeout is invalid")
        record = run_command(
            workspace,
            batch,
            str(step.get("name", "")),
            step["argv"],
            str(step.get("cwd", "")),
            str(step.get("producer_id", "")),
            step["timeout_seconds"],
            claim_type=str(step.get("claim_type", "")),
            claim_index=step.get("claim_index"),
        )
        results.append({"step_id": step_id, "evidence_id": record["evidence_id"], "outcome": record["outcome"]})
    return {
        "schema_version": "1.0",
        "batch": batch,
        "plan_sha256": sha256_file(plan_path.resolve()),
        "executed_steps": len(results),
        "decision": "PASS" if results and all(result["outcome"] == "PASS" for result in results) else ("NOT_RUN" if not results else "FAIL"),
        "results": results,
        "external_evidence_state": "NOT_RUN" if expected_external else "NOT_APPLICABLE",
    }


def plan_effect(workspace: Path, batch: int, idempotency_key: str, action: str, target: str, actor_id: str, approval_id: str, fencing_token: int, reversible: bool) -> dict[str, Any]:
    require_prepared(workspace, batch)
    if (
        not all(isinstance(value, str) and value.strip() for value in (idempotency_key, action, target, actor_id, approval_id))
        or not isinstance(fencing_token, int)
        or isinstance(fencing_token, bool)
        or fencing_token < 0
        or not isinstance(reversible, bool)
    ):
        raise RuntimeFailure("effect plans require idempotency, action, target, actor, approval, and fencing values")
    identity = {"batch": batch, "action": action, "target": target, "actor_id": actor_id, "approval_id": approval_id, "fencing_token": fencing_token, "reversible": reversible}
    identity_sha256 = sha256_bytes(canonical_bytes({"idempotency_key": idempotency_key, **identity}))
    record = {
        "schema_version": "1.0",
        "effect_id": "effect-" + identity_sha256.split(":", 1)[1][:24],
        "recorded_at": utc_now(),
        "idempotency_key": idempotency_key,
        **identity,
        "state": "PLANNED",
        "executed": False,
        "reconciled": False,
    }
    try:
        stored, _ = state_store(workspace).record_effect(record, identity_sha256)
    except StoreConflict as exc:
        raise RuntimeFailure(str(exc)) from exc
    return stored


def command_catalog(_: argparse.Namespace) -> tuple[Any, int]:
    return {"schema_version": "1.0", "runtime_version": RUNTIME_VERSION, "batches": [profile(number) for number in range(1, 39)]}, 0


def command_init(args: argparse.Namespace) -> tuple[Any, int]:
    metadata = initialize_workspace(
        Path(args.source), Path(args.workspace), args.target_objective,
        refresh=args.refresh_source,
        actor_trust_store=Path(args.actor_trust_store) if args.actor_trust_store else None,
    )
    return metadata, 0


def command_prepare(args: argparse.Namespace) -> tuple[Any, int]:
    report = prepare_batch(
        args.batch, Path(args.source), Path(args.workspace), args.target_objective,
        refresh=args.refresh_source,
        actor_trust_store=Path(args.actor_trust_store) if args.actor_trust_store else None,
    )
    return report, 0


def command_prepare_all(args: argparse.Namespace) -> tuple[Any, int]:
    reports = [
        prepare_batch(
            number, Path(args.source), Path(args.workspace), args.target_objective,
            refresh=args.refresh_source and number == 1,
            actor_trust_store=Path(args.actor_trust_store) if args.actor_trust_store else None,
        )
        for number in range(1, 39)
    ]
    return {"prepared": 38, "reports": reports, "certification_state": "NOT_RUN"}, 0


def command_record(args: argparse.Namespace) -> tuple[Any, int]:
    record = record_evidence(
        Path(args.workspace), args.batch, Path(args.file), kind=args.kind,
        claim_type=args.claim_type, claim_index=args.claim_index,
        producer_id=args.producer_id, producer_role=args.producer_role,
        environment=args.environment, outcome=args.outcome, external=args.external,
    )
    return record, 0


def command_verify(args: argparse.Namespace) -> tuple[Any, int]:
    attestation = load_json(Path(args.attestation)) if args.attestation else None
    return verify_evidence(Path(args.workspace), args.batch, args.evidence_id, args.verifier_id, args.outcome, attestation), 0


def command_gate(args: argparse.Namespace) -> tuple[Any, int]:
    result = evaluate_gate(Path(args.workspace), args.batch, mode=args.mode)
    return result, 0 if result["decision"] in FINAL_DECISIONS else 2


def command_gate_all(args: argparse.Namespace) -> tuple[Any, int]:
    results = [evaluate_gate(Path(args.workspace), number, mode=args.mode) for number in range(1, 39)]
    ready = all(result["decision"] in FINAL_DECISIONS for result in results)
    return {"decision": "LOCAL_TOOLKIT_PASS" if ready and args.mode == "local" else ("CERTIFIED" if ready else "BLOCKED"), "results": results}, 0 if ready else 2


def command_status(args: argparse.Namespace) -> tuple[Any, int]:
    workspace = Path(args.workspace)
    paths = workspace_paths(workspace)
    if not paths["metadata"].is_file():
        raise RuntimeFailure("workspace is not initialized")
    store = state_store(workspace)
    return {
        "workspace": store.metadata(),
        "transaction_store": {
            "path": str(store.path),
            "revision": store.revision(),
            "event_chain_findings": store.verify_event_chain(),
        },
        "batches": [
            {
                "batch": number,
                "prepared": (batch_dir(workspace, number) / "profile.json").is_file(),
                "decision": existing_gate_states(workspace).get(number, "NOT_RUN"),
                "evidence_count": len(store.evidence(number)),
            }
            for number in range(1, 39)
        ],
    }, 0


def command_run(args: argparse.Namespace) -> tuple[Any, int]:
    try:
        argv = json.loads(args.argv_json)
    except json.JSONDecodeError as exc:
        raise RuntimeFailure(f"argv-json is invalid: {exc}") from exc
    if not isinstance(argv, list):
        raise RuntimeFailure("argv-json must be an array")
    record = run_command(
        Path(args.workspace), args.batch, args.name, argv, args.cwd, args.producer_id, args.timeout,
        claim_type=args.claim_type, claim_index=args.claim_index,
    )
    return record, 0 if record["outcome"] == "PASS" else 2


def command_ingest(args: argparse.Namespace) -> tuple[Any, int]:
    return ingest_artifact(Path(args.workspace), Path(args.file)), 0


def command_execute_plan(args: argparse.Namespace) -> tuple[Any, int]:
    result = execute_plan(Path(args.workspace), args.batch, Path(args.plan))
    return result, 0 if result["decision"] == "PASS" else 2


def command_request(args: argparse.Namespace) -> tuple[Any, int]:
    return request_certificate(Path(args.workspace), args.batch, args.requester_id), 0


def command_import_certificate(args: argparse.Namespace) -> tuple[Any, int]:
    return import_certificate(Path(args.workspace), args.batch, Path(args.certificate), Path(args.signature)), 0


def command_effect(args: argparse.Namespace) -> tuple[Any, int]:
    return plan_effect(Path(args.workspace), args.batch, args.idempotency_key, args.action, args.target, args.actor_id, args.approval_id, args.fencing_token, args.reversible), 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Batch 1-38 repository migration Skill runtime")
    parser.add_argument("--pretty", action="store_true", help="pretty-print JSON output")
    subparsers = parser.add_subparsers(dest="command", required=True)

    catalog_parser = subparsers.add_parser("catalog", help="emit all executable Batch profiles")
    catalog_parser.set_defaults(handler=command_catalog)

    def add_workspace_inputs(target: argparse.ArgumentParser, include_batch: bool = False) -> None:
        if include_batch:
            target.add_argument("--batch", required=True, type=int, choices=range(1, 39))
        target.add_argument("--source", required=True)
        target.add_argument("--workspace", required=True)
        target.add_argument("--target-objective", required=True)
        target.add_argument("--refresh-source", action="store_true")
        target.add_argument("--actor-trust-store", help="immutable Ed25519 actor trust store")

    init_parser = subparsers.add_parser("init", help="bind a workspace to an immutable source fingerprint")
    add_workspace_inputs(init_parser)
    init_parser.set_defaults(handler=command_init)

    prepare_parser = subparsers.add_parser("prepare", help="discover and prepare one Batch")
    add_workspace_inputs(prepare_parser, include_batch=True)
    prepare_parser.set_defaults(handler=command_prepare)

    prepare_all_parser = subparsers.add_parser("prepare-all", help="prepare all 38 Batch work units without claiming completion")
    add_workspace_inputs(prepare_all_parser)
    prepare_all_parser.set_defaults(handler=command_prepare_all)

    record_parser = subparsers.add_parser("record", help="record content-addressed Batch evidence")
    record_parser.add_argument("--workspace", required=True)
    record_parser.add_argument("--batch", required=True, type=int, choices=range(1, 39))
    record_parser.add_argument("--file", required=True)
    record_parser.add_argument("--kind", required=True, choices=("artifact", "execution", "test", "proof", "review", "production", "finding", "counterexample"))
    record_parser.add_argument("--claim-type", required=True, choices=("output", "test", "external"))
    record_parser.add_argument("--claim-index", required=True, type=int)
    record_parser.add_argument("--producer-id", required=True)
    record_parser.add_argument("--producer-role", required=True)
    record_parser.add_argument("--environment", required=True)
    record_parser.add_argument("--outcome", required=True, choices=sorted(EVIDENCE_OUTCOMES))
    record_parser.add_argument("--external", action="store_true")
    record_parser.set_defaults(handler=command_record)

    verify_parser = subparsers.add_parser("verify", help="record an independent evidence decision")
    verify_parser.add_argument("--workspace", required=True)
    verify_parser.add_argument("--batch", required=True, type=int, choices=range(1, 39))
    verify_parser.add_argument("--evidence-id", required=True)
    verify_parser.add_argument("--verifier-id", required=True)
    verify_parser.add_argument("--outcome", required=True, choices=sorted(VERIFICATION_OUTCOMES))
    verify_parser.add_argument("--attestation", help="Ed25519 verifier attestation envelope")
    verify_parser.set_defaults(handler=command_verify)

    gate_parser = subparsers.add_parser("gate", help="evaluate one fail-closed Batch gate")
    gate_parser.add_argument("--workspace", required=True)
    gate_parser.add_argument("--batch", required=True, type=int, choices=range(1, 39))
    gate_parser.add_argument("--mode", choices=("local", "certification"), default="local")
    gate_parser.set_defaults(handler=command_gate)

    gate_all_parser = subparsers.add_parser("gate-all", help="evaluate all Batch gates in dependency order")
    gate_all_parser.add_argument("--workspace", required=True)
    gate_all_parser.add_argument("--mode", choices=("local", "certification"), default="local")
    gate_all_parser.set_defaults(handler=command_gate_all)

    status_parser = subparsers.add_parser("status", help="show prepared work, evidence, and decisions")
    status_parser.add_argument("--workspace", required=True)
    status_parser.set_defaults(handler=command_status)

    run_parser = subparsers.add_parser("run-command", help="run an argv-only local build/test command and record evidence")
    run_parser.add_argument("--workspace", required=True)
    run_parser.add_argument("--batch", required=True, type=int, choices=range(1, 39))
    run_parser.add_argument("--name", required=True)
    run_parser.add_argument("--argv-json", required=True)
    run_parser.add_argument("--cwd", default=".")
    run_parser.add_argument("--producer-id", required=True)
    run_parser.add_argument("--timeout", type=int, default=600)
    run_parser.add_argument("--claim-type", choices=("output", "test"), default="test")
    run_parser.add_argument("--claim-index", type=int, default=0)
    run_parser.set_defaults(handler=command_run)

    ingest_parser = subparsers.add_parser("ingest-artifact", help="store immutable subject bytes before constructing typed Evidence")
    ingest_parser.add_argument("--workspace", required=True)
    ingest_parser.add_argument("--file", required=True)
    ingest_parser.set_defaults(handler=command_ingest)

    execute_parser = subparsers.add_parser("execute-plan", help="execute a source-bound argv-only Batch plan")
    execute_parser.add_argument("--workspace", required=True)
    execute_parser.add_argument("--batch", required=True, type=int, choices=range(1, 39))
    execute_parser.add_argument("--plan", required=True)
    execute_parser.set_defaults(handler=command_execute_plan)

    request_parser = subparsers.add_parser("request-certificate", help="prepare a digest-bound request for an external CA")
    request_parser.add_argument("--workspace", required=True)
    request_parser.add_argument("--batch", required=True, type=int, choices=range(1, 39))
    request_parser.add_argument("--requester-id", required=True)
    request_parser.set_defaults(handler=command_request)

    import_parser = subparsers.add_parser("import-certificate", help="verify and import an externally signed certificate")
    import_parser.add_argument("--workspace", required=True)
    import_parser.add_argument("--batch", required=True, type=int, choices=range(1, 39))
    import_parser.add_argument("--certificate", required=True)
    import_parser.add_argument("--signature", required=True)
    import_parser.set_defaults(handler=command_import_certificate)

    effect_parser = subparsers.add_parser("plan-effect", help="append an idempotent, approved, fenced side-effect plan without executing it")
    effect_parser.add_argument("--workspace", required=True)
    effect_parser.add_argument("--batch", required=True, type=int, choices=range(1, 39))
    effect_parser.add_argument("--idempotency-key", required=True)
    effect_parser.add_argument("--action", required=True)
    effect_parser.add_argument("--target", required=True)
    effect_parser.add_argument("--actor-id", required=True)
    effect_parser.add_argument("--approval-id", required=True)
    effect_parser.add_argument("--fencing-token", required=True, type=int)
    effect_parser.add_argument("--reversible", action="store_true")
    effect_parser.set_defaults(handler=command_effect)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        payload, exit_code = args.handler(args)
    except RuntimeFailure as exc:
        payload, exit_code = {"error": str(exc), "status": "BLOCKED"}, 2
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2 if args.pretty else None))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

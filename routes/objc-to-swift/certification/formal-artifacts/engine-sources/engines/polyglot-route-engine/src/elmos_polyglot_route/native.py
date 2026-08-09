from __future__ import annotations

import atexit
import base64
import binascii
import hashlib
import json
import os
import pwd
import re
import shutil
import stat
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Any

from .clang_analyzer import analyze_clang, inventory_clang_module
from .emitter import _CPP_HELPERS, _OBJC_HELPERS, _SWIFT_HELPERS
from .models import ROUTED_LANGUAGES, Language, RouteError, SemanticIR
from .python_analyzer import analyze_python
from .toolchains import (
    ExactToolchain,
    exact_toolchain,
    sanitized_subprocess_env,
    verify_csharp_toolchain,
)

ENGINE_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = ENGINE_ROOT.parents[1]

# These native frontends can re-lift emitted target source even though they
# are not part of the older ROUTED_LANGUAGES evidence inventory.  Relift
# capability is deliberately named separately from route certification.
NATIVE_RELIFTABLE_LANGUAGES = frozenset({"cpp", "objc", "swift"})
MODULE_INVENTORY_KIND = "elmos.typed-pure-module-inventory"
MODULE_INVENTORY_PROFILE = "typed-pure-module-v1"
_SWIFT_ANALYZER_KIND = "elmos.swift-analyzer-build-receipt"
_SWIFT_SYNTAX_VERSION = "600.0.1"
_SWIFT_SYNTAX_REVISION = "0687f71944021d616d34d922343dcef086855920"
_SWIFT_SYNTAX_TREE_SHA256 = "b78ec1b227a6cbe43ca239585f66907e50485b9119f96b5461bfc888f0e5f45d"
_SWIFT_SYNTAX_TREE_FILE_COUNT = 753
_SWIFT_SYNTAX_TREE_BYTES = 8_866_479
_SWIFT_ANALYZER_BINARY_MAX_BYTES = 100_000_000
_APPLE_GIT = Path("/usr/bin/git")
_APPLE_GIT_VERSION = "git version 2.50.1 (Apple Git-155)"
_APPLE_GIT_SHA256 = "44a68ddc1983d6cff3fd35ba3f9ba5f82004216f1dcde69892b3d1b06e408698"
_SWIFT_ANALYZER_LOCK = threading.Lock()
_SWIFT_ANALYZER_TEMPORARY: tempfile.TemporaryDirectory[str] | None = None
_SWIFT_ANALYZER_BINARY: Path | None = None
_SWIFT_ANALYZER_RECEIPT: dict[str, Any] | None = None
_SWIFT_ANALYZE_PROMOTABLE_DOMAIN_ERRORS = frozenset(
    {
        "SWIFT_INTEGER_WIDTH_OUTSIDE_CERTIFIED_SUBSET:Int",
    }
)
_CSHARP_ANALYZER_KIND = "elmos.csharp-semantic-cli-build-receipt"
_CSHARP_ANALYZER_INPUTS = (
    "global.json",
    "Directory.Build.props",
    "Directory.Packages.props",
    "src/Elmos.Dotnet.SemanticCli/Elmos.Dotnet.SemanticCli.csproj",
    "src/Elmos.Dotnet.SemanticCli/Program.cs",
    "src/Elmos.Dotnet.SemanticCli/packages.lock.json",
)
_CSHARP_ANALYZER_ENTRYPOINT = "Elmos.Dotnet.SemanticCli.dll"
_CSHARP_ANALYZER_MAX_INPUT_BYTES = 2_000_000
_CSHARP_ANALYZER_MAX_OUTPUT_FILE_BYTES = 100_000_000
_CSHARP_ANALYZER_MAX_OUTPUT_BYTES = 250_000_000
_CSHARP_ANALYZER_LOCK = threading.Lock()
_CSHARP_ANALYZER_TEMPORARY: tempfile.TemporaryDirectory[str] | None = None
_CSHARP_ANALYZER_BINARY: Path | None = None
_CSHARP_ANALYZER_RECEIPT: dict[str, Any] | None = None
_CSHARP_ANALYZER_FAILURE: tuple[str, str, str] | None = None


def _scan_preprocessor_directives(
    source: Path,
    language: Language,
    source_bytes: bytes,
) -> list[dict[str, Any]]:
    if language not in {"cpp", "objc"}:
        return []
    directives: list[dict[str, Any]] = []
    offset = 0
    for line in source_bytes.splitlines(keepends=True):
        content = line.rstrip(b"\r\n")
        candidates = [(index, marker) for marker in (b"#", b"%:", b"??=") if (index := content.find(marker)) >= 0]
        if not candidates:
            offset += len(line)
            continue
        marker_offset, marker = min(candidates, key=lambda item: item[0])
        raw = content[marker_offset:]
        payload = raw[len(marker) :].lstrip()
        match = re.match(rb"([A-Za-z_][A-Za-z0-9_]*)", payload)
        if marker != b"#":
            kind = "alternative-directive-marker"
            value_bytes = raw
        elif match is None:
            kind = "invalid"
            value_bytes = payload
        else:
            kind = match.group(1).decode("ascii").lower()
            value_bytes = payload[match.end() :].strip()
        start_byte = offset + marker_offset
        end_byte = offset + len(content)
        directives.append(
            {
                "order": len(directives),
                "kind": kind,
                "value": value_bytes.decode("utf-8", errors="backslashreplace"),
                "source_span": {
                    "file": source.name,
                    "start_byte": start_byte,
                    "end_byte": end_byte,
                },
                "sha256": "sha256:" + hashlib.sha256(raw).hexdigest(),
            }
        )
        offset += len(line)
    return directives


def _verify_emitted_helper_sources(source: Path, language: Language) -> None:
    registries = {"cpp": _CPP_HELPERS, "objc": _OBJC_HELPERS, "swift": _SWIFT_HELPERS}
    registry = registries.get(language)
    if registry is None:
        return
    content = source.read_text(encoding="utf-8")
    for helper_id, expected in registry.items():
        first_line = expected.splitlines()[0]
        names = re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", first_line)
        if not names:
            raise RouteError(f"EMITTED_HELPER_REGISTRY_INVALID:{language}:{helper_id}")
        name = names[-1]
        if f"{name}(" not in content:
            continue
        if content.count(expected) != 1:
            raise RouteError(f"EMITTED_HELPER_SOURCE_MISMATCH:{language}:{helper_id}:{name}")


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _swift_analyzer_input_manifest(package: Path) -> dict[str, Any]:
    if package.is_symlink():
        raise RouteError("SWIFT_ANALYZER_PACKAGE_UNSAFE")
    try:
        package = package.resolve(strict=True)
    except OSError as error:
        raise RouteError("SWIFT_ANALYZER_INPUT_MISSING") from error
    if package.is_symlink() or not package.is_dir():
        raise RouteError("SWIFT_ANALYZER_PACKAGE_UNSAFE")
    sources = package / "Sources"
    if sources.is_symlink() or not sources.is_dir():
        raise RouteError("SWIFT_ANALYZER_INPUT_MISSING")

    def discover() -> list[Path]:
        return [
            package / "Package.swift",
            package / "Package.resolved",
            *sorted(sources.rglob("*.swift"), key=lambda item: item.relative_to(package).as_posix()),
        ]

    inputs = discover()
    if len(inputs) < 3 or len({item.relative_to(package).as_posix() for item in inputs}) != len(inputs):
        raise RouteError("SWIFT_ANALYZER_INPUT_SET_INVALID")
    files: list[dict[str, Any]] = []
    contents: dict[str, bytes] = {}
    for path in inputs:
        relative = path.relative_to(package).as_posix()
        try:
            before = path.lstat()
        except OSError as error:
            raise RouteError(f"SWIFT_ANALYZER_INPUT_MISSING:{relative}") from error
        if (
            stat.S_ISLNK(before.st_mode)
            or not stat.S_ISREG(before.st_mode)
            or before.st_size <= 0
            or before.st_size > 2_000_000
        ):
            raise RouteError(f"SWIFT_ANALYZER_INPUT_UNSAFE:{relative}")
        data = path.read_bytes()
        after = path.lstat()
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ) or len(data) != after.st_size:
            raise RouteError(f"SWIFT_ANALYZER_INPUT_CHANGED:{relative}")
        contents[relative] = data
        files.append(
            {
                "path": relative,
                "sha256": "sha256:" + hashlib.sha256(data).hexdigest(),
                "bytes": len(data),
            }
        )
    if [item.relative_to(package).as_posix() for item in discover()] != [item["path"] for item in files]:
        raise RouteError("SWIFT_ANALYZER_INPUT_SET_CHANGED")
    try:
        resolved = json.loads(contents["Package.resolved"])
    except (KeyError, json.JSONDecodeError) as error:
        raise RouteError("SWIFT_ANALYZER_RESOLUTION_INVALID") from error
    pins = resolved.get("pins") if isinstance(resolved, dict) else None
    expected_pin = {
        "identity": "swift-syntax",
        "kind": "remoteSourceControl",
        "location": "https://github.com/swiftlang/swift-syntax.git",
        "state": {"revision": _SWIFT_SYNTAX_REVISION, "version": _SWIFT_SYNTAX_VERSION},
    }
    if resolved.get("version") != 2 or pins != [expected_pin]:
        raise RouteError("SWIFT_ANALYZER_RESOLUTION_MISMATCH")
    summary = {"files": files}
    return {
        "package": package,
        "files": files,
        "contents": contents,
        "sha256": _canonical_digest(summary),
    }


def _swift_dependency_tree(checkout: Path) -> dict[str, Any]:
    if checkout.is_symlink() or not checkout.is_dir():
        raise RouteError("SWIFT_ANALYZER_DEPENDENCY_CHECKOUT_MISSING")
    files: list[dict[str, Any]] = []
    total = 0
    for path in sorted(checkout.rglob("*"), key=lambda item: item.relative_to(checkout).as_posix()):
        relative_path = path.relative_to(checkout)
        if ".git" in relative_path.parts:
            continue
        if path.is_symlink():
            raise RouteError(f"SWIFT_ANALYZER_DEPENDENCY_SYMLINK:{relative_path.as_posix()}")
        if not path.is_file():
            continue
        data = path.read_bytes()
        total += len(data)
        files.append(
            {
                "path": relative_path.as_posix(),
                "sha256": "sha256:" + hashlib.sha256(data).hexdigest(),
                "bytes": len(data),
            }
        )
    digest = _canonical_digest({"files": files})
    if (
        digest != "sha256:" + _SWIFT_SYNTAX_TREE_SHA256
        or len(files) != _SWIFT_SYNTAX_TREE_FILE_COUNT
        or total != _SWIFT_SYNTAX_TREE_BYTES
    ):
        raise RouteError(f"SWIFT_ANALYZER_DEPENDENCY_TREE_MISMATCH:sha256={digest}:files={len(files)}:bytes={total}")
    return {"sha256": digest, "file_count": len(files), "bytes": total}


def _verify_swift_analyzer_binary(binary: Path, expected_digest: str | None = None) -> dict[str, Any]:
    if binary.is_symlink():
        raise RouteError("SWIFT_ANALYZER_BINARY_UNSAFE")
    try:
        resolved = binary.resolve(strict=True)
        metadata = resolved.lstat()
    except OSError as error:
        raise RouteError("SWIFT_ANALYZER_BINARY_MISSING") from error
    if (
        resolved.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or metadata.st_size <= 0
        or metadata.st_size > _SWIFT_ANALYZER_BINARY_MAX_BYTES
        or stat.S_IMODE(metadata.st_mode) & 0o111 == 0
        or stat.S_IMODE(metadata.st_mode) & 0o022 != 0
    ):
        raise RouteError("SWIFT_ANALYZER_BINARY_UNSAFE")
    digest = "sha256:" + hashlib.sha256(resolved.read_bytes()).hexdigest()
    if expected_digest is not None and digest != expected_digest:
        raise RouteError("SWIFT_ANALYZER_BINARY_CHANGED")
    return {
        "name": "ElmosSwiftAnalyzer",
        "sha256": digest,
        "bytes": metadata.st_size,
        "mode": f"{stat.S_IMODE(metadata.st_mode):04o}",
    }


def _run_swift_build_step(
    command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    timeout: int,
    failure: str,
) -> subprocess.CompletedProcess[str]:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=environment,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RouteError(failure + ":process") from error
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()[-2_000:]
        raise RouteError(failure + ":" + detail)
    return completed


def _prepare_swift_dependency_mirror(
    package: Path,
    root: Path,
    environment: dict[str, str],
) -> tuple[Path, dict[str, Any]]:
    if not _APPLE_GIT.is_file() or hashlib.sha256(_APPLE_GIT.read_bytes()).hexdigest() != _APPLE_GIT_SHA256:
        raise RouteError("SWIFT_ANALYZER_GIT_PROVENANCE_MISMATCH")
    version = _run_swift_build_step(
        [str(_APPLE_GIT), "--version"],
        cwd=root,
        environment=environment,
        timeout=30,
        failure="SWIFT_ANALYZER_GIT_UNAVAILABLE",
    ).stdout.strip()
    if version != _APPLE_GIT_VERSION:
        raise RouteError("SWIFT_ANALYZER_GIT_VERSION_MISMATCH")

    account_home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    candidates = [
        ("verified-package-source-mirror", package / ".build" / "checkouts" / "swift-syntax", True),
        (
            "verified-user-git-cache",
            account_home / "Library" / "Caches" / "org.swift.swiftpm" / "repositories" / "swift-syntax-e1f983d3",
            False,
        ),
        ("network-exact-revision", Path("https://github.com/swiftlang/swift-syntax.git"), False),
    ]
    selected: tuple[Path, str, dict[str, Any]] | None = None
    for index, (source, candidate, verify_worktree) in enumerate(candidates):
        if source != "network-exact-revision" and not candidate.is_dir():
            continue
        if verify_worktree:
            try:
                _swift_dependency_tree(candidate)
            except RouteError:
                continue
        # SwiftPM derives package identity from the mirror URL basename. Keep
        # the exact locked identity while isolating each rejected candidate.
        mirror = root / f"candidate-{index}" / "swift-syntax.git"
        mirror.parent.mkdir(mode=0o700)
        clone_source = (
            "https://github.com/swiftlang/swift-syntax.git" if source == "network-exact-revision" else str(candidate)
        )
        clone_command = [str(_APPLE_GIT), "clone", "--no-checkout"]
        if source != "network-exact-revision":
            clone_command.append("--local")
        clone_command.extend([clone_source, str(mirror)])
        try:
            _run_swift_build_step(
                clone_command,
                cwd=root,
                environment=environment,
                timeout=900,
                failure="SWIFT_ANALYZER_DEPENDENCY_CLONE_FAILED",
            )
            _run_swift_build_step(
                [str(_APPLE_GIT), "-C", str(mirror), "checkout", "--detach", _SWIFT_SYNTAX_REVISION],
                cwd=root,
                environment=environment,
                timeout=300,
                failure="SWIFT_ANALYZER_DEPENDENCY_CHECKOUT_FAILED",
            )
            observed_revision = _run_swift_build_step(
                [str(_APPLE_GIT), "-C", str(mirror), "rev-parse", "HEAD"],
                cwd=root,
                environment=environment,
                timeout=30,
                failure="SWIFT_ANALYZER_DEPENDENCY_REVISION_FAILED",
            ).stdout.strip()
            if observed_revision != _SWIFT_SYNTAX_REVISION:
                raise RouteError("SWIFT_ANALYZER_DEPENDENCY_REVISION_MISMATCH")
            dependency = _swift_dependency_tree(mirror)
        except RouteError:
            if source == "network-exact-revision":
                raise
            continue
        selected = (mirror, source, dependency)
        break
    if selected is None:
        raise RouteError("SWIFT_ANALYZER_DEPENDENCY_MIRROR_UNAVAILABLE")
    mirror, source, dependency = selected
    return mirror, {
        "seed": source,
        "git": {
            "path": str(_APPLE_GIT),
            "sha256": "sha256:" + _APPLE_GIT_SHA256,
            "version": _APPLE_GIT_VERSION,
        },
        **dependency,
    }


def _build_swift_analyzer(toolchain: ExactToolchain, package: Path) -> tuple[Path, dict[str, Any]]:
    if toolchain.auxiliary is None or toolchain.auxiliary_sha256 is None:
        raise RouteError("SWIFT_ANALYZER_DRIVER_PROVENANCE_REQUIRED")
    source_manifest = _swift_analyzer_input_manifest(package)
    temporary = tempfile.TemporaryDirectory(prefix="elmos-swift-analyzer-")
    root = Path(temporary.name)
    root.chmod(0o700)
    snapshot = root / "package"
    snapshot.mkdir(mode=0o700)
    for item in source_manifest["files"]:
        relative = str(item["path"])
        destination = snapshot / relative
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        destination.write_bytes(source_manifest["contents"][relative])
        destination.chmod(0o600)
    home = root / "home"
    scratch_tmp = root / "tmp"
    cache = root / "cache"
    config = root / "config"
    security = root / "security"
    build = root / "build"
    for directory in (home, scratch_tmp, cache, config, security, build):
        directory.mkdir(mode=0o700)
    driver = Path(toolchain.auxiliary)
    environment = sanitized_subprocess_env(
        home=home,
        temp_dir=scratch_tmp,
        executable_dirs=(driver.resolve().parent, Path(toolchain.executable).resolve().parent),
    )
    mirror, mirror_receipt = _prepare_swift_dependency_mirror(package, root, environment)
    mirror_config = snapshot / ".swiftpm" / "configuration" / "mirrors.json"
    mirror_config.parent.mkdir(mode=0o700, parents=True)
    mirror_config.write_text(
        json.dumps(
            {
                "object": [
                    {
                        "mirror": mirror.as_uri(),
                        "original": "https://github.com/swiftlang/swift-syntax.git",
                    }
                ],
                "version": 1,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    mirror_config.chmod(0o600)
    command = [
        str(driver),
        "build",
        "--package-path",
        str(snapshot),
        "--cache-path",
        str(cache),
        "--config-path",
        str(config),
        "--security-path",
        str(security),
        "--scratch-path",
        str(build),
        "--manifest-cache",
        "none",
        "--disable-automatic-resolution",
        "-c",
        "release",
    ]
    try:
        _run_swift_build_step(
            command,
            cwd=snapshot,
            environment=environment,
            timeout=1_800,
            failure="SWIFT_ANALYZER_BUILD_FAILED",
        )
    except RouteError:
        temporary.cleanup()
        raise
    snapshot_manifest = _swift_analyzer_input_manifest(snapshot)
    current_manifest = _swift_analyzer_input_manifest(package)
    if (
        snapshot_manifest["sha256"] != source_manifest["sha256"]
        or current_manifest["sha256"] != source_manifest["sha256"]
    ):
        temporary.cleanup()
        raise RouteError("SWIFT_ANALYZER_INPUT_CHANGED_DURING_BUILD")
    dependency = _swift_dependency_tree(build / "checkouts" / "swift-syntax")
    binary_candidate = build / "release" / "ElmosSwiftAnalyzer"
    if binary_candidate.is_symlink():
        temporary.cleanup()
        raise RouteError("SWIFT_ANALYZER_BINARY_UNSAFE")
    binary = binary_candidate.resolve(strict=True)
    if not binary.is_relative_to(build.resolve()):
        temporary.cleanup()
        raise RouteError("SWIFT_ANALYZER_BINARY_PATH_ESCAPE")
    binary_receipt = _verify_swift_analyzer_binary(binary)
    receipt = {
        "schema_version": "1.0.0",
        "kind": _SWIFT_ANALYZER_KIND,
        "source_inputs": {
            "sha256": source_manifest["sha256"],
            "files": source_manifest["files"],
        },
        "dependency": {
            "identity": "swift-syntax",
            "version": _SWIFT_SYNTAX_VERSION,
            "revision": _SWIFT_SYNTAX_REVISION,
            **dependency,
            "mirror": mirror_receipt,
        },
        "toolchain": {
            "swiftc": toolchain.executable,
            "swiftc_sha256": "sha256:" + str(toolchain.executable_sha256),
            "swift_driver": toolchain.auxiliary,
            "swift_driver_sha256": "sha256:" + toolchain.auxiliary_sha256,
            "version": toolchain.version,
            "profile": list(toolchain.profile),
        },
        "build": {
            "configuration": "release",
            "automatic_resolution": False,
            "manifest_cache": "none",
            "environment_policy": "minimal-empty-home-v1",
            "argv": [
                "<swift-driver>",
                "build",
                "--package-path",
                "<source-snapshot>",
                "--cache-path",
                "<isolated-cache>",
                "--config-path",
                "<isolated-config>",
                "--security-path",
                "<isolated-security>",
                "--scratch-path",
                "<isolated-build>",
                "--manifest-cache",
                "none",
                "--disable-automatic-resolution",
                "-c",
                "release",
            ],
        },
        "binary": binary_receipt,
    }
    global _SWIFT_ANALYZER_TEMPORARY
    _SWIFT_ANALYZER_TEMPORARY = temporary
    return binary, receipt


def _swift_analyzer(toolchain: ExactToolchain) -> tuple[Path, dict[str, Any]]:
    package = ENGINE_ROOT / "native" / "swift"
    current = _swift_analyzer_input_manifest(package)
    with _SWIFT_ANALYZER_LOCK:
        global _SWIFT_ANALYZER_BINARY, _SWIFT_ANALYZER_RECEIPT
        if _SWIFT_ANALYZER_BINARY is None or _SWIFT_ANALYZER_RECEIPT is None:
            _SWIFT_ANALYZER_BINARY, _SWIFT_ANALYZER_RECEIPT = _build_swift_analyzer(toolchain, package)
        if current["sha256"] != _SWIFT_ANALYZER_RECEIPT["source_inputs"]["sha256"]:
            raise RouteError("SWIFT_ANALYZER_INPUT_CHANGED_DURING_PROCESS")
        _verify_swift_analyzer_binary(
            _SWIFT_ANALYZER_BINARY,
            str(_SWIFT_ANALYZER_RECEIPT["binary"]["sha256"]),
        )
        return _SWIFT_ANALYZER_BINARY, json.loads(json.dumps(_SWIFT_ANALYZER_RECEIPT))


def swift_analyzer_build_receipt() -> dict[str, Any]:
    """Return a defensive copy of the verified per-process Swift build receipt."""

    _, receipt = _swift_analyzer(exact_toolchain("swift"))
    return receipt


def _cleanup_swift_analyzer() -> None:
    global _SWIFT_ANALYZER_TEMPORARY, _SWIFT_ANALYZER_BINARY, _SWIFT_ANALYZER_RECEIPT
    with _SWIFT_ANALYZER_LOCK:
        if _SWIFT_ANALYZER_TEMPORARY is not None:
            _SWIFT_ANALYZER_TEMPORARY.cleanup()
        _SWIFT_ANALYZER_TEMPORARY = None
        _SWIFT_ANALYZER_BINARY = None
        _SWIFT_ANALYZER_RECEIPT = None


atexit.register(_cleanup_swift_analyzer)


def _bind_swift_analyzer_identity(value: dict[str, Any], receipt: dict[str, Any]) -> dict[str, Any]:
    analyzer_version = value.get("analyzer_version")
    if not isinstance(analyzer_version, str) or not analyzer_version:
        raise RouteError("SWIFT_ANALYZER_VERSION_REQUIRED")
    bound = dict(value)
    bound["analyzer_version"] = (
        f"{analyzer_version};source-inputs={receipt['source_inputs']['sha256']};"
        f"swift-driver={receipt['toolchain']['swift_driver_sha256']};"
        f"swift-syntax-tree={receipt['dependency']['sha256']}"
    )
    return bound


def _toolchain_profile_value(profile: tuple[str, ...], key: str) -> str:
    prefix = key + "="
    matches = [item[len(prefix) :] for item in profile if item.startswith(prefix)]
    if len(matches) != 1 or not matches[0]:
        raise RouteError(f"EXACT_TOOLCHAIN_PROFILE_VALUE_REQUIRED:{key}")
    return matches[0]


def _read_csharp_bound_file(
    path: Path,
    root: Path,
    *,
    failure: str,
    maximum_bytes: int,
) -> bytes:
    if root.is_symlink():
        raise RouteError(failure)
    try:
        relative = path.relative_to(root)
        resolved_root = root.resolve(strict=True)
    except (OSError, ValueError) as error:
        raise RouteError(failure) from error
    cursor = root
    try:
        for part in relative.parts:
            cursor = cursor / part
            metadata = cursor.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                raise RouteError(failure)
        before = path.lstat()
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise RouteError(failure) from error
    if (
        not resolved.is_relative_to(resolved_root)
        or not stat.S_ISREG(before.st_mode)
        or before.st_size <= 0
        or before.st_size > maximum_bytes
        or stat.S_IMODE(before.st_mode) & 0o022 != 0
    ):
        raise RouteError(failure)
    try:
        content = path.read_bytes()
        after = path.lstat()
    except OSError as error:
        raise RouteError(failure) from error
    before_identity = (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_size,
        before.st_mtime_ns,
    )
    after_identity = (
        after.st_dev,
        after.st_ino,
        after.st_mode,
        after.st_size,
        after.st_mtime_ns,
    )
    if before_identity != after_identity or len(content) != after.st_size:
        raise RouteError(failure + "_CHANGED")
    return content


def _csharp_analyzer_input_manifest(engine: Path) -> dict[str, Any]:
    if engine.is_symlink():
        raise RouteError("CSHARP_ANALYZER_INPUT_ROOT_UNSAFE")
    try:
        resolved = engine.resolve(strict=True)
    except OSError as error:
        raise RouteError("CSHARP_ANALYZER_INPUT_ROOT_MISSING") from error
    if not resolved.is_dir():
        raise RouteError("CSHARP_ANALYZER_INPUT_ROOT_UNSAFE")
    files: list[dict[str, Any]] = []
    contents: dict[str, bytes] = {}
    for relative in _CSHARP_ANALYZER_INPUTS:
        content = _read_csharp_bound_file(
            engine / relative,
            engine,
            failure=f"CSHARP_ANALYZER_INPUT_UNSAFE:{relative}",
            maximum_bytes=_CSHARP_ANALYZER_MAX_INPUT_BYTES,
        )
        contents[relative] = content
        files.append(
            {
                "path": relative,
                "bytes": len(content),
                "sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
            }
        )
    summary = {"files": files}
    return {
        "sha256": _canonical_digest(summary),
        "files": files,
        "contents": contents,
    }


def _csharp_package_cache_root() -> Path:
    return Path(pwd.getpwuid(os.getuid()).pw_dir) / ".nuget" / "packages"


def _csharp_verified_package_manifest(lock_bytes: bytes, cache_root: Path) -> dict[str, Any]:
    try:
        lock = json.loads(lock_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RouteError("CSHARP_ANALYZER_PACKAGE_LOCK_INVALID") from error
    if not isinstance(lock, dict):
        raise RouteError("CSHARP_ANALYZER_PACKAGE_LOCK_INVALID")
    dependencies = lock.get("dependencies")
    if lock.get("version") != 2 or not isinstance(dependencies, dict) or not dependencies:
        raise RouteError("CSHARP_ANALYZER_PACKAGE_LOCK_INVALID")
    packages: list[dict[str, Any]] = []
    contents: dict[str, bytes] = {}
    identities: set[tuple[str, str]] = set()
    for target_framework in sorted(dependencies):
        target_packages = dependencies[target_framework]
        if not isinstance(target_framework, str) or not target_framework or not isinstance(target_packages, dict):
            raise RouteError("CSHARP_ANALYZER_PACKAGE_LOCK_INVALID")
        for package_id in sorted(target_packages, key=str.casefold):
            metadata = target_packages[package_id]
            if (
                not isinstance(package_id, str)
                or re.fullmatch(r"[A-Za-z0-9_.-]+", package_id) is None
                or not isinstance(metadata, dict)
            ):
                raise RouteError("CSHARP_ANALYZER_PACKAGE_LOCK_INVALID")
            version = metadata.get("resolved")
            lock_content_hash = metadata.get("contentHash")
            if (
                not isinstance(version, str)
                or re.fullmatch(r"[A-Za-z0-9_.+-]+", version) is None
                or not isinstance(lock_content_hash, str)
            ):
                raise RouteError("CSHARP_ANALYZER_PACKAGE_LOCK_INVALID")
            try:
                decoded_lock_hash = base64.b64decode(lock_content_hash, validate=True)
            except (ValueError, binascii.Error) as error:
                raise RouteError("CSHARP_ANALYZER_PACKAGE_LOCK_INVALID") from error
            if len(decoded_lock_hash) != hashlib.sha512().digest_size:
                raise RouteError("CSHARP_ANALYZER_PACKAGE_LOCK_INVALID")
            identity = (package_id.casefold(), version.casefold())
            if identity in identities:
                raise RouteError("CSHARP_ANALYZER_PACKAGE_LOCK_DUPLICATED")
            identities.add(identity)
            normalized_id, normalized_version = identity
            package_directory = cache_root / normalized_id / normalized_version
            filename = f"{normalized_id}.{normalized_version}.nupkg"
            nupkg = package_directory / filename
            sha512_file = package_directory / f"{filename}.sha512"
            metadata_file = package_directory / ".nupkg.metadata"
            if any(path.is_symlink() for path in (nupkg, sha512_file, metadata_file)):
                raise RouteError(f"CSHARP_ANALYZER_PACKAGE_CACHE_UNSAFE:{package_id}:{version}")
            if not all(path.is_file() for path in (nupkg, sha512_file, metadata_file)):
                raise RouteError(f"CSHARP_ANALYZER_PACKAGE_CACHE_MISSING:{package_id}:{version}")
            package_bytes = _read_csharp_bound_file(
                nupkg,
                cache_root,
                failure=f"CSHARP_ANALYZER_PACKAGE_CACHE_UNSAFE:{package_id}:{version}:nupkg",
                maximum_bytes=_CSHARP_ANALYZER_MAX_OUTPUT_FILE_BYTES,
            )
            sha512_bytes = _read_csharp_bound_file(
                sha512_file,
                cache_root,
                failure=f"CSHARP_ANALYZER_PACKAGE_CACHE_UNSAFE:{package_id}:{version}:sha512",
                maximum_bytes=1_000,
            )
            metadata_bytes = _read_csharp_bound_file(
                metadata_file,
                cache_root,
                failure=f"CSHARP_ANALYZER_PACKAGE_CACHE_UNSAFE:{package_id}:{version}:metadata",
                maximum_bytes=10_000,
            )
            try:
                declared_sha512 = sha512_bytes.decode("ascii").strip()
                decoded_sha512 = base64.b64decode(declared_sha512, validate=True)
                package_metadata = json.loads(metadata_bytes)
            except (UnicodeDecodeError, ValueError, binascii.Error, json.JSONDecodeError) as error:
                raise RouteError(f"CSHARP_ANALYZER_PACKAGE_CACHE_INVALID:{package_id}:{version}") from error
            raw_sha512 = base64.b64encode(hashlib.sha512(package_bytes).digest()).decode("ascii")
            if len(decoded_sha512) != hashlib.sha512().digest_size or raw_sha512 != declared_sha512:
                raise RouteError(f"CSHARP_ANALYZER_PACKAGE_NUPKG_SHA512_MISMATCH:{package_id}:{version}")
            if package_metadata != {
                "version": 2,
                "contentHash": lock_content_hash,
                "source": "https://api.nuget.org/v3/index.json",
            }:
                raise RouteError(f"CSHARP_ANALYZER_PACKAGE_METADATA_MISMATCH:{package_id}:{version}")
            contents[filename] = package_bytes
            packages.append(
                {
                    "id": package_id,
                    "version": version,
                    "target_framework": target_framework,
                    "filename": filename,
                    "bytes": len(package_bytes),
                    "sha256": "sha256:" + hashlib.sha256(package_bytes).hexdigest(),
                    "raw_nupkg_sha512": raw_sha512,
                    "lock_content_hash": lock_content_hash,
                    "sha512_file_sha256": "sha256:" + hashlib.sha256(sha512_bytes).hexdigest(),
                    "metadata_sha256": "sha256:" + hashlib.sha256(metadata_bytes).hexdigest(),
                    "source": "https://api.nuget.org/v3/index.json",
                }
            )
    packages.sort(key=lambda item: (str(item["id"]).casefold(), str(item["version"]).casefold()))
    summary = {"packages": packages}
    return {
        "sha256": _canonical_digest(summary),
        "packages": packages,
        "contents": contents,
    }


def _verify_csharp_package_mirror(mirror: Path, expected: dict[str, Any]) -> None:
    packages = expected.get("packages")
    if not isinstance(packages, list):
        raise RouteError("CSHARP_ANALYZER_PACKAGE_MIRROR_INVALID")
    expected_paths = {str(item["filename"]) for item in packages}
    observed_paths: set[str] = set()
    for path in mirror.rglob("*"):
        relative = path.relative_to(mirror).as_posix()
        if path.is_symlink():
            raise RouteError(f"CSHARP_ANALYZER_PACKAGE_MIRROR_UNSAFE:{relative}")
        if path.is_file():
            observed_paths.add(relative)
        elif not path.is_dir():
            raise RouteError(f"CSHARP_ANALYZER_PACKAGE_MIRROR_UNSAFE:{relative}")
    if observed_paths != expected_paths:
        raise RouteError("CSHARP_ANALYZER_PACKAGE_MIRROR_PATH_SET_CHANGED")
    for item in packages:
        filename = str(item["filename"])
        content = _read_csharp_bound_file(
            mirror / filename,
            mirror,
            failure=f"CSHARP_ANALYZER_PACKAGE_MIRROR_UNSAFE:{filename}",
            maximum_bytes=_CSHARP_ANALYZER_MAX_OUTPUT_FILE_BYTES,
        )
        if (
            len(content) != item["bytes"]
            or "sha256:" + hashlib.sha256(content).hexdigest() != item["sha256"]
            or base64.b64encode(hashlib.sha512(content).digest()).decode("ascii") != item["raw_nupkg_sha512"]
        ):
            raise RouteError(f"CSHARP_ANALYZER_PACKAGE_MIRROR_CHANGED:{filename}")


def _csharp_toolchain_identity(toolchain: ExactToolchain) -> dict[str, Any]:
    if toolchain.language != "csharp" or toolchain.version != "10.0.301":
        raise RouteError("CSHARP_ANALYZER_TOOLCHAIN_IDENTITY_INVALID")
    bundle_identity = verify_csharp_toolchain(toolchain)
    declared = Path(toolchain.executable)
    if not declared.is_absolute():
        raise RouteError("CSHARP_ANALYZER_TOOLCHAIN_PATH_INVALID")
    try:
        declared_before = declared.lstat()
        resolved = declared.resolve(strict=True)
        before = resolved.lstat()
        content = resolved.read_bytes()
        after = resolved.lstat()
        declared_after = declared.lstat()
        resolved_after = declared.resolve(strict=True)
    except OSError as error:
        raise RouteError("CSHARP_ANALYZER_TOOLCHAIN_UNAVAILABLE") from error
    declared_identity = (
        declared_before.st_dev,
        declared_before.st_ino,
        declared_before.st_mode,
        declared_before.st_size,
        declared_before.st_mtime_ns,
    )
    if (
        declared_identity
        != (
            declared_after.st_dev,
            declared_after.st_ino,
            declared_after.st_mode,
            declared_after.st_size,
            declared_after.st_mtime_ns,
        )
        or resolved_after != resolved
    ):
        raise RouteError("CSHARP_ANALYZER_TOOLCHAIN_CHANGED")
    resolved_identity = (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_size,
        before.st_mtime_ns,
    )
    if (
        resolved_identity
        != (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_size,
            after.st_mtime_ns,
        )
        or len(content) != after.st_size
        or not stat.S_ISREG(after.st_mode)
        or stat.S_IMODE(after.st_mode) & 0o111 == 0
        or stat.S_IMODE(after.st_mode) & 0o022 != 0
    ):
        raise RouteError("CSHARP_ANALYZER_TOOLCHAIN_UNSAFE")
    executable_sha256 = "sha256:" + hashlib.sha256(content).hexdigest()
    if toolchain.executable_sha256 is not None and executable_sha256 != "sha256:" + toolchain.executable_sha256:
        raise RouteError("CSHARP_ANALYZER_TOOLCHAIN_DIGEST_MISMATCH")
    identity = {
        "language": toolchain.language,
        "version": toolchain.version,
        "declared_path": str(declared),
        "resolved_path": str(resolved),
        "executable_sha256": executable_sha256,
        "executable_bytes": len(content),
        "executable_mode": f"{stat.S_IMODE(after.st_mode):04o}",
        "profile": list(toolchain.profile),
        "bundle": bundle_identity,
    }
    return {**identity, "sha256": _canonical_digest(identity)}


def _csharp_analyzer_output_manifest(output: Path) -> dict[str, Any]:
    if output.is_symlink():
        raise RouteError("CSHARP_ANALYZER_OUTPUT_UNSAFE")
    try:
        resolved = output.resolve(strict=True)
    except OSError as error:
        raise RouteError("CSHARP_ANALYZER_OUTPUT_MISSING") from error
    if not resolved.is_dir():
        raise RouteError("CSHARP_ANALYZER_OUTPUT_UNSAFE")
    files: list[dict[str, Any]] = []
    total_bytes = 0
    for path in sorted(output.rglob("*"), key=lambda item: item.relative_to(output).as_posix()):
        relative = path.relative_to(output).as_posix()
        if path.is_symlink():
            raise RouteError(f"CSHARP_ANALYZER_OUTPUT_UNSAFE:{relative}")
        if path.is_dir():
            continue
        content = _read_csharp_bound_file(
            path,
            output,
            failure=f"CSHARP_ANALYZER_OUTPUT_UNSAFE:{relative}",
            maximum_bytes=_CSHARP_ANALYZER_MAX_OUTPUT_FILE_BYTES,
        )
        total_bytes += len(content)
        if total_bytes > _CSHARP_ANALYZER_MAX_OUTPUT_BYTES:
            raise RouteError("CSHARP_ANALYZER_OUTPUT_TOO_LARGE")
        files.append(
            {
                "path": relative,
                "bytes": len(content),
                "sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
            }
        )
    paths = {str(item["path"]) for item in files}
    if _CSHARP_ANALYZER_ENTRYPOINT not in paths:
        raise RouteError("CSHARP_ANALYZER_ENTRYPOINT_MISSING")
    summary = {"files": files}
    return {
        "sha256": _canonical_digest(summary),
        "bytes": total_bytes,
        "file_count": len(files),
        "entrypoint": _CSHARP_ANALYZER_ENTRYPOINT,
        "files": files,
    }


def _verify_csharp_analyzer_output(output: Path, expected: dict[str, Any]) -> None:
    if _csharp_analyzer_output_manifest(output) != expected:
        raise RouteError("CSHARP_ANALYZER_OUTPUT_CHANGED")


def _run_csharp_build_step(
    command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    failure: str,
) -> None:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=900,
            env=environment,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RouteError(failure + ":process") from error
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()[-2_000:]
        raise RouteError(failure + ":" + detail)


def _build_csharp_analyzer(
    toolchain: ExactToolchain,
    engine: Path,
) -> tuple[tempfile.TemporaryDirectory[str], Path, dict[str, Any]]:
    source_manifest = _csharp_analyzer_input_manifest(engine)
    toolchain_identity = _csharp_toolchain_identity(toolchain)
    package_lock_path = "src/Elmos.Dotnet.SemanticCli/packages.lock.json"
    package_cache = _csharp_package_cache_root()
    package_manifest = _csharp_verified_package_manifest(
        source_manifest["contents"][package_lock_path],
        package_cache,
    )
    temporary = tempfile.TemporaryDirectory(prefix="elmos-csharp-semantic-cli-")
    root = Path(temporary.name)
    try:
        root.chmod(0o700)
        snapshot = root / "dotnet-engine"
        snapshot.mkdir(mode=0o700)
        for item in source_manifest["files"]:
            relative = str(item["path"])
            destination = snapshot / relative
            destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            destination.write_bytes(source_manifest["contents"][relative])
            destination.chmod(0o600)
        home = root / "home"
        scratch = root / "tmp"
        packages = root / "packages"
        http_cache = root / "http-cache"
        package_mirror = root / "package-source"
        output = root / "output"
        for directory in (home, scratch, packages, http_cache, package_mirror, output):
            directory.mkdir(mode=0o700)
        for item in package_manifest["packages"]:
            filename = str(item["filename"])
            destination = package_mirror / filename
            destination.write_bytes(package_manifest["contents"][filename])
            destination.chmod(0o600)
        _verify_csharp_package_mirror(package_mirror, package_manifest)
        environment = sanitized_subprocess_env(
            home=home,
            temp_dir=scratch,
            executable_dirs=(Path(toolchain.executable).resolve().parent,),
        )
        environment.update(
            {
                "DOTNET_CLI_HOME": str(home.resolve()),
                "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
                "DOTNET_NOLOGO": "1",
                "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1",
                "DOTNET_CLI_WORKLOAD_UPDATE_NOTIFY_DISABLE": "1",
                "DOTNET_MULTILEVEL_LOOKUP": "0",
                "MSBUILDDISABLENODEREUSE": "1",
                "NUGET_PACKAGES": str(packages.resolve()),
                "NUGET_HTTP_CACHE_PATH": str(http_cache.resolve()),
            }
        )
        project = snapshot / "src" / "Elmos.Dotnet.SemanticCli" / "Elmos.Dotnet.SemanticCli.csproj"
        restore_command = [
            toolchain.executable,
            "restore",
            str(project),
            "--locked-mode",
            "--disable-parallel",
            "--packages",
            str(packages),
            "--source",
            str(package_mirror),
            "--no-http-cache",
            "--ignore-failed-sources",
            "--nologo",
        ]
        _run_csharp_build_step(
            restore_command,
            cwd=snapshot,
            environment=environment,
            failure="CSHARP_ANALYZER_RESTORE_FAILED",
        )
        build_command = [
            toolchain.executable,
            "build",
            str(project),
            "--configuration",
            "Release",
            "--no-restore",
            "--no-incremental",
            "--disable-build-servers",
            "--output",
            str(output),
            "--nologo",
        ]
        _run_csharp_build_step(
            build_command,
            cwd=snapshot,
            environment=environment,
            failure="CSHARP_ANALYZER_BUILD_FAILED",
        )
        snapshot_manifest = _csharp_analyzer_input_manifest(snapshot)
        current_manifest = _csharp_analyzer_input_manifest(engine)
        current_toolchain = _csharp_toolchain_identity(toolchain)
        if (
            snapshot_manifest["sha256"] != source_manifest["sha256"]
            or current_manifest["sha256"] != source_manifest["sha256"]
        ):
            raise RouteError("CSHARP_ANALYZER_INPUT_CHANGED_DURING_BUILD")
        if current_toolchain != toolchain_identity:
            raise RouteError("CSHARP_ANALYZER_TOOLCHAIN_CHANGED_DURING_BUILD")
        current_packages = _csharp_verified_package_manifest(
            current_manifest["contents"][package_lock_path],
            package_cache,
        )
        if current_packages["sha256"] != package_manifest["sha256"]:
            raise RouteError("CSHARP_ANALYZER_PACKAGE_CACHE_CHANGED_DURING_BUILD")
        _verify_csharp_package_mirror(package_mirror, package_manifest)
        output_manifest = _csharp_analyzer_output_manifest(output)
        binary = output / _CSHARP_ANALYZER_ENTRYPOINT
        receipt = {
            "schema_version": "1.0.0",
            "kind": _CSHARP_ANALYZER_KIND,
            "cache_scope": "process-local",
            "source_inputs": {
                "sha256": source_manifest["sha256"],
                "files": source_manifest["files"],
            },
            "toolchain": toolchain_identity,
            "packages": {
                "sha256": package_manifest["sha256"],
                "source_policy": "verified-nuget-org-flat-mirror-v1",
                "packages": package_manifest["packages"],
            },
            "restore": {
                "locked_mode": True,
                "disable_parallel": True,
                "http_cache": False,
                "environment_policy": "minimal-empty-home-v1",
                "argv": [
                    "<dotnet>",
                    "restore",
                    "<source-snapshot-project>",
                    "--locked-mode",
                    "--disable-parallel",
                    "--packages",
                    "<isolated-packages>",
                    "--source",
                    "<verified-flat-package-mirror>",
                    "--no-http-cache",
                    "--ignore-failed-sources",
                    "--nologo",
                ],
            },
            "build": {
                "configuration": "Release",
                "restore": False,
                "incremental": False,
                "build_servers": False,
                "repository_bin_obj_used": False,
                "argv": [
                    "<dotnet>",
                    "build",
                    "<source-snapshot-project>",
                    "--configuration",
                    "Release",
                    "--no-restore",
                    "--no-incremental",
                    "--disable-build-servers",
                    "--output",
                    "<isolated-output>",
                    "--nologo",
                ],
            },
            "output": output_manifest,
        }
    except RouteError:
        temporary.cleanup()
        raise
    except OSError as error:
        temporary.cleanup()
        raise RouteError("CSHARP_ANALYZER_BUILD_FILESYSTEM_FAILED") from error
    return temporary, binary, receipt


def _csharp_analyzer(toolchain: ExactToolchain) -> tuple[Path, dict[str, Any]]:
    engine = REPOSITORY_ROOT / "engines" / "dotnet-engine"
    with _CSHARP_ANALYZER_LOCK:
        global _CSHARP_ANALYZER_TEMPORARY, _CSHARP_ANALYZER_BINARY, _CSHARP_ANALYZER_RECEIPT
        global _CSHARP_ANALYZER_FAILURE
        current_inputs = _csharp_analyzer_input_manifest(engine)
        current_toolchain = _csharp_toolchain_identity(toolchain)
        if _CSHARP_ANALYZER_FAILURE is not None:
            failed_inputs, failed_toolchain, failure = _CSHARP_ANALYZER_FAILURE
            if current_inputs["sha256"] != failed_inputs or current_toolchain["sha256"] != failed_toolchain:
                raise RouteError("CSHARP_ANALYZER_IDENTITY_CHANGED_AFTER_BUILD_FAILURE")
            raise RouteError(failure)
        if _CSHARP_ANALYZER_BINARY is None or _CSHARP_ANALYZER_RECEIPT is None:
            try:
                temporary, binary, receipt = _build_csharp_analyzer(toolchain, engine)
            except RouteError as error:
                _CSHARP_ANALYZER_FAILURE = (
                    str(current_inputs["sha256"]),
                    str(current_toolchain["sha256"]),
                    str(error),
                )
                raise
            _CSHARP_ANALYZER_TEMPORARY = temporary
            _CSHARP_ANALYZER_BINARY = binary
            _CSHARP_ANALYZER_RECEIPT = receipt
        receipt = _CSHARP_ANALYZER_RECEIPT
        binary = _CSHARP_ANALYZER_BINARY
        if current_inputs["sha256"] != receipt["source_inputs"]["sha256"]:
            raise RouteError("CSHARP_ANALYZER_INPUT_CHANGED_DURING_PROCESS")
        if current_toolchain != receipt["toolchain"]:
            raise RouteError("CSHARP_ANALYZER_TOOLCHAIN_CHANGED_DURING_PROCESS")
        _verify_csharp_analyzer_output(binary.parent, receipt["output"])
        return binary, json.loads(json.dumps(receipt))


def csharp_analyzer_build_receipt() -> dict[str, Any]:
    """Return a defensive copy of the verified per-process C# build receipt."""

    _, receipt = _csharp_analyzer(exact_toolchain("csharp"))
    return receipt


def _cleanup_csharp_analyzer() -> None:
    global _CSHARP_ANALYZER_TEMPORARY, _CSHARP_ANALYZER_BINARY, _CSHARP_ANALYZER_RECEIPT
    global _CSHARP_ANALYZER_FAILURE
    with _CSHARP_ANALYZER_LOCK:
        if _CSHARP_ANALYZER_TEMPORARY is not None:
            _CSHARP_ANALYZER_TEMPORARY.cleanup()
        _CSHARP_ANALYZER_TEMPORARY = None
        _CSHARP_ANALYZER_BINARY = None
        _CSHARP_ANALYZER_RECEIPT = None
        _CSHARP_ANALYZER_FAILURE = None


atexit.register(_cleanup_csharp_analyzer)


def _bind_csharp_analyzer_identity(value: dict[str, Any], receipt: dict[str, Any]) -> dict[str, Any]:
    analyzer_version = value.get("analyzer_version")
    if not isinstance(analyzer_version, str) or not analyzer_version:
        raise RouteError("CSHARP_ANALYZER_VERSION_REQUIRED")
    bound = dict(value)
    bound["analyzer_version"] = (
        f"{analyzer_version};source-inputs={receipt['source_inputs']['sha256']};"
        f"dotnet={receipt['toolchain']['executable_sha256']};"
        f"dotnet-bundle={receipt['toolchain']['sha256']};"
        f"build-output={receipt['output']['sha256']}"
    )
    return bound


def _run(command: list[str], *, cwd: Path, timeout: int = 120) -> dict[str, Any]:
    executable = Path(command[0])
    executable = executable if executable.is_absolute() else (cwd / executable)
    try:
        with tempfile.TemporaryDirectory(prefix="elmos-native-process-") as temporary:
            root = Path(temporary)
            home = root / "home"
            scratch = root / "tmp"
            home.mkdir(mode=0o700)
            scratch.mkdir(mode=0o700)
            completed = subprocess.run(
                command,
                cwd=cwd,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=sanitized_subprocess_env(
                    home=home,
                    temp_dir=scratch,
                    executable_dirs=(executable.resolve().parent,),
                ),
            )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RouteError(f"NATIVE_ANALYZER_FAILED:{command[0]}:process") from error
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()[-2_000:]
        raise RouteError(f"NATIVE_ANALYZER_FAILED:{command[0]}:{detail}")
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RouteError(f"NATIVE_ANALYZER_INVALID_JSON:{command[0]}") from error
    if not isinstance(value, dict):
        raise RouteError("NATIVE_ANALYZER_OBJECT_REQUIRED")
    return value


def _run_trusted_swift_analyzer(
    binary: Path,
    receipt: dict[str, Any],
    arguments: list[str],
    *,
    allowed_domain_errors: frozenset[str],
) -> dict[str, Any]:
    """Run one receipt-bound Swift analyzer with exact error promotion.

    ``_run`` intentionally wraps every non-zero process result.  Only this
    Swift-specific trust boundary may unwrap a domain rejection, and only
    when the entire wrapped value binds the verified absolute executable and
    one complete allowlisted suffix. Unknown, forged, or multi-line output
    remains the original ``NATIVE_ANALYZER_FAILED`` value.
    """

    if not binary.is_absolute() or any(
        not reason or "\n" in reason or "\r" in reason for reason in allowed_domain_errors
    ):
        raise RouteError("SWIFT_ANALYZER_DOMAIN_ERROR_POLICY_INVALID")
    receipt_binary = receipt.get("binary")
    expected_digest = receipt_binary.get("sha256") if isinstance(receipt_binary, dict) else None
    if not isinstance(expected_digest, str):
        raise RouteError("SWIFT_ANALYZER_BINARY_RECEIPT_INVALID")
    _verify_swift_analyzer_binary(binary, expected_digest)
    try:
        value = _run([str(binary), *arguments], cwd=binary.parent)
    except RouteError as error:
        _verify_swift_analyzer_binary(binary, expected_digest)
        wrapped = str(error)
        for reason in allowed_domain_errors:
            if wrapped == f"NATIVE_ANALYZER_FAILED:{binary}:{reason}":
                raise RouteError(reason) from error
        raise
    _verify_swift_analyzer_binary(binary, expected_digest)
    return value


def _run_csharp_semantic_cli(
    toolchain: ExactToolchain,
    arguments: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    binary, receipt = _csharp_analyzer(toolchain)
    value = _run(
        [toolchain.executable, str(binary), *arguments],
        cwd=binary.parent,
    )
    verified_binary, verified_receipt = _csharp_analyzer(toolchain)
    if verified_binary != binary or verified_receipt != receipt:
        raise RouteError("CSHARP_ANALYZER_CHANGED_DURING_EXECUTION")
    return _bind_csharp_analyzer_identity(value, receipt), receipt


def _validated_module_inventory(
    value: dict[str, Any],
    language: Language,
    source: Path,
    source_bytes: bytes,
) -> dict[str, Any]:
    expected_inventory_keys = {
        "schema_version",
        "kind",
        "profile",
        "source_language",
        "source_file",
        "analyzer",
        "analyzer_version",
        "enumeration_status",
        "subjects",
        "diagnostics",
    }
    if set(value) != expected_inventory_keys:
        raise RouteError(f"MODULE_INVENTORY_KEYS_INVALID:{language}:{source.name}")
    if (
        value.get("schema_version") != "1.0.0"
        or value.get("kind") != MODULE_INVENTORY_KIND
        or value.get("profile") != MODULE_INVENTORY_PROFILE
        or value.get("source_language") != language
        or value.get("source_file") != source.name
    ):
        raise RouteError(f"MODULE_INVENTORY_IDENTITY_INVALID:{language}:{source.name}")
    status = value.get("enumeration_status")
    subjects = value.get("subjects")
    diagnostics = value.get("diagnostics")
    if status not in {"PASSED", "FAILED"} or not isinstance(subjects, list) or not isinstance(diagnostics, list):
        raise RouteError(f"MODULE_INVENTORY_CONTRACT_INVALID:{language}:{source.name}")

    normalized_subjects: list[dict[str, Any]] = []
    occurrences: dict[tuple[str, str], int] = {}
    for raw in subjects:
        if not isinstance(raw, dict):
            raise RouteError(f"MODULE_INVENTORY_SUBJECT_INVALID:{language}:{source.name}")
        if set(raw) != {
            "name",
            "qualified_name",
            "declaration_kind",
            "analyzable",
            "source_span",
            "signature",
        }:
            raise RouteError(f"MODULE_INVENTORY_SUBJECT_KEYS_INVALID:{language}:{source.name}")
        name = raw.get("name")
        qualified_name = raw.get("qualified_name")
        declaration_kind = raw.get("declaration_kind")
        analyzable = raw.get("analyzable")
        source_span = raw.get("source_span")
        signature = raw.get("signature")
        if (
            not isinstance(name, str)
            or not name
            or not isinstance(qualified_name, str)
            or not qualified_name
            or not isinstance(declaration_kind, str)
            or not declaration_kind
            or not isinstance(analyzable, bool)
            or not isinstance(signature, dict)
        ):
            raise RouteError(f"MODULE_INVENTORY_SUBJECT_INVALID:{language}:{source.name}")
        if source_span is not None:
            if not isinstance(source_span, dict):
                raise RouteError(f"MODULE_INVENTORY_SPAN_INVALID:{language}:{source.name}")
            span_file = source_span.get("file")
            start_byte = source_span.get("start_byte")
            end_byte = source_span.get("end_byte")
            if (
                span_file != source.name
                or not isinstance(start_byte, int)
                or not isinstance(end_byte, int)
                or start_byte < 0
                or end_byte <= start_byte
                or end_byte > source.stat().st_size
            ):
                raise RouteError(f"MODULE_INVENTORY_SPAN_INVALID:{language}:{source.name}")
        occurrence_key = (declaration_kind, qualified_name)
        occurrence = occurrences.get(occurrence_key, 0) + 1
        occurrences[occurrence_key] = occurrence
        normalized_subjects.append(
            {
                "name": name,
                "qualified_name": qualified_name,
                "declaration_kind": declaration_kind,
                "analyzable": analyzable,
                "source_span": source_span,
                "signature": signature,
                "occurrence": occurrence,
            }
        )
    return {
        **value,
        "source_artifact_sha256": "sha256:" + hashlib.sha256(source_bytes).hexdigest(),
        "source_artifact_bytes": len(source_bytes),
        "directives": _scan_preprocessor_directives(source, language, source_bytes),
        "subjects": normalized_subjects,
        "diagnostics": [str(item) for item in diagnostics],
    }


def inventory_module(source: Path, language: Language) -> dict[str, Any]:
    """Enumerate one file with its real parser/compiler frontend.

    This is deliberately separate from ``analyze``: enumeration establishes
    file closure, while the existing named-function mode decides whether each
    enumerated callable fits ``typed-pure-function-v1``.
    """

    source = source.resolve()
    if not source.is_file() or source.is_symlink() or source.stat().st_size > 2_000_000:
        raise RouteError("SOURCE_FILE_UNSAFE_OR_TOO_LARGE")
    if language == "python":
        raise RouteError("PYTHON_MODULE_INVENTORY_USES_CPYTHON_AST")
    source_bytes = source.read_bytes()
    toolchain = exact_toolchain(language)
    analyzer_build_receipt: dict[str, Any] | None = None
    if language in ("cpp", "objc"):
        value = inventory_clang_module(
            source,
            language,
            toolchain.executable,
            toolchain.version,
            sdk_path=_toolchain_profile_value(toolchain.profile, "sdk-path"),
        )
    elif language == "java":
        helper = ENGINE_ROOT / "native" / "java" / "Analyzer.java"
        value = _run(
            [toolchain.executable, "--source", "21", str(helper), str(source), "--inventory"],
            cwd=ENGINE_ROOT,
        )
    elif language == "csharp":
        value, _ = _run_csharp_semantic_cli(
            toolchain,
            [str(source), "--inventory"],
        )
    elif language == "typescript":
        frontend = REPOSITORY_ROOT / "engines" / "frontend-client-engine"
        cli = frontend / "dist" / "src" / "polyglot-cli.js"
        if not cli.is_file():
            pnpm = shutil.which("pnpm")
            if pnpm is None:
                raise RouteError("EXACT_TOOLCHAIN_UNAVAILABLE:pnpm")
            completed = subprocess.run(
                [pnpm, "run", "build"],
                cwd=frontend,
                check=False,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if completed.returncode != 0:
                raise RouteError("TYPESCRIPT_ANALYZER_BUILD_FAILED:" + completed.stderr[-2_000:])
        value = _run([toolchain.executable, str(cli), str(source), "--inventory"], cwd=frontend)
    elif language == "go":
        helper = ENGINE_ROOT / "native" / "go" / "analyzer.go"
        value = _run([toolchain.executable, "run", str(helper), "--", str(source), "--inventory"], cwd=ENGINE_ROOT)
    elif language == "rust":
        package = ENGINE_ROOT / "native" / "rust"
        assert toolchain.auxiliary is not None
        value = _run(
            [
                toolchain.auxiliary,
                "run",
                "--quiet",
                "--offline",
                "--locked",
                "--manifest-path",
                str(package / "Cargo.toml"),
                "--",
                str(source),
                "--inventory",
            ],
            cwd=package,
            timeout=900,
        )
    elif language == "swift":
        binary, analyzer_build_receipt = _swift_analyzer(toolchain)
        value = _bind_swift_analyzer_identity(
            _run([str(binary), str(source), "--inventory"], cwd=binary.parent),
            analyzer_build_receipt,
        )
    else:
        raise RouteError(f"MODULE_INVENTORY_UNSUPPORTED:{language}")
    if source.read_bytes() != source_bytes:
        raise RouteError(f"MODULE_INVENTORY_SOURCE_CHANGED:{language}:{source.name}")
    validated = _validated_module_inventory(value, language, source, source_bytes)
    if analyzer_build_receipt is not None:
        validated["analyzer_build_receipt"] = analyzer_build_receipt
    return validated


def analyze(
    source: Path,
    language: Language,
    function_name: str,
    *,
    emitted_target: bool = False,
) -> SemanticIR:
    source = source.resolve()
    if not source.is_file() or source.is_symlink() or source.stat().st_size > 2_000_000:
        raise RouteError("SOURCE_FILE_UNSAFE_OR_TOO_LARGE")
    if emitted_target and language not in ROUTED_LANGUAGES and language not in NATIVE_RELIFTABLE_LANGUAGES:
        raise RouteError(f"EMITTED_TARGET_REANALYSIS_UNSUPPORTED:{language}")
    if emitted_target:
        _verify_emitted_helper_sources(source, language)
    toolchain = exact_toolchain(language)
    if language == "python":
        return analyze_python(source, function_name, emitted_target=emitted_target)
    if language in ("cpp", "objc"):
        return analyze_clang(
            source,
            language,
            function_name,
            toolchain.executable,
            toolchain.version,
            emitted_target=emitted_target,
            sdk_path=_toolchain_profile_value(toolchain.profile, "sdk-path"),
        )
    if language == "swift":
        binary, receipt = _swift_analyzer(toolchain)
        value = _bind_swift_analyzer_identity(
            _run_trusted_swift_analyzer(
                binary,
                receipt,
                [str(source), function_name, *(["--emitted-target"] if emitted_target else [])],
                allowed_domain_errors=_SWIFT_ANALYZE_PROMOTABLE_DOMAIN_ERRORS,
            ),
            receipt,
        )
        return SemanticIR.from_mapping(value)
    if language == "java":
        helper = ENGINE_ROOT / "native" / "java" / "Analyzer.java"
        arguments = [str(source), function_name]
        if emitted_target:
            arguments.append("--emitted-target")
        value = _run(
            [toolchain.executable, "--source", "21", str(helper), *arguments],
            cwd=ENGINE_ROOT,
        )
    elif language == "csharp":
        arguments = [str(source), function_name]
        if emitted_target:
            arguments.append("--emitted-target")
            project = ENGINE_ROOT / "native" / "csharp"
            value = _run(
                [toolchain.executable, "run", "--project", str(project), "--", *arguments],
                cwd=REPOSITORY_ROOT,
            )
        else:
            value, _ = _run_csharp_semantic_cli(toolchain, arguments)
    elif language == "go":
        helper = ENGINE_ROOT / "native" / "go" / "analyzer.go"
        arguments = [str(source), function_name]
        if emitted_target:
            arguments.append("--emitted-target")
        value = _run([toolchain.executable, "run", str(helper), "--", *arguments], cwd=ENGINE_ROOT)
    elif language == "rust":
        package = ENGINE_ROOT / "native" / "rust"
        assert toolchain.auxiliary is not None
        value = _run(
            [
                toolchain.auxiliary,
                "run",
                "--quiet",
                "--offline",
                "--locked",
                "--manifest-path",
                str(package / "Cargo.toml"),
                "--",
                str(source),
                function_name,
                *(["--emitted-target"] if emitted_target else []),
            ],
            cwd=package,
            timeout=900,
        )
    elif emitted_target:
        helper = ENGINE_ROOT / "native" / "typescript" / "analyzer.mjs"
        typescript_module = (
            REPOSITORY_ROOT
            / "engines"
            / "frontend-client-engine"
            / "node_modules"
            / "typescript"
            / "lib"
            / "typescript.js"
        )
        value = _run(
            [
                toolchain.executable,
                str(helper),
                str(typescript_module),
                str(source),
                function_name,
                "--emitted-target",
            ],
            cwd=ENGINE_ROOT,
        )
    else:
        frontend = REPOSITORY_ROOT / "engines" / "frontend-client-engine"
        cli = frontend / "dist" / "src" / "polyglot-cli.js"
        if not cli.is_file():
            pnpm = shutil.which("pnpm")
            if pnpm is None:
                raise RouteError("EXACT_TOOLCHAIN_UNAVAILABLE:pnpm")
            completed = subprocess.run(
                [pnpm, "run", "build"],
                cwd=frontend,
                check=False,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if completed.returncode != 0:
                raise RouteError("TYPESCRIPT_ANALYZER_BUILD_FAILED:" + completed.stderr[-2_000:])
        value = _run([toolchain.executable, str(cli), str(source), function_name], cwd=frontend)
    return SemanticIR.from_mapping(value)

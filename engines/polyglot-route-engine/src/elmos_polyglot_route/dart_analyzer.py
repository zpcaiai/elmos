"""Exact Dart AST frontend for the active ``flutter`` route identity.

The route calls the Dart SDK bundled with Flutter 3.44.1, never ``dart`` from
``PATH``.  The parser is ``package:analyzer`` 10.1.0 from Flutter's own locked
tooling graph.  Its complete transitive source closure is content-verified
before and after execution and exposed to the helper through a generated,
restricted package config.

Only the typed pure-module subset represented by :mod:`models` is admitted.
Flutter Widget/UI constructs, imports, calls, async work and all other effects
fail closed in the Dart AST helper.
"""

from __future__ import annotations

import hashlib
import json
import stat
import subprocess
import tempfile
from os import stat_result
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from .models import RouteError, SemanticIR
from .toolchains import ExactToolchain, sanitized_subprocess_env

ENGINE_ROOT = Path(__file__).resolve().parents[2]
_HELPER = ENGINE_ROOT / "native" / "dart" / "analyzer.dart"
_HELPER_SHA256 = "f7dd0df7917e97a6e9b26f0534e7d56dcada5dfe89453a7f255e3e42641cb28e"
_HELPER_BYTES = 24_184
_MAX_SOURCE_BYTES = 2_000_000

_FLUTTER_VERSION = "3.44.1"
_FLUTTER_REVISION = "924134a44c189315be2148659913dda1671cbe99"
_FLUTTER_ENGINE_REVISION = "c416acfeb8126e097f758c664aaa3da929e27da0"
_DART_VERSION = "3.12.1"
_DART_EXECUTABLE_SHA256 = "657c6a1779596306b30c59e589762287ad75b5fd8f008c7873864622a8865152"
_DART_EXECUTABLE_BYTES = 3_884_832
_FLUTTER_TOOLS_LOCK_SHA256 = "1aa193fc5df798338a2ca97d1737450f9c2cc1984ec0095b2efbaa0f4dcad340"
_FLUTTER_TOOLS_LOCK_BYTES = 23_993

# name -> (versioned directory, language version, record count, bytes, tree digest)
# The 18 entries are analyzer 10.1.0's complete transitive runtime closure as
# resolved by Flutter 3.44.1's own flutter_tools lock.  Tests/dev files are
# intentionally included: a changed extracted package is drift even if the
# current helper does not import the changed file yet.
_PACKAGE_CLOSURE: dict[str, tuple[str, str, int, int, str]] = {
    "_fe_analyzer_shared": (
        "_fe_analyzer_shared-95.0.0",
        "3.9",
        570,
        4_410_715,
        "afa6a94154ca21bfb3fb6f79ff9907d15d957231cf793196d575c1ff78799424",
    ),
    "analyzer": (
        "analyzer-10.1.0",
        "3.9",
        1_839,
        49_854_004,
        "629d8bbe0174f298008bf48c4480230a646cc03987a36ad39e8ef7933ff1234d",
    ),
    "async": (
        "async-2.13.1",
        "3.4",
        91,
        478_151,
        "8dbfa2410941464548adbeae1abd3dc942d5420d757df7e54644af349251f368",
    ),
    "collection": (
        "collection-1.19.1",
        "3.4",
        61,
        411_675,
        "34bc748f45e27edb97ad4dcaf71defb16f2774997c6847b7892a211c9f984a56",
    ),
    "convert": (
        "convert-3.1.2",
        "3.4",
        38,
        96_917,
        "9afc2b71d1528b54da4b2ca928e8638559133164dca841ff17ed4350368c5dc7",
    ),
    "crypto": (
        "crypto-3.0.7",
        "3.4",
        37,
        1_179_048,
        "06d81be820ba8b3e272b3b0ab3038dd7404822ccac89fa8db0509a74c26087cf",
    ),
    "file": (
        "file-7.0.1",
        "3.0",
        72,
        335_990,
        "95771d661954a929d2e9a1069c9eddebfa60a134b0eedfe9f866c6d4011b70bb",
    ),
    "glob": (
        "glob-2.1.3",
        "3.3",
        19,
        90_977,
        "9daf3cbd8a073a54c51547112e6a11207a5339e2d8dfdeb8965090c9b70dade8",
    ),
    "meta": (
        "meta-1.18.0",
        "3.5",
        10,
        58_879,
        "db569031f416905ba7badc34c810d02c4260b5d125a7696fc196c67cecd3a6f7",
    ),
    "package_config": (
        "package_config-2.2.0",
        "3.4",
        30,
        158_749,
        "5c8a921bd504a8834aadab96bb661ba9e371f890ccfbb3fda47d0eff194f38f5",
    ),
    "path": (
        "path-1.9.1",
        "3.4",
        36,
        236_503,
        "9fb34b264ee7b4b090890945a7e29fdc0a7775e2f60b6db8bab20c81dcf038ca",
    ),
    "pub_semver": (
        "pub_semver-2.2.0",
        "3.4",
        22,
        137_633,
        "96aed36036640f80d9c3106c87fd2a45be029e51f9541cebba6a196540c3d163",
    ),
    "source_span": (
        "source_span-1.10.2",
        "3.1",
        29,
        145_150,
        "e6abfc825897383195a6ff547c92443a495e918d3e58a62dcc43a25f2dc15756",
    ),
    "string_scanner": (
        "string_scanner-1.4.1",
        "3.1",
        24,
        91_713,
        "fe656fb0964cc12ea7459bf5e11ce4b9fed5ba267125bb455d2e19094b5adba8",
    ),
    "term_glyph": (
        "term_glyph-1.2.2",
        "3.1",
        19,
        46_340,
        "a759f357d12e446568a4f0a11f964b3e9c0f57ef604f1b697704297536d83842",
    ),
    "typed_data": (
        "typed_data-1.4.0",
        "3.5",
        16,
        71_994,
        "4557c11dc0bc95fc03d5e37ca9320aa58b9958bad91c195143daf9a4c2da9511",
    ),
    "watcher": (
        "watcher-1.2.1",
        "3.4",
        81,
        243_717,
        "be6e6fcdac5ba260b4d54f98ec9b195b650689058149d4678690803b636eaef0",
    ),
    "yaml": (
        "yaml-3.1.3",
        "3.4",
        34,
        200_431,
        "02c89b528158b913fe39ca474825c0309e170bdfcc738389e76c4000eceaad6d",
    ),
}


def _stable_bytes(path: Path, failure: str, maximum: int) -> bytes:
    try:
        before = path.lstat()
        if (
            path.is_symlink()
            or not stat.S_ISREG(before.st_mode)
            or before.st_size <= 0
            or before.st_size > maximum
            or stat.S_IMODE(before.st_mode) & 0o022
        ):
            raise OSError(failure)
        content = path.read_bytes()
        after = path.lstat()
    except OSError as error:
        raise RouteError(failure) from error
    def identity(value: stat_result) -> tuple[int, ...]:
        return (
            value.st_dev,
            value.st_ino,
            value.st_mode,
            value.st_size,
            value.st_uid,
            value.st_gid,
            value.st_nlink,
            value.st_mtime_ns,
            value.st_ctime_ns,
        )
    if identity(before) != identity(after) or len(content) != before.st_size:
        raise RouteError(failure)
    return content


def _exact_file(path: Path, size: int, digest: str, failure: str) -> bytes:
    content = _stable_bytes(path, failure, size)
    if len(content) != size or hashlib.sha256(content).hexdigest() != digest:
        raise RouteError(failure)
    return content


def _tree_identity(root: Path) -> tuple[int, int, str]:
    try:
        resolved = root.resolve(strict=True)
    except OSError as error:
        raise RouteError("DART_ANALYZER_PACKAGE_CLOSURE_UNSAFE") from error
    if root.is_symlink() or resolved != root or not root.is_dir():
        raise RouteError("DART_ANALYZER_PACKAGE_CLOSURE_UNSAFE")
    records: list[dict[str, str | int]] = []
    byte_count = 0
    try:
        paths = sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix())
        for path in paths:
            relative = path.relative_to(root).as_posix()
            metadata = path.lstat()
            mode = stat.S_IMODE(metadata.st_mode)
            if stat.S_ISDIR(metadata.st_mode):
                records.append({"path": relative, "kind": "directory", "mode": mode})
            elif stat.S_ISREG(metadata.st_mode):
                content = _stable_bytes(path, "DART_ANALYZER_PACKAGE_CLOSURE_UNSAFE", 64 * 1024 * 1024)
                byte_count += len(content)
                records.append(
                    {
                        "path": relative,
                        "kind": "file",
                        "mode": mode,
                        "bytes": len(content),
                        "sha256": hashlib.sha256(content).hexdigest(),
                    }
                )
            else:
                # Package source is executable input. Symlinks and special
                # files are refused instead of expanding the trust root.
                raise RouteError("DART_ANALYZER_PACKAGE_CLOSURE_UNSAFE")
    except OSError as error:
        raise RouteError("DART_ANALYZER_PACKAGE_CLOSURE_UNSAFE") from error
    encoded = json.dumps(records, sort_keys=True, separators=(",", ":")).encode()
    return len(records), byte_count, hashlib.sha256(encoded).hexdigest()


def _file_uri_path(value: object) -> Path:
    if not isinstance(value, str):
        raise RouteError("DART_ANALYZER_PACKAGE_CONFIG_INVALID")
    parsed = urlparse(value)
    if parsed.scheme != "file" or parsed.netloc not in {"", "localhost"} or parsed.query or parsed.fragment:
        raise RouteError("DART_ANALYZER_PACKAGE_CONFIG_INVALID")
    path = Path(unquote(parsed.path))
    if not path.is_absolute():
        raise RouteError("DART_ANALYZER_PACKAGE_CONFIG_INVALID")
    return path


def _package_closure(flutter_root: Path) -> tuple[dict[str, Any], dict[str, tuple[int, int, str]]]:
    config_path = flutter_root / "packages" / "flutter_tools" / ".dart_tool" / "package_config.json"
    content = _stable_bytes(config_path, "DART_ANALYZER_PACKAGE_CONFIG_INVALID", 128 * 1024)
    try:
        config = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RouteError("DART_ANALYZER_PACKAGE_CONFIG_INVALID") from error
    if not isinstance(config, dict) or config.get("configVersion") != 2 or not isinstance(config.get("packages"), list):
        raise RouteError("DART_ANALYZER_PACKAGE_CONFIG_INVALID")
    by_name: dict[str, dict[str, Any]] = {}
    for raw in config["packages"]:
        if not isinstance(raw, dict) or not isinstance(raw.get("name"), str) or raw["name"] in by_name:
            raise RouteError("DART_ANALYZER_PACKAGE_CONFIG_INVALID")
        by_name[raw["name"]] = raw
    restricted: list[dict[str, str]] = []
    identities: dict[str, tuple[int, int, str]] = {}
    for name, (directory, language_version, records, byte_count, digest) in _PACKAGE_CLOSURE.items():
        raw = by_name.get(name)
        if (
            raw is None
            or raw.get("packageUri") != "lib/"
            or raw.get("languageVersion") != language_version
        ):
            raise RouteError(f"DART_ANALYZER_PACKAGE_CONFIG_MISMATCH:{name}")
        root = _file_uri_path(raw.get("rootUri"))
        if root.name != directory:
            raise RouteError(f"DART_ANALYZER_PACKAGE_VERSION_MISMATCH:{name}")
        observed = _tree_identity(root)
        if observed != (records, byte_count, digest):
            raise RouteError(f"DART_ANALYZER_PACKAGE_CLOSURE_CHANGED:{name}")
        identities[name] = observed
        restricted.append(
            {
                "name": name,
                "rootUri": root.as_uri(),
                "packageUri": "lib/",
                "languageVersion": language_version,
            }
        )
    return {"configVersion": 2, "packages": restricted}, identities


def _flutter_identity(toolchain: ExactToolchain) -> tuple[Path, Path]:
    if toolchain.language != "flutter" or toolchain.auxiliary is None:
        raise RouteError("EXACT_TOOLCHAIN_FLUTTER_DART_REQUIRED")
    try:
        flutter = Path(toolchain.executable).resolve(strict=True)
        flutter_root = flutter.parent.parent.resolve(strict=True)
        dart = Path(toolchain.auxiliary).resolve(strict=True)
    except OSError as error:
        raise RouteError("EXACT_TOOLCHAIN_FLUTTER_DART_REQUIRED") from error
    expected_dart = flutter_root / "bin" / "cache" / "dart-sdk" / "bin" / "dart"
    if (
        flutter != flutter_root / "bin" / "flutter"
        or dart != expected_dart
        or Path(toolchain.auxiliary) != dart
    ):
        raise RouteError("EXACT_TOOLCHAIN_FLUTTER_DART_PATH_MISMATCH")
    _exact_file(dart, _DART_EXECUTABLE_BYTES, _DART_EXECUTABLE_SHA256, "EXACT_TOOLCHAIN_DART_CHANGED")
    version_path = flutter_root / "bin" / "cache" / "flutter.version.json"
    try:
        version = json.loads(_stable_bytes(version_path, "EXACT_TOOLCHAIN_FLUTTER_VERSION_INVALID", 4_096))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RouteError("EXACT_TOOLCHAIN_FLUTTER_VERSION_INVALID") from error
    if not isinstance(version, dict) or (
        version.get("flutterVersion"),
        version.get("frameworkRevision"),
        version.get("engineRevision"),
        version.get("dartSdkVersion"),
    ) != (_FLUTTER_VERSION, _FLUTTER_REVISION, _FLUTTER_ENGINE_REVISION, _DART_VERSION):
        raise RouteError("EXACT_TOOLCHAIN_FLUTTER_VERSION_MISMATCH")
    _exact_file(
        flutter_root / "packages" / "flutter_tools" / "pubspec.lock",
        _FLUTTER_TOOLS_LOCK_BYTES,
        _FLUTTER_TOOLS_LOCK_SHA256,
        "DART_ANALYZER_PACKAGE_LOCK_CHANGED",
    )
    return flutter_root, dart


def _environment(home: Path, scratch: Path, dart: Path) -> dict[str, str]:
    value = sanitized_subprocess_env(
        home=home,
        temp_dir=scratch,
        executable_dirs=(dart.parent,),
    )
    value.update(
        {
            "DART_SUPPRESS_ANALYTICS": "true",
            "PUB_ENVIRONMENT": "elmos_polyglot_route",
        }
    )
    return value


def _run(
    command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    timeout: int = 180,
) -> subprocess.CompletedProcess[str]:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RouteError("DART_ANALYZER_PROCESS_FAILED") from error
    return completed


def _promote_failure(completed: subprocess.CompletedProcess[str]) -> None:
    detail = completed.stderr.strip()
    if (
        completed.returncode == 2
        and detail
        and "\n" not in detail
        and "\r" not in detail
        and len(detail) <= 500
        and (
            detail.startswith("DART_")
            or detail.startswith("FLUTTER_")
            or detail.startswith("FUNCTION_NOT_FOUND:")
        )
        and not detail.startswith("DART_ANALYZER_INTERNAL_FAILURE:")
    ):
        raise RouteError(detail)
    raise RouteError("DART_ANALYZER_FAILED")


def _invoke(
    source: Path,
    selector: str,
    toolchain: ExactToolchain,
    *,
    emitted_target: bool,
) -> dict[str, Any]:
    raw = source.expanduser()
    try:
        metadata = raw.lstat()
        resolved = raw.resolve(strict=True)
    except OSError as error:
        raise RouteError("SOURCE_FILE_UNSAFE_OR_TOO_LARGE") from error
    if (
        raw.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_size <= 0
        or metadata.st_size > _MAX_SOURCE_BYTES
        or stat.S_IMODE(metadata.st_mode) & 0o022
    ):
        raise RouteError("SOURCE_FILE_UNSAFE_OR_TOO_LARGE")
    source_bytes = _stable_bytes(resolved, "SOURCE_FILE_UNSAFE_OR_TOO_LARGE", _MAX_SOURCE_BYTES)
    helper_bytes = _exact_file(_HELPER, _HELPER_BYTES, _HELPER_SHA256, "DART_ANALYZER_SOURCE_CHANGED")
    flutter_root, dart = _flutter_identity(toolchain)
    restricted_config, closure_before = _package_closure(flutter_root)
    with tempfile.TemporaryDirectory(prefix="elmos-dart-analyzer-") as temporary:
        root = Path(temporary).resolve(strict=True)
        root.chmod(0o700)
        home = root / "home"
        scratch = root / "tmp"
        work = root / "work"
        for directory in (home, scratch, work):
            directory.mkdir(mode=0o700)
        snapshot = work / resolved.name
        snapshot.write_bytes(source_bytes)
        snapshot.chmod(0o400)
        helper = work / "analyzer.dart"
        helper.write_bytes(helper_bytes)
        helper.chmod(0o400)
        package_config = work / "package_config.json"
        package_config.write_text(json.dumps(restricted_config, sort_keys=True, separators=(",", ":")))
        package_config.chmod(0o400)
        environment = _environment(home, scratch, dart)

        # Run the AST boundary first so a Flutter import/Widget or another
        # explicitly unsupported construct retains its typed route diagnostic.
        # Only an AST-admitted, import-free pure module is handed to the SDK
        # analyzer in the isolated directory below.
        command = [
            str(dart),
            f"--packages={package_config}",
            str(helper),
            str(snapshot),
            selector,
        ]
        if emitted_target:
            command.append("--emitted-target")
        completed = _run(command, cwd=work, environment=environment)
        if completed.returncode != 0:
            _promote_failure(completed)
        if completed.stderr.strip() or len(completed.stdout.encode()) > 4 * 1024 * 1024:
            raise RouteError("DART_ANALYZER_OUTPUT_INVALID")
        try:
            value = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise RouteError("DART_ANALYZER_OUTPUT_INVALID") from error
        if not isinstance(value, dict):
            raise RouteError("DART_ANALYZER_OUTPUT_INVALID")
        if selector != "--inventory":
            static_check = _run(
                [str(dart), "analyze", "--fatal-infos", "--fatal-warnings", str(snapshot)],
                cwd=work,
                environment=environment,
            )
            if static_check.returncode != 0:
                raise RouteError("DART_STATIC_ANALYSIS_FAILED")
        if snapshot.read_bytes() != source_bytes or helper.read_bytes() != helper_bytes:
            raise RouteError("DART_ANALYZER_SNAPSHOT_CHANGED_DURING_EXECUTION")

    if _exact_file(_HELPER, _HELPER_BYTES, _HELPER_SHA256, "DART_ANALYZER_SOURCE_CHANGED") != helper_bytes:
        raise RouteError("DART_ANALYZER_SOURCE_CHANGED")
    if _package_closure(flutter_root)[1] != closure_before:
        raise RouteError("DART_ANALYZER_PACKAGE_CLOSURE_CHANGED_DURING_EXECUTION")
    if _stable_bytes(resolved, "SOURCE_FILE_UNSAFE_OR_TOO_LARGE", _MAX_SOURCE_BYTES) != source_bytes:
        raise RouteError("DART_SOURCE_CHANGED_DURING_EXECUTION")
    if selector == "--inventory":
        # Bind repository orchestration to the exact byte snapshot parsed by
        # the Dart helper.  Re-reading the caller path in inventory_flutter()
        # would leave a post-verification replacement window in which the
        # inventory described one file but its artifact digest named another.
        value["source_artifact_sha256"] = "sha256:" + hashlib.sha256(source_bytes).hexdigest()
        value["source_artifact_bytes"] = len(source_bytes)
    return value


def analyze_flutter(
    source: Path,
    function_name: str,
    toolchain: ExactToolchain,
    *,
    emitted_target: bool = False,
) -> SemanticIR:
    """Lift one bounded Dart function under the active ``flutter`` identity."""

    value = _invoke(source, function_name, toolchain, emitted_target=emitted_target)
    return SemanticIR.from_mapping(value)


def inventory_flutter(
    source: Path,
    toolchain: ExactToolchain,
    *,
    emitted_target: bool = False,
) -> dict[str, Any]:
    """Return the Dart AST module inventory for repository orchestration."""

    return _invoke(source, "--inventory", toolchain, emitted_target=emitted_target)


__all__ = ["analyze_flutter", "inventory_flutter"]

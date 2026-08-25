"""Exact, fail-closed React/TSX source analyzer for the route IR's pure slice.

React is a framework identity, not a synonym for TypeScript.  The active route
IR can represent typed pure functions only; it has no node for JSX, hooks,
effects, props, rendering or component lifecycle.  This frontend therefore
accepts only explicitly typed pure functions in a ``.tsx`` source and refuses
React UI semantics before lowering anything.

The parser is the repository's exact TypeScript 5.9.2 compiler frontend running
on the exact Node.js 26.0.0 toolchain.  The React 19.2.7 dependency tuple used by
``frontend-client-engine`` is verified by exact version, symlink target and
content tree, and the Node analyzer imports the real React and React DOM entry
points before parsing.  None of this is browser, renderer or certification
evidence; it is the local source-analyzer boundary only.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import RouteError, SemanticIR
from .toolchains import ExactToolchain, exact_toolchain, sanitized_subprocess_env

ENGINE_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_ENGINE_ROOT = ENGINE_ROOT.parent / "frontend-client-engine"
ANALYZER = ENGINE_ROOT / "native" / "react" / "analyzer.mjs"
ANALYZER_SHA256 = "e5e81537872c527f335479cddb929ad26cd2af8bc3b4dad0aa7da9644becd4b8"
ANALYZER_BYTES = 18_840
MAX_SOURCE_BYTES = 2_000_000
_RUNTIME_PROBE_SOURCE = """\
import { pathToFileURL } from "node:url";
const [reactPath, reactDomPath] = process.argv.slice(1);
if (!reactPath || !reactDomPath) throw new Error("REACT_RUNTIME_PROBE_ARGUMENTS_INVALID");
const reactModule = await import(pathToFileURL(reactPath).href);
const reactDomModule = await import(pathToFileURL(reactDomPath).href);
const reactVersion = reactModule.version ?? reactModule.default?.version;
const reactDomVersion = reactDomModule.version ?? reactDomModule.default?.version;
console.log(JSON.stringify({ react: reactVersion, "react-dom": reactDomVersion }));
"""
_RUNTIME_PROBE_SHA256 = hashlib.sha256(_RUNTIME_PROBE_SOURCE.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class _PackagePin:
    alias: Path
    link_target: str
    name: str
    version: str
    tree_sha256: str
    file_count: int
    byte_count: int
    runtime_entry: str | None = None


_PACKAGE_PINS = (
    _PackagePin(
        FRONTEND_ENGINE_ROOT / "node_modules" / "react",
        ".pnpm/react@19.2.7/node_modules/react",
        "react",
        "19.2.7",
        "72ee5c0b0835f78d5a88a4d62b6e8de13a0bd8d61fcf37eed00e7693e4f9a9a0",
        27,
        171_604,
        "index.js",
    ),
    _PackagePin(
        FRONTEND_ENGINE_ROOT / "node_modules" / "react-dom",
        ".pnpm/react-dom@19.2.7_react@19.2.7/node_modules/react-dom",
        "react-dom",
        "19.2.7",
        "47500a4b90c6e73b8c3b5f849ddd12ade3ca28f54ba83a2b9e95c903b16eded7",
        43,
        7_319_413,
        "index.js",
    ),
    _PackagePin(
        FRONTEND_ENGINE_ROOT / "node_modules" / "@types" / "react",
        "../.pnpm/@types+react@19.1.10/node_modules/@types/react",
        "@types/react",
        "19.1.10",
        "28dbd6484255ae39084a3d7014ef1110fdc02b656407991f536b3f931b79b3ac",
        24,
        806_683,
    ),
    _PackagePin(
        FRONTEND_ENGINE_ROOT / "node_modules" / "@types" / "react-dom",
        "../.pnpm/@types+react-dom@19.1.7_@types+react@19.1.10/node_modules/@types/react-dom",
        "@types/react-dom",
        "19.1.7",
        "02437f039d786fc99f4921e1726c766be33ef2bd61f12e147f2b0729aed737a9",
        17,
        24_378,
    ),
    _PackagePin(
        FRONTEND_ENGINE_ROOT / "node_modules" / "typescript",
        ".pnpm/typescript@5.9.2/node_modules/typescript",
        "typescript",
        "5.9.2",
        "c2e4c4d3914a9d8ac6ef5f95c483c371de7eb4380310c788fd05e1292005e0ea",
        132,
        23_622_869,
    ),
)


def _strict_json(path: Path, failure: str) -> dict[str, Any]:
    def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate key")
            value[key] = item
        return value

    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=no_duplicates)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise RouteError(failure) from error
    if type(value) is not dict:
        raise RouteError(failure)
    return value


def _tree_identity(root: Path, failure: str) -> dict[str, str | int]:
    """Hash one symlink-free package using the same canonical form as shasum."""

    try:
        root_metadata = root.lstat()
        if (
            stat.S_ISLNK(root_metadata.st_mode)
            or not stat.S_ISDIR(root_metadata.st_mode)
            or root_metadata.st_uid not in {0, os.getuid()}
            or stat.S_IMODE(root_metadata.st_mode) & 0o022
        ):
            raise RouteError(failure)
        paths = sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix())
        records: list[bytes] = []
        file_count = 0
        byte_count = 0
        for path in paths:
            relative = path.relative_to(root).as_posix()
            before = path.lstat()
            if stat.S_ISLNK(before.st_mode):
                raise RouteError(failure)
            if stat.S_ISDIR(before.st_mode):
                if before.st_uid not in {0, os.getuid()} or stat.S_IMODE(before.st_mode) & 0o022:
                    raise RouteError(failure)
                continue
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_uid not in {0, os.getuid()}
                or stat.S_IMODE(before.st_mode) & 0o022
                or before.st_nlink != 1
            ):
                raise RouteError(failure)
            content = path.read_bytes()
            after = path.lstat()
            if (
                before.st_dev,
                before.st_ino,
                before.st_mode,
                before.st_uid,
                before.st_gid,
                before.st_nlink,
                before.st_size,
                before.st_mtime_ns,
            ) != (
                after.st_dev,
                after.st_ino,
                after.st_mode,
                after.st_uid,
                after.st_gid,
                after.st_nlink,
                after.st_size,
                after.st_mtime_ns,
            ) or len(content) != before.st_size:
                raise RouteError(failure)
            digest = hashlib.sha256(content).hexdigest()
            records.append(f"{digest}  ./{relative}\n".encode())
            file_count += 1
            byte_count += len(content)
        root_after = root.lstat()
        if (
            root_metadata.st_dev,
            root_metadata.st_ino,
            root_metadata.st_mode,
            root_metadata.st_uid,
            root_metadata.st_gid,
            root_metadata.st_mtime_ns,
        ) != (
            root_after.st_dev,
            root_after.st_ino,
            root_after.st_mode,
            root_after.st_uid,
            root_after.st_gid,
            root_after.st_mtime_ns,
        ):
            raise RouteError(failure)
    except (OSError, ValueError) as error:
        raise RouteError(failure) from error
    return {
        "sha256": hashlib.sha256(b"".join(records)).hexdigest(),
        "file_count": file_count,
        "byte_count": byte_count,
    }


def _package_identity(pin: _PackagePin) -> dict[str, str | int]:
    failure = f"REACT_DEPENDENCY_CLOSURE_INVALID:{pin.name}"
    try:
        alias_before = pin.alias.lstat()
        target_before = pin.alias.readlink()
        resolved = pin.alias.resolve(strict=True)
        alias_after = pin.alias.lstat()
        target_after = pin.alias.readlink()
    except OSError as error:
        raise RouteError(failure) from error
    alias_identity = (
        alias_before.st_dev,
        alias_before.st_ino,
        alias_before.st_mode,
        alias_before.st_uid,
        alias_before.st_gid,
        alias_before.st_nlink,
        alias_before.st_mtime_ns,
    )
    if (
        not stat.S_ISLNK(alias_before.st_mode)
        or alias_before.st_uid not in {0, os.getuid()}
        or str(target_before) != pin.link_target
        or target_before != target_after
        or alias_identity
        != (
            alias_after.st_dev,
            alias_after.st_ino,
            alias_after.st_mode,
            alias_after.st_uid,
            alias_after.st_gid,
            alias_after.st_nlink,
            alias_after.st_mtime_ns,
        )
    ):
        raise RouteError(failure)
    pnpm_root = (FRONTEND_ENGINE_ROOT / "node_modules" / ".pnpm").resolve(strict=True)
    if not resolved.is_relative_to(pnpm_root):
        raise RouteError(failure)
    package = _strict_json(resolved / "package.json", failure)
    if package.get("name") != pin.name or package.get("version") != pin.version:
        raise RouteError(f"REACT_DEPENDENCY_VERSION_MISMATCH:{pin.name}")
    identity = _tree_identity(resolved, failure)
    expected = {
        "sha256": pin.tree_sha256,
        "file_count": pin.file_count,
        "byte_count": pin.byte_count,
    }
    if identity != expected:
        raise RouteError(failure)
    if pin.runtime_entry is not None:
        entry = (resolved / pin.runtime_entry).resolve(strict=True)
        if not entry.is_relative_to(resolved) or not entry.is_file():
            raise RouteError(failure)
    return {
        "name": pin.name,
        "version": pin.version,
        **identity,
        **({"runtime_entry": str((resolved / pin.runtime_entry).resolve())} if pin.runtime_entry else {}),
    }


def _dependency_receipt() -> tuple[dict[str, str | int], ...]:
    identities = tuple(_package_identity(pin) for pin in _PACKAGE_PINS)
    if [identity["name"] for identity in identities] != [pin.name for pin in _PACKAGE_PINS]:
        raise RouteError("REACT_DEPENDENCY_SET_INVALID")
    return identities


def react_dependency_receipt() -> tuple[dict[str, str | int], ...]:
    """Return the exact React/DOM/types/compiler closure for toolchain gates."""

    return _dependency_receipt()


def _runtime_probe_command(
    toolchain: ExactToolchain,
    dependency_receipt: tuple[dict[str, str | int], ...],
) -> list[str]:
    entries = {
        str(identity["name"]): str(identity["runtime_entry"])
        for identity in dependency_receipt
        if "runtime_entry" in identity
    }
    if set(entries) != {"react", "react-dom"}:
        raise RouteError("REACT_RUNTIME_ENTRY_SET_INVALID")
    return [
        toolchain.executable,
        "--input-type=module",
        "--eval",
        _RUNTIME_PROBE_SOURCE,
        entries["react"],
        entries["react-dom"],
    ]


def _runtime_probe_digest_payload(receipt: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in receipt.items() if key != "receipt_sha256"}


def validate_react_runtime_receipt(
    toolchain: ExactToolchain,
    receipt: dict[str, Any],
) -> dict[str, Any]:
    """Validate a local runtime-import receipt against current exact bytes."""

    expected_keys = {
        "schema_version",
        "kind",
        "status",
        "toolchain_language",
        "toolchain_version",
        "dependency_profile_sha256",
        "probe_source_sha256",
        "versions",
        "command",
        "stdout",
        "stderr",
        "browser_execution_status",
        "independent_verification_status",
        "certification_status",
        "receipt_sha256",
    }
    if set(receipt) != expected_keys:
        raise RouteError("REACT_RUNTIME_RECEIPT_SCHEMA_INVALID")
    payload = _runtime_probe_digest_payload(receipt)
    if receipt.get("receipt_sha256") != hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    ).hexdigest():
        raise RouteError("REACT_RUNTIME_RECEIPT_DIGEST_INVALID")
    dependencies = _dependency_receipt()
    stdout = receipt.get("stdout")
    if not isinstance(stdout, str) or len(stdout.encode("utf-8")) > 2_000:
        raise RouteError("REACT_RUNTIME_RECEIPT_STDOUT_INVALID")

    def no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate key")
            value[key] = item
        return value

    def reject_nonfinite(token: str) -> None:
        raise ValueError(f"non-finite value: {token}")

    try:
        observed_versions = json.loads(
            stdout,
            object_pairs_hook=no_duplicate_keys,
            parse_constant=reject_nonfinite,
        )
    except (json.JSONDecodeError, ValueError) as error:
        raise RouteError("REACT_RUNTIME_RECEIPT_STDOUT_INVALID") from error
    if observed_versions != receipt.get("versions"):
        raise RouteError("REACT_RUNTIME_RECEIPT_STDOUT_INVALID")
    if (
        toolchain.language != "react"
        or receipt.get("schema_version") != "1.0.0"
        or receipt.get("kind") != "elmos.react-runtime-import-receipt"
        or receipt.get("status") != "PASSED"
        or receipt.get("toolchain_language") != toolchain.language
        or receipt.get("toolchain_version") != toolchain.version
        or receipt.get("dependency_profile_sha256") != _profile_digest(dependencies)
        or receipt.get("probe_source_sha256") != _RUNTIME_PROBE_SHA256
        or receipt.get("versions") != {"react": "19.2.7", "react-dom": "19.2.7"}
        or receipt.get("command") != _runtime_probe_command(toolchain, dependencies)
        or receipt.get("stderr") != ""
        or receipt.get("browser_execution_status") != "NOT_RUN"
        or receipt.get("independent_verification_status") != "NOT_RUN"
        or receipt.get("certification_status") != "NOT_CERTIFIED"
    ):
        raise RouteError("REACT_RUNTIME_RECEIPT_INVALID")
    return dict(receipt)


def verify_react_runtime_import(toolchain: ExactToolchain) -> dict[str, Any]:
    """Import the exact React and React DOM runtime entries under pinned Node."""

    if toolchain.language != "react" or toolchain.version != (
        "React 19.2.7 / React DOM 19.2.7 / TypeScript 5.9.2 / Node 26.0.0"
    ):
        raise RouteError("REACT_RUNTIME_TOOLCHAIN_MISMATCH")
    dependency_before = _dependency_receipt()
    command = _runtime_probe_command(toolchain, dependency_before)
    try:
        with tempfile.TemporaryDirectory(prefix="elmos-react-runtime-probe-") as temporary:
            root = Path(temporary)
            root.chmod(0o700)
            home = root / "home"
            scratch = root / "tmp"
            home.mkdir(mode=0o700)
            scratch.mkdir(mode=0o700)
            completed = subprocess.run(
                command,
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
                env=sanitized_subprocess_env(
                    home=home,
                    temp_dir=scratch,
                    executable_dirs=(Path(toolchain.executable).resolve().parent,),
                ),
            )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RouteError("REACT_RUNTIME_IMPORT_NOT_PASSED") from error
    dependency_after = _dependency_receipt()
    if dependency_after != dependency_before:
        raise RouteError("REACT_DEPENDENCY_CHANGED_DURING_RUNTIME_PROBE")
    if completed.returncode != 0 or completed.stderr.strip():
        raise RouteError("REACT_RUNTIME_IMPORT_NOT_PASSED")
    if len(completed.stdout.encode("utf-8")) > 2_000:
        raise RouteError("REACT_RUNTIME_PROBE_OUTPUT_INVALID")
    try:
        versions = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RouteError("REACT_RUNTIME_PROBE_OUTPUT_INVALID") from error
    if versions != {"react": "19.2.7", "react-dom": "19.2.7"}:
        raise RouteError("REACT_RUNTIME_VERSION_MISMATCH")
    payload = {
        "schema_version": "1.0.0",
        "kind": "elmos.react-runtime-import-receipt",
        "status": "PASSED",
        "toolchain_language": toolchain.language,
        "toolchain_version": toolchain.version,
        "dependency_profile_sha256": _profile_digest(dependency_before),
        "probe_source_sha256": _RUNTIME_PROBE_SHA256,
        "versions": versions,
        "command": command,
        "stdout": completed.stdout[-2_000:],
        "stderr": completed.stderr[-2_000:],
        "browser_execution_status": "NOT_RUN",
        "independent_verification_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
    }
    receipt = {
        **payload,
        "receipt_sha256": hashlib.sha256(
            json.dumps(
                payload,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("ascii")
        ).hexdigest(),
    }
    return validate_react_runtime_receipt(toolchain, receipt)


def _analyzer_binding() -> tuple[int, str]:
    try:
        before = ANALYZER.lstat()
        content = ANALYZER.read_bytes()
        after = ANALYZER.lstat()
    except OSError as error:
        raise RouteError("REACT_ANALYZER_SOURCE_UNSAFE") from error
    if (
        ANALYZER.is_symlink()
        or not stat.S_ISREG(before.st_mode)
        or before.st_uid not in {0, os.getuid()}
        or stat.S_IMODE(before.st_mode) & 0o022
        or before.st_nlink != 1
        or before.st_size != ANALYZER_BYTES
        or len(content) != ANALYZER_BYTES
        or hashlib.sha256(content).hexdigest() != ANALYZER_SHA256
        or (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_uid,
            before.st_gid,
            before.st_nlink,
            before.st_size,
            before.st_mtime_ns,
        )
        != (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_uid,
            after.st_gid,
            after.st_nlink,
            after.st_size,
            after.st_mtime_ns,
        )
    ):
        raise RouteError("REACT_ANALYZER_SOURCE_UNSAFE")
    return len(content), hashlib.sha256(content).hexdigest()


def _typescript_parser(toolchain: ExactToolchain) -> Path:
    prefix = "typescript-package-root="
    values = [item[len(prefix) :] for item in toolchain.profile if item.startswith(prefix)]
    if len(values) != 1:
        raise RouteError("REACT_TYPESCRIPT_PROFILE_INVALID")
    root = Path(values[0])
    parser = root / "lib" / "typescript.js"
    try:
        resolved = parser.resolve(strict=True)
    except OSError as error:
        raise RouteError("REACT_TYPESCRIPT_PROFILE_INVALID") from error
    if resolved != parser or not resolved.is_relative_to(root) or not resolved.is_file():
        raise RouteError("REACT_TYPESCRIPT_PROFILE_INVALID")
    return parser


def _read_source(source: Path) -> tuple[bytes, tuple[int, ...]]:
    if source.suffix not in {".ts", ".tsx"} or source.is_symlink():
        raise RouteError("REACT_SOURCE_EXTENSION_UNSUPPORTED")
    try:
        before = source.lstat()
        content = source.read_bytes()
        after = source.lstat()
    except OSError as error:
        raise RouteError("REACT_SOURCE_FILE_UNSAFE_OR_TOO_LARGE") from error
    identity = (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_uid,
        before.st_gid,
        before.st_nlink,
        before.st_size,
        before.st_mtime_ns,
    )
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or before.st_size > MAX_SOURCE_BYTES
        or len(content) != before.st_size
        or identity
        != (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_uid,
            after.st_gid,
            after.st_nlink,
            after.st_size,
            after.st_mtime_ns,
        )
    ):
        raise RouteError("REACT_SOURCE_FILE_UNSAFE_OR_TOO_LARGE")
    return content, identity


def _source_unchanged(source: Path, content: bytes, identity: tuple[int, ...]) -> None:
    try:
        after = source.lstat()
        current = source.read_bytes()
    except OSError as error:
        raise RouteError("REACT_SOURCE_CHANGED_DURING_EXECUTION") from error
    observed = (
        after.st_dev,
        after.st_ino,
        after.st_mode,
        after.st_uid,
        after.st_gid,
        after.st_nlink,
        after.st_size,
        after.st_mtime_ns,
    )
    if observed != identity or current != content:
        raise RouteError("REACT_SOURCE_CHANGED_DURING_EXECUTION")


def _profile_digest(receipt: tuple[dict[str, str | int], ...]) -> str:
    portable = tuple(
        {key: value for key, value in identity.items() if key != "runtime_entry"}
        for identity in receipt
    )
    payload = json.dumps(portable, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def _run_react_frontend(
    source: Path,
    selector: str,
) -> tuple[dict[str, Any], tuple[dict[str, str | int], ...]]:
    """Run the sealed TS/TSX frontend once and return its dependency receipt."""

    if not selector or selector != selector.strip():
        raise RouteError("REACT_FUNCTION_NAME_INVALID")
    source = source.expanduser()
    content, source_identity = _read_source(source)
    toolchain = exact_toolchain("react")
    if toolchain.version != (
        "React 19.2.7 / React DOM 19.2.7 / TypeScript 5.9.2 / Node 26.0.0"
    ):
        raise RouteError("REACT_TYPESCRIPT_TOOLCHAIN_MISMATCH")
    parser = _typescript_parser(toolchain)
    analyzer_binding = _analyzer_binding()
    dependency_before = _dependency_receipt()
    runtime_entries = {
        str(identity["name"]): str(identity["runtime_entry"])
        for identity in dependency_before
        if "runtime_entry" in identity
    }
    try:
        with tempfile.TemporaryDirectory(prefix="elmos-react-analyzer-") as temporary:
            root = Path(temporary)
            root.chmod(0o700)
            home = root / "home"
            scratch = root / "tmp"
            home.mkdir(mode=0o700)
            scratch.mkdir(mode=0o700)
            snapshot = root / source.name
            snapshot.write_bytes(content)
            snapshot.chmod(0o600)
            command = [
                toolchain.executable,
                str(ANALYZER),
                str(parser),
                runtime_entries["react"],
                runtime_entries["react-dom"],
                str(snapshot),
                selector,
            ]
            try:
                completed = subprocess.run(
                    command,
                    cwd=root,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=60,
                    env=sanitized_subprocess_env(
                        home=home,
                        temp_dir=scratch,
                        executable_dirs=(Path(toolchain.executable).resolve().parent,),
                    ),
                )
            except (OSError, subprocess.TimeoutExpired) as error:
                raise RouteError("REACT_ANALYZER_PROCESS_FAILED") from error
    finally:
        _source_unchanged(source, content, source_identity)
        if _analyzer_binding() != analyzer_binding:
            raise RouteError("REACT_ANALYZER_SOURCE_CHANGED_DURING_EXECUTION")
        dependency_after = _dependency_receipt()
        if dependency_after != dependency_before:
            raise RouteError("REACT_DEPENDENCY_CHANGED_DURING_EXECUTION")
    if completed.returncode != 0:
        detail = completed.stderr.strip().splitlines()[-1] if completed.stderr.strip() else ""
        allowed = (
            "FUNCTION_NOT_FOUND",
            "REACT_",
        )
        if detail and any(detail == prefix or detail.startswith(prefix) for prefix in allowed):
            raise RouteError(detail)
        raise RouteError("REACT_ANALYZER_FAILED")
    if len(completed.stdout.encode("utf-8")) > MAX_SOURCE_BYTES or completed.stderr.strip():
        raise RouteError("REACT_ANALYZER_OUTPUT_INVALID")
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RouteError("REACT_ANALYZER_OUTPUT_INVALID") from error
    if type(value) is not dict:
        raise RouteError("REACT_ANALYZER_OUTPUT_INVALID")
    if value.get("source_file") != source.name or value.get("source_language") != "react":
        raise RouteError("REACT_ANALYZER_IDENTITY_INVALID")
    return value, dependency_before


def _emitted_target_analyzer_version(runtime_receipt: dict[str, Any]) -> str:
    return (
        "TypeScript 5.9.2 emitted-target / Node 26.0.0 / React 19.2.7 / "
        "React DOM 19.2.7;"
        f"dependency-profile-sha256={runtime_receipt['dependency_profile_sha256']};"
        f"runtime-receipt-sha256={runtime_receipt['receipt_sha256']}"
    )


def inventory_react_module(
    source: Path,
    *,
    emitted_target: bool = False,
) -> dict[str, Any]:
    """Enumerate TS/TSX source or a generated pure target exactly."""

    if emitted_target:
        runtime_receipt = verify_react_runtime_import(exact_toolchain("react"))
        # React target emission is deliberately the same typed TS/TSX pure
        # slice as TypeScript. Reuse its emitted-helper inventory so canonical
        # guard sources and signatures are checked byte-for-byte, then retain
        # React as the public target identity and bind the real runtime probe.
        from .native import inventory_module as inventory_native

        value = inventory_native(source, "typescript")
        value["source_language"] = "react"
        value["analyzer"] = "ELMOS React/TSX emitted-target inventory"
        value["analyzer_version"] = _emitted_target_analyzer_version(runtime_receipt)
        return value

    source = source.expanduser()
    content, _identity = _read_source(source)
    value, _receipt = _run_react_frontend(source, "--inventory")
    if (
        value.get("analyzer") != "TypeScript Compiler API TS/TSX / React dependency probe"
        or value.get("analyzer_version")
        != "TypeScript 5.9.2 / React 19.2.7 / React DOM 19.2.7"
    ):
        raise RouteError("REACT_ANALYZER_IDENTITY_INVALID")
    # Native inventory validation is language-neutral and supplies occurrence,
    # source-artifact and directive bindings used by repository discovery.
    from .native import _validated_module_inventory

    return _validated_module_inventory(value, "react", source.resolve(), content)


def analyze_react(source: Path, function_name: str, *, emitted_target: bool = False) -> SemanticIR:
    """Lift one exact React TS/TSX pure helper; UI semantics fail closed.

    Emitted targets use the same compiler-backed pure-slice frontend as source
    files. No broader React semantics are enabled: JSX, hooks, effects,
    components and module side effects remain rejected by the native frontend.
    """

    if emitted_target:
        runtime_receipt = verify_react_runtime_import(exact_toolchain("react"))
        # The TypeScript emitted-target frontend is the authoritative checker
        # for the shared canonical guard helpers and arithmetic rewrites. Its
        # SemanticIR is relabelled only after that exact check has passed and
        # after the real React/ReactDOM runtime entries have been imported.
        from .native import analyze as analyze_native

        semantic = analyze_native(
            source,
            "typescript",
            function_name,
            emitted_target=True,
        )
        value = semantic.to_mapping()
        value["source_language"] = "react"
        value["analyzer"] = "ELMOS React/TSX emitted-target analyzer"
        value["analyzer_version"] = _emitted_target_analyzer_version(runtime_receipt)
        return SemanticIR.from_mapping(value)
    value, dependency_before = _run_react_frontend(source, function_name)
    if (
        value.get("analyzer") != "TypeScript Compiler API TS/TSX / React dependency probe"
        or value.get("analyzer_version")
        != "TypeScript 5.9.2 / React 19.2.7 / React DOM 19.2.7"
    ):
        raise RouteError("REACT_ANALYZER_IDENTITY_INVALID")
    value["analyzer"] = "ELMOS React/TSX typed-pure source analyzer"
    value["analyzer_version"] = (
        "TypeScript 5.9.2 / Node 26.0.0 / React 19.2.7 / React DOM 19.2.7;"
        f"analyzer-sha256={ANALYZER_SHA256};dependency-profile-sha256={_profile_digest(dependency_before)}"
    )
    return SemanticIR.from_mapping(value)


__all__ = [
    "analyze_react",
    "inventory_react_module",
    "react_dependency_receipt",
    "validate_react_runtime_receipt",
    "verify_react_runtime_import",
]

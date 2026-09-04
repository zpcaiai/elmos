from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKED_LAUNCHER = ROOT / "scripts/batch35/validate_packed_route.py"
ENGINE_PROJECT = ROOT / "engines/polyglot-route-engine"
ENGINE_SOURCE_ROOT = ENGINE_PROJECT / "src/elmos_polyglot_route"
REFERENCE_ROUTE = ROOT / "routes/cpp-to-java"
REFERENCE_ENGINE_MANIFEST = (
    REFERENCE_ROUTE / "certification/formal-artifacts/engine-source-manifest.json"
)
REFERENCE_ENGINE_SOURCES = (
    REFERENCE_ROUTE / "certification/formal-artifacts/engine-sources"
)
_toolchain_root_value = os.environ.get(
    "ELMOS_POLYGLOT_ROUTE_TOOLCHAIN_ROOT", ""
).strip()
TOOLCHAIN_ROOT = (
    Path(_toolchain_root_value)
    if _toolchain_root_value
    else Path.home() / ".local/share/elmos/toolchains"
)
if not TOOLCHAIN_ROOT.is_absolute() or TOOLCHAIN_ROOT != Path(
    os.path.normpath(str(TOOLCHAIN_ROOT))
):
    raise RuntimeError(
        "ELMOS_POLYGLOT_ROUTE_TOOLCHAIN_ROOT must be absolute and normalized"
    )
AMBIENT_TYPESCRIPT_ROOT = TOOLCHAIN_ROOT / (
    "typescript/5.9.2/"
    "sha256-61c079831c707d58ee72cda08c279d3575f24f4d87f13d93aeed00b1d11a225a"
)
TYPESCRIPT_LAUNCHER_BYTES = b"#!/usr/bin/env node\nrequire('../lib/tsc.js')\n"
SCHEMA_RELATIVES = (
    "certification/replay/schemas/batch29/formal-input.schema.json",
    "certification/replay/schemas/batch29/identifier-plan.schema.json",
    ("certification/replay/schemas/batch29/formal-input-module-function.schema.json"),
)


def _load(path: Path, name: str) -> Any:
    parent = str(path.parent)
    inserted = parent not in sys.path
    if inserted:
        sys.path.insert(0, parent)
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if inserted:
            sys.path.remove(parent)


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _private_locked_interpreter() -> Path:
    """Bind tests to an explicit private uv venv without resolving its Python link."""

    executable = Path(os.path.abspath(sys.executable))
    if sys.version_info[:3] != (3, 12, 12):
        raise RuntimeError("packed replay test Python version is not 3.12.12")
    if executable.parent.name != "bin" or not executable.is_file():
        raise RuntimeError("packed replay test interpreter layout is invalid")
    venv_root = executable.parent.parent
    for forbidden_root in (
        ROOT.resolve(strict=True),
        ENGINE_PROJECT.resolve(strict=True),
    ):
        try:
            venv_root.resolve(strict=True).relative_to(forbidden_root)
        except ValueError:
            continue
        raise RuntimeError("packed replay test environment is inside repository")

    config = venv_root / "pyvenv.cfg"
    if config.exists():
        declared = os.environ.get("UV_PROJECT_ENVIRONMENT")
        if not declared or not Path(declared).is_absolute():
            raise RuntimeError("packed replay private uv environment is not declared")
        try:
            resolved_venv = venv_root.resolve(strict=True)
            if Path(declared).resolve(strict=True) != resolved_venv:
                raise RuntimeError("packed replay private uv environment differs")
            before = config.lstat()
            if config.is_symlink() or not stat.S_ISREG(before.st_mode):
                raise RuntimeError("packed replay pyvenv.cfg is not a regular file")
            config_bytes = config.read_bytes()
            after = config.lstat()
        except OSError as exc:
            raise RuntimeError(
                "packed replay private uv environment is unavailable"
            ) from exc
        stable_identity = (
            "st_dev",
            "st_ino",
            "st_mode",
            "st_nlink",
            "st_uid",
            "st_gid",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
        )
        if any(getattr(before, key) != getattr(after, key) for key in stable_identity):
            raise RuntimeError("packed replay pyvenv.cfg changed during read")
        try:
            fields = dict(
                line.split("=", 1)
                for line in config_bytes.decode("utf-8").splitlines()
                if "=" in line
            )
        except UnicodeDecodeError as exc:
            raise RuntimeError("packed replay pyvenv.cfg is not UTF-8") from exc
        normalized_fields = {
            key.strip(): value.strip() for key, value in fields.items()
        }
        expected_fields = {
            "implementation": "CPython",
            "uv": "0.11.16",
            "version_info": "3.12.12",
            "include-system-site-packages": "false",
        }
        if any(
            normalized_fields.get(key) != value
            for key, value in expected_fields.items()
        ):
            raise RuntimeError("packed replay pyvenv.cfg identity differs")
    return executable


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_reference_source(
    path: Path,
    *,
    expected_digest: str,
    expected_bytes: int,
) -> bytes:
    try:
        before = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(before.st_mode):
            raise RuntimeError(f"reference runtime source is not regular: {path}")
        content = path.read_bytes()
        after = path.lstat()
    except OSError as exc:
        raise RuntimeError(f"reference runtime source is unavailable: {path}") from exc
    stable_identity = (
        "st_dev",
        "st_ino",
        "st_mode",
        "st_nlink",
        "st_uid",
        "st_gid",
        "st_size",
        "st_mtime_ns",
        "st_ctime_ns",
    )
    if any(getattr(before, key) != getattr(after, key) for key in stable_identity):
        raise RuntimeError(f"reference runtime source changed during read: {path}")
    if len(content) != expected_bytes:
        raise RuntimeError(f"reference runtime source byte count differs: {path}")
    if "sha256:" + hashlib.sha256(content).hexdigest() != expected_digest:
        raise RuntimeError(f"reference runtime source digest differs: {path}")
    return content


@lru_cache(maxsize=1)
def _reference_runtime_fixture() -> tuple[
    dict[str, Any],
    dict[str, tuple[bytes, str]],
]:
    launcher = _load(PACKED_LAUNCHER, "packed_reference_runtime_launcher")
    if (
        REFERENCE_ENGINE_MANIFEST.is_symlink()
        or not REFERENCE_ENGINE_MANIFEST.is_file()
    ):
        raise RuntimeError("reference engine source manifest is not a regular file")
    try:
        reference_source_root = REFERENCE_ENGINE_SOURCES.resolve(strict=True)
    except OSError as exc:
        raise RuntimeError("reference engine source root is unavailable") from exc
    if REFERENCE_ENGINE_SOURCES.is_symlink() or not reference_source_root.is_dir():
        raise RuntimeError("reference engine source root is not a regular directory")
    source_manifest = launcher.load_json(REFERENCE_ENGINE_MANIFEST)
    expected = launcher.validate_runtime_source_receipts(source_manifest)
    files = source_manifest.get("files")
    if not isinstance(files, list):
        raise RuntimeError("reference engine source manifest file set is invalid")
    entries: dict[str, dict[str, Any]] = {}
    for entry in files:
        if not isinstance(entry, dict):
            raise RuntimeError("reference engine source manifest entry is invalid")
        repository_path = entry.get("repository_path")
        if repository_path not in expected:
            continue
        if repository_path in entries:
            raise RuntimeError("reference engine runtime source is duplicated")
        entries[repository_path] = entry
    if set(entries) != set(expected):
        raise RuntimeError("reference engine runtime source set is incomplete")

    runtime_sources: dict[str, tuple[bytes, str]] = {}
    launcher_repository_path = launcher.TYPESCRIPT_CAPTURED_ROOT_RELATIVE + "/bin/tsc"
    for repository_path, (
        expected_digest,
        expected_bytes,
        expected_mode,
    ) in expected.items():
        entry = entries[repository_path]
        if set(entry) != {
            "repository_path",
            "captured_path",
            "sha256",
            "bytes",
        }:
            raise RuntimeError("reference engine runtime source entry is not exact")
        if (
            entry.get("captured_path")
            != launcher.ENGINE_SOURCE_PREFIX + repository_path
            or entry.get("sha256") != expected_digest
            or entry.get("bytes") != expected_bytes
        ):
            raise RuntimeError("reference engine runtime source binding differs")
        if repository_path == launcher_repository_path:
            content = TYPESCRIPT_LAUNCHER_BYTES
            if len(content) != 45:
                raise RuntimeError("synthetic TypeScript launcher byte count differs")
            if "sha256:" + hashlib.sha256(content).hexdigest() != expected_digest:
                raise RuntimeError("synthetic TypeScript launcher digest differs")
        else:
            source_candidate = REFERENCE_ENGINE_SOURCES / repository_path
            try:
                if source_candidate.is_symlink():
                    raise RuntimeError("reference runtime source is a symbolic link")
                source_path = source_candidate.resolve(strict=True)
                source_path.relative_to(reference_source_root)
            except (OSError, ValueError) as exc:
                raise RuntimeError(
                    "reference runtime source escapes the frozen source root"
                ) from exc
            content = _read_reference_source(
                source_path,
                expected_digest=expected_digest,
                expected_bytes=expected_bytes,
            )
        runtime_sources[repository_path] = (content, expected_mode)

    receipts = source_manifest.get("runtime_source_receipts")
    if not isinstance(receipts, dict):
        raise RuntimeError("reference runtime source receipts are invalid")
    return receipts, runtime_sources


def _artifact_ref(route: Path, relative: str, role: str) -> dict[str, object]:
    path = route / relative
    return {
        "artifact_id": "artifact-" + hashlib.sha256(relative.encode()).hexdigest(),
        "role": role,
        "path": relative,
        "sha256": _digest(path),
        "bytes": path.stat().st_size,
    }


def _refresh_formal_bindings(route: Path, relatives: set[str]) -> None:
    formal_path = route / "certification/formal-equivalence.json"
    formal = json.loads(formal_path.read_text(encoding="utf-8"))
    for reference in formal["artifact_refs"]:
        relative = reference["path"]
        if relative in relatives:
            path = route / relative
            reference["sha256"] = _digest(path)
            reference["bytes"] = path.stat().st_size
    _write_json(formal_path, formal)
    certification_path = route / "certification/certification.json"
    certification = json.loads(certification_path.read_text(encoding="utf-8"))
    certification["formal_equivalence"].update(
        {
            "sha256": _digest(formal_path),
            "bytes": formal_path.stat().st_size,
        }
    )
    _write_json(certification_path, certification)


def _build_isolated_module_pack(
    route: Path,
    *,
    real_node_relift: bool = False,
    private_closure_tamper: bool = False,
) -> None:
    launcher = _load(PACKED_LAUNCHER, "isolated_packed_route_launcher")
    launcher_relative = "certification/replay/validate_packed_route.py"
    validator_relative = "certification/replay/scripts/batch29/validate_route.py"
    validator_source = (
        "def validate_formal_equivalence(route, manifest, certification):\n"
        "    return {'status': 'PASSED'}, []\n\n"
        "def validate_packed_module_equivalence(route, manifest, certification):\n"
        "    reference = certification.get('module_equivalence')\n"
        "    if not isinstance(reference, dict):\n"
        "        return {}, ['module reference missing']\n"
        "    return {'status': 'PASSED'}, []\n"
    )
    if real_node_relift:
        validator_source = (
            "from pathlib import Path\n\n"
            "def validate_formal_equivalence(route, manifest, certification):\n"
            "    return {'status': 'PASSED'}, []\n\n"
            "def validate_packed_module_equivalence(route, manifest, certification):\n"
            "    from elmos_polyglot_route import native, toolchains\n"
            "    source = route / 'certification/fixtures/source.mjs'\n"
            "    target = route / 'certification/fixtures/target.ts'\n"
            "    source_ir = native.analyze(source, 'javascript', 'identity')\n"
            "    target_ir = native.analyze(\n"
            "        target, 'typescript', 'identity', emitted_target=True\n"
            "    )\n"
            "    receipt = toolchains.typescript_parser_receipt()\n"
            f"    ambient = Path({str(AMBIENT_TYPESCRIPT_ROOT)!r})\n"
            "    private_root = Path(str(receipt['compiler_root']))\n"
            "    valid = (\n"
            "        source_ir.functions[0].name == 'identity'\n"
            "        and target_ir.functions[0].name == 'identity'\n"
            "        and private_root != ambient\n"
            "        and not private_root.is_relative_to(route)\n"
            "        and (private_root.parent.stat().st_mode & 0o7777) == 0o700\n"
            "        and receipt['path'] == str(private_root / 'lib/typescript.js')\n"
            "        and receipt['compiler_closure_sha256']\n"
            "            == 'aaab28fada5888d767a49f86d40e5a0c9073b23412257ccb3755e9c8fb8080d9'\n"
            "    )\n"
            "    if not valid:\n"
            "        return {}, ['private JavaScript/TypeScript relift binding failed']\n"
            "    return {'status': 'PASSED'}, []\n"
        )
    elif private_closure_tamper:
        validator_source = (
            "from pathlib import Path\n\n"
            "def validate_formal_equivalence(route, manifest, certification):\n"
            "    return {'status': 'PASSED'}, []\n\n"
            "def validate_packed_module_equivalence(route, manifest, certification):\n"
            "    from elmos_polyglot_route import toolchains\n"
            "    parser = Path(str(toolchains.typescript_parser_receipt()['path']))\n"
            "    content = bytearray(parser.read_bytes())\n"
            "    content[0] ^= 1\n"
            "    parser.chmod(0o600)\n"
            "    parser.write_bytes(bytes(content))\n"
            "    parser.chmod(0o444)\n"
            "    return {'status': 'PASSED'}, []\n"
        )
    replay_files = {
        launcher_relative: (PACKED_LAUNCHER, "replay-tool"),
        validator_relative: (None, "replay-tool"),
        (
            "certification/replay/schemas/batch29/"
            "formal-equivalence-evidence.schema.json"
        ): (
            ROOT / "schemas/batch29/formal-equivalence-evidence.schema.json",
            "replay-schema",
        ),
        SCHEMA_RELATIVES[0]: (
            ROOT / "schemas/batch29/formal-input.schema.json",
            "replay-schema",
        ),
        SCHEMA_RELATIVES[1]: (
            ROOT / "schemas/batch29/identifier-plan.schema.json",
            "replay-schema",
        ),
        (
            "certification/replay/schemas/batch29/"
            "module-equivalence-evidence.schema.json"
        ): (
            ROOT / "schemas/batch29/module-equivalence-evidence.schema.json",
            "replay-schema",
        ),
        ("certification/replay/schemas/batch29/module-case-manifest.schema.json"): (
            ROOT / "schemas/batch29/module-case-manifest.schema.json",
            "replay-schema",
        ),
        SCHEMA_RELATIVES[2]: (
            ROOT / "schemas/batch29/formal-input-module-function.schema.json",
            "replay-schema",
        ),
    }
    for relative, (source, _role) in replay_files.items():
        destination = route / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source is None:
            destination.write_text(validator_source, encoding="utf-8")
        else:
            shutil.copy2(source, destination)

    engine_sources: list[tuple[str, Path | str]] = []
    if real_node_relift:
        engine_sources.extend(
            (
                source.relative_to(ROOT).as_posix(),
                (
                    "# isolated captured engine package\n"
                    if source.name == "__init__.py"
                    else source
                ),
            )
            for source in sorted(ENGINE_SOURCE_ROOT.glob("*.py"))
        )
        engine_sources.extend(
            (source.relative_to(ROOT).as_posix(), source)
            for native_root in (
                ENGINE_PROJECT / "native/javascript",
                ENGINE_PROJECT / "native/typescript",
            )
            for source in sorted(native_root.rglob("*"))
            if source.is_file() and not source.is_symlink()
        )
    else:
        engine_sources.extend(
            (
                source.relative_to(ROOT).as_posix(),
                source,
            )
            for source in (
                ENGINE_SOURCE_ROOT / "models.py",
                ENGINE_SOURCE_ROOT / "toolchains.py",
            )
        )
        engine_sources.extend(
            [
                (
                    "engines/polyglot-route-engine/src/"
                    "elmos_polyglot_route/__init__.py",
                    "# isolated captured engine package\n",
                ),
                (
                    "engines/polyglot-route-engine/src/elmos_polyglot_route/native.py",
                    "from .toolchains import typescript_parser_receipt\n",
                ),
            ]
        )
    engine_entries: list[dict[str, Any]] = []
    engine_source_relatives: list[str] = []
    for repository_path, engine_source_value in sorted(engine_sources):
        captured_relative = launcher.ENGINE_SOURCE_PREFIX + repository_path
        captured = route / captured_relative
        captured.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(engine_source_value, Path):
            shutil.copy2(engine_source_value, captured)
        else:
            captured.write_text(engine_source_value, encoding="utf-8")
        engine_source_relatives.append(captured_relative)
        engine_entries.append(
            {
                "repository_path": repository_path,
                "captured_path": captured_relative,
                "sha256": _digest(captured),
                "bytes": captured.stat().st_size,
            }
        )
    if real_node_relift:
        fixture_root = route / "certification/fixtures"
        fixture_root.mkdir(parents=True, exist_ok=True)
        (fixture_root / "source.mjs").write_text(
            "/** @param {integer} value @returns {number} */\n"
            "export function identity(value) { return value; }\n",
            encoding="utf-8",
        )
        (fixture_root / "target.ts").write_text(
            "function _elmosRequireSafeInteger(value: number): number {\n"
            "  if (!Number.isSafeInteger(value)) {\n"
            "    throw new RangeError(`ELMOS_INTEGER_NOT_SAFE:${value}`);\n"
            "  }\n"
            "  return Object.is(value, -0) ? 0 : value;\n"
            "}\n"
            "function _elmosRequireFiniteNumber(value: number): number {\n"
            '  if (typeof value !== "number" || !Number.isFinite(value)) {\n'
            '    throw new TypeError("ELMOS_NUMBER_NOT_FINITE");\n'
            "  }\n"
            "  return value;\n"
            "}\n"
            "export function identity(value: number): number {\n"
            "  value = _elmosRequireSafeInteger(value);\n"
            "  return _elmosRequireFiniteNumber(value);\n"
            "}\n",
            encoding="utf-8",
        )
    runtime_entries: list[dict[str, Any]] = []
    runtime_receipts, runtime_sources = _reference_runtime_fixture()
    for repository_path, (content, expected_mode) in runtime_sources.items():
        captured_relative = launcher.ENGINE_SOURCE_PREFIX + repository_path
        captured = route / captured_relative
        captured.parent.mkdir(parents=True, exist_ok=True)
        captured.write_bytes(content)
        captured.chmod(int(expected_mode, 8))
        observed = captured.lstat()
        if (
            captured.is_symlink()
            or not stat.S_ISREG(observed.st_mode)
            or observed.st_nlink != 1
            or stat.S_IMODE(observed.st_mode) != int(expected_mode, 8)
        ):
            raise RuntimeError("captured runtime source mode or type differs")
        if captured.read_bytes() != content:
            raise RuntimeError("captured runtime source bytes differ")
        runtime_entries.append(
            {
                "repository_path": repository_path,
                "captured_path": captured_relative,
                "sha256": _digest(captured),
                "bytes": captured.stat().st_size,
            }
        )
    engine_manifest_relative = (
        "certification/formal-artifacts/engine-source-manifest.json"
    )
    engine_entries.extend(runtime_entries)
    _write_json(
        route / engine_manifest_relative,
        {
            "schema_version": 1,
            "kind": "polyglot-route-engine-source-bundle",
            "file_count": len(engine_entries),
            "files": engine_entries,
            "runtime_source_receipts": runtime_receipts,
        },
    )
    solver_relative = "certification/artifacts/solver-result.json"
    _write_json(route / solver_relative, {"status": "PROVED_UNDER_ASSUMPTIONS"})
    module_relative = "certification/module-equivalence.json"
    _write_json(route / module_relative, {"status": "PASSED"})

    references = [
        _artifact_ref(route, relative, role)
        for relative, (_source, role) in replay_files.items()
    ]
    references.extend(
        (
            _artifact_ref(route, engine_manifest_relative, "engine-source-manifest"),
            *(
                _artifact_ref(route, relative, "engine-source")
                for relative in engine_source_relatives
            ),
            *(
                _artifact_ref(
                    route,
                    launcher.ENGINE_SOURCE_PREFIX + repository_path,
                    "engine-source",
                )
                for repository_path in runtime_sources
            ),
            _artifact_ref(route, solver_relative, "solver-result"),
        )
    )
    formal_relative = "certification/formal-equivalence.json"
    solver_digest = _digest(route / solver_relative)
    _write_json(
        route / formal_relative,
        {
            "artifact_refs": references,
            "formal_proof": {
                "replay": {
                    "expected_result_artifact_id": _artifact_ref(
                        route, solver_relative, "solver-result"
                    )["artifact_id"],
                    "expected_result_sha256": solver_digest,
                }
            },
        },
    )
    _write_json(
        route / "route.json",
        {
            "route_key": "cpp-to-objc",
            "source": {"language": "cpp"},
            "target": {"language": "objc"},
        },
    )
    _write_json(
        route / "certification/certification.json",
        {
            "formal_equivalence": {
                "path": formal_relative,
                "sha256": _digest(route / formal_relative),
                "bytes": (route / formal_relative).stat().st_size,
            },
            "module_equivalence": {
                "path": module_relative,
                "sha256": _digest(route / module_relative),
                "bytes": (route / module_relative).stat().st_size,
            },
        },
    )


def _run_pack(
    route: Path,
    *,
    real_node_relift: bool = False,
) -> subprocess.CompletedProcess[str]:
    isolated_python = (
        _private_locked_interpreter() if real_node_relift else Path("/usr/bin/python3")
    )
    assert isolated_python.is_file()
    command = [
        str(isolated_python),
        "-I",
        *(["-S"] if real_node_relift else []),
        "-B",
        str(route / "certification/replay/validate_packed_route.py"),
        "--route",
        str(route),
    ]
    if real_node_relift:
        profile = (
            "(version 1)\n"
            "(allow default)\n"
            f'(deny file-read* (subpath "{AMBIENT_TYPESCRIPT_ROOT}"))\n'
            f'(deny file-read* (subpath "{ENGINE_PROJECT}"))\n'
            f'(deny file-read* (subpath "{REFERENCE_ENGINE_SOURCES}"))\n'
        )
        command = ["/usr/bin/sandbox-exec", "-p", profile, *command]
    return subprocess.run(
        command,
        cwd=route,
        check=False,
        capture_output=True,
        text=True,
        timeout=120 if real_node_relift else 30,
    )


def test_packed_replay_constants_bind_all_identifier_schemas() -> None:
    campaign = _load(
        ROOT / "scripts/batch35/validate_formal_route_campaign.py",
        "packed_campaign_validator",
    )
    launcher = _load(PACKED_LAUNCHER, "packed_route_launcher")
    base_generator = _load(
        ROOT / "tooling/generate_polyglot_formal_verification_pack.py",
        "base_pack_generator",
    )
    specialized_generator = _load(
        ROOT / "tooling/generate_specialized_polyglot_formal_verification_pack.py",
        "specialized_pack_generator",
    )
    campaign_paths = {
        specification["relative"]
        for specification in (
            *campaign.PACKED_REPLAY_FILES.values(),
            *campaign.PACKED_MODULE_REPLAY_FILES.values(),
        )
    }
    assert len(campaign.PACKED_REPLAY_FILES) == 3
    assert len(campaign.PACKED_MODULE_REPLAY_FILES) == 5
    assert set(SCHEMA_RELATIVES) <= campaign_paths
    assert len(launcher.REQUIRED_REPLAY_FILES) == 3
    assert len(launcher.MODULE_REPLAY_FILES) == 5
    assert set(SCHEMA_RELATIVES) <= set(launcher.REQUIRED_REPLAY_FILES) | set(
        launcher.MODULE_REPLAY_FILES
    )
    assert len(base_generator.PACKED_REPLAY_FILES) == 3
    assert not set(SCHEMA_RELATIVES) & set(base_generator.PACKED_REPLAY_FILES)
    assert len(specialized_generator.PACKED_REPLAY_FILES) == 8
    assert set(SCHEMA_RELATIVES) <= set(specialized_generator.PACKED_REPLAY_FILES)


def test_reference_pack_preserves_frozen_swift_component_read_bound() -> None:
    captured_validator = (
        REFERENCE_ENGINE_SOURCES / "scripts/batch29/validate_route.py"
    ).read_text(encoding="utf-8")
    assert "if total > 250_000_000:" in captured_validator
    assert "SWIFT_BUILD_CLOSURE_COMPONENT_MAXIMUM_BYTES" not in captured_validator


def test_private_locked_interpreter_rejects_repository_venv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "repo"
    engine_project = repository / "engines/polyglot-route-engine"
    venv = engine_project / ".venv"
    interpreter = venv / "bin/python"
    interpreter.parent.mkdir(parents=True)
    interpreter.write_bytes(b"fixture interpreter\n")
    (venv / "pyvenv.cfg").write_text(
        "implementation = CPython\n"
        "uv = 0.11.16\n"
        "version_info = 3.12.12\n"
        "include-system-site-packages = false\n",
        encoding="utf-8",
    )
    monkeypatch.setitem(globals(), "ROOT", repository)
    monkeypatch.setitem(globals(), "ENGINE_PROJECT", engine_project)
    monkeypatch.setattr(sys, "executable", str(interpreter))
    monkeypatch.setenv("UV_PROJECT_ENVIRONMENT", str(venv))
    with pytest.raises(
        RuntimeError,
        match="packed replay test environment is inside repository",
    ):
        _private_locked_interpreter()


def _private_typescript_identity_fixture(
    root: Path,
) -> tuple[Path, dict[str, object]]:
    private_root = root / "typescript-5.9.2"
    binary = private_root / "bin"
    library = private_root / "lib"
    binary.mkdir(parents=True)
    library.mkdir()
    parser = library / "typescript.js"
    content = b"parser-private-closure\n"
    parser.write_bytes(content)
    parser.chmod(0o444)
    binary.chmod(0o555)
    library.chmod(0o555)
    private_root.chmod(0o555)
    package_metadata = private_root.lstat()
    manifest: dict[str, object] = {
        "schema_version": 2,
        "kind": "elmos.typescript-5.9.2-full-stdlib-compiler-closure",
        "package_root": {
            "root": str(private_root),
            "mode": "0555",
            "uid": package_metadata.st_uid,
            "gid": package_metadata.st_gid,
            "nlink": package_metadata.st_nlink,
        },
        "directories": [
            {
                "relative_path": relative,
                "resolved_path": str(private_root / relative),
                "mode": "0555",
                "uid": (private_root / relative).lstat().st_uid,
                "gid": (private_root / relative).lstat().st_gid,
                "nlink": (private_root / relative).lstat().st_nlink,
            }
            for relative in ("bin", "lib")
        ],
        "files": [
            {
                "role": "parser",
                "resolved_path": str(parser),
                "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
                "mode": "0444",
                "uid": parser.lstat().st_uid,
                "gid": parser.lstat().st_gid,
                "nlink": parser.lstat().st_nlink,
            }
        ],
        "semantic_soundness": "NOT_RUN",
    }
    return private_root, manifest


def _restore_private_typescript_fixture(private_root: Path) -> None:
    parser = private_root / "lib/typescript.js"
    if parser.exists() and not parser.is_symlink():
        parser.chmod(0o644)
    for directory in (private_root / "bin", private_root / "lib", private_root):
        if directory.exists() and not directory.is_symlink():
            directory.chmod(0o755)


def test_private_typescript_identity_canonicalizes_live_private_ownership(
    tmp_path: Path,
) -> None:
    launcher = _load(PACKED_LAUNCHER, "packed_cross_user_typescript_launcher")
    private_root, manifest = _private_typescript_identity_fixture(tmp_path)
    observed: dict[str, object] = {}

    def identity(canonical: dict[str, object]) -> dict[str, object]:
        observed.update(canonical)
        encoded = json.dumps(
            canonical, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        files = canonical["files"]
        assert isinstance(files, list)
        return {
            "manifest": canonical,
            "sha256": hashlib.sha256(encoded).hexdigest(),
            "file_count": len(files),
            "bytes": sum(int(item["bytes"]) for item in files),
        }

    try:
        result = launcher._canonical_private_typescript_identity(
            identity,
            private_root,
            manifest,
        )
    finally:
        _restore_private_typescript_fixture(private_root)

    package = observed["package_root"]
    directories = observed["directories"]
    files = observed["files"]
    assert isinstance(package, dict)
    assert isinstance(directories, list)
    assert isinstance(files, list)
    assert (package["uid"], package["gid"], package["nlink"]) == (501, 20, 6)
    assert [(item["uid"], item["gid"], item["nlink"]) for item in directories] == [
        (501, 20, 3),
        (501, 20, 107),
    ]
    assert (files[0]["uid"], files[0]["gid"], files[0]["nlink"]) == (501, 20, 1)
    assert result["sha256"] == hashlib.sha256(
        json.dumps(observed, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    original_package = manifest["package_root"]
    assert isinstance(original_package, dict)
    assert original_package["uid"] == os.getuid()


@pytest.mark.parametrize("forgery", ["package", "directory", "file"])
def test_private_typescript_identity_rejects_forged_live_manifest(
    tmp_path: Path,
    forgery: str,
) -> None:
    launcher = _load(PACKED_LAUNCHER, f"packed_forged_typescript_{forgery}")
    private_root, manifest = _private_typescript_identity_fixture(tmp_path)
    package = manifest["package_root"]
    directories = manifest["directories"]
    files = manifest["files"]
    assert isinstance(package, dict)
    assert isinstance(directories, list)
    assert isinstance(files, list)
    if forgery == "package":
        package["nlink"] = int(package["nlink"]) + 1
    elif forgery == "directory":
        directories[0]["uid"] = int(directories[0]["uid"]) + 1
    else:
        files[0]["sha256"] = "0" * 64
    callback_called = False

    def identity(_canonical: dict[str, object]) -> dict[str, object]:
        nonlocal callback_called
        callback_called = True
        return {}

    try:
        with pytest.raises(ValueError, match="private TypeScript"):
            launcher._canonical_private_typescript_identity(
                identity,
                private_root,
                manifest,
            )
    finally:
        _restore_private_typescript_fixture(private_root)
    assert callback_called is False


def test_isolated_packed_module_replay_binds_all_schemas(tmp_path: Path) -> None:
    route = tmp_path / "route"
    _build_isolated_module_pack(route)
    completed = _run_pack(route)
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["status"] == "PASSED"
    assert result["route_key"] == "cpp-to-objc"


def test_private_route_typescript_closure_drives_real_javascript_to_typescript_relift(
    tmp_path: Path,
) -> None:
    route = tmp_path / "route"
    _build_isolated_module_pack(route, real_node_relift=True)
    completed = _run_pack(route, real_node_relift=True)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["status"] == "PASSED"


def test_private_route_typescript_closure_rejects_post_launch_tamper(
    tmp_path: Path,
) -> None:
    route = tmp_path / "route"
    _build_isolated_module_pack(route, private_closure_tamper=True)
    completed = _run_pack(route)
    assert completed.returncode == 2
    result = json.loads(completed.stderr)
    assert result["status"] == "FAILED"
    assert "TYPESCRIPT" in result["error"].upper()


@pytest.mark.parametrize("missing_relative", SCHEMA_RELATIVES)
def test_isolated_packed_module_replay_rejects_each_missing_schema(
    tmp_path: Path,
    missing_relative: str,
) -> None:
    route = tmp_path / "route"
    _build_isolated_module_pack(route)
    (route / missing_relative).unlink()
    completed = _run_pack(route)
    assert completed.returncode == 2
    result = json.loads(completed.stderr)
    assert result["status"] == "FAILED"
    assert missing_relative in result["error"]


@pytest.mark.parametrize("mutation", ("missing", "extra", "mode"))
def test_isolated_packed_runtime_sources_reject_missing_extra_and_mode_drift(
    tmp_path: Path,
    mutation: str,
) -> None:
    launcher = _load(PACKED_LAUNCHER, "packed_runtime_mutation_launcher")
    route = tmp_path / "route"
    _build_isolated_module_pack(route)
    typescript = (
        route
        / launcher.ENGINE_SOURCE_PREFIX
        / launcher.TYPESCRIPT_CAPTURED_ROOT_RELATIVE
        / "lib/typescript.js"
    )
    if mutation == "missing":
        typescript.unlink()
    elif mutation == "extra":
        extra = typescript.parent / "unbound-extra.d.ts"
        extra.write_text("declare const forged: true;\n", encoding="utf-8")
    else:
        typescript.chmod(0o644)
    completed = _run_pack(route)
    assert completed.returncode == 2
    result = json.loads(completed.stderr)
    assert result["status"] == "FAILED"


def test_isolated_packed_runtime_rejects_self_consistent_digest_rewrite(
    tmp_path: Path,
) -> None:
    launcher = _load(PACKED_LAUNCHER, "packed_runtime_rewrite_launcher")
    route = tmp_path / "route"
    _build_isolated_module_pack(route)
    manifest_relative = launcher.ENGINE_MANIFEST_RELATIVE
    manifest_path = route / manifest_relative
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    receipt = manifest["runtime_source_receipts"]["typescript_compiler_closure"]
    record = next(
        item for item in receipt["files"] if item["path"] == "lib/typescript.js"
    )
    repository_path = launcher.TYPESCRIPT_CAPTURED_ROOT_RELATIVE + "/lib/typescript.js"
    entry = next(
        item for item in manifest["files"] if item["repository_path"] == repository_path
    )
    captured_relative = entry["captured_path"]
    captured = route / captured_relative
    content = bytearray(captured.read_bytes())
    content[0] ^= 1
    captured.chmod(0o600)
    captured.write_bytes(bytes(content))
    captured.chmod(0o444)
    forged_digest = hashlib.sha256(content).hexdigest()
    record["sha256"] = forged_digest
    entry["sha256"] = "sha256:" + forged_digest
    source_records = [
        {key: item[key] for key in ("path", "bytes", "sha256")}
        for item in receipt["files"]
    ]
    runtime_records = [
        {key: item[key] for key in ("path", "bytes", "sha256", "mode")}
        for item in receipt["files"]
    ]
    receipt["source_manifest_sha256"] = hashlib.sha256(
        json.dumps(
            {"files": source_records}, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    receipt["runtime_manifest_sha256"] = hashlib.sha256(
        json.dumps(
            {"files": runtime_records}, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    _write_json(manifest_path, manifest)
    _refresh_formal_bindings(route, {captured_relative, manifest_relative})
    completed = _run_pack(route)
    assert completed.returncode == 2
    result = json.loads(completed.stderr)
    assert result["status"] == "FAILED"
    assert "receipt identity is invalid" in result["error"]


@pytest.mark.parametrize("mutation", ("missing", "tampered"))
def test_isolated_packed_runtime_rejects_standard_library_drift(
    tmp_path: Path,
    mutation: str,
) -> None:
    launcher = _load(PACKED_LAUNCHER, "packed_stdlib_mutation_launcher")
    route = tmp_path / "route"
    _build_isolated_module_pack(route)
    manifest = json.loads(
        (route / launcher.ENGINE_MANIFEST_RELATIVE).read_text(encoding="utf-8")
    )
    receipt = manifest["runtime_source_receipts"]["typescript_compiler_closure"]
    record = next(item for item in receipt["files"] if item["path"].endswith(".d.ts"))
    standard_library = (
        route
        / launcher.ENGINE_SOURCE_PREFIX
        / launcher.TYPESCRIPT_CAPTURED_ROOT_RELATIVE
        / record["path"]
    )
    if mutation == "missing":
        standard_library.unlink()
    else:
        content = bytearray(standard_library.read_bytes())
        content[-1] ^= 1
        standard_library.chmod(0o600)
        standard_library.write_bytes(bytes(content))
        standard_library.chmod(int(record["mode"], 8))
    completed = _run_pack(route)
    assert completed.returncode == 2
    assert json.loads(completed.stderr)["status"] == "FAILED"

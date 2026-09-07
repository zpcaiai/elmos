from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = ROOT / "scripts/batch29/run_polyglot_routes.py"
EXCLUDED_DIRECTORIES = frozenset(
    {".build", ".cache", ".gradle", "bin", "build", "obj", "target"}
)


def _load_runner() -> Any:
    spec = importlib.util.spec_from_file_location(
        "batch29_engine_source_capture_runner", RUNNER_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _tree_identity(root: Path) -> dict[str, tuple[str, int, int]]:
    return {
        path.relative_to(root).as_posix(): (
            _sha256(path),
            path.stat().st_size,
            path.stat().st_mode & 0o7777,
        )
        for path in root.rglob("*")
        if path.is_file()
    }


def _controlled_native_files(language: str) -> set[str]:
    native_root = ROOT / "engines/polyglot-route-engine/native" / language
    return {
        path.relative_to(ROOT).as_posix()
        for path in native_root.rglob("*")
        if path.is_file()
        and not path.is_symlink()
        and not any(
            part in EXCLUDED_DIRECTORIES for part in path.relative_to(native_root).parts
        )
    }


@pytest.fixture(scope="module")
def captured_engine_bundle(tmp_path_factory: pytest.TempPathFactory) -> Path:
    route = tmp_path_factory.mktemp("captured-engine-route") / "route"
    manifest_path, _captured = _load_runner()._capture_engine_sources(ROOT, route)
    assert manifest_path.is_file()
    return route


def test_capture_binds_repository_identifier_and_node_frontends_exactly(
    captured_engine_bundle: Path,
) -> None:
    runner = _load_runner()
    from elmos_polyglot_route import native
    from elmos_polyglot_route.toolchains import (
        python_source_archive_receipt,
        typescript_compiler_capture_receipt,
    )
    from fresh_route_runtime import (
        PYTHON_CAPTURED_ARCHIVE_RELATIVE,
        TYPESCRIPT_CAPTURED_ROOT_RELATIVE,
    )

    manifest_path = (
        captured_engine_bundle
        / "certification/formal-artifacts/engine-source-manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["file_count"] == len(manifest["files"])
    by_repository_path = {
        entry["repository_path"]: entry for entry in manifest["files"]
    }
    assert len(by_repository_path) == manifest["file_count"]

    required = {
        "engines/polyglot-route-engine/src/elmos_polyglot_route/repository.py",
        "engines/polyglot-route-engine/src/elmos_polyglot_route/identifier_hygiene.py",
        "schemas/batch29/formal-input.schema.json",
        "schemas/batch29/formal-input-module-function.schema.json",
        "schemas/batch29/identifier-plan.schema.json",
    }
    expected_csharp = {
        f"engines/dotnet-engine/{relative}"
        for relative in native._CSHARP_ANALYZER_INPUTS
    }
    assert set(runner.CSHARP_ANALYZER_CAPTURE_INPUTS) == expected_csharp
    required |= expected_csharp
    required |= _controlled_native_files("javascript")
    required |= _controlled_native_files("rust")
    required |= _controlled_native_files("typescript")
    assert required <= set(by_repository_path)
    assert {
        path
        for path in by_repository_path
        if path.startswith("engines/polyglot-route-engine/native/javascript/")
    } == _controlled_native_files("javascript")
    assert {
        path
        for path in by_repository_path
        if path.startswith("engines/polyglot-route-engine/native/rust/")
    } == _controlled_native_files("rust")
    assert {
        path
        for path in by_repository_path
        if path.startswith("engines/polyglot-route-engine/native/typescript/")
    } == _controlled_native_files("typescript")
    assert PYTHON_CAPTURED_ARCHIVE_RELATIVE in by_repository_path
    typescript_receipt = typescript_compiler_capture_receipt()
    expected_typescript_paths = {
        f"{TYPESCRIPT_CAPTURED_ROOT_RELATIVE}/{record['path']}"
        for record in typescript_receipt["files"]
    }
    assert expected_typescript_paths <= set(by_repository_path)
    receipts = manifest["runtime_source_receipts"]
    assert set(receipts) == {
        "python_source_archive",
        "typescript_compiler_closure",
    }
    assert (
        receipts["python_source_archive"]["capture_relative_path"]
        == PYTHON_CAPTURED_ARCHIVE_RELATIVE
    )
    assert {
        item["path"] for item in receipts["typescript_compiler_closure"]["files"]
    } == {record["path"] for record in typescript_receipt["files"]}
    assert (
        receipts["typescript_compiler_closure"]["capture_relative_path"]
        == TYPESCRIPT_CAPTURED_ROOT_RELATIVE
    )
    assert receipts["typescript_compiler_closure"]["file_count"] == 108
    assert receipts["typescript_compiler_closure"]["bytes"] == 19_067_381

    python_source = Path(str(python_source_archive_receipt()["source_path"]))
    typescript_sources = {
        f"{TYPESCRIPT_CAPTURED_ROOT_RELATIVE}/{record['path']}": Path(
            str(record["source_path"])
        )
        for record in typescript_receipt["files"]
    }
    for repository_path, entry in by_repository_path.items():
        captured = captured_engine_bundle / entry["captured_path"]
        assert captured.is_file() and not captured.is_symlink()
        assert entry["sha256"] == _sha256(captured)
        assert entry["bytes"] == captured.stat().st_size
        source = (
            python_source
            if repository_path == PYTHON_CAPTURED_ARCHIVE_RELATIVE
            else typescript_sources[repository_path]
            if repository_path in typescript_sources
            else ROOT / repository_path
        )
        assert captured.read_bytes() == source.read_bytes()
    assert runner.current_engine_source_binding(ROOT, captured_engine_bundle) == (
        True,
        "ENGINE_SOURCE_EVIDENCE_CURRENT",
    )


@pytest.mark.parametrize(
    ("field", "value"),
    (("schema_version", 2), ("kind", "self-consistent-forgery")),
)
def test_current_engine_binding_rejects_manifest_identity_rewrite(
    captured_engine_bundle: Path,
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    import shutil

    route = tmp_path / "route"
    shutil.copytree(captured_engine_bundle, route)
    manifest_path = (
        route / "certification/formal-artifacts/engine-source-manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest[field] = value
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    assert _load_runner().current_engine_source_binding(ROOT, route) == (
        False,
        "ENGINE_SOURCE_MANIFEST_INVALID",
    )


def _detached_import(bundle: Path) -> subprocess.CompletedProcess[str]:
    source_root = (
        bundle / "certification/formal-artifacts/engine-sources/engines/"
        "polyglot-route-engine/src"
    )
    script = "\n".join(
        (
            "import importlib, pathlib, sys",
            f"root = pathlib.Path({str(source_root)!r}).resolve(strict=True)",
            "sys.path.insert(0, str(root))",
            "names = ('elmos_polyglot_route.engine', "
            "'elmos_polyglot_route.native', 'elmos_polyglot_route.validation', "
            "'elmos_polyglot_route.repository')",
            "for name in names:",
            "    module = importlib.import_module(name)",
            "    pathlib.Path(module.__file__).resolve(strict=True).relative_to(root)",
            "print('CAPTURED_ENGINE_IMPORTS_PASSED')",
        )
    )
    environment = {
        key: value
        for key, value in os.environ.items()
        if key
        not in {
            "PYTHONHOME",
            "PYTHONINSPECT",
            "PYTHONPATH",
            "PYTHONSTARTUP",
            "PYTHONUSERBASE",
        }
    }
    environment["PYTHONNOUSERSITE"] = "1"
    return subprocess.run(
        [sys.executable, "-I", "-B", "-c", script],
        cwd=source_root,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_captured_engine_imports_without_live_checkout(
    captured_engine_bundle: Path,
) -> None:
    completed = _detached_import(captured_engine_bundle)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == "CAPTURED_ENGINE_IMPORTS_PASSED\n"


def test_captured_engine_fails_closed_without_repository_module(
    captured_engine_bundle: Path,
    tmp_path: Path,
) -> None:
    detached = tmp_path / "detached"
    import shutil

    shutil.copytree(captured_engine_bundle, detached)
    repository = (
        detached / "certification/formal-artifacts/engine-sources/engines/"
        "polyglot-route-engine/src/elmos_polyglot_route/repository.py"
    )
    repository.unlink()
    completed = _detached_import(detached)
    assert completed.returncode != 0
    assert "elmos_polyglot_route.repository" in completed.stderr


@pytest.mark.parametrize("runtime_source", ["python", "typescript"])
@pytest.mark.parametrize("mutation", ["missing", "tampered"])
def test_runtime_bootstrap_capture_fails_closed_per_source(
    captured_engine_bundle: Path,
    tmp_path: Path,
    runtime_source: str,
    mutation: str,
) -> None:
    import shutil

    from fresh_route_runtime import (
        PYTHON_CAPTURED_ARCHIVE_RELATIVE,
        TYPESCRIPT_CAPTURED_ROOT_RELATIVE,
    )

    detached = tmp_path / "detached"
    shutil.copytree(captured_engine_bundle, detached)
    relative = (
        PYTHON_CAPTURED_ARCHIVE_RELATIVE
        if runtime_source == "python"
        else f"{TYPESCRIPT_CAPTURED_ROOT_RELATIVE}/lib/typescript.js"
    )
    captured = detached / "certification/formal-artifacts/engine-sources" / relative
    if mutation == "missing":
        captured.unlink()
    else:
        captured.chmod(0o600)
        captured.write_bytes(captured.read_bytes() + b"tamper")
    current, reason = _load_runner().current_engine_source_binding(ROOT, detached)
    assert not current
    assert reason in {
        "ENGINE_SOURCE_ARTIFACT_INVALID",
        "ENGINE_SOURCE_EVIDENCE_STALE",
    }


@pytest.mark.parametrize(
    "repository_path",
    [
        "engines/polyglot-route-engine/native/rust/.cargo/config.toml",
        "engines/polyglot-route-engine/native/rust/vendor/syn-2.0.119/src/lib.rs",
        "engines/dotnet-engine/global.json",
        "engines/dotnet-engine/Directory.Build.props",
        "engines/dotnet-engine/Directory.Packages.props",
        (
            "engines/dotnet-engine/src/Elmos.Dotnet.SemanticCli/"
            "Elmos.Dotnet.SemanticCli.csproj"
        ),
        "engines/dotnet-engine/src/Elmos.Dotnet.SemanticCli/Program.cs",
        "engines/dotnet-engine/src/Elmos.Dotnet.SemanticCli/packages.lock.json",
    ],
)
@pytest.mark.parametrize("mutation", ["missing", "tampered"])
def test_compiler_input_capture_fails_closed_per_source(
    captured_engine_bundle: Path,
    tmp_path: Path,
    repository_path: str,
    mutation: str,
) -> None:
    import shutil

    detached = tmp_path / "detached"
    shutil.copytree(captured_engine_bundle, detached)
    captured = (
        detached
        / "certification/formal-artifacts/engine-sources"
        / repository_path
    )
    if mutation == "missing":
        captured.unlink()
    else:
        captured.chmod(0o600)
        captured.write_bytes(captured.read_bytes() + b"tamper")
    current, reason = _load_runner().current_engine_source_binding(ROOT, detached)
    assert not current
    assert reason in {
        "ENGINE_SOURCE_ARTIFACT_INVALID",
        "ENGINE_SOURCE_EVIDENCE_STALE",
    }


def test_capture_rejects_copy_window_replacement_and_preserves_previous_bundle(
    captured_engine_bundle: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import shutil

    from elmos_polyglot_route import toolchains

    route = tmp_path / "route"
    shutil.copytree(captured_engine_bundle, route)
    manifest = route / "certification/formal-artifacts/engine-source-manifest.json"
    capture_root = route / "certification/formal-artifacts/engine-sources"
    manifest_before = manifest.read_bytes()
    capture_before = _tree_identity(capture_root)

    receipt = dict(toolchains.python_source_archive_receipt())
    isolated_archive = tmp_path / "sealed-python.tar.gz"
    shutil.copy2(Path(str(receipt["source_path"])), isolated_archive)
    receipt["source_path"] = str(isolated_archive.resolve(strict=True))
    monkeypatch.setattr(
        toolchains,
        "python_source_archive_receipt",
        lambda: dict(receipt),
    )

    runner = _load_runner()
    original_copy2 = runner.shutil.copy2
    replaced = False

    def replace_before_copy(source: Path, destination: Path, *args: Any, **kwargs: Any):
        nonlocal replaced
        source_path = Path(source)
        if source_path == isolated_archive and not replaced:
            replaced = True
            source_path.chmod(0o600)
            source_path.write_bytes(source_path.read_bytes() + b"replaced")
        return original_copy2(source, destination, *args, **kwargs)

    monkeypatch.setattr(runner.shutil, "copy2", replace_before_copy)
    with pytest.raises(RuntimeError, match="FORMAL_ENGINE_SOURCE_(COPY|SEAL)_"):
        runner._capture_engine_sources(ROOT, route)
    assert replaced
    assert manifest.read_bytes() == manifest_before
    assert _tree_identity(capture_root) == capture_before


def test_detached_fresh_child_bootstraps_python_and_typescript_from_capture(
    captured_engine_bundle: Path,
    tmp_path: Path,
) -> None:
    import importlib.util
    import shutil

    detached = tmp_path / "detached"
    shutil.copytree(captured_engine_bundle, detached)
    captured_root = (
        detached / "certification/formal-artifacts/engine-sources"
    ).resolve(strict=True)
    fresh_path = captured_root / "scripts/batch29/fresh_route_runtime.py"
    specification = importlib.util.spec_from_file_location(
        "detached_fresh_route_runtime",
        fresh_path,
    )
    assert specification is not None and specification.loader is not None
    fresh = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(fresh)

    cache_anchor = tmp_path / "empty-cache-anchor"
    cache_anchor.mkdir(mode=0o700)
    cache = cache_anchor / "share/elmos/toolchains"
    python_cache = cache / "python-build-standalone"
    typescript_cache = cache / "typescript" / fresh.TYPESCRIPT_VERSION
    fresh.TOOLCHAIN_CACHE_ANCHOR = cache_anchor
    fresh.TOOLCHAIN_CACHE = cache
    fresh.PYTHON_CACHE = python_cache
    fresh.PYTHON_ARCHIVE_CACHE = (
        python_cache
        / "archives"
        / ("sha256-" + fresh.PYTHON_ARCHIVE_SHA256 + ".tar.gz")
    )
    fresh.PYTHON_RUNTIME_ROOT = (
        python_cache
        / "runtimes/3.12.12+20260211-aarch64-apple-darwin"
        / ("sha256-" + fresh.PYTHON_SOURCE_TREE_SHA256)
        / "python"
    )
    fresh.TYPESCRIPT_CACHE = typescript_cache
    fresh.TYPESCRIPT_RUNTIME_ROOT = (
        typescript_cache
        / ("sha256-" + fresh.TYPESCRIPT_SOURCE_MANIFEST_SHA256)
    )

    probe = captured_root / "scripts/batch29/detached_toolchain_probe.py"
    probe.write_text(
        "\n".join(
            (
                "from __future__ import annotations",
                "import sys",
                "from pathlib import Path",
                "",
                "def main() -> int:",
                "    repository = Path(__file__).resolve().parents[2]",
                "    engine = repository / 'engines/polyglot-route-engine/src'",
                "    sys.path.insert(0, str(engine))",
                "    from elmos_polyglot_route import toolchains",
                "    root = Path(sys.argv[1]).resolve(strict=True)",
                "    anchor = Path(sys.argv[2]).resolve(strict=True)",
                "    toolchains._EXPECTED_TYPESCRIPT_CACHE_ANCHOR = anchor",
                "    toolchains._EXPECTED_TYPESCRIPT_ROOT = root",
                "    toolchains._EXPECTED_TYPESCRIPT_LAUNCHER = root / 'bin/tsc'",
                "    toolchains._EXPECTED_TYPESCRIPT_TSC_SHIM = root / 'lib/tsc.js'",
                "    toolchains._EXPECTED_TYPESCRIPT_COMPILER = root / 'lib/_tsc.js'",
                    "    toolchains._EXPECTED_TYPESCRIPT_PARSER = root / 'lib/typescript.js'",
                    "    toolchains._EXPECTED_TYPESCRIPT_PACKAGE = root / 'package.json'",
                    "    toolchains._EXPECTED_TYPESCRIPT_LICENSE = root / 'LICENSE.txt'",
                    "    # The closure receipt intentionally binds its absolute cache root;",
                    "    # retain all fixed file and manifest identities while projecting",
                    "    # that one location-aware digest onto this private test cache.",
                    "    toolchains._EXPECTED_TYPESCRIPT_CLOSURE_SHA256 = str(",
                    "        toolchains._typescript_compiler_closure()['sha256']",
                    "    )",
                    "    receipt = toolchains.exact_toolchain('typescript')",
                "    if receipt.language != 'typescript':",
                "        raise RuntimeError('detached TypeScript selector mismatch')",
                "    print('DETACHED_TYPESCRIPT_EXACT_TOOLCHAIN_PASSED')",
                "    return 0",
                "",
            )
        ),
        encoding="utf-8",
    )
    assert not fresh.PYTHON_ARCHIVE_CACHE.exists()
    assert not fresh.PYTHON_RUNTIME_ROOT.exists()
    assert not fresh.TYPESCRIPT_RUNTIME_ROOT.exists()
    result = fresh.run_in_fresh_locked_runtime(
        probe,
        [str(fresh.TYPESCRIPT_RUNTIME_ROOT), str(cache_anchor)],
        captured_python_archive_root=captured_root,
        captured_python_archive_relative=fresh.PYTHON_CAPTURED_ARCHIVE_RELATIVE,
        captured_typescript_root=captured_root,
        captured_typescript_relative=fresh.TYPESCRIPT_CAPTURED_ROOT_RELATIVE,
    )
    assert result == 0
    assert fresh.PYTHON_ARCHIVE_CACHE.is_file()
    assert fresh.PYTHON_RUNTIME_ROOT.is_dir()
    assert fresh.TYPESCRIPT_RUNTIME_ROOT.is_dir()

from __future__ import annotations

import hashlib
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPOSITORY = Path(__file__).resolve().parents[2]
RUNTIME_PATH = REPOSITORY / "scripts" / "batch29" / "fresh_route_runtime.py"


def _runtime() -> Any:
    spec = importlib.util.spec_from_file_location(
        "focused_fresh_route_runtime", RUNTIME_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fake_uv(tmp_path: Path) -> Path:
    executable = tmp_path / "fixed" / "bin" / "uv"
    executable.parent.mkdir(parents=True)
    executable.write_text("#!/bin/sh\necho 'uv fixture 0.11.16'\n", encoding="utf-8")
    executable.chmod(0o555)
    return executable


def _patch_uv_identity(
    runtime: Any,
    monkeypatch: pytest.MonkeyPatch,
    executable: Path,
) -> None:
    metadata = executable.lstat()
    content = executable.read_bytes()
    monkeypatch.setattr(runtime, "PINNED_UV_PATH", executable)
    monkeypatch.setattr(
        runtime, "PINNED_UV_SHA256", "sha256:" + hashlib.sha256(content).hexdigest()
    )
    monkeypatch.setattr(runtime, "PINNED_UV_BYTES", len(content))
    monkeypatch.setattr(runtime, "PINNED_UV_VERSION", "uv fixture 0.11.16")
    monkeypatch.setattr(runtime, "PINNED_UV_MODE", 0o555)
    monkeypatch.setattr(runtime, "PINNED_UV_UID", metadata.st_uid)
    monkeypatch.setattr(runtime, "PINNED_UV_GID", metadata.st_gid)
    monkeypatch.setattr(runtime, "PINNED_UV_NLINK", 1)


def _isolate_python_cache(
    runtime: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    anchor = tmp_path / "private-home"
    anchor.mkdir(mode=0o700)
    toolchains = anchor / "share" / "elmos" / "toolchains"
    python_cache = toolchains / "python-build-standalone"
    archive = (
        python_cache
        / "archives"
        / ("sha256-" + runtime.PYTHON_ARCHIVE_SHA256 + ".tar.gz")
    )
    runtime_root = (
        python_cache
        / "runtimes"
        / "3.12.12+20260211-aarch64-apple-darwin"
        / ("sha256-" + runtime.PYTHON_SOURCE_TREE_SHA256)
        / "python"
    )
    monkeypatch.setattr(runtime, "TOOLCHAIN_CACHE_ANCHOR", anchor)
    monkeypatch.setattr(runtime, "TOOLCHAIN_CACHE", toolchains)
    monkeypatch.setattr(runtime, "PYTHON_CACHE", python_cache)
    monkeypatch.setattr(runtime, "PYTHON_ARCHIVE_CACHE", archive)
    monkeypatch.setattr(runtime, "PYTHON_RUNTIME_ROOT", runtime_root)


def _write_captured_python_archive(
    runtime: Any,
    root: Path,
    content: bytes,
) -> Path:
    root.mkdir(mode=0o700)
    archive = root / runtime.PYTHON_CAPTURED_ARCHIVE_RELATIVE
    archive.parent.mkdir(mode=0o700, parents=True)
    archive.write_bytes(content)
    archive.chmod(0o444)
    return archive


def _isolate_typescript_cache(
    runtime: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    anchor = tmp_path / "private-typescript-home"
    anchor.mkdir(mode=0o700)
    toolchains = anchor / "share" / "elmos" / "toolchains"
    cache = toolchains / "typescript" / runtime.TYPESCRIPT_VERSION
    runtime_root = cache / ("sha256-" + runtime.TYPESCRIPT_SOURCE_MANIFEST_SHA256)
    monkeypatch.setattr(runtime, "TOOLCHAIN_CACHE_ANCHOR", anchor)
    monkeypatch.setattr(runtime, "TOOLCHAIN_CACHE", toolchains)
    monkeypatch.setattr(runtime, "TYPESCRIPT_CACHE", cache)
    monkeypatch.setattr(runtime, "TYPESCRIPT_RUNTIME_ROOT", runtime_root)


def _write_captured_typescript_closure(
    runtime: Any,
    root: Path,
    source: Path,
) -> Path:
    captured = root / runtime.TYPESCRIPT_CAPTURED_ROOT_RELATIVE
    for relative in runtime.TYPESCRIPT_FILES:
        target = captured / relative
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        shutil.copyfile(source / relative, target)
        target.chmod(0o644)
    return captured


def test_pinned_uv_is_path_independent_in_a_scrubbed_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime()
    executable = _fake_uv(tmp_path)
    _patch_uv_identity(runtime, monkeypatch, executable)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    monkeypatch.setattr(
        runtime.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command, 0, stdout="uv fixture 0.11.16\n", stderr=""
        ),
    )

    assert runtime._pinned_uv() == executable


def test_pinned_uv_accepts_only_the_explicit_ci_bottle_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime()
    executable = _fake_uv(tmp_path)
    _patch_uv_identity(runtime, monkeypatch, executable)
    content = executable.read_bytes()
    monkeypatch.setattr(runtime, "PINNED_UV_SHA256", "sha256:" + "0" * 64)
    monkeypatch.setattr(runtime, "PINNED_UV_BYTES", len(content) + 1)
    monkeypatch.setattr(
        runtime,
        "PINNED_UV_CI_BOTTLE_SHA256",
        "sha256:" + hashlib.sha256(content).hexdigest(),
    )
    monkeypatch.setattr(runtime, "PINNED_UV_CI_BOTTLE_BYTES", len(content))
    monkeypatch.setattr(
        runtime.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command, 0, stdout="uv fixture 0.11.16\n", stderr=""
        ),
    )

    assert runtime._pinned_uv() == executable


def test_pinned_uv_rejects_retargeting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime()
    executable = _fake_uv(tmp_path)
    declared = executable.parent / "declared-uv"
    declared.symlink_to(executable.name)
    _patch_uv_identity(runtime, monkeypatch, executable)
    monkeypatch.setattr(runtime, "PINNED_UV_PATH", declared)

    with pytest.raises(RuntimeError, match="origin mismatch"):
        runtime._pinned_uv()


@pytest.mark.parametrize("drift", ["content", "mode"])
def test_pinned_uv_rejects_content_or_mode_drift(
    drift: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime()
    executable = _fake_uv(tmp_path)
    _patch_uv_identity(runtime, monkeypatch, executable)
    if drift == "content":
        monkeypatch.setattr(runtime, "PINNED_UV_SHA256", "sha256:" + "0" * 64)
    else:
        executable.chmod(0o775)

    with pytest.raises(RuntimeError, match="bytes/metadata/digest mismatch"):
        runtime._pinned_uv()


def test_python_archive_and_typescript_cache_are_exact_and_read_only() -> None:
    runtime = _runtime()

    python = runtime._prepare_python_runtime()
    typescript = runtime._prepare_typescript_runtime()

    assert python == runtime.PYTHON_RUNTIME_ROOT / "bin" / "python3.12"
    assert typescript == runtime.TYPESCRIPT_RUNTIME_ROOT / "bin" / "tsc"
    assert runtime._python_runtime_manifest(runtime.PYTHON_RUNTIME_ROOT)["sha256"] == (
        runtime.PYTHON_RUNTIME_TREE_SHA256
    )
    assert runtime._typescript_runtime_manifest(runtime.TYPESCRIPT_RUNTIME_ROOT) == {
        "sha256": runtime.TYPESCRIPT_RUNTIME_MANIFEST_SHA256,
        "file_count": runtime.TYPESCRIPT_FILE_COUNT,
        "bytes": runtime.TYPESCRIPT_CLOSURE_BYTES,
    }


def test_python_archive_rejects_same_size_content_drift() -> None:
    runtime = _runtime()
    archive = runtime.PYTHON_ARCHIVE_CACHE.read_bytes()
    forged = bytearray(archive)
    forged[len(forged) // 2] ^= 1

    with pytest.raises(
        RuntimeError, match="Python archive is invalid|inventory mismatch"
    ):
        runtime._verify_python_archive(bytes(forged))


def test_empty_cache_materializes_from_explicit_detached_archive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime()
    archive_content = runtime.PYTHON_ARCHIVE_CACHE.read_bytes()
    _isolate_python_cache(runtime, monkeypatch, tmp_path)
    captured_root = tmp_path / "detached-route"
    _write_captured_python_archive(runtime, captured_root, archive_content)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    monkeypatch.setenv(
        "ELMOS_BATCH29_PYTHON_ARCHIVE",
        "/private/tmp/ambient-python-archive-must-not-be-used.tar.gz",
    )

    python = runtime._prepare_python_runtime(
        captured_archive_root=captured_root,
        captured_archive_relative=runtime.PYTHON_CAPTURED_ARCHIVE_RELATIVE,
    )

    assert python == runtime.PYTHON_RUNTIME_ROOT / "bin" / "python3.12"
    assert runtime.PYTHON_ARCHIVE_CACHE.read_bytes() == archive_content
    assert runtime._python_runtime_manifest(runtime.PYTHON_RUNTIME_ROOT)["sha256"] == (
        runtime.PYTHON_RUNTIME_TREE_SHA256
    )


def test_empty_cache_rejects_missing_captured_archive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime()
    ambient_archive = runtime.PYTHON_ARCHIVE_CACHE
    _isolate_python_cache(runtime, monkeypatch, tmp_path)
    monkeypatch.setenv("ELMOS_BATCH29_PYTHON_ARCHIVE", str(ambient_archive))
    monkeypatch.setenv("TMPDIR", "/private/tmp/elmos-packed-runtime-poc-20260811")

    with pytest.raises(RuntimeError, match="required for first materialization"):
        runtime._prepare_python_runtime()


def test_empty_cache_rejects_tampered_captured_archive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime()
    archive_content = bytearray(runtime.PYTHON_ARCHIVE_CACHE.read_bytes())
    archive_content[len(archive_content) // 2] ^= 1
    _isolate_python_cache(runtime, monkeypatch, tmp_path)
    captured_root = tmp_path / "detached-route"
    _write_captured_python_archive(runtime, captured_root, bytes(archive_content))

    with pytest.raises(RuntimeError, match="fixed asset identity mismatch"):
        runtime._prepare_python_runtime(
            captured_archive_root=captured_root,
            captured_archive_relative=runtime.PYTHON_CAPTURED_ARCHIVE_RELATIVE,
        )
    assert not runtime.PYTHON_ARCHIVE_CACHE.exists()
    assert not runtime.PYTHON_RUNTIME_ROOT.exists()


@pytest.mark.parametrize(
    "relative",
    [
        "../" + "sha256-" + "0" * 64 + ".tar.gz",
        "runtime/python/cpython-3.12.12.tar.gz",
    ],
)
def test_captured_archive_rejects_non_content_addressed_paths(
    relative: str,
    tmp_path: Path,
) -> None:
    runtime = _runtime()
    root = tmp_path.resolve()

    with pytest.raises(RuntimeError, match="path is not content-addressed"):
        runtime._captured_python_archive_bytes(root, relative)


def test_empty_typescript_cache_materializes_from_explicit_detached_closure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime()
    fixed_source = runtime.TYPESCRIPT_RUNTIME_ROOT
    _isolate_typescript_cache(runtime, monkeypatch, tmp_path)
    captured_root = tmp_path / "detached-route"
    _write_captured_typescript_closure(runtime, captured_root, fixed_source)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    monkeypatch.setenv(
        "ELMOS_BATCH29_TYPESCRIPT_ROOT",
        "/private/tmp/ambient-typescript-must-not-be-used",
    )

    compiler = runtime._prepare_typescript_runtime(
        captured_root=captured_root,
        captured_relative=runtime.TYPESCRIPT_CAPTURED_ROOT_RELATIVE,
    )

    assert compiler == runtime.TYPESCRIPT_RUNTIME_ROOT / "bin" / "tsc"
    assert runtime._typescript_runtime_manifest(runtime.TYPESCRIPT_RUNTIME_ROOT) == {
        "sha256": runtime.TYPESCRIPT_RUNTIME_MANIFEST_SHA256,
        "file_count": runtime.TYPESCRIPT_FILE_COUNT,
        "bytes": runtime.TYPESCRIPT_CLOSURE_BYTES,
    }


def test_empty_typescript_cache_rejects_missing_explicit_closure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime()
    _isolate_typescript_cache(runtime, monkeypatch, tmp_path)
    monkeypatch.setenv(
        "ELMOS_BATCH29_TYPESCRIPT_ROOT",
        str(REPOSITORY / "engines/frontend-client-engine/node_modules/typescript"),
    )

    with pytest.raises(RuntimeError, match="required for first materialization"):
        runtime._prepare_typescript_runtime()


@pytest.mark.parametrize(
    ("library", "mutation"),
    [
        ("lib/lib.es2022.full.d.ts", "missing"),
        ("lib/lib.es5.d.ts", "tampered"),
    ],
)
def test_captured_typescript_closure_rejects_missing_or_tampered_stdlib(
    library: str,
    mutation: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime()
    fixed_source = runtime.TYPESCRIPT_RUNTIME_ROOT
    _isolate_typescript_cache(runtime, monkeypatch, tmp_path)
    captured_root = tmp_path / "detached-route"
    captured = _write_captured_typescript_closure(
        runtime, captured_root, fixed_source
    )
    selected = captured / library
    if mutation == "missing":
        selected.unlink()
    else:
        selected.write_bytes(selected.read_bytes() + b"tamper")

    with pytest.raises(
        RuntimeError,
        match="file inventory mismatch|source manifest mismatch",
    ):
        runtime._prepare_typescript_runtime(
            captured_root=captured_root,
            captured_relative=runtime.TYPESCRIPT_CAPTURED_ROOT_RELATIVE,
        )
    assert not runtime.TYPESCRIPT_RUNTIME_ROOT.exists()


def test_captured_typescript_closure_rejects_non_content_addressed_path(
    tmp_path: Path,
) -> None:
    runtime = _runtime()

    with pytest.raises(RuntimeError, match="path is not content-addressed"):
        runtime._captured_typescript_snapshot(
            tmp_path.resolve(),
            "runtime/typescript/5.9.2",
        )


def test_fresh_runtime_forwards_only_explicit_archive_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime()
    repository = tmp_path / "repository"
    script = repository / "scripts" / "batch29" / "entry.py"
    project = repository / "engines" / "polyglot-route-engine"
    script.parent.mkdir(parents=True)
    project.mkdir(parents=True)
    script.write_text("# fixture\n", encoding="utf-8")
    (project / "pyproject.toml").write_text("[project]\nname='fixture'\n", encoding="utf-8")
    (project / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    captured_root = tmp_path / "captured"
    captured_root.mkdir(mode=0o700)
    observed_python: dict[str, object] = {}
    observed_typescript: dict[str, object] = {}

    def prepare_python(**kwargs: object) -> Path:
        observed_python.update(kwargs)
        return Path("/fixed/python3.12")

    def prepare_typescript(**kwargs: object) -> Path:
        observed_typescript.update(kwargs)
        return Path("/fixed/tsc")

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        environment = kwargs["env"]
        assert isinstance(environment, dict)
        assert "ELMOS_BATCH29_PYTHON_ARCHIVE" not in environment
        assert environment["PATH"] == "/fixed/bin:/bin:/usr/bin"
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setenv("PATH", "/hostile/bin")
    monkeypatch.setenv("ELMOS_BATCH29_PYTHON_ARCHIVE", "/private/tmp/ambient")
    monkeypatch.setattr(runtime, "_pinned_uv", lambda: Path("/fixed/bin/uv"))
    monkeypatch.setattr(runtime, "_prepare_python_runtime", prepare_python)
    monkeypatch.setattr(runtime, "_prepare_typescript_runtime", prepare_typescript)
    monkeypatch.setattr(runtime.subprocess, "run", run)

    assert (
        runtime.run_in_fresh_locked_runtime(
            script,
            ["--fixture"],
            captured_python_archive_root=captured_root,
            captured_python_archive_relative=runtime.PYTHON_CAPTURED_ARCHIVE_RELATIVE,
            captured_typescript_root=captured_root,
            captured_typescript_relative=runtime.TYPESCRIPT_CAPTURED_ROOT_RELATIVE,
        )
        == 0
    )
    assert observed_python == {
        "captured_archive_root": captured_root,
        "captured_archive_relative": runtime.PYTHON_CAPTURED_ARCHIVE_RELATIVE,
    }
    assert observed_typescript == {
        "captured_root": captured_root,
        "captured_relative": runtime.TYPESCRIPT_CAPTURED_ROOT_RELATIVE,
    }


def test_fresh_child_selects_all_thirteen_active_language_ids_with_a_sanitized_path() -> None:
    runtime = _runtime()

    assert (
        runtime.run_in_fresh_locked_runtime(Path(__file__), ["--selector-smoke"]) == 0
    )


def main() -> int:
    if sys.argv[1:] != ["--selector-smoke"]:
        raise SystemExit("focused fresh-child fixture received unexpected arguments")
    from elmos_polyglot_route import toolchains
    from elmos_polyglot_route.models import DEPRECATED_LANGUAGES, ROUTED_LANGUAGES
    from elmos_polyglot_route.toolchains import ExactToolchain

    selectors = {
        "java": "_java",
        "python": "_python",
        "csharp": "_csharp",
        "typescript": "_typescript",
        "go": "_go",
        "rust": "_rust",
        "cpp": "_cpp",
        "objc": "_objc",
        "swift": "_swift",
        "php": "_php",
        "kotlin": "_kotlin",
        "react": "_react",
        "flutter": "_flutter",
    }
    assert tuple(selectors) == tuple(ROUTED_LANGUAGES)
    assert tuple(DEPRECATED_LANGUAGES) == ("javascript",)
    assert callable(toolchains._javascript)
    for language, selector in selectors.items():
        setattr(
            toolchains,
            selector,
            lambda language=language: ExactToolchain(
                language, "fixture", "/fixed/tool"
            ),
        )
    selected = [toolchains.exact_toolchain(language) for language in selectors]  # type: ignore[arg-type]
    assert [item.language for item in selected] == list(selectors)
    path = os.environ["PATH"].split(os.pathsep)
    assert "/opt/homebrew/Cellar/uv/0.11.16/bin" in path
    assert path[0].endswith("/.venv/bin")
    assert "/Users/stephen/.local/bin" not in path
    assert "/opt/homebrew/bin" not in path
    assert os.environ["UV_OFFLINE"] == "1"
    assert os.environ["UV_PYTHON_DOWNLOADS"] == "never"
    return 0

from __future__ import annotations

import hashlib
import importlib.util
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

REPOSITORY = Path(__file__).resolve().parents[2]
RUNTIME_PATH = REPOSITORY / "scripts" / "batch29" / "fresh_route_runtime.py"
CI_INSTALLER_PATH = (
    REPOSITORY / "scripts" / "toolchains" / "install_polyglot_route_ci_toolchains.sh"
)
FRESH_RUNTIME_SELECTOR_FIXTURE = (
    REPOSITORY / "tests" / "batch29" / "fresh_runtime_selector_fixture.py"
)


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
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setattr(
        runtime.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command, 0, stdout="uv fixture 0.11.16\n", stderr=""
        ),
    )

    for profile in ("full", "java-python"):
        monkeypatch.setenv("ELMOS_POLYGLOT_ROUTE_CI_PROFILE", profile)
        assert runtime._pinned_uv() == executable

    for profile in (None, "typed-sql", "frontend-formal", "ten-language"):
        if profile is None:
            monkeypatch.delenv("ELMOS_POLYGLOT_ROUTE_CI_PROFILE")
        else:
            monkeypatch.setenv("ELMOS_POLYGLOT_ROUTE_CI_PROFILE", profile)
        with pytest.raises(RuntimeError, match="bytes/metadata/digest mismatch"):
            runtime._pinned_uv()


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


def test_ci_installer_seals_the_captured_python_runtime_before_use() -> None:
    installer = CI_INSTALLER_PATH.read_text(encoding="utf-8")
    executable_files = (
        'find "${PYTHON_RUNTIME_TARGET}" -type f -perm -0100 '
        "-exec chmod 0555 {} +"
    )
    data_files = (
        'find "${PYTHON_RUNTIME_TARGET}" -type f ! -perm -0100 '
        "-exec chmod 0444 {} +"
    )
    directories = (
        'find "${PYTHON_RUNTIME_TARGET}" -type d -exec chmod 0555 {} +'
    )
    persisted_profile = (
        "printf 'ELMOS_POLYGLOT_ROUTE_CI_PROFILE=%s\\n' \"${CI_PROFILE}\""
    )
    python_probe = '"${PYTHON_RUNTIME_TARGET}/bin/python3.12" --version'

    assert executable_files in installer
    assert data_files in installer
    assert directories in installer
    assert persisted_profile in installer
    assert installer.index(executable_files) < installer.index(python_probe)
    assert installer.index(data_files) < installer.index(python_probe)
    assert installer.index(directories) < installer.index(python_probe)


def test_java_python_ci_profile_materializes_the_required_typescript_closure() -> None:
    installer = CI_INSTALLER_PATH.read_text(encoding="utf-8")
    profile_guard = (
        'if [[ "${CI_PROFILE}" == "full" || '
        '"${CI_PROFILE}" == "java-python" ]]; then'
    )
    capture_guard = 'if [[ ! -d "${TYPESCRIPT_CAPTURE}" || -L "${TYPESCRIPT_CAPTURE}" ]]'
    manifest_validation = (
        "fresh_route_runtime._typescript_runtime_manifest(target)"
    )
    full_only_toolchains = (
        'if [[ "${CI_PROFILE}" == "full" ]]; then\n'
        '  HOME="${PINNED_HOME}"'
    )

    assert profile_guard in installer
    assert installer.index(profile_guard) < installer.index(capture_guard)
    assert installer.index(capture_guard) < installer.index(manifest_validation)
    assert installer.index(manifest_validation) < installer.index(full_only_toolchains)


def test_java_python_ci_profile_uses_the_verified_setup_java_temurin_contract() -> None:
    installer = CI_INSTALLER_PATH.read_text(encoding="utf-8")
    temurin_guard = 'if [[ "${CI_PROFILE}" == "java-python" ]]; then\n  : "${JAVA_HOME:?JAVA_HOME must be provided by actions/setup-java}"'
    homebrew_install = 'install_pinned_formula \\\n    "openjdk@21" "21.0.11"'
    signature_verification = "/usr/bin/codesign --verify --deep --strict "
    environment_binding = "printf 'ELMOS_JAVA21_DISTRIBUTION=temurin\\n'"

    assert temurin_guard in installer
    assert installer.index(temurin_guard) < installer.index(homebrew_install)
    assert signature_verification in installer
    assert environment_binding in installer


def test_full_ci_profile_rebuilds_only_the_exact_homebrew_java_resource_seal() -> None:
    installer = CI_INSTALLER_PATH.read_text(encoding="utf-8")
    homebrew_install = 'install_pinned_formula \\\n    "openjdk@21" "21.0.11"'
    input_identity = (
        '"$(file_sha256 "${HOMEBREW_JAVA_HOME}/bin/java")" '
        '!= "${HOMEBREW_JAVA_SHA256}"'
    )
    preseal_identity = (
        'readonly HOMEBREW_JAVA_PRESEAL_IDENTITY="$(file_sha256 '
        '"${HOMEBREW_JAVA_EXECUTABLE}"):$(stat -f \'%Lp:%l:%z\' '
        '"${HOMEBREW_JAVA_EXECUTABLE}")"'
    )
    preseal_cases = (
        '"${HOMEBREW_JAVA_BOTTLE_EXECUTABLE_SHA256}:644:1:130384"|\\\n'
        '    "${HOMEBREW_JAVA_RUBY_MACHO_EXECUTABLE_SHA256}:644:1:112176"|\\\n'
        '    "${HOMEBREW_JAVA_EXECUTABLE_SHA256}:644:1:130192")'
    )
    signature_entry_enumeration = (
        'HOMEBREW_JAVA_UNEXPECTED_SIGNATURE_ENTRY="$(find \\\n'
        '      "${HOMEBREW_JAVA_BUNDLE}/Contents/_CodeSignature" \\\n'
        "      -mindepth 1 -maxdepth 1 ! -name 'CodeResources' -print -quit)\""
    )
    signature_entry_freeze = "readonly HOMEBREW_JAVA_UNEXPECTED_SIGNATURE_ENTRY"
    signature_entry_guard = (
        '[[ -n "${HOMEBREW_JAVA_UNEXPECTED_SIGNATURE_ENTRY}" ]]'
    )
    resource_preimage_guard = (
        '"$(stat -f \'%Lp:%l:%z\' "${HOMEBREW_JAVA_CODE_RESOURCES}")" '
        '!= "644:1:81759"'
    )
    exact_resign = (
        "/usr/bin/codesign --force --deep --sign - --pagesize 4096 "
        '"${HOMEBREW_JAVA_BUNDLE}"'
    )
    strict_verification = (
        "/usr/bin/codesign --verify --deep --strict "
        '"${HOMEBREW_JAVA_BUNDLE}"'
    )
    sealed_identity = (
        '"$(file_sha256 "${HOMEBREW_JAVA_CODE_RESOURCES}")" '
        '!= "${HOMEBREW_JAVA_CODE_RESOURCES_SHA256}"'
    )

    assert homebrew_install in installer
    assert input_identity in installer
    assert preseal_identity in installer
    assert preseal_cases in installer
    assert signature_entry_enumeration in installer
    assert signature_entry_freeze in installer
    assert signature_entry_guard in installer
    assert resource_preimage_guard in installer
    assert exact_resign in installer
    assert strict_verification in installer
    assert sealed_identity in installer
    assert "dbf6c7847b3bd0a476bd5e980ada9112a35c4ef00348209ad511031944d986fc" in installer
    assert "83bba6f42332fe76c090d99acd7b68947f687fade1827a0917d7e27df9b1258d" in installer
    assert "02f323e9d3f58bc04d228d475b745111af37871c3a1f7acdd23d656bde1452a3" in installer
    assert "56f1666041b6451258db96c168353f40ffeb3c98d0b7d8b7c4f2d29257563e4f" in installer
    assert "5a88122cc14733538f6b92d150fafb7f5b560455bfda0ae83c93a34eef2887e8" in installer
    assert installer.index(homebrew_install) < installer.index(input_identity)
    assert installer.index(input_identity) < installer.index(preseal_identity)
    assert installer.index(preseal_identity) < installer.index(exact_resign)
    assert installer.index(signature_entry_enumeration) < installer.index(
        signature_entry_freeze
    )
    assert installer.index(signature_entry_guard) < installer.index(exact_resign)
    assert installer.index(resource_preimage_guard) < installer.index(exact_resign)
    assert installer.index(sealed_identity) < installer.index(exact_resign)
    assert installer.index(exact_resign) < installer.index(strict_verification)
    assert installer.index(strict_verification) < installer.rindex(sealed_identity)


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
        assert environment["ELMOS_JAVA21_HOME"] == "/fixed/java/Contents/Home"
        assert environment["ELMOS_JAVA21_DISTRIBUTION"] == "temurin"
        assert "JAVA_HOME" not in environment
        assert "_JAVA_OPTIONS" not in environment
        assert command[command.index("run") + 1] == "--no-dev"
        assert "--no-default-groups" in command
        assert command.index("--no-dev") < command.index("--locked")
        assert command.index("--no-default-groups") < command.index("--locked")
        assert "mypy" not in command
        assert "pytest" not in command
        assert "ruff" not in command
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setenv("PATH", "/hostile/bin")
    monkeypatch.setenv("ELMOS_BATCH29_PYTHON_ARCHIVE", "/private/tmp/ambient")
    monkeypatch.setenv("ELMOS_JAVA21_HOME", "/fixed/java/Contents/Home")
    monkeypatch.setenv("ELMOS_JAVA21_DISTRIBUTION", "temurin")
    monkeypatch.setenv("JAVA_HOME", "/hostile/java")
    monkeypatch.setenv("_JAVA_OPTIONS", "-javaagent:/hostile/agent.jar")
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
        runtime.run_in_fresh_locked_runtime(
            FRESH_RUNTIME_SELECTOR_FIXTURE,
            ["--selector-smoke"],
        )
        == 0
    )

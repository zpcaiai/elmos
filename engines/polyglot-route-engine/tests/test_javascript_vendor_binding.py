"""Execution binding for the engine-owned TypeScript 5.9.2 parser."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from elmos_polyglot_route import native
from elmos_polyglot_route.models import RouteError
from elmos_polyglot_route.toolchains import ExactToolchain

ENGINE_ROOT = Path(__file__).resolve().parents[1]
VENDOR_ROOT = ENGINE_ROOT / "native" / "javascript" / "vendor" / "typescript-5.9.2"
FRONTEND_ROOT = ENGINE_ROOT.parent / "frontend-client-engine"
EXPECTED_ASSETS = {
    "asset-manifest.json",
    "LICENSE.txt",
    "package.json",
    "typescript.js",
}
NODE_SHA256 = "1" * 64
CLOSURE_SHA256 = "bd919085f8ae40bca10d5a2da36542eb90c5f18424dc60780c73c70b90d4244b"
CLOSURE_PROFILE = "homebrew-node26-libada-77917065434c-616512"


def _toolchain() -> ExactToolchain:
    return ExactToolchain(
        language="javascript",
        version="Node.js 26.0.0 / ES2022 / ESM",
        executable="/private/exact/node",
        profile=(
            "node-toolchain-closure-schema=v1",
            f"node-closure-sha256={CLOSURE_SHA256}",
            f"node-closure-profile={CLOSURE_PROFILE}",
            "platform=Darwin/arm64",
            "module=ESM",
        ),
        executable_sha256=NODE_SHA256,
    )


@pytest.fixture
def vendor_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "typescript-5.9.2"
    shutil.copytree(VENDOR_ROOT, root)
    monkeypatch.setattr(native, "_JAVASCRIPT_TYPESCRIPT_ROOT", root)
    return root


@pytest.fixture
def javascript_source(tmp_path: Path) -> Path:
    source = tmp_path / "identity.mjs"
    source.write_text(
        "/** @param {integer} value @returns {integer} */\nexport function identity(value) { return value; }\n",
        encoding="utf-8",
    )
    return source


def _bind_fake_toolchain(monkeypatch: pytest.MonkeyPatch) -> ExactToolchain:
    toolchain = _toolchain()
    monkeypatch.setattr(native, "exact_toolchain", lambda language: toolchain)
    return toolchain


def test_engine_owned_vendor_snapshot_is_complete_and_frontend_independent(
    vendor_root: Path,
    javascript_source: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    toolchain = _bind_fake_toolchain(monkeypatch)
    monkeypatch.setattr(native, "REPOSITORY_ROOT", tmp_path / "repository-without-frontend")
    observed_command: list[str] = []

    def fake_run(command: list[str], *, cwd: Path, timeout: int = 120) -> dict[str, Any]:
        del timeout
        observed_command.extend(command)
        assert cwd == Path(command[1]).parents[1]
        analyzer = Path(command[1])
        parser = Path(command[2])
        source = Path(command[3])
        snapshot_vendor = parser.parent
        assert analyzer == cwd / "assets" / "analyzer.mjs"
        assert parser == cwd / "assets" / "typescript-5.9.2" / "typescript.js"
        assert source == cwd / "source" / javascript_source.name
        assert {item.name for item in snapshot_vendor.iterdir()} == EXPECTED_ASSETS
        for directory in (cwd, cwd / "assets", snapshot_vendor, cwd / "source"):
            assert stat.S_IMODE(directory.lstat().st_mode) == 0o700
        for path in (analyzer, source, *(snapshot_vendor / name for name in EXPECTED_ASSETS)):
            metadata = path.lstat()
            assert stat.S_IMODE(metadata.st_mode) == 0o600
            assert metadata.st_nlink == 1
            assert metadata.st_uid == os.getuid()
            assert metadata.st_gid == os.getgid()
        assert all(str(vendor_root) not in argument for argument in command)
        assert all(str(FRONTEND_ROOT) not in argument for argument in command)
        return {"analyzer_version": "typescript-ast-test"}

    monkeypatch.setattr(native, "_run", fake_run)

    result = native._run_trusted_javascript_analyzer(toolchain, javascript_source, "identity")

    profile_bytes = json.dumps(list(toolchain.profile), ensure_ascii=True, separators=(",", ":")).encode("ascii")
    assert observed_command[0] == toolchain.executable
    assert f"typescript-assets={native._JAVASCRIPT_TYPESCRIPT_MANIFEST_SHA256}" in result["analyzer_version"]
    assert f"node-closure={CLOSURE_SHA256}" in result["analyzer_version"]
    assert f"node-profile={hashlib.sha256(profile_bytes).hexdigest()}" in result["analyzer_version"]


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda root, outside: (root / "typescript.js").unlink(), id="missing"),
        pytest.param(
            lambda root, outside: (root / "package.json").write_bytes((root / "package.json").read_bytes() + b" "),
            id="tampered",
        ),
        pytest.param(
            lambda root, outside: (
                (outside.write_bytes((root / "typescript.js").read_bytes())),
                (root / "typescript.js").unlink(),
                (root / "typescript.js").symlink_to(outside),
            ),
            id="symlink",
        ),
        pytest.param(lambda root, outside: (root / "unexpected.txt").write_text("unexpected"), id="extra"),
        pytest.param(lambda root, outside: (root / "LICENSE.txt").chmod(0o666), id="mode"),
        pytest.param(lambda root, outside: os.link(root / "LICENSE.txt", outside), id="hardlink"),
    ],
)
def test_live_vendor_rejects_path_content_and_metadata_drift(
    vendor_root: Path,
    tmp_path: Path,
    mutate: Callable[[Path, Path], object],
) -> None:
    mutate(vendor_root, tmp_path / "outside-asset")

    with pytest.raises(RouteError, match="^JAVASCRIPT_TYPESCRIPT_ASSET_UNSAFE$"):
        native._javascript_typescript_assets()


@pytest.mark.parametrize("process_raises", [False, True], ids=["success-path", "error-path"])
def test_live_mutation_is_promoted_to_input_changed_on_all_exit_paths(
    vendor_root: Path,
    javascript_source: Path,
    monkeypatch: pytest.MonkeyPatch,
    process_raises: bool,
) -> None:
    toolchain = _bind_fake_toolchain(monkeypatch)

    def mutate_live(command: list[str], *, cwd: Path, timeout: int = 120) -> dict[str, Any]:
        del command, cwd, timeout
        package = vendor_root / "package.json"
        package.write_bytes(package.read_bytes() + b" ")
        if process_raises:
            raise RouteError("SIMULATED_ANALYZER_FAILURE")
        return {"analyzer_version": "typescript-ast-test"}

    monkeypatch.setattr(native, "_run", mutate_live)

    with pytest.raises(RouteError, match="^JAVASCRIPT_ANALYZER_INPUT_CHANGED_DURING_EXECUTION$"):
        native._run_trusted_javascript_analyzer(toolchain, javascript_source, "identity")


@pytest.mark.parametrize("process_raises", [False, True], ids=["success-path", "error-path"])
def test_snapshot_mutation_is_promoted_to_snapshot_changed_on_all_exit_paths(
    vendor_root: Path,
    javascript_source: Path,
    monkeypatch: pytest.MonkeyPatch,
    process_raises: bool,
) -> None:
    del vendor_root
    toolchain = _bind_fake_toolchain(monkeypatch)

    def mutate_snapshot(command: list[str], *, cwd: Path, timeout: int = 120) -> dict[str, Any]:
        del cwd, timeout
        parser = Path(command[2])
        (parser.parent / "unexpected.txt").write_text("unexpected", encoding="utf-8")
        if process_raises:
            raise RouteError("SIMULATED_ANALYZER_FAILURE")
        return {"analyzer_version": "typescript-ast-test"}

    monkeypatch.setattr(native, "_run", mutate_snapshot)

    with pytest.raises(RouteError, match="^JAVASCRIPT_ANALYZER_SNAPSHOT_CHANGED_DURING_EXECUTION$"):
        native._run_trusted_javascript_analyzer(toolchain, javascript_source, "identity")


def test_manifest_and_package_declarations_are_parsed_strictly() -> None:
    _binding, contents = native._javascript_typescript_assets()
    manifest = json.loads(contents["asset-manifest.json"])
    manifest["files"] = list(reversed(manifest["files"]))
    reordered = {**contents, "asset-manifest.json": json.dumps(manifest).encode("utf-8")}
    with pytest.raises(RouteError, match="^JAVASCRIPT_TYPESCRIPT_ASSET_UNSAFE$"):
        native._validate_javascript_typescript_metadata(reordered)

    package = json.loads(contents["package.json"])
    package["license"] = "UNKNOWN"
    wrong_license = {**contents, "package.json": json.dumps(package).encode("utf-8")}
    with pytest.raises(RouteError, match="^JAVASCRIPT_TYPESCRIPT_ASSET_UNSAFE$"):
        native._validate_javascript_typescript_metadata(wrong_license)

    with pytest.raises(RouteError, match="^JAVASCRIPT_TYPESCRIPT_ASSET_UNSAFE$"):
        native._javascript_strict_json_object(
            b'{"name":"typescript","name":"other"}', "JAVASCRIPT_TYPESCRIPT_ASSET_UNSAFE"
        )


def test_toolchain_binding_rejects_ambiguous_node_closure_profiles() -> None:
    toolchain = _toolchain()
    ambiguous = ExactToolchain(
        language=toolchain.language,
        version=toolchain.version,
        executable=toolchain.executable,
        profile=(
            *toolchain.profile,
            f"node-toolchain-closure-sha256={'3' * 64}",
        ),
        executable_sha256=toolchain.executable_sha256,
    )

    with pytest.raises(RouteError, match="^JAVASCRIPT_ANALYZER_TOOLCHAIN_POLICY_INVALID$"):
        native._javascript_toolchain_binding(ambiguous)


@pytest.mark.parametrize("profile_value", [None, "mismatched-profile"])
def test_toolchain_binding_requires_matching_node_closure_profile(
    profile_value: str | None,
) -> None:
    toolchain = _toolchain()
    profile = tuple(
        item for item in toolchain.profile if not item.startswith("node-closure-profile=")
    )
    if profile_value is not None:
        profile = (*profile, f"node-closure-profile={profile_value}")
    candidate = ExactToolchain(
        language=toolchain.language,
        version=toolchain.version,
        executable=toolchain.executable,
        profile=profile,
        executable_sha256=toolchain.executable_sha256,
    )

    with pytest.raises(RouteError, match="^JAVASCRIPT_ANALYZER_TOOLCHAIN_POLICY_INVALID$"):
        native._javascript_toolchain_binding(candidate)

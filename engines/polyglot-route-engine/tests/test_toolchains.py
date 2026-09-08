from __future__ import annotations

import subprocess
import tempfile
import time
from pathlib import Path

import pytest

from elmos_polyglot_route import native, toolchains
from elmos_polyglot_route.models import RouteError


def test_apple_host_profiles_select_only_exact_complete_tuples() -> None:
    legacy = toolchains._select_apple_route_host_profile(
        image_version="20260728.0273.1",
        product_version="26.5.2",
        build_version="25F84",
        xcode="Xcode 26.6\nBuild version 17F113",
    )
    current = toolchains._select_apple_route_host_profile(
        image_version="20260831.0337.3",
        product_version="26.6.2",
        build_version="25G83",
        xcode="Xcode 26.6\nBuild version 17F113",
    )

    assert legacy.profile_id == "github-macos26-20260728.0273.1"
    assert current.profile_id == "github-macos26-20260831.0337.3"
    assert legacy.swiftc_sha256 == current.swiftc_sha256
    assert legacy.apple_git_sha256 == current.apple_git_sha256
    assert legacy.sandbox_exec_sha256 != current.sandbox_exec_sha256

    local = toolchains._select_apple_route_host_profile(
        image_version="",
        product_version="26.6.2",
        build_version="25G83",
        xcode="Xcode 26.6\nBuild version 17F113",
    )
    assert local.profile_id == "local-macos26-20260904"
    assert local.swiftc_sha256 != current.swiftc_sha256

    sanitized_child = toolchains._select_apple_route_host_profile(
        image_version="",
        product_version="26.5.2",
        build_version="25F84",
        xcode="Xcode 26.6\nBuild version 17F113",
    )
    assert sanitized_child is legacy


@pytest.mark.parametrize(
    ("image_version", "product_version", "build_version"),
    [
        ("20260728.0273.1", "26.6.2", "25G83"),
        ("20260831.0337.3", "26.5.2", "25F84"),
        ("20260905.0000.0", "26.6.2", "25G83"),
    ],
)
def test_apple_host_profiles_reject_hybrid_and_unknown_tuples(
    image_version: str,
    product_version: str,
    build_version: str,
) -> None:
    with pytest.raises(RouteError, match="EXACT_TOOLCHAIN_APPLE_HOST_PROFILE_MISMATCH"):
        toolchains._select_apple_route_host_profile(
            image_version=image_version,
            product_version=product_version,
            build_version=build_version,
            xcode="Xcode 26.6\nBuild version 17F113",
        )


def test_legacy_apple_profile_replaces_one_complete_closure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy = toolchains._APPLE_ROUTE_LEGACY_PROFILE
    monkeypatch.setattr(native, "_apple_native_profile", lambda: legacy)

    components = {
        str(spec[0]): (str(spec[4]), int(spec[5]))
        for spec in native._profiled_swift_build_component_specs()
    }
    trees = {
        str(spec[0]): (str(spec[3]), int(spec[4]), int(spec[5]))
        for spec in native._profiled_swift_build_tree_specs()
    }

    assert components["swift-dispatcher"] == (
        legacy.swiftc_sha256,
        357_109_680,
    )
    assert components["clang"] == (legacy.clang_sha256, 290_664_032)
    assert trees["toolchain-host-plugins"] == (
        "4fa83d7d2c0246c4fbe83cc8d71fe26b8beacc27f2a650fb0945d23de0eacbcc",
        4,
        3_222_976,
    )


def test_output_prefers_successful_stdout_over_diagnostic_stderr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        toolchains.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0],
            0,
            stdout="Xcode 26.6\nBuild version 17F113\n",
            stderr="DVTFilePathFSEvents: Failed to start fs event stream.\n",
        ),
    )

    assert (
        toolchains._output(["/usr/bin/env"], include_stderr=False)
        == "Xcode 26.6\nBuild version 17F113"
    )


def test_output_keeps_successful_stderr_only_version_surfaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        toolchains.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0],
            0,
            stdout="",
            stderr=toolchains._EXPECTED_JAVA_VERSION + "\n",
        ),
    )

    assert toolchains._output(["/usr/bin/env"]) == toolchains._EXPECTED_JAVA_VERSION


def test_output_keeps_split_success_identity_streams_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stdout = toolchains._EXPECTED_SWIFT_VERSION + "\n" + toolchains._EXPECTED_SWIFT_TARGET + "\n"
    stderr = toolchains._EXPECTED_SWIFT_DRIVER_VERSION + "\n"
    monkeypatch.setattr(
        toolchains.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0],
            0,
            stdout=stdout,
            stderr=stderr,
        ),
    )

    assert toolchains._output(["/usr/bin/env"]) == (stdout + stderr).strip()


def test_output_preserves_bounded_sanitized_failure_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        toolchains.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0],
            7,
            stdout="",
            stderr="bundle verification failed\nnested component invalid\n",
        ),
    )

    with pytest.raises(RouteError) as failure:
        toolchains._output(
            ["/usr/bin/codesign", "--verify"],
            include_failure_diagnostic=True,
        )

    assert str(failure.value) == (
        "EXACT_TOOLCHAIN_UNAVAILABLE:/usr/bin/codesign:exit=7:"
        "diagnostic=bundle verification failed?nested component invalid"
    )


def _mock_go_closure(monkeypatch: pytest.MonkeyPatch, observed: str) -> None:
    tree = {
        "root": str(toolchains._EXPECTED_GO_ROOT),
        "sha256": toolchains._EXPECTED_GO_TREE_SHA256,
        "record_count": toolchains._EXPECTED_GO_TREE_RECORD_COUNT,
        "file_count": toolchains._EXPECTED_GO_TREE_FILE_COUNT,
        "directory_count": toolchains._EXPECTED_GO_TREE_DIRECTORY_COUNT,
        "bytes": toolchains._EXPECTED_GO_TREE_BYTES,
    }
    executable = {
        "path": "bin/go",
        "kind": "file",
        "mode": "0755",
        "uid": 501,
        "gid": 20,
        "nlink": 1,
        "bytes": toolchains._EXPECTED_GO_EXECUTABLE_BYTES,
        "sha256": toolchains._EXPECTED_GO_EXECUTABLE_SHA256,
    }
    monkeypatch.setattr(toolchains.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(toolchains.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(toolchains, "_qualified_fixed_symlink", lambda *args, **kwargs: ("fixed",))
    monkeypatch.setattr(toolchains, "_go_tree_identity", lambda: tree)
    monkeypatch.setattr(toolchains, "_qualified_file_record", lambda *args, **kwargs: executable)
    monkeypatch.setattr(toolchains, "_output", lambda command: observed)


def test_go_accepts_only_the_fixed_darwin_arm64_distribution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_go_closure(monkeypatch, toolchains._EXPECTED_GO_VERSION)

    selected = toolchains._go()

    assert selected.version == "1.25.0"
    assert selected.executable == str(toolchains._EXPECTED_GO_EXECUTABLE)
    assert selected.executable_sha256 == toolchains._EXPECTED_GO_EXECUTABLE_SHA256


@pytest.mark.parametrize(
    "observed",
    [
        "go version go1.24.13 linux/amd64",
        "go version go1.25.0 linux/amd64",
        "go version go1.25.0 windows/amd64",
        "go1.25.0",
    ],
)
def test_go_rejects_version_platform_and_output_drift(monkeypatch: pytest.MonkeyPatch, observed: str) -> None:
    _mock_go_closure(monkeypatch, observed)

    with pytest.raises(RouteError, match="EXACT_TOOLCHAIN_MISMATCH:go"):
        toolchains._go()


@pytest.mark.skipif(
    not toolchains._EXPECTED_GO_EXECUTABLE.is_file(),
    reason="the exact pinned Go distribution is unavailable",
)
def test_repeated_go_probes_leave_no_toolchain_environment_roots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))

    assert toolchains._output([str(toolchains._EXPECTED_GO_EXECUTABLE), "env", "GOTELEMETRY"]) == "off"
    for _ in range(3):
        assert (
            toolchains._output([str(toolchains._EXPECTED_GO_EXECUTABLE), "version"])
            == toolchains._EXPECTED_GO_VERSION
        )

    deadline = time.monotonic() + 1.0
    observed_roots: set[Path] = set()
    while time.monotonic() < deadline:
        observed_roots.update(tmp_path.glob("elmos-toolchain-env-*"))
        if observed_roots:
            break
        time.sleep(0.02)
    assert observed_roots == set()

from __future__ import annotations

import tempfile
import time
from pathlib import Path

import pytest

from elmos_polyglot_route import toolchains
from elmos_polyglot_route.models import RouteError


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

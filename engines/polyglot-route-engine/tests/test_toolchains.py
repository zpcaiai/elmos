from __future__ import annotations

import pytest

from elmos_polyglot_route import toolchains
from elmos_polyglot_route.models import RouteError


@pytest.mark.parametrize(
    "observed",
    [
        "go version go1.25.0 darwin/arm64",
        "go version go1.25.0 linux/amd64",
    ],
)
def test_go_accepts_only_declared_exact_ci_platform_tuples(monkeypatch: pytest.MonkeyPatch, observed: str) -> None:
    monkeypatch.setattr(toolchains.shutil, "which", lambda name: "/usr/local/bin/go")
    monkeypatch.setattr(toolchains, "_output", lambda command: observed)

    selected = toolchains._go()

    assert selected.version == "1.25.0"
    assert selected.executable == "/usr/local/bin/go"


@pytest.mark.parametrize(
    "observed",
    [
        "go version go1.24.13 linux/amd64",
        "go version go1.25.0 windows/amd64",
        "go1.25.0",
    ],
)
def test_go_rejects_version_platform_and_output_drift(monkeypatch: pytest.MonkeyPatch, observed: str) -> None:
    monkeypatch.setattr(toolchains.shutil, "which", lambda name: "/usr/local/bin/go")
    monkeypatch.setattr(toolchains, "_output", lambda command: observed)

    with pytest.raises(RouteError, match="EXACT_TOOLCHAIN_MISMATCH:go"):
        toolchains._go()


def test_exact_toolchain_probes_once_per_environment_and_binary_fingerprint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    toolchains.clear_exact_toolchain_cache()
    calls = 0

    def selected() -> toolchains.ExactToolchain:
        nonlocal calls
        calls += 1
        return toolchains.ExactToolchain("typescript", "test", "/bin/node", "/bin/tsc")

    monkeypatch.setattr(toolchains, "_typescript", selected)
    first = toolchains.exact_toolchain("typescript")
    second = toolchains.exact_toolchain("typescript")

    assert first is second
    assert calls == 1
    monkeypatch.setenv("PATH", f"{toolchains.os.environ.get('PATH', '')}:/new-fingerprint")
    toolchains.exact_toolchain("typescript")
    assert calls == 2
    toolchains.clear_exact_toolchain_cache()
